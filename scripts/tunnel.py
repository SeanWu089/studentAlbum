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
    def __init__(self, runtime, state, port):
        self.runtime, self.state, self.port = runtime, state, port
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

    def start(self, token=''):
        with self.lock:
            self.stop()
            config = self.runtime / 'ngrok.yml'
            if token:
                fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as output:
                    output.write('version: "2"\nauthtoken: ' + json.dumps(token) + '\nweb_addr: 127.0.0.1:4045\n')
            self.stop_event.clear()
            self.state.update(publicUrl='', tunnelStatus='connecting', message='正在连接 ngrok…')
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def run(self):
        bundled_name = 'ngrok.exe' if platform.system() == 'Windows' else 'ngrok'
        executable = shutil.which('ngrok') or str(self.runtime / bundled_name)
        config = self.runtime / 'ngrok.yml'
        defaults = [Path.home() / 'Library/Application Support/ngrok/ngrok.yml', Path.home() / '.config/ngrok/ngrok.yml']
        if not config.exists() and not any(p.exists() for p in defaults) and not os.getenv('NGROK_AUTHTOKEN'):
            self.state.update(tunnelStatus='token_required', message='首次使用，请在下方粘贴 ngrok Authtoken 后连接。')
            return
        arguments = ['--config', str(config)] if config.exists() else []
        logpath = self.runtime / 'ngrok.log'
        try:
            with logpath.open('w') as log:
                self.process = subprocess.Popen([executable, 'http', f'http://127.0.0.1:{self.port}',
                    '--inspect=false', '--log', 'stdout', '--log-format', 'json', *arguments], stdout=log, stderr=log)
                deadline = time.monotonic() + 45
                api_port = None
                while not self.stop_event.wait(1):
                    if self.process.poll() is not None:
                        failure = logpath.read_text(errors='replace')[-15000:]
                        code = re.search(r'ERR_NGROK_\d+', failure)
                        missing = any(value in failure for value in ('ERR_NGROK_4018', 'ERR_NGROK_105'))
                        self.state.update(publicUrl='', tunnelStatus='token_required' if missing else 'error',
                            message=('ngrok 账号令牌无效，请重新填写。' if missing else
                                     f'ngrok 连接失败{("（" + code.group() + "）") if code else ""}，请检查账号和网络后重试。'))
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
                        if url != self.state.get('publicUrl'):
                            print('学生公网入口：' + url, flush=True)
                        self.state.update(publicUrl=url, tunnelStatus='online', message='公网填写入口已开启，手机可使用移动数据访问。')
                        deadline = time.monotonic() + 45
                    else:
                        self.state.update(publicUrl='', tunnelStatus='connecting', message='正在连接 ngrok…')
                        if time.monotonic() > deadline:
                            self.state.update(tunnelStatus='error', message='连接 ngrok 超时，请检查网络、代理设置后点击重新连接。')
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
