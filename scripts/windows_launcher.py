#!/usr/bin/env python3
"""Start the bundled server invisibly on Windows and open the teacher page."""
from pathlib import Path
import ctypes
import socket
import subprocess
import sys
import time
import webbrowser


ROOT = Path(__file__).resolve().parent.parent
ADMIN_URL = 'http://127.0.0.1:8765/admin.html'


def server_ready():
    try:
        with socket.create_connection(('127.0.0.1', 8765), timeout=0.5):
            return True
    except OSError:
        return False


def alert(message):
    ctypes.windll.user32.MessageBoxW(0, message, '学生小档案', 0x10)


def main():
    if server_ready():
        webbrowser.open(ADMIN_URL)
        return 0

    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    pythonw = Path(sys.executable)
    server_script = ROOT / 'scripts' / 'serve.py'
    log_path = runtime / 'server.log'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
    try:
        log = log_path.open('a', encoding='utf-8')
        subprocess.Popen(
            [str(pythonw), str(server_script), '--local', '--lan', '--no-open'],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as error:
        alert(f'启动失败：{error}')
        return 1

    for _ in range(40):
        if server_ready():
            webbrowser.open(ADMIN_URL)
            return 0
        time.sleep(0.25)
    alert('启动超时，请查看应用目录中的 app\\.runtime\\server.log。')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
