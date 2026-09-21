"""Regression tests for the self-contained Windows package."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name('build_windows.py')
ROOT = MODULE_PATH.parent.parent
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

    def test_windows_launcher_starts_lan_and_ngrok_together(self):
        source = (ROOT / 'scripts' / 'windows_launcher.py').read_text(encoding='utf-8')
        self.assertIn("'--lan'", source)
        self.assertNotIn("'--local', '--lan'", source)

    def test_windows_launcher_replaces_old_server(self):
        source = (ROOT / 'scripts' / 'windows_launcher.py').read_text(encoding='utf-8')
        self.assertIn('/api/admin/instance', source)
        self.assertIn('stop_old_server()', source)

    def test_installer_migrates_old_ngrok_config(self):
        source = (ROOT / 'scripts' / 'windows_setup.py').read_text(encoding='utf-8')
        self.assertIn("old_app / '.runtime' / 'ngrok.yml'", source)
        self.assertIn("LOCALAPPDATA", source)
        self.assertIn("StudentAlbum", source)

    def test_setup_files_are_single_entrypoints(self):
        windows = ROOT / 'packaging' / 'windows'
        self.assertFalse((windows / 'install-shortcut.ps1').exists())
        self.assertTrue((windows / 'InstallAndStart.cmd').exists())
        self.assertTrue((windows / 'Uninstall.cmd').exists())
        install = (windows / 'InstallAndStart.cmd').read_text(encoding='utf-8')
        uninstall = (windows / 'Uninstall.cmd').read_text(encoding='utf-8')
        self.assertIn('windows_setup.py', install)
        self.assertIn('--uninstall', uninstall)


if __name__ == '__main__':
    unittest.main()
