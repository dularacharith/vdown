"""Comprehensive test suite for simple-downloader."""

import os
import shutil
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import unittest

from simple_downloader.utils import (
    format_bytes,
    format_duration,
    sanitize_filename,
    get_filename_from_headers_or_url,
    is_direct_media_url,
    parse_speed_limit,
)
from simple_downloader.direct_downloader import DirectDownloader
from simple_downloader.engine import DownloadEngine
from simple_downloader.cli import create_parser


class MockServerHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler serving a sample file with Content-Disposition and Range support."""

    SAMPLE_DATA = b"Hello, this is a test payload for simple-downloader video stream!" * 100

    def log_message(self, format, *args):
        # Suppress server logs during test run
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(self.SAMPLE_DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", 'attachment; filename="sample_video.mp4"')
        self.end_headers()

    def do_GET(self):
        range_header = self.headers.get("Range")
        total_len = len(self.SAMPLE_DATA)

        if range_header and range_header.startswith("bytes="):
            byte_range = range_header[6:].split("-")
            start = int(byte_range[0])
            end = int(byte_range[1]) if byte_range[1] else total_len - 1

            if start >= total_len:
                self.send_response(416)
                self.end_headers()
                return

            self.send_response(206)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(self.SAMPLE_DATA[start : end + 1])
        else:
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", 'attachment; filename="sample_video.mp4"')
            self.end_headers()
            self.wfile.write(self.SAMPLE_DATA)


class TestUtils(unittest.TestCase):
    """Test helper functions in utils.py."""

    def test_format_bytes(self):
        self.assertEqual(format_bytes(None), "Unknown")
        self.assertEqual(format_bytes(0), "0.00 B")
        self.assertEqual(format_bytes(512), "512.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024 * 1024 * 15), "15.00 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024 * 2.5), "2.50 GB")

    def test_format_duration(self):
        self.assertEqual(format_duration(None), "Unknown")
        self.assertEqual(format_duration(45), "00:45")
        self.assertEqual(format_duration(125), "02:05")
        self.assertEqual(format_duration(3665), "01:01:05")

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("my:cool*video?.mp4"), "my_cool_video_.mp4")
        self.assertEqual(sanitize_filename("../../etc/passwd"), ".._.._etc_passwd")
        self.assertEqual(sanitize_filename(""), "download")

    def test_get_filename_from_headers_or_url(self):
        headers = {"Content-Disposition": 'attachment; filename="trailer.mp4"'}
        self.assertEqual(get_filename_from_headers_or_url("https://example.com/stream", headers), "trailer.mp4")

        # Filename* RFC 5987
        headers_star = {"Content-Disposition": "attachment; filename*=UTF-8''my%20cool%20clip.mp4"}
        self.assertEqual(get_filename_from_headers_or_url("https://example.com/video", headers_star), "my cool clip.mp4")

        # Fallback to URL
        self.assertEqual(
            get_filename_from_headers_or_url("https://example.com/media/clip.webm"),
            "clip.webm"
        )

    def test_is_direct_media_url(self):
        self.assertTrue(is_direct_media_url("https://example.com/movie.mp4"))
        self.assertTrue(is_direct_media_url("https://example.com/audio.mp3?token=123"))
        self.assertTrue(is_direct_media_url("https://cdn.site.com/video.mkv"))
        self.assertFalse(is_direct_media_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(is_direct_media_url("https://vimeo.com/123456"))

    def test_parse_speed_limit(self):
        self.assertEqual(parse_speed_limit("500K"), 500 * 1024)
        self.assertEqual(parse_speed_limit("5M"), 5 * 1024 * 1024)
        self.assertEqual(parse_speed_limit("1G"), 1024 * 1024 * 1024)
        self.assertEqual(parse_speed_limit("2048"), 2048)
        self.assertIsNone(parse_speed_limit(None))
        self.assertIsNone(parse_speed_limit("invalid"))


class TestDirectDownloader(unittest.TestCase):
    """Test direct HTTP download and resume functionality."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_direct_download(self):
        url = f"http://127.0.0.1:{self.port}/test"
        downloader = DirectDownloader()
        out_file = downloader.download(
            url=url,
            output_dir=self.test_dir,
            show_progress=False,
        )

        self.assertTrue(os.path.exists(out_file))
        self.assertEqual(Path(out_file).name, "sample_video.mp4")
        with open(out_file, "rb") as f:
            content = f.read()
        self.assertEqual(content, MockServerHandler.SAMPLE_DATA)

    def test_resumable_download(self):
        url = f"http://127.0.0.1:{self.port}/test"
        downloader = DirectDownloader()

        # Simulate partial file
        part_file = Path(self.test_dir) / "sample_video.mp4.part"
        half_len = len(MockServerHandler.SAMPLE_DATA) // 2
        with open(part_file, "wb") as f:
            f.write(MockServerHandler.SAMPLE_DATA[:half_len])

        out_file = downloader.download(
            url=url,
            output_dir=self.test_dir,
            show_progress=False,
        )

        self.assertTrue(os.path.exists(out_file))
        self.assertFalse(part_file.exists())
        with open(out_file, "rb") as f:
            content = f.read()
        self.assertEqual(content, MockServerHandler.SAMPLE_DATA)


