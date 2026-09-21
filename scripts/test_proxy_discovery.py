"""Tests for proxy discovery without assuming a specific proxy app or port."""
import os
import sys
from unittest.mock import patch
import unittest
from urllib.parse import urlsplit

from proxy_discovery import _windows_proxy_values, normalize_proxy_url, parse_proxy_server, proxy_routes


class ProxyDiscoveryTest(unittest.TestCase):
    def test_normalize_proxy_url_accepts_supported_schemes_and_plain_host_port(self):
        self.assertEqual(normalize_proxy_url('127.0.0.1:7890'), 'http://127.0.0.1:7890')
        self.assertEqual(normalize_proxy_url('socks5://127.0.0.1:1080'), 'socks5://127.0.0.1:1080')
        self.assertEqual(normalize_proxy_url('socks5h://127.0.0.1:1080'), '')

    def test_parse_windows_proxy_server_prefers_https_then_http_then_socks(self):
        values = parse_proxy_server('http=127.0.0.1:7890;https=127.0.0.1:7891;socks=127.0.0.1:1080')
        self.assertEqual(values, [
            'http://127.0.0.1:7891',
            'http://127.0.0.1:7890',
            'socks5://127.0.0.1:1080',
        ])

    def test_proxy_routes_deduplicates_sources_and_prioritizes_last_success(self):
        env = {'HTTPS_PROXY': 'http://127.0.0.1:7890'}
        windows = [
            ('windows:manual', 'http://127.0.0.1:7890'),
            ('windows:auto', 'socks5://127.0.0.1:1080'),
        ]
        with patch.dict(os.environ, env, clear=True):
            routes = proxy_routes('windows:auto', windows_values=windows)
        self.assertEqual(routes[0], ('windows:auto', 'socks5://127.0.0.1:1080'))
        self.assertEqual(routes[1], ('direct', ''))
        self.assertEqual(routes[2], ('env:HTTPS_PROXY', 'http://127.0.0.1:7890'))
        self.assertEqual(len(routes), 3)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows API check')
    def test_windows_proxy_api_discovery_does_not_require_a_specific_client(self):
        values = _windows_proxy_values()
        self.assertIsInstance(values, list)
        for source, proxy in values:
            self.assertTrue(source.startswith('windows:'))
            self.assertIn(urlsplit(proxy).scheme, {'http', 'https', 'socks5'})


if __name__ == '__main__':
    unittest.main()
