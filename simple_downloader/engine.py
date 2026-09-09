"""Core engine orchestrating yt-dlp, webpage scraping, and direct HTTP downloading."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
import yt_dlp
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

from simple_downloader.direct_downloader import DirectDownloader
from simple_downloader.scraper import WebpageVideoScraper
from simple_downloader.tiktok import TikTokDownloader, is_tiktok_url
from simple_downloader.spotify import SpotifyDownloader, is_spotify_url
from simple_downloader.tidal import TidalDownloader, is_tidal_url
from simple_downloader.applemusic import AppleMusicDownloader, is_apple_music_url
from simple_downloader.series import (
    SeriesDownloader,
    is_series_url,
    get_series_extractor,
    parse_episode_selection,
)
from simple_downloader.utils import (
    is_direct_media_url,
    format_bytes,
    format_duration,
    sanitize_filename,
    attach_splash_art,
)

console = Console()


class DownloadEngine:
    """Unified engine for media extraction and downloading across any platform or link."""

    def __init__(self, console_instance: Optional[Console] = None):
        self.console = console_instance or console

    def get_media_info(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract metadata and formats for any given URL.

        Falls back to webpage scraping and direct HTTP probing if yt-dlp does not support the URL.
        """
        # Specialized TikTok handler (watermark-free videos & photo posts)
        if is_tiktok_url(url):
            try:
                tt = TikTokDownloader()
                tt_info = tt.get_info(url)
                if tt_info:
                    return tt_info
            except Exception:
                pass

        # Specialized Spotify handler (tracks, playlists, albums)
        if is_spotify_url(url):
            try:
                sp = SpotifyDownloader(console=self.console)
                sp_info = sp.get_info(url)
                if sp_info:
                    return sp_info
            except Exception:
                pass

        # Specialized TIDAL handler (tracks, albums, playlists)
        if is_tidal_url(url):
            try:
                td = TidalDownloader(console=self.console)
                td_info = td.get_info(url)
                if td_info:
                    return td_info
            except Exception:
                pass

        # Specialized Apple Music handler (songs, albums, playlists)
        if is_apple_music_url(url):
            try:
                am = AppleMusicDownloader(console=self.console)
                am_info = am.get_info(url)
                if am_info:
                    return am_info
            except Exception:
                pass

        # Specialized Series & TV Show handler (Roopa Hala, Netflix, Web Streaming)
        if is_series_url(url):
            try:
                extractor = get_series_extractor(url)
                series_obj = extractor.extract_series(
                    url,
                    browser=browser,
                    cookie_file=cookie_file,
                )
                if series_obj:
                    entries = [
                        {
                            "id": f"s{ep.season_number:02d}e{ep.episode_number:02d}",
                            "title": ep.formatted_title(),
                            "url": ep.url,
                            "thumbnail": ep.thumbnail,
                            "duration": ep.duration,
                            "season_number": ep.season_number,
                            "episode_number": ep.episode_number,
                        }
                        for ep in series_obj.all_episodes
                    ]
                    return {
                        "id": "series",
                        "title": series_obj.title,
                        "url": series_obj.url,
                        "thumbnail": series_obj.poster_url,
                        "is_series": True,
                        "is_playlist": True,
                        "playlist_count": series_obj.total_episodes,
                        "platform_name": series_obj.platform_name,
                        "series_obj": series_obj,
                        "entries": entries,
                        "formats": [],
                    }
            except Exception:
                pass

        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
        }

        if browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if proxy:
            ydl_opts["proxy"] = proxy
        if user_agent or referer:
            headers = {}
            if user_agent:
                headers["User-Agent"] = user_agent
            if referer:
                headers["Referer"] = referer
            ydl_opts["http_headers"] = headers

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    entries = info.get("entries")
                    if entries is not None:
                        if not isinstance(entries, list):
                            entries = list(entries)
                            info["entries"] = entries
                        info["is_playlist"] = True
                        info["playlist_count"] = len(entries)
                    elif info.get("_type") == "playlist":
                        info["is_playlist"] = True
                    else:
                        info["is_playlist"] = False
                    return info
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["login required", "bot", "confirm you're not a bot", "private video", "sign in", "401"]):
                self.console.print("\n[bold yellow]⚠ Authentication or anti-bot verification required.[/bold yellow]")
                self.console.print("[dim]Tip: Pass cookies from your browser, e.g. --browser chromium (or brave, chrome)[/dim]")

        # 2. Try scraping embedded videos from arbitrary webpage
        try:
            scraper = WebpageVideoScraper(headers={"User-Agent": user_agent} if user_agent else None)
            candidates = scraper.find_videos(url)
            if candidates:
                for candidate in candidates:
                    cand_url = candidate["url"]
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            cand_info = ydl.extract_info(cand_url, download=False)
                            if cand_info:
                                cand_info["is_scraped"] = True
                                cand_info["scraped_source"] = candidate["source"]
                                return cand_info
                    except Exception:
                        continue

                # If yt-dlp didn't parse candidate, return first candidate as direct stream
                first_cand = candidates[0]
                return {
                    "id": "embedded_media",
                    "title": f"Embedded Video ({first_cand['source']})",
                    "url": first_cand["url"],
                    "is_direct": True,
                    "is_playlist": False,
                    "formats": [],
                }
        except Exception:
            pass

        # 3. Fallback inspection for direct HTTP/HTTPS media files
        try:
            import requests

            req_headers = {"User-Agent": user_agent or "Mozilla/5.0"}
            if referer:
                req_headers["Referer"] = referer

            head = requests.head(
                url,
                allow_redirects=True,
                timeout=15,
                headers=req_headers,
            )
            size = int(head.headers.get("content-length", 0)) or None
            content_type = head.headers.get("content-type", "application/octet-stream")
            from simple_downloader.utils import get_filename_from_headers_or_url

            filename = get_filename_from_headers_or_url(url, head.headers)

            return {
                "id": "direct_stream",
                "title": filename,
                "url": url,
                "filesize": size,
                "content_type": content_type,
                "is_direct": True,
                "is_playlist": False,
                "formats": [],
            }
        except Exception as e:
            raise RuntimeError(f"Could not extract info from URL: {e}")

    def list_formats(self, info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse formats list into clean, deduplicated video and audio options."""
        formats = info.get("formats") or []
        parsed = []
        for f in formats:
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            is_video = vcodec != "none"
            is_audio = acodec != "none"
            height = f.get("height")
            filesize = f.get("filesize") or f.get("filesize_approx")

            note = f.get("format_note", "")
            ext = f.get("ext", "")
            fid = f.get("format_id", "")
            tbr = f.get("tbr")
            fps = f.get("fps")

            parsed.append(
                {
                    "format_id": fid,
                    "ext": ext,
                    "resolution": f"{f.get('width', '?')}x{height}" if height else note or "audio only",
                    "height": height or 0,
                    "is_video": is_video,
                    "is_audio": is_audio,
                    "fps": fps,
                    "vcodec": vcodec if is_video else None,
                    "acodec": acodec if is_audio else None,
                    "filesize": filesize,
                    "tbr": tbr,
                    "format_str": f.get("format", ""),
                }
            )
        return parsed

    def download(
        self,
        url: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = "downloads",
        quality: Optional[str] = "best",
        format_id: Optional[str] = None,
        audio_only: bool = False,
        audio_format: str = "mp3",
        audio_quality: str = "320",
        video_format: Optional[str] = None,
        rate_limit: Optional[int] = None,
        subtitles: bool = False,
        sub_lang: str = "en",
        embed_subs: bool = False,
        embed_thumbnail: bool = True,
        embed_metadata: bool = True,
        playlist: bool = False,
        playlist_items: Optional[str] = None,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
        show_progress: bool = True,
    ) -> Optional[str]:
        """Execute the download using the most appropriate engine."""
        # 1. Inspect URL info
        info = None
        try:
            info = self.get_media_info(
                url,
                browser=browser,
                cookie_file=cookie_file,
                proxy=proxy,
                user_agent=user_agent,
                referer=referer,
            )
        except Exception:
            pass

        # Specialized TikTok handler (watermark-free videos & photo posts)
        if info and info.get("is_tiktok"):
            try:
                tt = TikTokDownloader()
                res = tt.download(
                    info=info,
                    output_path=output_path,
                    output_dir=output_dir or "downloads",
                    audio_only=audio_only,
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                    rate_limit=rate_limit,
                    show_progress=show_progress,
                )
                if res and embed_thumbnail:
                    if not attach_splash_art(res) and info.get("thumbnail"):
                        try:
                            p = Path(res)
                            temp_thumb = str(p.parent / f"{p.stem}_remote_cover.jpg")
                            resp = requests.get(info["thumbnail"], timeout=10)
                            if resp.status_code == 200 and resp.content:
                                with open(temp_thumb, "wb") as tf:
                                    tf.write(resp.content)
                                attach_splash_art(res, temp_thumb)
                        except Exception:
                            pass
                return res
            except Exception as e:
                self.console.print(f"[yellow]TikTok watermark-free download failed: {e}. Trying fallback...[/yellow]")

        # Specialized Spotify handler (tracks, playlists, albums)
        if (info and info.get("is_spotify")) or is_spotify_url(url):
            try:
                sp = SpotifyDownloader(console=self.console)
                sp_info = info if (info and info.get("is_spotify")) else sp.get_info(url)
                if sp_info:
                    if sp_info.get("is_playlist"):
                        return sp.download_playlist(
                            info=sp_info,
                            output_dir=output_dir or "downloads",
                            audio_format=audio_format,
                            audio_quality=audio_quality,
                            playlist_items=playlist_items,
                            rate_limit=rate_limit,
                            show_progress=show_progress,
                        )
                    else:
                        return sp.download_track(
                            info=sp_info,
                            output_path=output_path,
                            output_dir=output_dir or "downloads",
                            audio_format=audio_format,
                            audio_quality=audio_quality,
                            rate_limit=rate_limit,
                            show_progress=show_progress,
                        )
            except Exception as e:
                self.console.print(f"[yellow]Spotify download failed: {e}.[/yellow]")
                raise e

        # Specialized TIDAL handler (tracks, playlists, albums)
        if (info and info.get("is_tidal")) or is_tidal_url(url):
            try:
                td = TidalDownloader(console=self.console)
                td_info = info if (info and info.get("is_tidal")) else td.get_info(url)
                if td_info:
                    if td_info.get("is_playlist"):
                        return td.download_collection(
                            info=td_info,
                            base_dest=Path(output_dir or "downloads").expanduser().resolve(),
                            playlist_items=playlist_items,
                            audio_format=audio_format or "flac",
                            audio_quality=audio_quality or "320",
                        )
                    else:
                        return td.download_track(
                            track_info=td_info,
                            output_path=output_path,
                            output_dir=output_dir or "downloads",
                            audio_format=audio_format or "flac",
                            audio_quality=audio_quality or "320",
                        )
            except Exception as e:
                self.console.print(f"[yellow]TIDAL download failed: {e}.[/yellow]")
                raise e

        # Specialized Apple Music handler (songs, playlists, albums)
        if (info and info.get("is_apple_music")) or is_apple_music_url(url):
            try:
                am = AppleMusicDownloader(console=self.console)
                am_info = info if (info and info.get("is_apple_music")) else am.get_info(url)
                if am_info:
                    if am_info.get("is_playlist"):
                        return am.download_collection(
                            info=am_info,
                            base_dest=Path(output_dir or "downloads").expanduser().resolve(),
                            playlist_items=playlist_items,
                            audio_format=audio_format or "flac",
                            audio_quality=audio_quality or "320",
                        )
                    else:
                        return am.download_track(
                            track_info=am_info,
                            output_path=output_path,
                            output_dir=output_dir or "downloads",
                            audio_format=audio_format or "flac",
                            audio_quality=audio_quality or "320",
                        )
            except Exception as e:
                self.console.print(f"[yellow]Apple Music download failed: {e}.[/yellow]")
                raise e

        # Specialized Series & TV Show handler (Roopa Hala, Netflix, Web Streaming)
        if (info and info.get("is_series")) or is_series_url(url):
            try:
                series_obj = info.get("series_obj") if info else None
                if not series_obj:
                    extractor = get_series_extractor(url)
                    series_obj = extractor.extract_series(url, browser=browser, cookie_file=cookie_file)
                if series_obj:
                    episodes_to_download = series_obj.all_episodes
                    if playlist_items:
                        episodes_to_download = parse_episode_selection(playlist_items, series_obj.all_episodes)
                    elif not playlist and series_obj.all_episodes:
                        # If single download requested, take first matching episode
                        episodes_to_download = [series_obj.all_episodes[0]]

                    s_dl = SeriesDownloader(console=self.console)
                    s_res = s_dl.download_series(
                        series=series_obj,
                        episodes=episodes_to_download,
                        output_dir=output_dir or "downloads",
                        quality=quality,
                        browser=browser,
                        cookie_file=cookie_file,
                        subtitles=subtitles,
                        sub_lang=sub_lang,
                        embed_subs=embed_subs,
                        embed_thumbnail=embed_thumbnail,
                        rate_limit=rate_limit,
                    )
                    clean_title = sanitize_filename(series_obj.title)
                    return os.path.join(output_dir or "downloads", clean_title)
            except Exception as e:
                self.console.print(f"[yellow]Series download failed: {e}.[/yellow]")
                raise e

        # If info indicated direct stream or scraper extracted an embedded stream URL
        if info and info.get("is_direct"):
            target_download_url = info.get("url") or url
            downloader = DirectDownloader(rate_limit=rate_limit)
            if audio_only:
                import tempfile
                import subprocess
                import shutil

                temp_dir = tempfile.mkdtemp(prefix="vdown_audio_")
                try:
                    temp_file = downloader.download(
                        url=target_download_url,
                        output_dir=temp_dir,
                        show_progress=show_progress,
                    )
                    dest_dir = Path(output_dir or "downloads").expanduser().resolve()
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if output_path:
                        final_name = Path(output_path).name
                    else:
                        stem = Path(temp_file).stem
                        final_name = f"{stem}.{audio_format}"
                    final_path = dest_dir / final_name

                    if shutil.which("ffmpeg"):
                        cmd = ["ffmpeg", "-y", "-i", temp_file, "-vn"]
                        if audio_format.lower() == "flac":
                            cmd += ["-c:a", "flac"]
                        elif audio_format.lower() == "wav":
                            cmd += ["-c:a", "pcm_s16le"]
                        elif audio_format.lower() == "mp3":
                            q = audio_quality.rstrip("kK") if audio_quality else "320"
                            cmd += ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
                        elif audio_format.lower() in ("m4a", "aac"):
                            q = audio_quality.rstrip("kK") if audio_quality else "320"
                            cmd += ["-c:a", "aac", "-b:a", f"{q}k"]
                        elif audio_format.lower() == "opus":
                            q = audio_quality.rstrip("kK") if audio_quality else "320"
                            cmd += ["-c:a", "libopus", "-b:a", f"{q}k"]
                        else:
                            cmd += ["-c:a", "copy"]
                        cmd.append(str(final_path))
                        proc = subprocess.run(cmd, capture_output=True, text=True)
                        if proc.returncode == 0:
                            return str(final_path)

                    # Fallback if ffmpeg is unavailable or failed
                    shutil.move(temp_file, str(final_path))
                    return str(final_path)
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
            else:
                return downloader.download(
                    url=target_download_url,
                    output_path=output_path,
                    output_dir=output_dir or "downloads",
                    show_progress=show_progress,
                )

        # 2. Build yt-dlp options
        dest_dir = Path(output_dir or "downloads").expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        if output_path:
            p = Path(output_path).expanduser()
            if p.is_absolute() or len(p.parts) > 1:
                base_target = p.parent
                stem_name = p.stem
                full_name = p.name
            else:
                base_target = dest_dir
                stem_name = p.stem
                full_name = p.name

            if audio_only and p.suffix.lower().lstrip(".") == audio_format.lower():
                out_template = str(base_target / stem_name)
            elif video_format and p.suffix.lower().lstrip(".") == video_format.lower():
                out_template = str(base_target / stem_name)
            else:
                out_template = str(base_target / full_name)
        elif playlist:
            if audio_only:
                out_template = str(dest_dir / "%(playlist_title,playlist|Playlist)s/%(playlist_index|0)02d - %(title).200B.%(ext)s")
            else:
                out_template = str(dest_dir / "%(playlist_title,playlist|Playlist)s/%(playlist_index|0)02d - %(title).200B [%(id)s].%(ext)s")
        else:
            out_template = str(dest_dir / "%(title).200B [%(id)s].%(ext)s")

        ydl_opts: Dict[str, Any] = {
            "outtmpl": out_template,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": not playlist,
        }

        # Browser cookies and proxies
        if browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if proxy:
            ydl_opts["proxy"] = proxy

        if user_agent or referer:
            headers = {}
            if user_agent:
                headers["User-Agent"] = user_agent
            if referer:
                headers["Referer"] = referer
            ydl_opts["http_headers"] = headers

        if playlist_items:
            ydl_opts["playlist_items"] = playlist_items

        if rate_limit:
            ydl_opts["ratelimit"] = rate_limit

        # Format / Quality selection string
        if format_id:
            ydl_opts["format"] = format_id
        elif audio_only:
            ydl_opts["format"] = "bestaudio/best"
            preferred_q = audio_quality.rstrip("kK") if audio_quality else "320"
            pp: Dict[str, Any] = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format,
            }
            if audio_format.lower() not in ("flac", "wav"):
                pp["preferredquality"] = preferred_q
            ydl_opts["postprocessors"] = [pp]
        else:
            # Video quality logic
            quality_map = {
                "4k": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
                "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
                "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
                "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
                "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
                "worst": "worstvideo+worstaudio/worst",
                "best": "bestvideo+bestaudio/best",
            }
            ydl_opts["format"] = quality_map.get(
                (quality or "best").lower(),
                "bestvideo+bestaudio/best"
            )

        # Merge container
        if video_format and not audio_only:
            ydl_opts["merge_output_format"] = video_format
        elif not audio_only:
            ydl_opts["merge_output_format"] = "mp4"

        # Subtitles
        if subtitles or embed_subs:
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = [sub_lang]
            if embed_subs:
                if "postprocessors" not in ydl_opts:
                    ydl_opts["postprocessors"] = []
                ydl_opts["postprocessors"].append(
                    {"key": "FFmpegEmbedSubtitle"}
                )

        # Thumbnail embedding
        if embed_thumbnail:
            ydl_opts["writethumbnail"] = True
            if "postprocessors" not in ydl_opts:
                ydl_opts["postprocessors"] = []
            ydl_opts["postprocessors"].append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
        # Metadata embedding
        if embed_metadata:
            if "postprocessors" not in ydl_opts:
                ydl_opts["postprocessors"] = []
            ydl_opts["postprocessors"].append({"key": "FFmpegMetadata"})

        # Rich progress bar setup
        last_file_downloaded = None
        downloaded_files: List[str] = []

        def ydl_progress_hook(d: Dict[str, Any]):
            nonlocal last_file_downloaded
            status = d.get("status")

            if status == "downloading":
                raw_fn = d.get("filename") or "Media"
                filename = Path(raw_fn).name
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed")
                eta = d.get("eta")

                # Show [playlist_index/n_entries] prefix for playlists
                info_dict = d.get("info_dict") or {}
                p_idx = info_dict.get("playlist_index")
                p_count = info_dict.get("n_entries") or info_dict.get("playlist_count")
                prefix = f"[{p_idx}/{p_count}] " if p_idx and p_count else ""
                task_label = f"{prefix}{filename}"

                if "task_id" not in task_tracker:
                    task_tracker["task_id"] = progress.add_task(
                        task_label,
                        total=total,
                        completed=downloaded,
                        speed=speed,
                        eta=eta,
                    )
                    task_tracker["current_fn"] = filename
                elif task_tracker.get("current_fn") != filename:
                    task_tracker["current_fn"] = filename
                    progress.reset(
                        task_tracker["task_id"],
                        description=task_label,
                        total=total,
                        completed=downloaded,
                    )
                else:
                    progress.update(
                        task_tracker["task_id"],
                        description=task_label,
                        total=total,
                        completed=downloaded,
                        speed=speed,
                        eta=eta,
                    )

            elif status == "finished":
                fn = d.get("filename")
                if fn:
                    last_file_downloaded = fn
                    if fn not in downloaded_files:
                        downloaded_files.append(fn)
                if "task_id" in task_tracker:
                    label = "Extracting Audio..." if audio_only else "Processing / Merging..."
                    progress.update(
                        task_tracker["task_id"],
                        description=label,
                    )

        def ydl_postprocessor_hook(d: Dict[str, Any]):
            nonlocal last_file_downloaded
            if d.get("status") == "finished":
                filepath = d.get("filepath") or d.get("info_dict", {}).get("filepath")
                if filepath:
                    last_file_downloaded = filepath
                    if filepath not in downloaded_files:
                        downloaded_files.append(filepath)

        ydl_opts["postprocessor_hooks"] = [ydl_postprocessor_hook]

        def _attach_thumbnails():
            if not embed_thumbnail:
                return
            targets = list(downloaded_files)
            if last_file_downloaded and last_file_downloaded not in targets:
                targets.append(last_file_downloaded)

            for target in targets:
                if not target or not os.path.exists(target) or os.path.isdir(target):
                    continue
                attached = attach_splash_art(target)
                if not attached and info and info.get("thumbnail"):
                    thumb_url = info["thumbnail"]
                    try:
                        p = Path(target)
                        temp_thumb = str(p.parent / f"{p.stem}_remote_cover.jpg")
                        resp = requests.get(thumb_url, timeout=10)
                        if resp.status_code == 200 and resp.content:
                            with open(temp_thumb, "wb") as tf:
                                tf.write(resp.content)
                            attach_splash_art(target, temp_thumb)
                    except Exception:
                        pass

        if show_progress:
            from simple_downloader.progress import create_download_progress

            progress = create_download_progress(show_progress=True)
            task_tracker: Dict[str, Any] = {}
            ydl_opts["progress_hooks"] = [ydl_progress_hook]

            try:
                with progress:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ret_code = ydl.download([url])
                        if ret_code != 0:
                            raise RuntimeError(f"Download failed with exit code {ret_code}")
                _attach_thumbnails()
                if playlist and downloaded_files:
                    if len(downloaded_files) > 1:
                        common_dir = os.path.dirname(downloaded_files[0])
                        return common_dir if common_dir and os.path.isdir(common_dir) else last_file_downloaded
                    return downloaded_files[0]
                return last_file_downloaded

            except Exception as e:
                err_str = str(e).lower()
                if any(k in err_str for k in ["login required", "bot", "confirm you're not a bot", "private video", "sign in", "401"]):
                    self.console.print("\n[bold yellow]⚠ This platform requires authentication or session cookies.[/bold yellow]")
                    self.console.print("[dim]Tip: Retry with your browser session, e.g.:[/dim]")
                    self.console.print("  [cyan]vdown \"<link>\" --browser chromium[/cyan]")
                    self.console.print("  [cyan]vdown \"<link>\" --browser brave[/cyan]")
                    self.console.print("  [cyan]vdown \"<link>\" --browser chrome[/cyan]\n")

                # Fallback: Try webpage video scraper
                scraper = WebpageVideoScraper(headers={"User-Agent": user_agent} if user_agent else None)
                candidates = scraper.find_videos(url)
                if candidates:
                    self.console.print(f"[yellow]Searching embedded videos on page... found {len(candidates)} candidates.[/yellow]")
                    for cand in candidates:
                        try:
                            return self.download(
                                url=cand["url"],
                                output_path=output_path,
                                output_dir=output_dir or "downloads",
                                quality=quality,
                                format_id=format_id,
                                audio_only=audio_only,
                                audio_format=audio_format,
                                video_format=video_format,
                                rate_limit=rate_limit,
                                show_progress=show_progress,
                            )
                        except Exception:
                            continue

                # Fallback: Direct HTTP downloader
                if is_direct_media_url(url) or "http" in url:
                    self.console.print("[yellow]Trying direct HTTP streaming downloader...[/yellow]")
                    downloader = DirectDownloader(rate_limit=rate_limit)
                    return downloader.download(
                        url=url,
                        output_path=output_path,
                        output_dir=output_dir or "downloads",
                        show_progress=show_progress,
                    )
                raise e
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            _attach_thumbnails()
            if playlist and downloaded_files:
                if len(downloaded_files) > 1:
                    common_dir = os.path.dirname(downloaded_files[0])
                    return common_dir if common_dir and os.path.isdir(common_dir) else last_file_downloaded
                return downloaded_files[0]
            return last_file_downloaded
