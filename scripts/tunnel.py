"""Owned ngrok process with continuously refreshed public URL."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import threading
import time
import urllib.request


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

    def run(self):
        bundled_name = 'ngrok.exe' if platform.system() == 'Windows' else 'ngrok'
        executable = shutil.which('ngrok') or str(self.runtime / bundled_name)
        config = self.config_path()
        defaults = [Path.home() / 'Library/Application Support/ngrok/ngrok.yml', Path.home() / '.config/ngrok/ngrok.yml']
        if not config and not any(p.exists() for p in defaults) and not os.getenv('NGROK_AUTHTOKEN'):
            self.state.update(publicUrl='', tunnelStatus='not_configured', needsToken=True,
                              message='尚未配置公网连接。')
            return
        logpath = self.runtime / 'ngrok.log'
        try:
            with logpath.open('w') as log:
                self.process = subprocess.Popen(self.command(executable, config), stdout=log, stderr=log)
                deadline = time.monotonic() + 45
                api_port = None
                while not self.stop_event.wait(1):
                    if self.process.poll() is not None:
                        failure = logpath.read_text(errors='replace')[-15000:]
                        code = re.search(r'ERR_NGROK_\d+', failure)
                        missing = any(value in failure for value in ('ERR_NGROK_4018', 'ERR_NGROK_105'))
                        self.state.update(publicUrl='', tunnelStatus='error', needsToken=missing,
                            message=('公网连接凭证无效，请检查本机 ngrok 配置。' if missing else
                                     f'固定公网地址连接失败{("（" + code.group() + "）") if code else ""}，请检查网络后重试。'))
                        return
                    url = ''
                    try:
                        if api_port is None:
                            # Discover the API from this process's own startup log, never another agent.
                            with logpath.open() as startup:
                                for line in startup.read(32768).splitlines():
                                    try:
                                        entry = json.loads(line)
                                    except ValueError:
                                        continue
                                    if entry.get('msg') == 'starting web service':
                                        match = re.fullmatch(r'(?:127\.0\.0\.1|localhost|0\.0\.0\.0):([0-9]+)', entry.get('addr', ''))
                                        if match:
                                            api_port = int(match[1])
                        if api_port is None:
                            raise OSError('Agent API is not ready')
                        with urllib.request.urlopen(f'http://127.0.0.1:{api_port}/api/tunnels', timeout=2) as response:
                            tunnels = json.load(response)['tunnels']
                        for tunnel in tunnels:
                            if (tunnel['public_url'].startswith('https://') and
                                tunnel.get('config', {}).get('addr', '').rstrip('/') == f'http://127.0.0.1:{self.port}'):
                                url = tunnel['public_url']
                    except (OSError, ValueError, KeyError):
                        pass
                    if url:
                        url = url.rstrip('/')
                        if not self.configured_url:
                            self.remember_public_url(url)
                        elif url != self.configured_url:
                            self.state.update(publicUrl='', tunnelStatus='error',
                                              message='实际公网地址与固定地址不一致，请重新连接。')
                            return
                        if url != self.state.get('publicUrl'):
                            print('学生公网入口：' + url, flush=True)
                        self.state.update(publicUrl=url, tunnelStatus='online',
                                          needsToken=False,
                                          message='固定公网入口已连接，手机可使用移动数据访问。')
                        deadline = time.monotonic() + 45
                    else:
                        self.state.update(publicUrl='', tunnelStatus='connecting', message='正在连接固定公网地址…')
                        if time.monotonic() > deadline:
                            self.state.update(tunnelStatus='error', message='公网连接超时，请检查网络后点击重新连接。')
                            return
        except OSError:
            self.state.update(publicUrl='', tunnelStatus='error', message='无法运行 ngrok，请确认已安装并重试。')
        finally:
            self.terminate()

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
