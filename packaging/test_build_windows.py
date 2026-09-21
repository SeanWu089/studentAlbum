"""Regression tests for the self-contained Windows package."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name('build_windows.py')
SPEC = importlib.util.spec_from_file_location('student_album_build_windows', MODULE_PATH)
build_windows = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_windows)


class WindowsPackageTest(unittest.TestCase):
    def test_embedded_python_can_import_application_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            build_windows.write_python_path(runtime, 'python313.zip')
            paths = (runtime / 'python313._pth').read_text(encoding='utf-8').splitlines()
            self.assertIn('../app/scripts', paths)

    def test_ngrok_download_is_locked_to_known_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'ngrok.zip'
            archive.write_bytes(b'not the pinned ngrok archive')
            with self.assertRaisesRegex(RuntimeError, 'ngrok 3.39.11 校验失败'):
                build_windows.verify_checksum(
                    archive,
                    build_windows.NGROK_SHA256,
                    f'ngrok {build_windows.NGROK_VERSION}',
                )


if __name__ == '__main__':
    unittest.main()
