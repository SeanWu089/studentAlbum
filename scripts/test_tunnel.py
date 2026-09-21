"""Tests for automatic ngrok startup and Windows credential persistence."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tunnel import Tunnel


class TunnelTest(unittest.TestCase):
    def test_windows_migrates_legacy_config_to_user_profile(self):
        with tempfile.TemporaryDirectory() as runtime_dir, tempfile.TemporaryDirectory() as local_app_data:
            runtime = Path(runtime_dir)
            legacy = runtime / 'ngrok.yml'
            legacy.write_text('version: "2"\nauthtoken: example\n', encoding='utf-8')
            state = {}
            with patch('tunnel.platform.system', return_value='Windows'), \
                 patch.dict(os.environ, {'LOCALAPPDATA': local_app_data}, clear=False):
                tunnel = Tunnel(runtime, state, 8766, 'https://fixed.example.ngrok-free.dev')
                config = tunnel.config_path()
            expected = Path(local_app_data) / 'StudentAlbum' / 'ngrok.yml'
            self.assertEqual(config, expected)
            self.assertEqual(expected.read_text(encoding='utf-8'), legacy.read_text(encoding='utf-8'))

    def test_command_binds_configured_fixed_url(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            tunnel = Tunnel(Path(runtime_dir), {}, 8766, 'https://fixed.example.ngrok-free.dev/')
            command = tunnel.command('ngrok.exe', Path('ngrok.yml'))
        self.assertEqual(command[0:3], ['ngrok.exe', 'http', 'http://127.0.0.1:8766'])
        self.assertEqual(command[command.index('--url') + 1], 'https://fixed.example.ngrok-free.dev')
        self.assertEqual(command[-2:], ['--config', 'ngrok.yml'])

    def test_first_connection_can_learn_and_persist_fixed_url(self):
        with tempfile.TemporaryDirectory() as runtime_dir, tempfile.TemporaryDirectory() as local_app_data:
            with patch('tunnel.platform.system', return_value='Windows'), \
                 patch.dict(os.environ, {'LOCALAPPDATA': local_app_data}, clear=False):
                tunnel = Tunnel(Path(runtime_dir), {}, 8766)
                self.assertNotIn('--url', tunnel.command('ngrok.exe'))
                tunnel.remember_public_url('https://assigned.ngrok-free.dev/')
                self.assertEqual(tunnel.configured_url, 'https://assigned.ngrok-free.dev')
                reopened = Tunnel(Path(runtime_dir), {}, 8766)
                self.assertEqual(reopened.configured_url, 'https://assigned.ngrok-free.dev')


if __name__ == '__main__':
    unittest.main()
