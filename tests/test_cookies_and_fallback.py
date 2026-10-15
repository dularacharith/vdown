"""Unit tests for browser cookie discovery, auto-retry, and direct download protection."""

import unittest
from unittest.mock import patch, MagicMock

from simple_downloader.browser_cookies import (
    detect_available_browsers,
    get_best_browser,
    get_browser_cookie_summary,
)
from simple_downloader.direct_downloader import DirectDownloader
from simple_downloader.engine import DownloadEngine, KNOWN_SOCIAL_DOMAINS


class TestBrowserCookies(unittest.TestCase):
    """Test browser cookie detection and priority order."""

    def test_detect_available_browsers_structure(self):
        browsers = detect_available_browsers()
        self.assertIsInstance(browsers, list)
        self.assertGreater(len(browsers), 0)
        first = browsers[0]
        self.assertIn("browser", first)
        self.assertIn("available", first)
        self.assertIn("cookies_count", first)
        # Verify Firefox is priority 1
        self.assertEqual(first["browser"], "firefox")

    @patch("simple_downloader.browser_cookies.detect_available_browsers")
    def test_get_best_browser_selects_firefox(self, mock_detect):
        mock_detect.return_value = [
            {"browser": "firefox", "available": True, "cookies_count": 150, "has_auth": True},
            {"browser": "chrome", "available": True, "cookies_count": 80, "has_auth": False},
        ]
        self.assertEqual(get_best_browser(), "firefox")

    @patch("simple_downloader.browser_cookies.detect_available_browsers")
    def test_get_best_browser_none_available(self, mock_detect):
        mock_detect.return_value = [
            {"browser": "firefox", "available": False, "cookies_count": 0, "has_auth": False},
            {"browser": "chrome", "available": False, "cookies_count": 0, "has_auth": False},
        ]
        self.assertIsNone(get_best_browser())

    @patch("simple_downloader.browser_cookies.detect_available_browsers")
    def test_get_browser_cookie_summary(self, mock_detect):
        mock_detect.return_value = [
            {"name": "Mozilla Firefox", "available": True, "cookies_count": 236},
        ]
        summary = get_browser_cookie_summary()
        self.assertIn("Mozilla Firefox", summary)
        self.assertIn("236 cookies", summary)


class TestDirectDownloadProtection(unittest.TestCase):
    """Test that direct downloader rejects HTML and social links do not fall through."""

    @patch("requests.Session.get")
    def test_direct_downloader_rejects_html_content_type(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            "content-type": "text/html; charset=utf-8",
            "content-length": "1500000",
        }
        mock_get.return_value = mock_resp

        downloader = DirectDownloader()
        with self.assertRaises(ValueError) as ctx:
            downloader.download("https://www.youtube.com/watch?v=12345", output_dir="tmp_test")
        self.assertIn("HTML webpage", str(ctx.exception))

    @patch("yt_dlp.YoutubeDL")
    def test_social_domains_do_not_fallback_to_direct_downloader(self, mock_ydl):
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {"id": "123", "title": "Test Video", "formats": []}
        mock_instance.download.side_effect = RuntimeError("Sign in to confirm you're not a bot")
        mock_instance.__enter__.return_value = mock_instance
        mock_ydl.return_value = mock_instance

        engine = DownloadEngine()
        for social_url in [
            "https://www.youtube.com/watch?v=CluuHrr7HG4",
            "https://youtu.be/CluuHrr7HG4",
            "https://www.facebook.com/reel/123456",
            "https://www.instagram.com/reel/abcdef/",
        ]:
            with self.subTest(url=social_url):
                with patch("simple_downloader.engine.get_best_browser", return_value=None):
                    with self.assertRaises(Exception) as ctx:
                        engine.download(social_url, show_progress=False)
                    # Must fail with yt-dlp error, NOT succeed or download direct stream
                    self.assertIn("bot", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
