"""Unit tests for YouTube and YouTube Shorts detection, normalization, and downloading."""

import unittest
from unittest.mock import patch, MagicMock

from simple_downloader.youtube import (
    is_youtube_url,
    is_youtube_shorts_url,
    extract_youtube_id,
    normalize_youtube_url,
    to_watch_url,
    to_shorts_url,
    get_shorts_format_selector,
    YouTubeDownloader,
)
from simple_downloader.engine import DownloadEngine


class TestYouTubeShorts(unittest.TestCase):
    """Test suite covering YouTube Shorts detection, parsing, and formatting."""

    def test_is_youtube_url(self):
        self.assertTrue(is_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_youtube_url("https://youtube.com/shorts/3jz_kL8w0p0"))
        self.assertTrue(is_youtube_url("https://m.youtube.com/shorts/3jz_kL8w0p0"))
        self.assertTrue(is_youtube_url("https://youtu.be/3jz_kL8w0p0"))
        self.assertTrue(is_youtube_url("https://music.youtube.com/watch?v=abc12345678"))

        self.assertFalse(is_youtube_url("https://vimeo.com/123456"))
        self.assertFalse(is_youtube_url("https://tiktok.com/@user/video/123"))
        self.assertFalse(is_youtube_url("https://example.com/video.mp4"))
        self.assertFalse(is_youtube_url(""))
        self.assertFalse(is_youtube_url(None))

    def test_is_youtube_shorts_url(self):
        self.assertTrue(is_youtube_shorts_url("https://www.youtube.com/shorts/3jz_kL8w0p0"))
        self.assertTrue(is_youtube_shorts_url("https://youtube.com/shorts/3jz_kL8w0p0"))
        self.assertTrue(is_youtube_shorts_url("https://m.youtube.com/shorts/3jz_kL8w0p0?feature=share"))
        self.assertTrue(is_youtube_shorts_url("https://www.youtube.com/shorts/3jz_kL8w0p0?si=abcdef123456"))
        self.assertTrue(is_youtube_shorts_url("youtube.com/shorts/3jz_kL8w0p0"))

        # Standard videos are not shorts URLs
        self.assertFalse(is_youtube_shorts_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(is_youtube_shorts_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(is_youtube_shorts_url("https://example.com/shorts/video.mp4"))
        self.assertFalse(is_youtube_shorts_url(""))
        self.assertFalse(is_youtube_shorts_url(None))

    def test_extract_youtube_id(self):
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/shorts/3jz_kL8w0p0"),
            "3jz_kL8w0p0",
        )
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_id("https://youtu.be/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/embed/dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/shorts/3jz_kL8w0p0?feature=share&si=123"),
            "3jz_kL8w0p0",
        )
        self.assertIsNone(extract_youtube_id("https://example.com/video.mp4"))

    def test_normalize_youtube_url(self):
        # Shorts with tracking tokens stripped
        url_shorts = "https://www.youtube.com/shorts/3jz_kL8w0p0?feature=share&si=xyz987"
        self.assertEqual(
            normalize_youtube_url(url_shorts),
            "https://www.youtube.com/shorts/3jz_kL8w0p0",
        )

        # Standard video
        url_watch = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=youtu.be"
        self.assertEqual(
            normalize_youtube_url(url_watch),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )

    def test_to_watch_and_to_shorts_url(self):
        shorts_url = "https://www.youtube.com/shorts/3jz_kL8w0p0"
        self.assertEqual(to_watch_url(shorts_url), "https://www.youtube.com/watch?v=3jz_kL8w0p0")
        self.assertEqual(to_shorts_url("3jz_kL8w0p0"), "https://www.youtube.com/shorts/3jz_kL8w0p0")

    def test_get_shorts_format_selector(self):
        fmt_1080 = get_shorts_format_selector("1080p")
        self.assertIn("width<=1080", fmt_1080)

        fmt_720 = get_shorts_format_selector("720p")
        self.assertIn("width<=720", fmt_720)

        fmt_best = get_shorts_format_selector("best")
        self.assertEqual(fmt_best, "bestvideo+bestaudio/best")

        fmt_worst = get_shorts_format_selector("worst")
        self.assertEqual(fmt_worst, "worstvideo+worstaudio/worst")

    @patch("yt_dlp.YoutubeDL")
    def test_youtube_downloader_get_info_mock(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {
            "id": "3jz_kL8w0p0",
            "title": "Amazing YouTube Short",
            "uploader": "Creator",
            "duration": 42,
            "width": 1080,
            "height": 1920,
            "formats": [
                {"format_id": "137", "width": 1080, "height": 1920, "ext": "mp4"},
                {"format_id": "140", "acodec": "mp4a.40.2", "ext": "m4a"},
            ],
        }
        mock_instance.__enter__.return_value = mock_instance
        mock_ydl_cls.return_value = mock_instance

        yt = YouTubeDownloader()
        info = yt.get_info("https://www.youtube.com/shorts/3jz_kL8w0p0")

        self.assertIsNotNone(info)
        self.assertTrue(info.get("is_youtube_shorts"))
        self.assertTrue(info.get("is_short"))
        self.assertEqual(info.get("id"), "3jz_kL8w0p0")

    @patch("yt_dlp.YoutubeDL")
    def test_engine_shorts_format_selection_in_download(self, mock_ydl_cls):
        mock_instance = MagicMock()
        mock_instance.download.return_value = 0
        mock_instance.__enter__.return_value = mock_instance
        mock_ydl_cls.return_value = mock_instance

        engine = DownloadEngine()
        captured_opts = {}

        def mock_init(opts):
            nonlocal captured_opts
            captured_opts = opts
            return mock_instance

        mock_ydl_cls.side_effect = mock_init

        with patch.object(
            engine,
            "get_media_info",
            return_value={
                "id": "3jz_kL8w0p0",
                "title": "Vertical Short",
                "is_youtube_shorts": True,
                "formats": [],
            },
        ):
            engine.download(
                "https://www.youtube.com/shorts/3jz_kL8w0p0",
                quality="1080p",
                show_progress=False,
            )

        # Check format selector includes vertical width rule
        fmt_string = captured_opts.get("format", "")
        self.assertIn("width<=1080", fmt_string)

        # Check YouTube player_client extractor_args are set
        ext_args = captured_opts.get("extractor_args", {})
        self.assertIn("youtube", ext_args)
        self.assertIn("player_client", ext_args["youtube"])


if __name__ == "__main__":
    unittest.main()