class TestCLIParser(unittest.TestCase):
    """Test CLI arguments parsing."""

    def test_parser_defaults(self):
        parser = create_parser()
        args = parser.parse_args(["https://example.com/video.mp4"])
        self.assertEqual(args.url, "https://example.com/video.mp4")
        self.assertEqual(args.quality, "best")
        self.assertFalse(args.audio_only)
        self.assertEqual(args.audio_format, "mp3")
        self.assertEqual(args.audio_quality, "320")
        self.assertFalse(args.playlist)
        self.assertFalse(args.no_playlist)
        self.assertIsNone(args.playlist_items)
        self.assertEqual(args.output_dir, "downloads")

    def test_parser_custom_options(self):
        parser = create_parser()
        args = parser.parse_args([
            "https://example.com/watch",
            "-q", "1080p",
            "-a",
            "--audio-format", "flac",
            "-aq", "320",
            "-o", "song.flac",
            "-d", "/tmp",
            "--rate-limit", "2M",
            "--playlist",
            "--playlist-items", "1-10",
            "--embed-subs",
            "--embed-thumbnail",
            "--browser", "chromium",
            "--cookies", "/tmp/cookies.txt",
            "--proxy", "socks5://127.0.0.1:9050",
            "--user-agent", "CustomUA/1.0",
            "--referer", "https://instagram.com",
        ])
        self.assertEqual(args.quality, "1080p")
        self.assertTrue(args.audio_only)
        self.assertEqual(args.audio_format, "flac")
        self.assertEqual(args.audio_quality, "320")
        self.assertEqual(args.output, "song.flac")
        self.assertEqual(args.output_dir, "/tmp")
        self.assertEqual(args.rate_limit, "2M")
        self.assertTrue(args.playlist)
        self.assertEqual(args.playlist_items, "1-10")
        self.assertTrue(args.embed_subs)
        self.assertTrue(args.embed_thumbnail)
        self.assertEqual(args.browser, "chromium")
        self.assertEqual(args.cookie_file, "/tmp/cookies.txt")
        self.assertEqual(args.proxy, "socks5://127.0.0.1:9050")
        self.assertEqual(args.user_agent, "CustomUA/1.0")
        self.assertEqual(args.referer, "https://instagram.com")

    def test_parser_no_playlist_flag(self):
        parser = create_parser()
        args = parser.parse_args(["https://example.com/watch?v=123&list=abc", "--no-playlist"])
        self.assertTrue(args.no_playlist)

    def test_main_keyboard_interrupt_exits_gracefully(self):
        from unittest.mock import patch
        from simple_downloader.cli import main
        import io

        test_console_buf = io.StringIO()
        with patch("simple_downloader.cli.console.print") as mock_print:
            with patch("simple_downloader.cli.do_download", side_effect=KeyboardInterrupt):
                exit_code = main(["https://example.com/video.mp4"])
                self.assertEqual(exit_code, 130)
                # Verify Goodbye was printed
                calls = [str(call) for call in mock_print.call_args_list]
                self.assertTrue(any("Goodbye" in c for c in calls))

    def test_interactive_keyboard_interrupt_exits_gracefully(self):
        from unittest.mock import patch
        from simple_downloader.cli import run_interactive_mode
        from simple_downloader.engine import DownloadEngine

        engine = DownloadEngine()
        with patch("simple_downloader.cli.console.print") as mock_print:
            with patch("simple_downloader.cli.Prompt.ask", side_effect=KeyboardInterrupt):
                exit_code = run_interactive_mode(engine)
                self.assertEqual(exit_code, 130)
                calls = [str(call) for call in mock_print.call_args_list]
                self.assertTrue(any("Goodbye" in c for c in calls))


