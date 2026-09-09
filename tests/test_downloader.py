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

    def test_embed_wav_cover_art_utility(self):
        from simple_downloader.utils import embed_wav_cover_art
        import subprocess
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as td:
            wav_file = os.path.join(td, "test.wav")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", wav_file], capture_output=True, check=True)
            cover_jpg = os.path.join(td, "cover.jpg")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=100x100", "-vframes", "1", cover_jpg], capture_output=True, check=True)

            success = embed_wav_cover_art(wav_file, cover_jpg)
            self.assertTrue(success)

            probe = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", wav_file], capture_output=True, text=True)
            data = json.loads(probe.stdout)
            self.assertEqual(len(data.get("streams", [])), 2)
            stream_codecs = [s.get("codec_name") for s in data.get("streams", [])]
            self.assertIn("pcm_s16le", stream_codecs)
            self.assertIn("mjpeg", stream_codecs)
            attached_pics = [s.get("disposition", {}).get("attached_pic") for s in data.get("streams", [])]
            self.assertIn(1, attached_pics)

    def test_build_vorbis_picture_block_utility(self):
        from simple_downloader.utils import build_vorbis_picture_block
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            cover_jpg = os.path.join(td, "cover.jpg")
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=green:s=200x200", "-vframes", "1", cover_jpg], capture_output=True, check=True)

            b64_pic = build_vorbis_picture_block(cover_jpg)
            self.assertIsNotNone(b64_pic)
            self.assertTrue(isinstance(b64_pic, str))
            self.assertGreater(len(b64_pic), 50)


