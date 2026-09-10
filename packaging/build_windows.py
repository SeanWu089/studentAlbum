#!/usr/bin/env python3
"""Build a self-contained Windows x64 folder and zip without user data."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / '.build' / 'windows'
DIST = ROOT / 'dist'
VERSION = 'v0.2'
PYTHON_VERSION = '3.13.7'
PILLOW_VERSION = '12.3.0'
PYTHON_URL = f'https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip'
NGROK_URL = 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip'
PACKAGE_NAME = f'StudentAlbum-Windows-x64-{VERSION}'


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    print(f'下载 {path.name}…', flush=True)
    with urllib.request.urlopen(url, timeout=90) as response, path.open('wb') as output:
        shutil.copyfileobj(response, output)


def copy_app(target):
    app = target / 'app'
    shutil.copytree(ROOT / 'demo', app / 'demo')
    (app / 'scripts').mkdir(parents=True)
    for name in ('serve.py', 'storage.py', 'tunnel.py', 'webserver.py', 'windows_launcher.py'):
        shutil.copy2(ROOT / 'scripts' / name, app / 'scripts' / name)


def install_pillow(runtime, downloads):
    wheel_dir = downloads / 'pillow'
    wheel_dir.mkdir(parents=True, exist_ok=True)
    wheels = list(wheel_dir.glob('*.whl'))
    if not wheels:
        subprocess.run([
            sys.executable, '-m', 'pip', 'download', '--no-deps', '--only-binary=:all:',
            '--platform', 'win_amd64', '--implementation', 'cp', '--python-version', '313',
            '--abi', 'cp313', f'Pillow=={PILLOW_VERSION}', '--dest', str(wheel_dir),
        ], check=True)
        wheels = list(wheel_dir.glob('*.whl'))
    if len(wheels) != 1:
        raise RuntimeError('Pillow Windows wheel 数量不正确')
    site_packages = runtime / 'Lib' / 'site-packages'
    site_packages.mkdir(parents=True)
    with zipfile.ZipFile(wheels[0]) as bundle:
        bundle.extractall(site_packages)


def verify_package(target):
    forbidden = list(target.rglob('album.sqlite3')) + list(target.rglob('ngrok.yml'))
    if forbidden:
        raise RuntimeError('安装包中发现了不应包含的数据或凭证')
    required = [
        target / 'runtime' / 'pythonw.exe',
        target / 'app' / '.runtime' / 'ngrok.exe',
        target / 'app' / 'scripts' / 'serve.py',
        target / 'assets' / 'student-album.ico',
        target / '安装并启动学生小档案.cmd',
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError('安装包缺少文件：' + ', '.join(missing))


def main():
    downloads = ROOT / '.build' / 'downloads'
    python_zip = downloads / f'python-{PYTHON_VERSION}-embed-amd64.zip'
    ngrok_zip = downloads / 'ngrok-windows-amd64.zip'
    download(PYTHON_URL, python_zip)
    download(NGROK_URL, ngrok_zip)

    shutil.rmtree(BUILD, ignore_errors=True)
    target = BUILD / PACKAGE_NAME
    runtime = target / 'runtime'
    runtime.mkdir(parents=True)
    with zipfile.ZipFile(python_zip) as bundle:
        bundle.extractall(runtime)
    pth = next(runtime.glob('python*._pth'))
    pth.write_text(f'python313.zip\n.\nLib/site-packages\nimport site\n', encoding='utf-8')
    install_pillow(runtime, downloads)
    copy_app(target)

    (target / 'app' / '.runtime').mkdir(parents=True)
    with zipfile.ZipFile(ngrok_zip) as bundle:
        (target / 'app' / '.runtime' / 'ngrok.exe').write_bytes(bundle.read('ngrok.exe'))
    shutil.copytree(ROOT / 'packaging' / 'assets', target / 'assets')
    for name in ('StudentAlbum.vbs', 'install-shortcut.ps1', 'README-Windows.txt'):
        shutil.copy2(ROOT / 'packaging' / 'windows' / name, target / name)
    shutil.copy2(ROOT / 'packaging' / 'windows' / 'InstallAndStart.cmd', target / '安装并启动学生小档案.cmd')

    verify_package(target)
    DIST.mkdir(exist_ok=True)
    archive = DIST / f'{PACKAGE_NAME}.zip'
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(target.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(BUILD))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    print(f'已生成：{archive}')
    print(f'大小：{archive.stat().st_size / 1024 / 1024:.1f} MB')
    print(f'SHA-256：{digest}')


if __name__ == '__main__':
    main()