class TestWebpageVideoScraper(unittest.TestCase):
    """Test webpage video scraper for embedded videos."""

    def test_find_videos_from_html(self):
        from unittest.mock import patch, Mock
        from simple_downloader.scraper import WebpageVideoScraper

        sample_html = """
        <html>
        <head>
            <meta property="og:video" content="https://example.com/og_video.mp4" />
            <meta name="twitter:player:stream" content="https://example.com/twitter_stream.m3u8" />
        </head>
        <body>
            <video src="https://example.com/direct_video.webm"></video>
            <video>
                <source src="https://example.com/source_video.mp4" type="video/mp4">
            </video>
            <script>
                const videoData = {
                    "contentUrl": "https://example.com/json_ld_video.mp4"
                };
            </script>
        </body>
        </html>
        """

        mock_resp = Mock()
        mock_resp.text = sample_html
        mock_resp.raise_for_status = Mock()

        scraper = WebpageVideoScraper()
        with patch("requests.get", return_value=mock_resp):
            candidates = scraper.find_videos("https://example.com/article")

        urls = [c["url"] for c in candidates]
        self.assertIn("https://example.com/og_video.mp4", urls)
        self.assertIn("https://example.com/twitter_stream.m3u8", urls)
        self.assertIn("https://example.com/direct_video.webm", urls)
        self.assertIn("https://example.com/source_video.mp4", urls)
        self.assertIn("https://example.com/json_ld_video.mp4", urls)