class TestTidalDownloader(unittest.TestCase):
    """Unit tests for TIDAL lossless track, album, and playlist downloader."""

    def test_is_tidal_url_and_parsing(self):
        from simple_downloader.tidal import is_tidal_url, parse_tidal_url

        self.assertTrue(is_tidal_url("https://tidal.com/track/12345678"))
        self.assertTrue(is_tidal_url("https://listen.tidal.com/track/12345678"))
        self.assertTrue(is_tidal_url("https://tidal.com/browse/track/12345678"))
        self.assertTrue(is_tidal_url("https://tidal.com/album/87654321"))
        self.assertTrue(is_tidal_url("https://listen.tidal.com/album/87654321"))
        self.assertTrue(is_tidal_url("https://tidal.com/playlist/5ac41fbb-927b-427e-8224-87bf12d218a3"))
        self.assertTrue(is_tidal_url("https://listen.tidal.com/playlist/5ac41fbb-927b-427e-8224-87bf12d218a3"))
        self.assertFalse(is_tidal_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"))
        self.assertFalse(is_tidal_url("https://youtube.com/watch?v=12345"))
        self.assertFalse(is_tidal_url(None))
        self.assertFalse(is_tidal_url(""))

        self.assertEqual(parse_tidal_url("https://tidal.com/track/12345678"), ("track", "12345678"))
        self.assertEqual(parse_tidal_url("https://listen.tidal.com/album/87654321"), ("album", "87654321"))
        self.assertEqual(
            parse_tidal_url("https://tidal.com/playlist/5ac41fbb-927b-427e-8224-87bf12d218a3"),
            ("playlist", "5ac41fbb-927b-427e-8224-87bf12d218a3")
        )

    def test_build_tidal_cover_url(self):
        from simple_downloader.tidal import build_tidal_cover_url

        self.assertIsNone(build_tidal_cover_url(None))
        self.assertEqual(
            build_tidal_cover_url("5ac41fbb-927b-427e-8224-87bf12d218a3"),
            "https://resources.tidal.com/images/5ac41fbb/927b/427e/8224/87bf12d218a3/1280x1280.jpg"
        )
        self.assertEqual(
            build_tidal_cover_url("5ac41fbb-927b-427e-8224-87bf12d218a3", size="640x640"),
            "https://resources.tidal.com/images/5ac41fbb/927b/427e/8224/87bf12d218a3/640x640.jpg"
        )

    def test_tidal_track_info_mock_api(self):
        from unittest.mock import patch, Mock
        from simple_downloader.tidal import TidalDownloader

        td = TidalDownloader()
        mock_api_data = {
            "id": 12345,
            "title": "Masterpiece",
            "artists": [{"name": "Audiophile Artist"}],
            "album": {
                "title": "Audiophile Album",
                "cover": "11111111-2222-3333-4444-555555555555"
            },
            "duration": 240,
            "audioQuality": "HI_RES_LOSSLESS",
            "trackNumber": 3,
        }
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_api_data

        with patch("requests.get", return_value=mock_resp):
            info = td.get_info("https://tidal.com/track/12345")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_tidal"])
        self.assertFalse(info["is_playlist"])
        self.assertEqual(info["title"], "Audiophile Artist - Masterpiece")
        self.assertEqual(info["track_title"], "Masterpiece")
        self.assertEqual(info["artist"], "Audiophile Artist")
        self.assertEqual(info["album"], "Audiophile Album")
        self.assertEqual(info["duration"], 240)
        self.assertEqual(info["audio_quality"], "HI_RES_LOSSLESS")
        self.assertEqual(info["track_number"], 3)
        self.assertIn("11111111/2222/3333/4444/555555555555", info["thumbnail"])

    def test_tidal_track_info_html_fallback(self):
        from unittest.mock import patch, Mock
        from simple_downloader.tidal import TidalDownloader

        td = TidalDownloader()
        mock_html = '''
        <html><head>
        <script type="application/ld+json">
        {
            "@type": "MusicRecording",
            "name": "Fallback Song",
            "byArtist": {"name": "Fallback Artist"},
            "inAlbum": {"name": "Fallback Album"},
            "image": "https://resources.tidal.com/images/cover.jpg",
            "duration": "PT3M30S"
        }
        </script></head><body></body></html>
        '''
        fail_resp = Mock()
        fail_resp.status_code = 404
        html_resp = Mock()
        html_resp.status_code = 200
        html_resp.text = mock_html

        with patch("requests.get", side_effect=[fail_resp, html_resp]):
            info = td.get_info("https://tidal.com/track/99999")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_tidal"])
        self.assertEqual(info["track_title"], "Fallback Song")
        self.assertEqual(info["artist"], "Fallback Artist")
        self.assertEqual(info["album"], "Fallback Album")
        self.assertEqual(info["duration"], 210)

    def test_tidal_album_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.tidal import TidalDownloader

        td = TidalDownloader()
        album_meta = {
            "title": "Greatest Hits",
            "artist": {"name": "Legend"},
            "cover": "aaaa-bbbb-cccc",
            "releaseDate": "2025-05-01",
        }
        album_tracks = {
            "items": [
                {"id": 1, "title": "Track One", "artists": [{"name": "Legend"}], "duration": 180, "trackNumber": 1},
                {"id": 2, "title": "Track Two", "artists": [{"name": "Legend"}], "duration": 200, "trackNumber": 2},
            ]
        }
        resp1 = Mock(status_code=200)
        resp1.json.return_value = album_meta
        resp2 = Mock(status_code=200)
        resp2.json.return_value = album_tracks

        with patch("requests.get", side_effect=[resp1, resp2]):
            info = td.get_info("https://tidal.com/album/1010")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_tidal"])
        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["tidal_type"], "album")
        self.assertEqual(info["album_title"], "Greatest Hits")
        self.assertEqual(info["playlist_count"], 2)
        self.assertEqual(len(info["entries"]), 2)
        self.assertEqual(info["entries"][0]["track_title"], "Track One")

    def test_tidal_playlist_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.tidal import TidalDownloader

        td = TidalDownloader()
        pl_meta = {
            "title": "Hi-Fi Chill",
            "image": "pppp-qqqq-rrrr",
        }
        pl_tracks = {
            "items": [
                {"id": 10, "title": "Chill 1", "artists": [{"name": "Artist 1"}], "album": {"title": "Alb 1"}, "duration": 190},
                {"id": 20, "title": "Chill 2", "artists": [{"name": "Artist 2"}], "album": {"title": "Alb 2"}, "duration": 210},
            ]
        }
        resp1 = Mock(status_code=200)
        resp1.json.return_value = pl_meta
        resp2 = Mock(status_code=200)
        resp2.json.return_value = pl_tracks

        with patch("requests.get", side_effect=[resp1, resp2]):
            info = td.get_info("https://tidal.com/playlist/5ac41fbb-927b-427e-8224-87bf12d218a3")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_tidal"])
        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["tidal_type"], "playlist")
        self.assertEqual(info["title"], "Hi-Fi Chill")
        self.assertEqual(info["playlist_count"], 2)

    def test_tidal_resolve_audio_stream_proximity(self):
        from unittest.mock import patch, MagicMock
        from simple_downloader.tidal import TidalDownloader
        import yt_dlp

        td = TidalDownloader()
        mock_candidates = [
            {"id": "video_intro_version", "title": "Artist - Song (10min Movie)", "duration": 600},
            {"id": "exact_album_version", "title": "Artist - Song (Official Audio)", "duration": 210},
            {"id": "short_snippet", "title": "Artist - Song Teaser", "duration": 30},
        ]
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {"entries": mock_candidates}

        with patch.object(yt_dlp, "YoutubeDL", return_value=mock_ydl):
            resolved = td.resolve_audio_stream("Artist", "Song", expected_duration=212)

        self.assertEqual(resolved, "https://www.youtube.com/watch?v=exact_album_version")

    def test_tidal_engine_routing(self):
        from unittest.mock import patch
        from simple_downloader.engine import DownloadEngine

        engine = DownloadEngine()
        with patch("simple_downloader.engine.TidalDownloader") as mock_td_cls:
            mock_td_inst = mock_td_cls.return_value
            mock_td_inst.get_info.return_value = {
                "id": "123", "title": "Artist - Song", "is_tidal": True, "is_playlist": False,
            }
            mock_td_inst.download_track.return_value = "/downloads/Song.flac"

            info = engine.get_media_info("https://tidal.com/track/123")
            self.assertTrue(info.get("is_tidal"))

            res = engine.download(
                "https://tidal.com/track/123",
                audio_format="flac",
                show_progress=False,
            )
            self.assertEqual(res, "/downloads/Song.flac")
            mock_td_inst.download_track.assert_called_once()

    def test_tidal_download_track_calls_ffmpeg_flac(self):
        from unittest.mock import patch, MagicMock
        from simple_downloader.tidal import TidalDownloader
        import tempfile
        import glob

        td = TidalDownloader()
        track_info = {
            "id": "12345",
            "title": "Artist - Hi-Fi Master",
            "track_title": "Hi-Fi Master",
            "artist": "Artist",
            "album": "Master Album",
            "duration": 210,
            "thumbnail": None,
            "audio_quality": "HI_RES_LOSSLESS",
            "track_number": 1,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(td, "resolve_audio_stream", return_value="https://youtube.com/watch?v=test1234"):
                with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
                    def mock_download(urls):
                        temps = glob.glob(tempfile.gettempdir() + "/vdown_tidal_*")
                        if temps:
                            with open(os.path.join(temps[-1], "stream.webm"), "wb") as f:
                                f.write(b"dummy tidal audio")
                        return 0

                    mock_inst = MagicMock()
                    mock_inst.__enter__.return_value = mock_inst
                    mock_inst.download.side_effect = mock_download
                    mock_ydl_cls.return_value = mock_inst

                    captured_cmd = []
                    def mock_run(cmd, *args, **kwargs):
                        captured_cmd.extend(cmd)
                        # Touch target output file
                        out = cmd[-1]
                        with open(out, "wb") as f:
                            f.write(b"flac data")
                        res = MagicMock()
                        res.returncode = 0
                        return res

                    with patch("subprocess.run", side_effect=mock_run):
                        res = td.download_track(
                            track_info=track_info,
                            output_dir=temp_dir,
                            audio_format="flac",
                        )

            self.assertTrue(os.path.exists(res))
            self.assertTrue(res.endswith(".flac"))
            self.assertIn("flac", captured_cmd)
            self.assertIn("-metadata", captured_cmd)
            self.assertIn("title=Hi-Fi Master", captured_cmd)
            self.assertIn("artist=Artist", captured_cmd)

    def test_tidal_download_collection_selection(self):
        from unittest.mock import patch
        from simple_downloader.tidal import TidalDownloader
        import tempfile
        from pathlib import Path

        td = TidalDownloader()
        col_info = {
            "id": "col1",
            "title": "Audiophile Master Collection",
            "album_title": "Audiophile Master Collection",
            "tidal_type": "album",
            "entries": [
                {"title": "Track 1", "track_title": "Track 1", "artist": "A1"},
                {"title": "Track 2", "track_title": "Track 2", "artist": "A2"},
                {"title": "Track 3", "track_title": "Track 3", "artist": "A3"},
            ]
        }

        with tempfile.TemporaryDirectory() as td_dir:
            with patch.object(td, "download_track", return_value="fake.flac") as mock_dt:
                folder = td.download_collection(
                    info=col_info,
                    base_dest=Path(td_dir),
                    playlist_items="2-3",
                    audio_format="flac",
                )
                self.assertEqual(mock_dt.call_count, 2)
                self.assertTrue(Path(folder).exists())

    def test_cli_tidal_routing(self):
        from unittest.mock import patch
        from simple_downloader.cli import main

        with patch("sys.argv", ["vdown", "https://tidal.com/track/12345", "--audio-format", "flac"]), \
             patch("simple_downloader.cli.do_download") as mock_dd, \
             patch("simple_downloader.cli.DownloadEngine"):
            main()
            mock_dd.assert_called_once()
            call_kwargs = mock_dd.call_args[1]
            self.assertTrue(call_kwargs["audio_only"])
            self.assertEqual(call_kwargs["audio_format"], "flac")


class TestAppleMusicDownloader(unittest.TestCase):
    """Unit tests for Apple Music lossless track, album, and playlist downloader."""

    def test_is_apple_music_url_and_parsing(self):
        from simple_downloader.applemusic import is_apple_music_url, parse_apple_music_url

        self.assertTrue(is_apple_music_url("https://music.apple.com/us/album/better-together/1440857781?i=1440857786"))
        self.assertTrue(is_apple_music_url("https://music.apple.com/us/album/in-between-dreams/1440857781"))
        self.assertTrue(is_apple_music_url("https://music.apple.com/us/song/better-together/1440857786"))
        self.assertTrue(is_apple_music_url("https://music.apple.com/song/1440857786"))
        self.assertTrue(is_apple_music_url("https://music.apple.com/album/1440857781"))
        self.assertTrue(is_apple_music_url("https://music.apple.com/us/playlist/apple-music-list/pl.41fda5adbf9b4db4ba1a2c0a76099ef9"))
        self.assertTrue(is_apple_music_url("https://embed.music.apple.com/us/playlist/august-2026/pl.u-W3mVfPPj76"))
        self.assertFalse(is_apple_music_url("https://open.spotify.com/track/12345"))
        self.assertFalse(is_apple_music_url("https://tidal.com/track/12345"))
        self.assertFalse(is_apple_music_url(None))
        self.assertFalse(is_apple_music_url(""))

        self.assertEqual(
            parse_apple_music_url("https://music.apple.com/us/album/better-together/1440857781?i=1440857786"),
            ("song", "1440857786")
        )
        self.assertEqual(
            parse_apple_music_url("https://music.apple.com/us/album/in-between-dreams/1440857781"),
            ("album", "1440857781")
        )
        self.assertEqual(
            parse_apple_music_url("https://music.apple.com/us/playlist/apple-music-list/pl.41fda5adbf9b4db4ba1a2c0a76099ef9"),
            ("playlist", "pl.41fda5adbf9b4db4ba1a2c0a76099ef9")
        )

    def test_build_apple_artwork_url(self):
        from simple_downloader.applemusic import build_apple_artwork_url

        self.assertIsNone(build_apple_artwork_url(None))
        raw_art = "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/44/06/fd/cover.rgb.jpg/100x100bb.jpg"
        scaled = build_apple_artwork_url(raw_art, size=1400)
        self.assertEqual(scaled, "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/44/06/fd/cover.rgb.jpg/1400x1400bb.jpg")

    def test_apple_music_song_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.applemusic import AppleMusicDownloader

        am = AppleMusicDownloader()
        mock_api_data = {
            "resultCount": 1,
            "results": [
                {
                    "wrapperType": "track",
                    "trackId": 1440857786,
                    "trackName": "Better Together",
                    "artistName": "Jack Johnson",
                    "collectionName": "In Between Dreams",
                    "trackTimeMillis": 207679,
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/image/cover/100x100bb.jpg",
                    "trackNumber": 1,
                    "releaseDate": "2005-03-01T08:00:00Z",
                }
            ]
        }
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = mock_api_data

        with patch("requests.get", return_value=mock_resp):
            info = am.get_info("https://music.apple.com/us/song/better-together/1440857786")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_apple_music"])
        self.assertFalse(info["is_playlist"])
        self.assertEqual(info["track_title"], "Better Together")
        self.assertEqual(info["artist"], "Jack Johnson")
        self.assertEqual(info["album"], "In Between Dreams")
        self.assertEqual(info["duration"], 207)
        self.assertEqual(info["track_number"], 1)
        self.assertIn("1400x1400bb.jpg", info["thumbnail"])

    def test_apple_music_album_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.applemusic import AppleMusicDownloader

        am = AppleMusicDownloader()
        mock_album_data = {
            "resultCount": 3,
            "results": [
                {
                    "wrapperType": "collection",
                    "collectionId": 1440857781,
                    "collectionName": "In Between Dreams",
                    "artistName": "Jack Johnson",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/image/cover/100x100bb.jpg",
                    "releaseDate": "2005-03-01T08:00:00Z",
                },
                {
                    "wrapperType": "track",
                    "trackId": 1440857786,
                    "trackName": "Better Together",
                    "artistName": "Jack Johnson",
                    "trackTimeMillis": 207000,
                    "trackNumber": 1,
                },
                {
                    "wrapperType": "track",
                    "trackId": 1440857794,
                    "trackName": "Never Know",
                    "artistName": "Jack Johnson",
                    "trackTimeMillis": 212000,
                    "trackNumber": 2,
                }
            ]
        }
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = mock_album_data

        with patch("requests.get", return_value=mock_resp):
            info = am.get_info("https://music.apple.com/us/album/in-between-dreams/1440857781")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_apple_music"])
        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["apple_music_type"], "album")
        self.assertEqual(info["album_title"], "In Between Dreams")
        self.assertEqual(info["playlist_count"], 2)
        self.assertEqual(len(info["entries"]), 2)
        self.assertEqual(info["entries"][0]["track_title"], "Better Together")

    def test_apple_music_playlist_info_mock(self):
        from unittest.mock import patch, Mock
        from simple_downloader.applemusic import AppleMusicDownloader

        am = AppleMusicDownloader()
        mock_html = '''
        <html><head>
        <meta property="og:title" content="Top Hits on Apple Music" />
        <meta property="og:image" content="https://is1-ssl.mzstatic.com/image/pl_cover/100x100bb.jpg" />
        <meta property="music:song" content="https://music.apple.com/us/song/song-one/11111" />
        <meta property="music:song" content="https://music.apple.com/us/song/song-two/22222" />
        </head><body></body></html>
        '''
        mock_batch_data = {
            "resultCount": 2,
            "results": [
                {
                    "trackId": 11111,
                    "trackName": "Song One",
                    "artistName": "Artist A",
                    "collectionName": "Album A",
                    "trackTimeMillis": 180000,
                },
                {
                    "trackId": 22222,
                    "trackName": "Song Two",
                    "artistName": "Artist B",
                    "collectionName": "Album B",
                    "trackTimeMillis": 200000,
                }
            ]
        }

        resp_html = Mock(status_code=200, text=mock_html)
        resp_batch = Mock(status_code=200)
        resp_batch.json.return_value = mock_batch_data

        with patch("requests.get", side_effect=[resp_html, resp_batch]):
            info = am.get_info("https://music.apple.com/us/playlist/top-hits/pl.12345")

        self.assertIsNotNone(info)
        self.assertTrue(info["is_apple_music"])
        self.assertTrue(info["is_playlist"])
        self.assertEqual(info["title"], "Top Hits")
        self.assertEqual(info["playlist_count"], 2)
        self.assertEqual(info["entries"][0]["track_title"], "Song One")

    def test_apple_music_resolve_audio_stream_proximity(self):
        from unittest.mock import patch, MagicMock
        from simple_downloader.applemusic import AppleMusicDownloader
        import yt_dlp

        am = AppleMusicDownloader()
        mock_candidates = [
            {"id": "long_music_video", "title": "Jack Johnson - Better Together (Official Video)", "duration": 350},
            {"id": "studio_audio_track", "title": "Jack Johnson - Better Together (Audio)", "duration": 208},
            {"id": "short_clip", "title": "Better Together Preview", "duration": 25},
        ]
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {"entries": mock_candidates}

        with patch.object(yt_dlp, "YoutubeDL", return_value=mock_ydl):
            resolved = am.resolve_audio_stream("Jack Johnson", "Better Together", expected_duration=207)

        self.assertEqual(resolved, "https://www.youtube.com/watch?v=studio_audio_track")

    def test_apple_music_engine_routing(self):
        from unittest.mock import patch
        from simple_downloader.engine import DownloadEngine

        engine = DownloadEngine()
        with patch("simple_downloader.engine.AppleMusicDownloader") as mock_am_cls:
            mock_am_inst = mock_am_cls.return_value
            mock_am_inst.get_info.return_value = {
                "id": "1440857786", "title": "Jack Johnson - Better Together", "is_apple_music": True, "is_playlist": False,
            }
            mock_am_inst.download_track.return_value = "/downloads/Better_Together.flac"

            info = engine.get_media_info("https://music.apple.com/us/song/better-together/1440857786")
            self.assertTrue(info.get("is_apple_music"))

            res = engine.download(
                "https://music.apple.com/us/song/better-together/1440857786",
                audio_format="flac",
                show_progress=False,
            )
            self.assertEqual(res, "/downloads/Better_Together.flac")
            mock_am_inst.download_track.assert_called_once()

    def test_cli_apple_music_routing(self):
        from unittest.mock import patch
        from simple_downloader.cli import main

        with patch("sys.argv", ["vdown", "https://music.apple.com/us/song/better-together/1440857786", "--audio-format", "flac"]), \
             patch("simple_downloader.cli.do_download") as mock_dd, \
             patch("simple_downloader.cli.DownloadEngine"):
            main()
            mock_dd.assert_called_once()
            call_kwargs = mock_dd.call_args[1]
            self.assertTrue(call_kwargs["audio_only"])
            self.assertEqual(call_kwargs["audio_format"], "flac")


