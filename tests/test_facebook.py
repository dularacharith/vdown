"""Unit tests for Facebook downloader and URL normalizer."""

import unittest
from unittest.mock import patch, MagicMock

from simple_downloader.facebook import (
    is_facebook_url,
    normalize_facebook_url,
    FacebookDownloader,
)
from simple_downloader.engine import DownloadEngine


class TestFacebookDownloader(unittest.TestCase):
    """Test Facebook URL detection, normalization, and direct stream extraction."""

    def test_is_facebook_url(self):
        self.assertTrue(is_facebook_url("https://www.facebook.com/reel/1195289147628387"))
        self.assertTrue(is_facebook_url("https://facebook.com/share/r/1195289147628387/"))
        self.assertTrue(is_facebook_url("https://www.facebook.com/share/v/99887766/"))
        self.assertTrue(is_facebook_url("https://fb.watch/xYz123/"))
        self.assertTrue(is_facebook_url("https://m.facebook.com/watch/?v=123456"))
        self.assertTrue(is_facebook_url("https://web.facebook.com/reel/123456"))

        self.assertFalse(is_facebook_url("https://www.youtube.com/watch?v=123"))
        self.assertFalse(is_facebook_url("https://www.tiktok.com/@user/video/123"))
        self.assertFalse(is_facebook_url("https://example.com/video.mp4"))
        self.assertFalse(is_facebook_url(""))
        self.assertFalse(is_facebook_url(None))

    def test_normalize_facebook_url(self):
        # Numeric share reel URL
        url_reel = "https://www.facebook.com/share/r/1195289147628387/?mibextid=000"
        self.assertEqual(
            normalize_facebook_url(url_reel),
            "https://www.facebook.com/reel/1195289147628387/",
        )

        # Numeric share video URL
        url_video = "https://www.facebook.com/share/v/987654321/?mibextid=000"
        self.assertEqual(
            normalize_facebook_url(url_video),
            "https://www.facebook.com/watch/?v=987654321",
        )

        # Standard reel URL
        url_std = "https://www.facebook.com/reel/1195289147628387"
        self.assertEqual(normalize_facebook_url(url_std), url_std)

        # Alphanumeric share reel URL (without redirect, returns clean reel URL or clean input)
        url_alpha_reel = "https://www.facebook.com/share/r/1K5916ZbCbpLgtwJ/?mibextid=000"
        self.assertTrue(is_facebook_url(url_alpha_reel))

    @patch("requests.get")
    def test_extract_direct_streams_mock(self, mock_get):
        mock_html = """
        <html>
        <head>
            <meta property="og:title" content="Awesome Facebook Reel &amp; Fun" />
            <meta property="og:image" content="https://fbcdn.net/thumb.jpg" />
        </head>
        <body>
            <script>
            var data = {
                "browser_native_hd_url": "https:\\/\\/video.fbcdn.net\\/hd.mp4?token=123",
                "browser_native_sd_url": "https:\\/\\/video.fbcdn.net\\/sd.mp4?token=456"
            };
            </script>
        </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        fb = FacebookDownloader()
        info = fb._extract_direct_streams("https://www.facebook.com/reel/12345678/")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_facebook"])
        self.assertTrue(info["is_direct"])
        self.assertIn("Awesome Facebook Reel", info["title"])
        self.assertEqual(info["thumbnail"], "https://fbcdn.net/thumb.jpg")

        formats = info["formats"]
        self.assertEqual(len(formats), 3)  # hd, sd, audio-only
        format_ids = [f["format_id"] for f in formats]
        self.assertIn("hd", format_ids)
        self.assertIn("sd", format_ids)
        self.assertIn("audio-only", format_ids)

        hd_fmt = next(f for f in formats if f["format_id"] == "hd")
        self.assertEqual(hd_fmt["url"], "https://video.fbcdn.net/hd.mp4?token=123")


if __name__ == "__main__":
    unittest.main()
