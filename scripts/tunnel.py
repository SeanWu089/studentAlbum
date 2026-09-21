"""Owned ngrok process with continuously refreshed public URL."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request

from proxy_discovery import proxy_routes


def is_network_failure(text):
    return any(marker in text for marker in (
        'heartbeat timeout',
        'failed to reconnect session',
        'proxyconnect tcp',
        'connection refused',
    ))


class Tunnel:
    def __init__(self, runtime, state, port, configured_url=''):
        self.runtime, self.state, self.port = runtime, state, port
        self.configured_url = configured_url.rstrip('/') or self.saved_public_url()
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.state['configuredPublicUrl'] = self.configured_url

    def user_directory(self):
        if platform.system() == 'Windows' and os.getenv('LOCALAPPDATA'):
            return Path(os.environ['LOCALAPPDATA']) / 'StudentAlbum'
        return self.runtime

    def saved_public_url(self):
        path = self.user_directory() / 'public-url.txt'
        if not path.exists():
            return ''
        value = path.read_text(encoding='utf-8', errors='replace').strip().rstrip('/')
        return value if value.startswith('https://') and len(value) <= 300 else ''

    def remember_public_url(self, url):
        url = url.rstrip('/')
        directory = self.user_directory()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'public-url.txt').write_text(url + '\n', encoding='utf-8')
        self.configured_url = url
        self.state['configuredPublicUrl'] = url

    def saved_route(self):
        path = self.user_directory() / 'proxy-route.txt'
        if not path.exists():
            return ''
        value = path.read_text(encoding='utf-8', errors='replace').strip()
        return value if re.fullmatch(r'[A-Za-z0-9:_-]{1,80}', value) else ''

    def remember_route(self, source):
        if not re.fullmatch(r'[A-Za-z0-9:_-]{1,80}', source or ''):
            return
        directory = self.user_directory()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'proxy-route.txt').write_text(source + '\n', encoding='utf-8')

    def save_token(self, token):
        directory = self.user_directory()
        directory.mkdir(parents=True, exist_ok=True)
        config = directory / 'ngrok.yml'
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write('version: "2"\nauthtoken: ' + json.dumps(token) + '\n')
        saved_url = directory / 'public-url.txt'
        saved_url.unlink(missing_ok=True)
        self.configured_url = ''
        self.state['configuredPublicUrl'] = ''
        return config

    def config_path(self):
        """Use a per-user config on Windows and migrate the old app-local config once."""
        legacy = self.runtime / 'ngrok.yml'
        if platform.system() != 'Windows':
            return legacy if legacy.exists() else None
        base = os.getenv('LOCALAPPDATA')
        if not base:
            return legacy if legacy.exists() else None
        directory = self.user_directory()
        config = directory / 'ngrok.yml'
        if not config.exists() and legacy.exists():
            directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, config)
        return config if config.exists() else None

    def proxy_config(self, base_config, proxy_url):
        """Create a short-lived ngrok config with the same auth plus an outbound proxy."""
        content = ''
        if base_config and Path(base_config).exists():
            content = Path(base_config).read_text(encoding='utf-8', errors='strict')
        if not content.strip():
            content = 'version: "2"\n'
        content = re.sub(r'(?m)^proxy_url\s*:.*(?:\n|$)', '', content)
        if not content.endswith('\n'):
            content += '\n'
        content += 'proxy_url: ' + json.dumps(proxy_url) + '\n'
        handle, name = tempfile.mkstemp(prefix='ngrok-proxy-', suffix='.yml', dir=self.runtime)
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as output:
                output.write(content)
        except Exception:
            Path(name).unlink(missing_ok=True)
            raise
        return Path(name)

    def start(self, token=''):
        with self.lock:
            self.stop()
            if token:
                self.save_token(token)
            self.stop_event.clear()
            self.state.update(publicUrl='', configuredPublicUrl=self.configured_url,
                              tunnelStatus='connecting', needsToken=False,
                              message='正在连接公网固定地址…')
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def command(self, executable, config=None):
        arguments = ['--config', str(config)] if config else []
        url_argument = ['--url', self.configured_url] if self.configured_url else []
        return [executable, 'http', f'http://127.0.0.1:{self.port}', *url_argument,
                '--inspect=false', '--log', 'stdout', '--log-format', 'json', *arguments]

    def _attempt_text(self, logpath, offset):
        try:
            with logpath.open('r', encoding='utf-8', errors='replace') as source:
                source.seek(offset)
                return source.read()[-20000:]
        except OSError:
            return ''

    def _discover_tunnel(self, logpath, offset, api_port):
        text = self._attempt_text(logpath, offset)
        if api_port is None:
            for line in text.splitlines():
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get('msg') == 'starting web service':
                    match = re.fullmatch(r'(?:127\.0\.0\.1|localhost|0\.0\.0\.0):([0-9]+)', entry.get('addr', ''))
                    if match:
                        api_port = int(match[1])
        if api_port is None:
            return '', None
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{api_port}/api/tunnels', timeout=2) as response:
                tunnels = json.load(response)['tunnels']
            for tunnel in tunnels:
                if (tunnel['public_url'].startswith('https://') and
                    tunnel.get('config', {}).get('addr', '').rstrip('/') == f'http://127.0.0.1:{self.port}'):
                    return tunnel['public_url'].rstrip('/'), api_port
        except (OSError, ValueError, KeyError):
            pass
        return '', api_port

    def _run_route(self, executable, config, source, proxy_url, logpath, timeout):
        generated = None
        route_config = config
        try:
            if proxy_url:
                generated = self.proxy_config(config, proxy_url)
                route_config = generated
            with logpath.open('a', encoding='utf-8') as log:
                log.write(json.dumps({'lvl':'info', 'msg':'StudentAlbum network route attempt', 'route':source}, ensure_ascii=False) + '\n')
                log.flush()
                offset = log.tell()
                self.process = subprocess.Popen(self.command(executable, route_config), stdout=log, stderr=log)
                deadline = time.monotonic() + timeout
                api_port = None
                connected = False
                missing_since = None
                while not self.stop_event.wait(1):
                    failure = self._attempt_text(logpath, offset)
                    if is_network_failure(failure):
                        return 'network', ''
                    if self.process.poll() is not None:
                        code = re.search(r'ERR_NGROK_\d+', failure)
                        if any(value in failure for value in ('ERR_NGROK_4018', 'ERR_NGROK_105')):
                            return 'auth', code.group() if code else ''
                        return 'error', code.group() if code else ''

                    url, api_port = self._discover_tunnel(logpath, offset, api_port)
                    if url:
                        missing_since = None
                        if not self.configured_url:
                            self.remember_public_url(url)
                        elif url != self.configured_url:
                            return 'address', ''
                        if not connected:
                            self.remember_route(source)
                            print('学生公网入口：' + url, flush=True)
                        connected = True
                        self.state.update(publicUrl=url, tunnelStatus='online', needsToken=False,
                                          message='固定公网入口已连接，已自动适配当前网络。')
                    else:
                        if connected:
                            missing_since = missing_since or time.monotonic()
                            if time.monotonic() - missing_since > 20:
                                return 'network', ''
                        elif time.monotonic() > deadline:
                            return 'network', ''
            return 'stopped', ''
        except (OSError, UnicodeError):
            return 'error', ''
        finally:
            self.terminate()
            if generated:
                generated.unlink(missing_ok=True)

    def run(self):
        bundled_name = 'ngrok.exe' if platform.system() == 'Windows' else 'ngrok'
        executable = shutil.which('ngrok') or str(self.runtime / bundled_name)
        config = self.config_path()
        defaults = [Path.home() / 'Library/Application Support/ngrok/ngrok.yml', Path.home() / '.config/ngrok/ngrok.yml']
        if not config and not any(p.exists() for p in defaults) and not os.getenv('NGROK_AUTHTOKEN'):
            self.state.update(publicUrl='', tunnelStatus='not_configured', needsToken=True,
                              message='尚未配置公网连接。')
            return

        routes = proxy_routes(self.saved_route()) if platform.system() == 'Windows' else [('direct', '')]
        logpath = self.runtime / 'ngrok.log'
        try:
            logpath.write_text('', encoding='utf-8')
        except OSError:
            self.state.update(publicUrl='', tunnelStatus='error', message='无法创建公网连接日志。')
            return

        for index, (source, proxy_url) in enumerate(routes):
            if self.stop_event.is_set():
                return
            self.state.update(publicUrl='', tunnelStatus='connecting', needsToken=False,
                              message='正在自动适配当前网络并连接公网…')
            # Failed routes should give way quickly; the final route gets a longer grace period.
            timeout = 35 if index == len(routes) - 1 else 14
            outcome, code = self._run_route(executable, config, source, proxy_url, logpath, timeout)
            if outcome == 'stopped':
                return
            if outcome == 'auth':
                self.state.update(publicUrl='', tunnelStatus='error', needsToken=True,
                                  message='公网连接凭证无效，请重新输入 ngrok Authtoken。')
                return
            if outcome == 'address':
                self.state.update(publicUrl='', tunnelStatus='error', needsToken=False,
                                  message='实际公网地址与固定地址不一致，请重新连接。')
                return
            if outcome == 'error' and code:
                self.state.update(publicUrl='', tunnelStatus='connecting', needsToken=False,
                                  message=f'当前网络方式连接失败（{code}），正在尝试其他方式…')

        self.state.update(publicUrl='', tunnelStatus='error', needsToken=False,
                          message='公网连接失败。请确认代理或 VPN 已连接，然后点击重新连接。')

    def terminate(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=7)
        self.terminate()
        self.state.update(publicUrl='')