class TestEngineDirectFallback(unittest.TestCase):
    """Test that DownloadEngine handles direct links gracefully."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockServerHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever)
        cls.server_thread.daemon = True
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_engine_extract_direct_info(self):
        url = f"http://127.0.0.1:{self.port}/clip.mp4"
        engine = DownloadEngine()
        info = engine.get_media_info(url)
        self.assertIsNotNone(info)
        # yt-dlp generic extractor extracts the basename without extension
        self.assertIn(info.get("title"), ["clip", "sample_video.mp4"])

    def test_engine_direct_fallback_when_ytdlp_fails(self):
        from unittest.mock import patch
        import yt_dlp

        url = f"http://127.0.0.1:{self.port}/custom_stream"
        engine = DownloadEngine()

        with patch.object(yt_dlp.YoutubeDL, "extract_info", side_effect=yt_dlp.utils.DownloadError("Simulated error")):
            info = engine.get_media_info(url)
            self.assertTrue(info.get("is_direct"))
            self.assertEqual(info.get("title"), "sample_video.mp4")
            self.assertEqual(info.get("filesize"), len(MockServerHandler.SAMPLE_DATA))


class TestProgressColumns(unittest.TestCase):
    """Test progress bar dual speed and ETA formatting."""

    def test_dual_speed_column_render(self):
        from simple_downloader.progress import DualSpeedColumn
        from rich.progress import Progress

        col = DualSpeedColumn()
        p = Progress(col)
        tid = p.add_task("Test", total=100000000, completed=50000000, speed=37.5 * 1024 * 1024, eta=15)
        rendered = col.render(p.tasks[0])
        plain = rendered.plain
        self.assertIn("37.50 MB/s", plain)
        self.assertIn("Mbps", plain)

    def test_dynamic_eta_column_render(self):
        from simple_downloader.progress import DynamicETAColumn
        from rich.progress import Progress

        col = DynamicETAColumn()
        p = Progress(col)
        tid = p.add_task("Test", total=100000000, completed=50000000, speed=1000000, eta=125)
        rendered = col.render(p.tasks[0])
        self.assertIn("02:05", rendered.plain)


class TestTikTokDownloader(unittest.TestCase):
    """Test TikTok detection and info extraction."""

    def test_is_tiktok_url(self):
        from simple_downloader.tiktok import is_tiktok_url

        self.assertTrue(is_tiktok_url("https://www.tiktok.com/@user/video/123456789"))
        self.assertTrue(is_tiktok_url("https://vt.tiktok.com/ZSqF9Tr6a/"))
        self.assertTrue(is_tiktok_url("https://vm.tiktok.com/ZM8ABCDEF/"))
        self.assertTrue(is_tiktok_url("https://www.tiktok.com/@user/photo/123456789"))
        self.assertFalse(is_tiktok_url("https://www.youtube.com/watch?v=1234"))
        self.assertFalse(is_tiktok_url("https://example.com/video.mp4"))

    def test_tiktok_get_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.tiktok import TikTokDownloader

        mock_resp = Mock()
        mock_resp.json.return_value = {
            "code": 0,
            "data": {
                "id": "7663645630136339734",
                "title": "Inspiring Quote",
                "author": {"nickname": "thecapitalclub_"},
                "hdplay": "https://example.com/clean_video.mp4",
                "play": "https://example.com/clean_video.mp4",
                "music": "https://example.com/music.mp3",
                "images": None,
                "duration": 15,
                "play_count": 50000,
            }
        }

        tt = TikTokDownloader()
        with patch("requests.post", return_value=mock_resp):
            info = tt.get_info("https://vt.tiktok.com/ZSqF9Tr6a/")

        self.assertIsNotNone(info)
        self.assertTrue(info.get("is_tiktok"))
        self.assertEqual(info.get("author"), "thecapitalclub_")
        self.assertEqual(info.get("video_url"), "https://example.com/clean_video.mp4")
        self.assertEqual(len(info.get("formats", [])), 2)  # Video + Audio


class TestPlaylistAndAudioEngine(unittest.TestCase):
    """Test engine playlist and high-quality audio extraction configurations."""

    def test_engine_flac_audio_postprocessor(self):
        from unittest.mock import patch, MagicMock
        import yt_dlp

        engine = DownloadEngine()
        captured_opts = {}

        def mock_ydl_init(opts):
            nonlocal captured_opts
            captured_opts = opts
            mock_inst = MagicMock()
            mock_inst.download.return_value = 0
            return mock_inst

        with patch.object(engine, "get_media_info", return_value={"id": "123", "title": "Song", "formats": [{"format_id": "251"}]}):
            with patch.object(yt_dlp, "YoutubeDL", side_effect=mock_ydl_init):
                engine.download(
                    "https://example.com/song",
                    audio_only=True,
                    audio_format="flac",
                    show_progress=False,
                )

        self.assertIn("postprocessors", captured_opts)
        pps = captured_opts["postprocessors"]
        self.assertEqual(len(pps), 1)
        self.assertEqual(pps[0]["key"], "FFmpegExtractAudio")
        self.assertEqual(pps[0]["preferredcodec"], "flac")
        self.assertNotIn("preferredquality", pps[0])

    def test_engine_320k_mp3_postprocessor(self):
        from unittest.mock import patch, MagicMock
        import yt_dlp

        engine = DownloadEngine()
        captured_opts = {}

        def mock_ydl_init(opts):
            nonlocal captured_opts
            captured_opts = opts
            mock_inst = MagicMock()
            mock_inst.download.return_value = 0
            return mock_inst

        with patch.object(engine, "get_media_info", return_value={"id": "123", "title": "Song", "formats": [{"format_id": "140"}]}):
            with patch.object(yt_dlp, "YoutubeDL", side_effect=mock_ydl_init):
                engine.download(
                    "https://example.com/song",
                    audio_only=True,
                    audio_format="mp3",
                    audio_quality="320",
                    show_progress=False,
                )

        self.assertIn("postprocessors", captured_opts)
        pps = captured_opts["postprocessors"]
        self.assertEqual(len(pps), 1)
        self.assertEqual(pps[0]["key"], "FFmpegExtractAudio")
        self.assertEqual(pps[0]["preferredcodec"], "mp3")
        self.assertEqual(pps[0]["preferredquality"], "320")
        self.assertIn("downloads", captured_opts.get("outtmpl", ""))

    def test_engine_playlist_options(self):
        from unittest.mock import patch, MagicMock
        import yt_dlp

        engine = DownloadEngine()
        captured_opts = {}

        def mock_ydl_init(opts):
            nonlocal captured_opts
            captured_opts = opts
            mock_inst = MagicMock()
            mock_inst.download.return_value = 0
            return mock_inst

        with patch.object(engine, "get_media_info", return_value={"is_playlist": True, "title": "My Hits", "entries": []}):
            with patch.object(yt_dlp, "YoutubeDL", side_effect=mock_ydl_init):
                engine.download(
                    "https://example.com/playlist",
                    playlist=True,
                    playlist_items="1-5",
                    show_progress=False,
                )

        self.assertFalse(captured_opts.get("noplaylist"))
        self.assertEqual(captured_opts.get("playlist_items"), "1-5")
        self.assertIn("playlist", captured_opts.get("outtmpl", ""))

    def test_display_media_info_playlist(self):
        from rich.console import Console
        from simple_downloader.info import display_media_info
        import io

        test_console = Console(file=io.StringIO())
        playlist_info = {
            "is_playlist": True,
            "title": "Top Hits 2026",
            "uploader": "Music Channel",
            "playlist_count": 25,
            "entries": [{"title": "Track 1"}, {"title": "Track 25"}],
        }
        # Verify it executes without raising exception
        display_media_info(playlist_info, test_console)


class TestSpotifyDownloader(unittest.TestCase):
    """Test Spotify URL detection, metadata extraction, search matching, and transcoding."""

    def test_is_spotify_url_and_parsing(self):
        from simple_downloader.spotify import is_spotify_url, parse_spotify_url

        self.assertTrue(is_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"))
        self.assertTrue(is_spotify_url("https://open.spotify.com/intl-es/track/4cOdK2wGLETKBW3PvgPWqT?si=123"))
        self.assertTrue(is_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"))
        self.assertTrue(is_spotify_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"))
        self.assertTrue(is_spotify_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT"))
        self.assertTrue(is_spotify_url("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"))
        self.assertFalse(is_spotify_url("https://www.youtube.com/watch?v=12345"))
        self.assertFalse(is_spotify_url("https://example.com/audio.mp3"))

        self.assertEqual(parse_spotify_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"), ("track", "4cOdK2wGLETKBW3PvgPWqT"))
        self.assertEqual(parse_spotify_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"), ("playlist", "37i9dQZF1DXcBWIGoYBM5M"))
        self.assertEqual(parse_spotify_url("https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"), ("album", "1DFixLWuPkv3KT3TnV35m3"))

    def test_spotify_track_get_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.spotify import SpotifyDownloader

        mock_html = '''
        <html><head>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "state": {
                        "data": {
                            "entity": {
                                "type": "track",
                                "name": "Never Gonna Give You Up",
                                "title": "Never Gonna Give You Up",
                                "artists": [{"name": "Rick Astley"}],
                                "duration": 213573,
                                "releaseDate": {"isoString": "1987-11-12T00:00:00Z"},
                                "visualIdentity": {
                                    "image": [{"url": "https://example.com/cover640.jpg", "maxHeight": 640, "maxWidth": 640}]
                                }
                            }
                        }
                    }
                }
            }
        }
        </script></head><body></body></html>
        '''
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html

        sd = SpotifyDownloader()
        with patch("requests.get", return_value=mock_resp):
            info = sd.get_info("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_spotify"])
        self.assertFalse(info["is_playlist"])
        self.assertEqual(info["track_title"], "Never Gonna Give You Up")
        self.assertEqual(info["artist"], "Rick Astley")
        self.assertEqual(info["duration"], 213)
        self.assertEqual(info["upload_date"], "1987-11-12")
        self.assertEqual(info["thumbnail"], "https://example.com/cover640.jpg")

    def test_spotify_playlist_get_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.spotify import SpotifyDownloader

        mock_html = '''
        <html><head>
        <script id="__NEXT_DATA__" type="application/json">
        {
            "props": {
                "pageProps": {
                    "state": {
                        "data": {
                            "entity": {
                                "type": "playlist",
                                "title": "Top Hits 2026",
                                "subtitle": "Spotify Curator",
                                "trackList": [
                                    {"title": "Track One", "subtitle": "Artist A", "duration": 180000, "uri": "spotify:track:111"},
                                    {"title": "Track Two", "subtitle": "Artist B", "duration": 200000, "uri": "spotify:track:222"}
                                ],
                                "visualIdentity": {
                                    "image": [{"url": "https://example.com/pl_cover.jpg", "maxHeight": 300}]
                                }
                            }
                        }
                    }
                }
            }
        }
        </script></head><body></body></html>
        '''
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = mock_html

        sd = SpotifyDownloader()
        with patch("requests.get", return_value=mock_resp):
            info = sd.get_info("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_spotify"])
        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["title"], "Top Hits 2026")
        self.assertEqual(info["uploader"], "Spotify Curator")
        self.assertEqual(info["playlist_count"], 2)
        self.assertEqual(len(info["entries"]), 2)
        self.assertEqual(info["entries"][0]["track_title"], "Track One")
        self.assertEqual(info["entries"][0]["artist"], "Artist A")

    def test_spotify_search_best_audio_match(self):
        from unittest.mock import patch, MagicMock
        from simple_downloader.spotify import SpotifyDownloader
        import yt_dlp

        sd = SpotifyDownloader()
        mock_entries = [
            {"id": "wrong1", "title": "Artist - Song Live at Stadium", "duration": 280, "uploader": "FanChannel"},
            {"id": "correct_match", "title": "Artist - Song (Official Audio)", "duration": 215, "uploader": "Artist - Topic"},
            {"id": "wrong2", "title": "Artist - Song (Acoustic Cover)", "duration": 215, "uploader": "Cover Singer"},
        ]

        def mock_extract(query, download=False):
            return {"entries": mock_entries}

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = mock_extract

        with patch.object(yt_dlp, "YoutubeDL", return_value=mock_ydl):
            best = sd.search_best_audio_match("Artist", "Song", expected_duration=214)

        self.assertIsNotNone(best)
        self.assertEqual(best["id"], "correct_match")

    def test_spotify_engine_routing(self):
        from unittest.mock import patch
        from simple_downloader.engine import DownloadEngine

        engine = DownloadEngine()
        with patch("simple_downloader.engine.SpotifyDownloader") as mock_sd_cls:
            mock_sd_inst = mock_sd_cls.return_value
            mock_sd_inst.get_info.return_value = {
                "id": "123", "title": "Artist - Song", "is_spotify": True, "is_playlist": False,
            }
            mock_sd_inst.download_track.return_value = "/downloads/Song.flac"

            res = engine.download(
                "https://open.spotify.com/track/123",
                audio_format="flac",
                show_progress=False,
            )
            self.assertEqual(res, "/downloads/Song.flac")
            mock_sd_inst.download_track.assert_called_once()

    def test_spotify_download_track_calls_ffmpeg_flac(self):
        from unittest.mock import patch, MagicMock
        from simple_downloader.spotify import SpotifyDownloader
        import tempfile
        import glob

        sd = SpotifyDownloader()
        track_info = {
            "id": "123",
            "title": "Artist - Hit Song",
            "track_title": "Hit Song",
            "artist": "Artist",
            "album": "Hit Album",
            "duration": 210,
            "thumbnail": None,
            "upload_date": "2026-01-01",
        }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(sd, "search_best_audio_match", return_value={"id": "match123"}):
                with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
                    def mock_download(urls):
                        temps = glob.glob(tempfile.gettempdir() + "/vdown_spotify_*")
                        if temps:
                            with open(os.path.join(temps[-1], "audio.webm"), "wb") as f:
                                f.write(b"dummy audio")
                        return 0

                    mock_inst = MagicMock()
                    mock_inst.__enter__.return_value = mock_inst
                    mock_inst.download.side_effect = mock_download
                    mock_ydl_cls.return_value = mock_inst

                    captured_cmd = []
                    def mock_subp_run(cmd, *args, **kwargs):
                        nonlocal captured_cmd
                        captured_cmd = cmd
                        target_file = cmd[-1]
                        with open(target_file, "wb") as f:
                            f.write(b"dummy flac")
                        m = MagicMock()
                        m.returncode = 0
                        return m

                    with patch("subprocess.run", side_effect=mock_subp_run):
                        res = sd.download_track(
                            info=track_info,
                            output_dir=td,
                            audio_format="flac",
                            show_progress=False,
                        )

            self.assertTrue(os.path.exists(res))
            self.assertTrue(res.endswith(".flac"))
            self.assertIn("flac", captured_cmd)
            self.assertIn("-metadata", captured_cmd)
            self.assertIn("title=Hit Song", captured_cmd)
            self.assertIn("artist=Artist", captured_cmd)

    def test_spotify_download_playlist_selection(self):
        from unittest.mock import patch
        from simple_downloader.spotify import SpotifyDownloader
        import tempfile

        sd = SpotifyDownloader()
        pl_info = {
            "id": "pl1",
            "title": "Summer Vibes",
            "entries": [
                {"title": "Track 1", "track_title": "Track 1", "artist": "A1"},
                {"title": "Track 2", "track_title": "Track 2", "artist": "A2"},
                {"title": "Track 3", "track_title": "Track 3", "artist": "A3"},
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            with patch.object(sd, "download_track", return_value="dummy_path") as mock_dt:
                res = sd.download_playlist(
                    info=pl_info,
                    output_dir=td,
                    playlist_items="2-3",
                    show_progress=False,
                )
                self.assertEqual(mock_dt.call_count, 2)


if __name__ == "__main__":
    unittest.main()
