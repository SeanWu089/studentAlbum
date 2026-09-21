"""Tests for automatic ngrok startup and Windows credential persistence."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tunnel import Tunnel, is_network_failure


class TunnelTest(unittest.TestCase):
    def test_heartbeat_timeout_is_treated_as_network_failure(self):
        self.assertTrue(is_network_failure('{"msg":"heartbeat timeout, terminating session"}'))
        self.assertTrue(is_network_failure('{"msg":"failed to reconnect session"}'))
        self.assertFalse(is_network_failure('{"msg":"starting web service"}'))

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

    def test_saving_new_token_resets_old_public_url(self):
        with tempfile.TemporaryDirectory() as runtime_dir, tempfile.TemporaryDirectory() as local_app_data:
            state = {}
            with patch('tunnel.platform.system', return_value='Windows'), \
                 patch.dict(os.environ, {'LOCALAPPDATA': local_app_data}, clear=False):
                tunnel = Tunnel(Path(runtime_dir), state, 8766)
                tunnel.remember_public_url('https://old.ngrok-free.dev')
                config = tunnel.save_token('secret-example-token')
                self.assertEqual(tunnel.configured_url, '')
                self.assertEqual(state['configuredPublicUrl'], '')
                self.assertFalse((Path(local_app_data) / 'StudentAlbum' / 'public-url.txt').exists())
                saved = config.read_text(encoding='utf-8')
                self.assertIn('authtoken: "secret-example-token"', saved)
                self.assertNotIn('old.ngrok-free.dev', saved)

    def test_proxy_config_preserves_token_and_adds_proxy_url(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime = Path(runtime_dir)
            base = runtime / 'ngrok.yml'
            base.write_text('version: "2"\nauthtoken: "secret"\n', encoding='utf-8')
            tunnel = Tunnel(runtime, {}, 8766)
            generated = tunnel.proxy_config(base, 'socks5://127.0.0.1:1080')
            try:
                text = generated.read_text(encoding='utf-8')
                self.assertIn('authtoken: "secret"', text)
                self.assertIn('proxy_url: "socks5://127.0.0.1:1080"', text)
            finally:
                generated.unlink(missing_ok=True)

    def test_route_memory_persists_source_without_storing_proxy_address(self):
        with tempfile.TemporaryDirectory() as runtime_dir, tempfile.TemporaryDirectory() as local_app_data:
            with patch('tunnel.platform.system', return_value='Windows'), \
                 patch.dict(os.environ, {'LOCALAPPDATA': local_app_data}, clear=False):
                tunnel = Tunnel(Path(runtime_dir), {}, 8766)
                tunnel.remember_route('windows:auto')
                route_file = Path(local_app_data) / 'StudentAlbum' / 'proxy-route.txt'
                self.assertEqual(route_file.read_text(encoding='utf-8').strip(), 'windows:auto')
                self.assertNotIn('127.0.0.1', route_file.read_text(encoding='utf-8'))
                self.assertEqual(Tunnel(Path(runtime_dir), {}, 8766).saved_route(), 'windows:auto')


if __name__ == '__main__':
    unittest.main()
