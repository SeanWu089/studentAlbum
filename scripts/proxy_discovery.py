"""Discover usable outbound proxies on Windows without depending on proxy-app brands."""
import ctypes
from ctypes import wintypes
import os
import platform
from urllib.parse import urlsplit


SUPPORTED_SCHEMES = {'http', 'https', 'socks5'}


def normalize_proxy_url(value, default_scheme='http'):
    value = (value or '').strip().strip('"').strip("'")
    if not value or value.lower() in {'direct', 'direct://', '<local>'}:
        return ''
    if value.upper().startswith('PROXY '):
        value = value[6:].strip()
    if '://' not in value:
        value = f'{default_scheme}://{value}'
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in SUPPORTED_SCHEMES or not parsed.hostname or parsed.port is None:
            return ''
    except ValueError:
        return ''
    return value


def parse_proxy_server(value):
    """Parse WinINET/WinHTTP proxy strings into ngrok-compatible proxy URLs."""
    value = (value or '').strip()
    if not value:
        return []
    keyed = {}
    plain = []
    for part in value.split(';'):
        part = part.strip()
        if not part or part.upper() == 'DIRECT':
            continue
        if '=' in part and '://' not in part.split('=', 1)[0]:
            key, address = part.split('=', 1)
            keyed[key.strip().lower()] = address.strip()
        else:
            plain.append(part)
    candidates = []
    for key in ('https', 'http', 'socks', 'socks5'):
        if key in keyed:
            scheme = 'socks5' if key.startswith('socks') else 'http'
            candidates.append(normalize_proxy_url(keyed[key], scheme))
    candidates.extend(normalize_proxy_url(item) for item in plain)
    return [item for item in dict.fromkeys(candidates) if item]


def _pointer_text(pointer):
    return ctypes.wstring_at(pointer) if pointer else ''


def _global_free(pointer):
    if pointer:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL
        kernel32.GlobalFree(pointer)


def _windows_proxy_values():
    """Read manual, PAC/WPAD and WinHTTP proxy settings through Windows APIs."""
    if platform.system() != 'Windows':
        return []
    try:
        winhttp = ctypes.WinDLL('winhttp', use_last_error=True)
    except OSError:
        return []

    class IEConfig(ctypes.Structure):
        _fields_ = [
            ('auto_detect', wintypes.BOOL),
            ('auto_config_url', ctypes.c_void_p),
            ('proxy', ctypes.c_void_p),
            ('proxy_bypass', ctypes.c_void_p),
        ]

    class AutoProxyOptions(ctypes.Structure):
        _fields_ = [
            ('flags', wintypes.DWORD),
            ('auto_detect_flags', wintypes.DWORD),
            ('auto_config_url', wintypes.LPCWSTR),
            ('reserved', ctypes.c_void_p),
            ('reserved_dword', wintypes.DWORD),
            ('auto_logon', wintypes.BOOL),
        ]

    class ProxyInfo(ctypes.Structure):
        _fields_ = [
            ('access_type', wintypes.DWORD),
            ('proxy', ctypes.c_void_p),
            ('proxy_bypass', ctypes.c_void_p),
        ]

    winhttp.WinHttpGetIEProxyConfigForCurrentUser.argtypes = [ctypes.POINTER(IEConfig)]
    winhttp.WinHttpGetIEProxyConfigForCurrentUser.restype = wintypes.BOOL
    winhttp.WinHttpGetDefaultProxyConfiguration.argtypes = [ctypes.POINTER(ProxyInfo)]
    winhttp.WinHttpGetDefaultProxyConfiguration.restype = wintypes.BOOL
    winhttp.WinHttpOpen.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    winhttp.WinHttpOpen.restype = wintypes.HANDLE
    winhttp.WinHttpGetProxyForUrl.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.POINTER(AutoProxyOptions), ctypes.POINTER(ProxyInfo)]
    winhttp.WinHttpGetProxyForUrl.restype = wintypes.BOOL
    winhttp.WinHttpCloseHandle.argtypes = [wintypes.HANDLE]
    winhttp.WinHttpCloseHandle.restype = wintypes.BOOL

    found = []
    ie = IEConfig()
    auto_url = ''
    auto_detect = False
    if winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(ie)):
        try:
            for proxy in parse_proxy_server(_pointer_text(ie.proxy)):
                found.append(('windows:manual', proxy))
            auto_url = _pointer_text(ie.auto_config_url)
            auto_detect = bool(ie.auto_detect)
        finally:
            _global_free(ie.auto_config_url)
            _global_free(ie.proxy)
            _global_free(ie.proxy_bypass)

    default = ProxyInfo()
    if winhttp.WinHttpGetDefaultProxyConfiguration(ctypes.byref(default)):
        try:
            for proxy in parse_proxy_server(_pointer_text(default.proxy)):
                found.append(('windows:winhttp', proxy))
        finally:
            _global_free(default.proxy)
            _global_free(default.proxy_bypass)

    if auto_url or auto_detect:
        session = winhttp.WinHttpOpen('StudentAlbum/1.0', 1, None, None, 0)
        if session:
            result = ProxyInfo()
            options = AutoProxyOptions()
            if auto_url:
                options.flags |= 0x00000002  # WINHTTP_AUTOPROXY_CONFIG_URL
                options.auto_config_url = auto_url
            if auto_detect:
                options.flags |= 0x00000001  # WINHTTP_AUTOPROXY_AUTO_DETECT
                options.auto_detect_flags = 0x00000001 | 0x00000002  # DHCP | DNS_A
            options.auto_logon = True
            try:
                if winhttp.WinHttpGetProxyForUrl(session, 'https://connect.ngrok-agent.com/', ctypes.byref(options), ctypes.byref(result)):
                    try:
                        for proxy in parse_proxy_server(_pointer_text(result.proxy)):
                            found.append(('windows:auto', proxy))
                    finally:
                        _global_free(result.proxy)
                        _global_free(result.proxy_bypass)
            finally:
                winhttp.WinHttpCloseHandle(session)
    return found


def proxy_routes(last_success='', windows_values=None):
    """Return (source, proxy_url) routes. Empty proxy URL means direct/TUN routing."""
    routes = [('direct', '')]
    for key in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy', 'ALL_PROXY', 'all_proxy'):
        proxy = normalize_proxy_url(os.getenv(key, ''))
        if proxy:
            routes.append((f'env:{key}', proxy))
    if windows_values is None:
        windows_values = _windows_proxy_values()
    routes.extend((source, normalize_proxy_url(proxy)) for source, proxy in windows_values)

    deduped = []
    seen = set()
    for source, proxy in routes:
        key = proxy or '<direct>'
        if not proxy and source != 'direct':
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, proxy))

    if last_success:
        for index, route in enumerate(deduped):
            if route[0] == last_success:
                deduped.insert(0, deduped.pop(index))
                break
    return deduped