class TestTurboAndTorrentDownloader(unittest.TestCase):
    """Unit tests for IDM-style Turbo multi-connection and BitTorrent modules."""

    def test_turbo_chunk_calculation(self):
        from simple_downloader.turbo import TurboDownloader

        # 100 bytes across 4 connections
        chunks = TurboDownloader.calculate_chunks(100, 4)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0], (0, 24))
        self.assertEqual(chunks[1], (25, 49))
        self.assertEqual(chunks[2], (50, 74))
        self.assertEqual(chunks[3], (75, 99))

        # 1 connection
        single_chunk = TurboDownloader.calculate_chunks(100, 1)
        self.assertEqual(single_chunk, [(0, 99)])

    def test_turbo_download_mock_server(self):
        from simple_downloader.turbo import TurboDownloader
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading
        import tempfile
        import hashlib

        # Create 1 MB of test data
        test_payload = (b"0123456789abcdef" * 65536)  # 1,048,576 bytes
        expected_md5 = hashlib.md5(test_payload).hexdigest()

        class RangeHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_HEAD(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(test_payload)))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            def do_GET(self):
                range_header = self.headers.get("Range")
                if range_header and range_header.startswith("bytes="):
                    rng = range_header.replace("bytes=", "").split("-")
                    start = int(rng[0])
                    end = int(rng[1]) if rng[1] else len(test_payload) - 1
                    end = min(end, len(test_payload) - 1)
                    body = test_payload[start : end + 1]

                    self.send_response(206)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(test_payload)}")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(test_payload)))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(test_payload)

        server = HTTPServer(("127.0.0.1", 0), RangeHandler)
        port = server.server_port
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            with tempfile.TemporaryDirectory() as td:
                out_file = os.path.join(td, "downloaded.bin")
                turbo = TurboDownloader(connections=4)
                res = turbo.download(
                    f"http://127.0.0.1:{port}/test.bin",
                    output_path=out_file,
                    connections=4,
                    show_progress=False,
                )
                self.assertTrue(os.path.exists(res))
                with open(res, "rb") as f:
                    downloaded_bytes = f.read()
                self.assertEqual(len(downloaded_bytes), len(test_payload))
                self.assertEqual(hashlib.md5(downloaded_bytes).hexdigest(), expected_md5)
        finally:
            server.shutdown()
            server.server_close()

    def test_is_torrent_or_magnet(self):
        from simple_downloader.torrent import is_torrent_or_magnet

        self.assertTrue(is_torrent_or_magnet("magnet:?xt=urn:btih:3b5f903820fae4123"))
        self.assertTrue(is_torrent_or_magnet("https://example.com/archlinux.torrent"))
        self.assertTrue(is_torrent_or_magnet("debian-12.torrent"))
        self.assertFalse(is_torrent_or_magnet("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(is_torrent_or_magnet("https://open.spotify.com/track/123"))

    def test_parse_magnet_link(self):
        from simple_downloader.torrent import parse_magnet_link

        mag = "magnet:?xt=urn:btih:3b5f903820fae4123&dn=Ubuntu-24.04-Desktop.iso&tr=http%3A%2F%2Ftracker.example.com%2Fannounce"
        parsed = parse_magnet_link(mag)
        self.assertEqual(parsed["name"], "Ubuntu-24.04-Desktop.iso")
        self.assertEqual(parsed["info_hash"], "3b5f903820fae4123")
        self.assertEqual(len(parsed["trackers"]), 1)

    def test_bencode_decoder(self):
        from simple_downloader.torrent import decode_bencode

        # Integer
        val, end = decode_bencode(b"i42e")
        self.assertEqual(val, 42)

        # String
        val, end = decode_bencode(b"4:spam")
        self.assertEqual(val, b"spam")

        # List
        val, end = decode_bencode(b"l4:spami42ee")
        self.assertEqual(val, [b"spam", 42])

        # Dictionary
        val, end = decode_bencode(b"d3:cow3:moo4:spami10ee")
        self.assertEqual(val, {"cow": b"moo", "spam": 10})

    def test_cli_turbo_and_torrent_args(self):
        from simple_downloader.cli import create_parser

        parser = create_parser()
        args = parser.parse_args(["https://example.com/file.zip", "--turbo", "-c", "8"])
        self.assertTrue(args.turbo)
        self.assertEqual(args.connections, 8)

        args_torrent = parser.parse_args(["magnet:?xt=urn:btih:123", "--torrent"])
        self.assertTrue(args_torrent.torrent)

    def test_welcome_screen_and_diagnostics(self):
        from simple_downloader.cli import display_welcome_screen, ASCII_BANNER
        from unittest.mock import patch

        self.assertGreater(len(ASCII_BANNER), 50)
        self.assertIn("bright_cyan", ASCII_BANNER)

        # Ensure display_welcome_screen runs without crashing
        with patch("rich.console.Console.print"):
            display_welcome_screen()


class TestInstallerModule(unittest.TestCase):
    """Unit tests for automated dependency installer."""

    def test_detect_package_manager(self):
        from simple_downloader.installer import detect_package_manager

        mgr = detect_package_manager()
        # On Arch Linux with pacman, it should detect pacman
        if shutil.which("pacman"):
            self.assertEqual(mgr, "pacman")
        elif shutil.which("apt-get"):
            self.assertEqual(mgr, "apt")

    def test_get_install_command_for_tool(self):
        from simple_downloader.installer import get_install_command_for_tool

        cmd_args, cmd_str, mgr = get_install_command_for_tool("aria2c")
        self.assertIsNotNone(cmd_str)
        if mgr == "pacman":
            self.assertEqual(cmd_args, ["sudo", "pacman", "-S", "--noconfirm", "aria2"])
            self.assertEqual(cmd_str, "sudo pacman -S aria2")

    def test_is_tool_installed(self):
        from simple_downloader.installer import is_tool_installed

        self.assertTrue(is_tool_installed("python3") or is_tool_installed("sh"))
        self.assertFalse(is_tool_installed("non_existent_tool_12345"))

    def test_ensure_tool_installed_when_already_installed(self):
        from simple_downloader.installer import ensure_tool_installed
        from unittest.mock import patch

        with patch("simple_downloader.installer.is_tool_installed", return_value=True):
            self.assertTrue(ensure_tool_installed("aria2c"))

    def test_ensure_tool_installed_prompt_declined(self):
        from simple_downloader.installer import ensure_tool_installed
        from unittest.mock import patch

        with patch("simple_downloader.installer.is_tool_installed", return_value=False), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("rich.prompt.Confirm.ask", return_value=False):
            res = ensure_tool_installed("aria2c")
            self.assertFalse(res)

    def test_ensure_tool_installed_prompt_accepted_success(self):
        from simple_downloader.installer import ensure_tool_installed
        from unittest.mock import patch, MagicMock

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("simple_downloader.installer.is_tool_installed", side_effect=[False, True]), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("rich.prompt.Confirm.ask", return_value=True), \
             patch("subprocess.run", return_value=mock_proc):
            res = ensure_tool_installed("aria2c")
            self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
