"""Exercise the ZIP's own Windows runtime, outside the source checkout."""
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from build_windows import DIST, PACKAGE_NAME


def main():
    if sys.platform != 'win32':
        raise SystemExit('This check requires Windows; run it in GitHub Actions.')
    archive = DIST / f'{PACKAGE_NAME}.zip'
    expected = archive.with_suffix('.zip.sha256').read_text().split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
    with tempfile.TemporaryDirectory(prefix='学生档案 测试 ') as directory:
        root = Path(directory)
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            bundle.extractall(root)
        package = root / PACKAGE_NAME
        python = package / 'runtime' / 'python.exe'
        subprocess.run([str(python), '-c',
                        'import storage, webserver, tunnel; from PIL import Image; '
                        'import io; b=io.BytesIO(); Image.new("RGB", (8,8)).save(b,"JPEG"); '
                        'assert Image.open(io.BytesIO(b.getvalue())).size == (8,8)'],
                       cwd=root, check=True, timeout=30)
        with socket.socket() as admin, socket.socket() as student:
            admin.bind(('127.0.0.1', 0))
            student.bind(('127.0.0.1', 0))
            admin_port, student_port = admin.getsockname()[1], student.getsockname()[1]
        with (root / 'smoke.log').open('w+', encoding='utf-8') as log:
            process = subprocess.Popen([
                str(python), str(package / 'app/scripts/serve.py'),
                '--local', '--no-open', '--data-dir', str(root / 'test-data'),
                '--admin-port', str(admin_port), '--student-port', str(student_port),
            ], cwd=root, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError('Packaged server exited before becoming ready')
                    try:
                        for port, path in ((admin_port, '/admin.html'), (student_port, '/')):
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
                                assert response.status == 200
                                assert b'<html' in response.read().lower()
                        break
                    except (urllib.error.URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.2)
                assert (root / 'test-data/album.sqlite3').is_file()
                print('Bundled Python imports, JPEG processing and both web pages passed.')
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                log.seek(0)
                print(log.read())


if __name__ == '__main__':
    main()
