#!/usr/bin/env python3
"""Install/update or uninstall the Windows portable app without extra user steps."""
from pathlib import Path
import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import time


APP_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = APP_ROOT.parent
APP_NAME = '学生小档案'


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(script, check=True):
    return subprocess.run(
        ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script],
        text=True, capture_output=True, check=check,
    )


def desktop_directory():
    buffer = ctypes.create_unicode_buffer(32768)
    # CSIDL_DESKTOPDIRECTORY = 0x10. This respects OneDrive/localized desktops.
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buffer)
    if result != 0:
        raise OSError(f'无法找到桌面目录（错误 {result}）')
    return Path(buffer.value)


def shortcut_path():
    return desktop_directory() / f'{APP_NAME}.lnk'


def shortcut_root(link):
    if not link.exists():
        return None
    script = (
        '$shell=New-Object -ComObject WScript.Shell; '
        f'$shortcut=$shell.CreateShortcut({ps_quote(link)}); '
        '[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; '
        'Write-Output $shortcut.WorkingDirectory'
    )
    result = run_powershell(script, check=False)
    value = result.stdout.strip()
    return Path(value) if result.returncode == 0 and value else None


def stop_servers():
    """Stop only StudentAlbum serve.py processes; needed when upgrading from old packages."""
    script = r'''
$ErrorActionPreference='SilentlyContinue'
Get-CimInstance Win32_Process | Where-Object {
  ($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and
  $_.CommandLine -and
  $_.CommandLine -match 'app[\\/]scripts[\\/]serve\.py'
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
'''
    run_powershell(script, check=False)
    time.sleep(0.7)


def copy_if_missing(source, destination):
    if source.is_file() and not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def migrate(old_root):
    if not old_root or not old_root.exists() or old_root.resolve() == PACKAGE_ROOT.resolve():
        return
    old_app = old_root / 'app'
    old_data = old_app / 'data'
    new_data = APP_ROOT / 'data'
    if old_data.is_dir() and not new_data.exists():
        shutil.copytree(old_data, new_data)

    local_app_data = os.getenv('LOCALAPPDATA')
    if local_app_data:
        user_dir = Path(local_app_data) / 'StudentAlbum'
        copy_if_missing(old_app / '.runtime' / 'ngrok.yml', user_dir / 'ngrok.yml')
        copy_if_missing(old_app / '.runtime' / 'public-url.txt', user_dir / 'public-url.txt')


def create_shortcut(link):
    target = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'wscript.exe'
    vbs = PACKAGE_ROOT / 'StudentAlbum.vbs'
    icon = PACKAGE_ROOT / 'assets' / 'student-album.ico'
    script = (
        '$ErrorActionPreference=\'Stop\'; '
        '$shell=New-Object -ComObject WScript.Shell; '
        f'$shortcut=$shell.CreateShortcut({ps_quote(link)}); '
        f'$shortcut.TargetPath={ps_quote(target)}; '
        f'$shortcut.Arguments={ps_quote(chr(34) + str(vbs) + chr(34))}; '
        f'$shortcut.WorkingDirectory={ps_quote(PACKAGE_ROOT)}; '
        f'$shortcut.IconLocation={ps_quote(str(icon) + ",0")}; '
        f'$shortcut.Description={ps_quote(APP_NAME)}; '
        '$shortcut.Save()'
    )
    run_powershell(script)


def install():
    link = shortcut_path()
    old_root = shortcut_root(link)
    stop_servers()
    migrate(old_root)
    create_shortcut(link)
    os.startfile(link)
    print('学生小档案已安装并启动。')


def uninstall():
    stop_servers()
    link = shortcut_path()
    link.unlink(missing_ok=True)
    print('学生小档案已停止，桌面快捷方式已删除。')
    print('学生资料和 ngrok 配置已保留；确认不再需要后，可手动删除解压目录。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'win32':
        raise SystemExit('此脚本仅用于 Windows。')
    uninstall() if args.uninstall else install()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
