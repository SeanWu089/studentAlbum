#!/usr/bin/env python3
"""Local demo launcher; only student assets are exposed through ngrok."""
import argparse
import functools
import getpass
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import threading
import time
import urllib.request
import webbrowser
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / '.runtime'
STATE = {'publicUrl': '', 'localUrl': '', 'message': '本地预览已开启，正在准备手机访问链接…'}
ALLOWED = {'/', '/index.html', '/styles.css', '/app.js', '/assets/welcome-illustration.png', '/assets/welcome-portrait.png'}

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, public=False, **kwargs):
        self.public = public
        super().__init__(*args, directory=str(ROOT / 'demo'), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if self.public and path not in ALLOWED:
            self.send_error(404)
            return
        if path == '/api/status':
            payload = json.dumps(STATE, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path not in ALLOWED | {'/admin.html', '/admin.css', '/admin.js'}:
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        if self.path.split('?')[0] not in (ALLOWED if self.public else ALLOWED | {'/admin.html', '/admin.css', '/admin.js'}):
            self.send_error(404)
            return
        super().do_HEAD()

    def log_message(self, *_):
        pass


def ngrok_binary():
    existing = shutil.which('ngrok')
    if existing:
        return existing
    local = RUNTIME / 'ngrok'
    if local.exists():
        return str(local)
    arch = 'arm64' if platform.machine() == 'arm64' else 'amd64'
    if platform.system() != 'Darwin':
        raise RuntimeError('请先从 https://ngrok.com/download 安装 ngrok。')
    print('首次启动：正在从 ngrok 官方下载程序…', flush=True)
    archive = RUNTIME / 'ngrok.zip'
    with urllib.request.urlopen(f'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-{arch}.zip', timeout=30) as response:
        with archive.open('wb') as output:
            shutil.copyfileobj(response, output)
    with zipfile.ZipFile(archive) as bundle:
        local.write_bytes(bundle.read('ngrok'))
    local.chmod(0o755)
    archive.unlink()
    return str(local)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', action='store_true', help='仅启动本地预览')
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    servers = []
    process = None
    log = None
    try:
        for port, public in [(8765, False), (8766, True)]:
            server = http.server.ThreadingHTTPServer(('0.0.0.0' if public else '127.0.0.1', port), functools.partial(Handler, public=public))
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        if platform.system() == 'Darwin':
            for interface in ('en0', 'en1'):
                result = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface], capture_output=True, text=True)
                address = result.stdout.strip()
                if result.returncode == 0 and address:
                    STATE['localUrl'] = f'http://{address}:8766/'
                    print('同一 Wi-Fi 手机访问：' + STATE['localUrl'], flush=True)
                    break
        print('老师管理页：http://127.0.0.1:8765/admin.html\n学生预览：http://127.0.0.1:8765/\n保持本窗口开启；按 Control+C 停止演示。', flush=True)
        if not args.no_open:
            webbrowser.open('http://127.0.0.1:8765/admin.html')
        if args.local:
            STATE['message'] = '局域网预览已开启，ngrok 未启动。'
        else:
            try:
                binary = ngrok_binary()
                # Prefer user's existing config without reading or printing its secrets.
                config = RUNTIME / 'ngrok.yml'
                config_args = ['--config', str(config)] if config.exists() else []
                log = (RUNTIME / 'ngrok.log').open('w')
                def launch():
                    return subprocess.Popen([binary, 'http', 'http://127.0.0.1:8766', '--log', 'stdout', '--log-format', 'json', *config_args], stdout=log, stderr=log)
                process = launch()
                attempted_token = False
                for _ in range(90):
                    time.sleep(1)
                    if process.poll() is not None:
                        log.flush()
                        failure = (RUNTIME / 'ngrok.log').read_text()
                        if not attempted_token and ('ERR_NGROK_4018' in failure or 'ERR_NGROK_105' in failure) and os.isatty(0):
                            STATE['message'] = '首次使用：请在启动窗口输入 ngrok 账号令牌。'
                            print('\n打开 https://dashboard.ngrok.com/get-started/your-authtoken 获取令牌。')
                            token = getpass.getpass('粘贴 Authtoken（输入不显示）：').strip()
                            if not token:
                                raise RuntimeError('尚未配置 ngrok 令牌；本地预览仍可使用。')
                            config.write_text('version: "2"\nauthtoken: ' + json.dumps(token) + '\n')
                            config.chmod(0o600)
                            config_args = ['--config', str(config)]
                            attempted_token = True
                            process = launch()
                            continue
                        raise RuntimeError('ngrok 启动失败，请检查账号令牌或网络。诊断记录位于 .runtime/ngrok.log。')
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=1) as response:
                            tunnels = json.load(response)['tunnels']
                        matching = [t['public_url'] for t in tunnels if t['public_url'].startswith('https://') and t.get('config', {}).get('addr', '').rstrip('/') == 'http://127.0.0.1:8766']
                        if matching:
                            STATE.update(publicUrl=matching[0], message='手机访问已开启')
                            print('\n手机访问链接：' + matching[0], flush=True)
                            break
                    except (OSError, ValueError, KeyError):
                        pass
                else:
                    raise RuntimeError('获取 ngrok 链接超时，请检查网络后重启。')
            except Exception as error:
                STATE.update(publicUrl='', message=str(error))
                if process and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                print(str(error), flush=True)
        while True:
            time.sleep(1)
            if process and process.poll() is not None and STATE['publicUrl']:
                STATE.update(publicUrl='', message='手机访问连接已断开，请重新启动演示。')
    except OSError as error:
        print(f'无法启动：{error}\n如果演示已经开启，请使用现有窗口，或关闭后重试。', flush=True)
        return 1
    except KeyboardInterrupt:
        print('\n演示已停止。', flush=True)
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if log:
            log.close()
        for server in servers:
            server.shutdown()
            server.server_close()
    return 0

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    signal.signal(signal.SIGHUP, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    raise SystemExit(main())
