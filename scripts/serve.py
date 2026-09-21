#!/usr/bin/env python3
"""Launch the local student album, its database and optional ngrok tunnel."""
import argparse
from pathlib import Path
import signal
import socket
import threading
import time
import webbrowser

from storage import Store
from tunnel import Tunnel
from webserver import Application

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--local', action='store_true', help='仅本机运行，不启动 ngrok')
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--admin-port', type=int, default=8765)
    parser.add_argument('--student-port', type=int, default=8766)
    parser.add_argument('--lan', action='store_true', help='让同一 Wi-Fi 内的学生手机访问填写页')
    args = parser.parse_args()
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True, mode=0o700)
    state = {'publicUrl': '', 'lanUrl': '', 'tunnelStatus': 'off', 'message': '公网入口未开启，请点击连接 ngrok。'}
    store = Store(args.data_dir)
    tunnel = Tunnel(runtime, state, args.student_port)
    app = Application(ROOT, store, state, tunnel)
    servers = []
    try:
        for port, public in [(args.admin_port, False), (args.student_port, True)]:
            server = app.server(port, public, '0.0.0.0' if public and args.lan else '127.0.0.1')
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        if args.lan:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                    probe.connect(('1.1.1.1', 80))
                    address = probe.getsockname()[0]
                state.update(lanUrl=f'http://{address}:{args.student_port}/',
                             message='同一 Wi-Fi 填写入口已开启。老师管理页仍只限本机。')
            except OSError:
                state.update(message='学生填写服务已开启；电脑连接 Wi-Fi 后会显示局域网入口。')
        url = f'http://127.0.0.1:{args.admin_port}/admin.html'
        print(f'老师管理页：{url}\n' +
              (f'同一 Wi-Fi 填写入口：{state["lanUrl"]}\n' if args.lan else '') +
              f'资料保存在：{store.path}\n保持电脑联网、唤醒；按 Control+C 停止服务。', flush=True)
        if not args.no_open:
            webbrowser.open(url)
        if not args.local and not args.lan:
            tunnel.start()
        while True:
            time.sleep(1)
    except OSError as error:
        print(f'无法启动：{error}。请先关闭已运行的学生档案窗口。', flush=True)
        return 1
    except KeyboardInterrupt:
        print('\n服务已停止，学生资料已保留。', flush=True)
    finally:
        tunnel.stop()
        for server in servers:
            server.shutdown()
            server.server_close()
        store.close()
    return 0


if __name__ == '__main__':
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, stop)
    raise SystemExit(main())
