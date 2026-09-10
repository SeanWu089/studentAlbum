"""Prepare only the local runtime needed for the double-click launcher."""
from pathlib import Path
import platform
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    executable_name = 'ngrok.exe' if platform.system() == 'Windows' else 'ngrok'
    if shutil.which('ngrok') or (ROOT / '.runtime' / executable_name).is_file():
        return 0
    if platform.system() not in ('Darwin', 'Windows'):
        print('请从 https://ngrok.com/download 安装 ngrok。')
        return 1
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True, mode=0o700)
    arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'amd64'
    system = 'windows' if platform.system() == 'Windows' else 'darwin'
    archive = runtime / 'ngrok-download.zip'
    print('首次启动：正在下载 ngrok 官方程序…', flush=True)
    try:
        with urllib.request.urlopen(f'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-{system}-{arch}.zip', timeout=30) as response:
            with archive.open('wb') as output:
                shutil.copyfileobj(response, output)
        with zipfile.ZipFile(archive) as bundle:
            executable = runtime / executable_name
            executable.write_bytes(bundle.read(executable_name))
            if platform.system() != 'Windows':
                executable.chmod(0o755)
        archive.unlink()
    except Exception:
        print('ngrok 下载失败。本机资料管理仍可使用；联网后再次启动即可重试。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
