"""Apple Music lossless track, album, and playlist downloader.

Extracts official Apple Music metadata (songs, albums, playlists) and high-res 1400x1400 album artwork,
resolves the highest-fidelity matching audio stream via yt-dlp with duration proximity matching,
and transcodes with FFmpeg into Lossless FLAC, uncompressed Lossless WAV, or 320 kbps MP3 with embedded splash art.
"""

import os
import re
import shutil
import tempfile
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
from rich.console import Console

from simple_downloader.utils import (
    sanitize_filename,
    embed_wav_cover_art,
    build_vorbis_picture_block,
)


def is_apple_music_url(url: str) -> bool:
    """Check if the given URL is an Apple Music track, album, or playlist link."""
    if not url or not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url.strip())
    return any(h in parsed.netloc for h in ["music.apple.com", "itunes.apple.com"])


def parse_apple_music_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract entity type (song, album, playlist) and ID from an Apple Music URL.

    Handles:
    - https://music.apple.com/us/album/better-together/1440857781?i=1440857786 -> ('song', '1440857786')
    - https://music.apple.com/us/song/better-together/1440857786 -> ('song', '1440857786')
    - https://music.apple.com/us/album/in-between-dreams/1440857781 -> ('album', '1440857781')
    - https://music.apple.com/us/playlist/apple-music-list/pl.41fda5ad... -> ('playlist', 'pl.41fda5ad...')
    """
    if not is_apple_music_url(url):
        return None

    parsed = urllib.parse.urlparse(url.strip())
    # Check query params for ?i= (song nested in album)
    qs = urllib.parse.parse_qs(parsed.query)
    if "i" in qs and qs["i"]:
        return "song", qs["i"][0]

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    # Remove regional prefix (e.g. us, gb, es, pl, pt-br)
    if parts and (len(parts[0]) == 2 or (len(parts[0]) == 5 and "-" in parts[0])):
        parts = parts[1:]

    if not parts:
        return None

    entity_type = parts[0].lower()
    if entity_type not in ("album", "song", "playlist"):
        return None

    if len(parts) >= 3:
        entity_id = parts[2]
    elif len(parts) == 2:
        entity_id = parts[1]
    else:
        return None

    return entity_type, entity_id


def build_apple_artwork_url(artwork_url: Optional[str], size: int = 1400) -> Optional[str]:
    """Convert a thumbnail Apple Music artwork URL into a high-res cover image URL."""
    if not artwork_url:
        return None
    scaled = re.sub(r"/\d+x\d+bb\.[a-zA-Z]+$", f"/{size}x{size}bb.jpg", artwork_url)
    scaled = scaled.replace("{w}", str(size)).replace("{h}", str(size)).replace("{f}", "jpg")
    return scaled


class AppleMusicDownloader:
    """Downloader and metadata extractor for Apple Music lossless media."""

    LOOKUP_API = "https://itunes.apple.com/lookup"
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata for an Apple Music song, album, or playlist."""
        parsed = parse_apple_music_url(url)
        if not parsed:
            return None

        entity_type, entity_id = parsed

        if entity_type == "song":
            return self._get_song_info(entity_id, url)
        elif entity_type == "album":
            return self._get_album_info(entity_id, url)
        elif entity_type == "playlist":
            return self._get_playlist_info(entity_id, url)
        return None

    def _get_song_info(self, song_id: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch song metadata via iTunes lookup API."""
        try:
            resp = requests.get(
                self.LOOKUP_API,
                params={"id": song_id},
                headers=self.DEFAULT_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    track = results[0]
                    title = track.get("trackName") or "Unknown Track"
                    artist = track.get("artistName") or "Unknown Artist"
                    album = track.get("collectionName") or ""
                    duration_ms = track.get("trackTimeMillis")
                    duration = int(duration_ms / 1000) if duration_ms else None
                    raw_art = track.get("artworkUrl100") or track.get("artworkUrl60")
                    cover_url = build_apple_artwork_url(raw_art, size=1400)
                    release_date = track.get("releaseDate", "")[:10] if track.get("releaseDate") else None
                    track_number = track.get("trackNumber", 1)

                    return {
                        "id": str(song_id),
                        "title": f"{artist} - {title}",
                        "track_title": title,
                        "artist": artist,
                        "album": album,
                        "duration": duration,
                        "thumbnail": cover_url,
                        "upload_date": release_date,
                        "track_number": track_number,
                        "is_apple_music": True,
                        "is_playlist": False,
                        "apple_music_type": "song",
                        "url": original_url,
                    }
        except Exception as e:
            self.console.print(f"[dim]Apple Music song lookup warning: {e}[/dim]")

        # Web scrape fallback
        try:
            resp = requests.get(original_url, headers=self.DEFAULT_HEADERS, timeout=10)
            if resp.status_code == 200:
                og_title_m = re.search(r'<meta property="og:title" content="([^"]+)"', resp.text)
                og_image_m = re.search(r'<meta property="og:image" content="([^"]+)"', resp.text)
                title_val = og_title_m.group(1) if og_title_m else "Apple Music Song"
                title_val = re.sub(r"\s+on Apple Music$", "", title_val)
                raw_img = og_image_m.group(1) if og_image_m else None
                cover_url = build_apple_artwork_url(raw_img, size=1400)

                return {
                    "id": str(song_id),
                    "title": title_val,
                    "track_title": title_val,
                    "artist": "Apple Music Artist",
                    "album": "",
                    "duration": None,
                    "thumbnail": cover_url,
                    "is_apple_music": True,
                    "is_playlist": False,
                    "apple_music_type": "song",
                    "url": original_url,
                }
        except Exception:
            pass

        return None

    def _get_album_info(self, album_id: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch album details and complete track listing via iTunes lookup API."""
        try:
            resp = requests.get(
                self.LOOKUP_API,
                params={"id": album_id, "entity": "song"},
                headers=self.DEFAULT_HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    collection = results[0]
                    album_title = collection.get("collectionName") or "Unknown Album"
                    artist = collection.get("artistName") or "Unknown Artist"
                    raw_art = collection.get("artworkUrl100") or collection.get("artworkUrl60")
                    cover_url = build_apple_artwork_url(raw_art, size=1400)
                    release_date = collection.get("releaseDate", "")[:10] if collection.get("releaseDate") else None

                    entries = []
                    for item in results[1:]:
                        if item.get("wrapperType") == "track":
                            t_title = item.get("trackName") or "Unknown Track"
                            t_artist = item.get("artistName") or artist
                            dur_ms = item.get("trackTimeMillis")
                            t_dur = int(dur_ms / 1000) if dur_ms else None
                            t_art = build_apple_artwork_url(item.get("artworkUrl100") or raw_art, size=1400)
                            entries.append({
                                "id": str(item.get("trackId")),
                                "title": f"{t_artist} - {t_title}",
                                "track_title": t_title,
                                "artist": t_artist,
                                "album": album_title,
                                "duration": t_dur,
                                "thumbnail": t_art,
                                "track_number": item.get("trackNumber", len(entries) + 1),
                                "is_apple_music": True,
                            })

                    return {
                        "id": str(album_id),
                        "title": f"{artist} - {album_title}",
                        "album_title": album_title,
                        "artist": artist,
                        "upload_date": release_date,
                        "thumbnail": cover_url,
                        "is_apple_music": True,
                        "is_playlist": True,
                        "apple_music_type": "album",
                        "url": original_url,
                        "playlist_count": len(entries),
                        "entries": entries,
                    }
        except Exception as e:
            self.console.print(f"[yellow]Apple Music album lookup warning: {e}[/yellow]")

        return None

    def _get_playlist_info(self, playlist_id: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch playlist details and track listing via page scraping and batch lookup."""
        try:
            resp = requests.get(original_url, headers=self.DEFAULT_HEADERS, timeout=12)
            if resp.status_code != 200:
                return None

            html = resp.text
            og_title_m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            og_img_m = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            pl_title = og_title_m.group(1) if og_title_m else "Apple Music Playlist"
            pl_title = re.sub(r"\s+on Apple Music$", "", pl_title)
            raw_cover = og_img_m.group(1) if og_img_m else None
            cover_url = build_apple_artwork_url(raw_cover, size=1400)

            song_matches = re.findall(
                r'<meta property="music:song" content="https?://music\.apple\.com/[^"]+/song/([^/?#]+)/(\d+)"',
                html,
            )
            if not song_matches:
                song_matches = re.findall(
                    r'<meta property="music:song" content="https?://music\.apple\.com/[^"]+/(\d+)"',
                    html,
                )
                song_ids = [m for m in song_matches]
            else:
                song_ids = [m[1] for m in song_matches]

            entries = []
            if song_ids:
                chunk_size = 50
                for i in range(0, min(len(song_ids), 150), chunk_size):
                    chunk = song_ids[i : i + chunk_size]
                    try:
                        b_resp = requests.get(
                            self.LOOKUP_API,
                            params={"id": ",".join(chunk)},
                            headers=self.DEFAULT_HEADERS,
                            timeout=10,
                        )
                        if b_resp.status_code == 200:
                            lookup_map = {
                                str(r.get("trackId")): r
                                for r in b_resp.json().get("results", [])
                                if r.get("trackId")
                            }
                            for sid in chunk:
                                item = lookup_map.get(str(sid))
                                if item:
                                    t_title = item.get("trackName") or "Unknown Track"
                                    t_artist = item.get("artistName") or "Unknown Artist"
                                    dur_ms = item.get("trackTimeMillis")
                                    t_dur = int(dur_ms / 1000) if dur_ms else None
                                    t_art = build_apple_artwork_url(item.get("artworkUrl100"), size=1400) or cover_url
                                    entries.append({
                                        "id": str(sid),
                                        "title": f"{t_artist} - {t_title}",
                                        "track_title": t_title,
                                        "artist": t_artist,
                                        "album": item.get("collectionName"),
                                        "duration": t_dur,
                                        "thumbnail": t_art,
                                        "track_number": len(entries) + 1,
                                        "is_apple_music": True,
                                    })
                    except Exception:
                        pass

            return {
                "id": str(playlist_id),
                "title": pl_title,
                "thumbnail": cover_url,
                "is_apple_music": True,
                "is_playlist": True,
                "apple_music_type": "playlist",
                "url": original_url,
                "playlist_count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            self.console.print(f"[yellow]Apple Music playlist error: {e}[/yellow]")
            return None

    def resolve_audio_stream(
        self, artist: str, title: str, expected_duration: Optional[int] = None
    ) -> Optional[str]:
        """Resolve highest-fidelity audio match using duration proximity matching."""
        import yt_dlp

        search_query = f"{artist} - {title}"
        self.console.print(
            f"[dim]Resolving high-fidelity audio stream for:[/dim] [cyan]{search_query}[/cyan]"
        )

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "default_search": "ytsearch5",
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(f"ytsearch5:{search_query}", download=False)
                if not res or "entries" not in res:
                    return None

                candidates = [e for e in res["entries"] if e and e.get("id")]
                if not candidates:
                    return None

                best_entry = candidates[0]
                if expected_duration and expected_duration > 0:
                    best_diff = float("inf")
                    for c in candidates:
                        dur = c.get("duration")
                        if dur is not None:
                            diff = abs(dur - expected_duration)
                            if diff > 30:
                                diff += 100
                            if diff < best_diff:
                                best_diff = diff
                                best_entry = c

                return f"https://www.youtube.com/watch?v={best_entry['id']}"
        except Exception as e:
            self.console.print(f"[red]Error searching audio stream:[/red] {e}")
            return None

    def download_track(
        self,
        track_info: Dict[str, Any],
        output_path: Optional[str] = None,
        output_dir: Optional[str] = "downloads",
        audio_format: str = "flac",
        audio_quality: str = "320",
    ) -> str:
        """Download and transcode Apple Music track to Lossless FLAC, WAV, 320k MP3, etc. with cover art."""
        artist = track_info.get("artist") or "Unknown Artist"
        title = track_info.get("track_title") or track_info.get("title") or "Unknown Title"
        album = track_info.get("album") or ""
        expected_dur = track_info.get("duration")
        cover_url = track_info.get("thumbnail")
        track_num = track_info.get("track_number", 1)

        source_url = self.resolve_audio_stream(artist, title, expected_dur)
        if not source_url:
            raise RuntimeError(f"Could not resolve audio stream for '{artist} - {title}'")

        dest_folder = Path(output_dir or "downloads").expanduser().resolve()
        dest_folder.mkdir(parents=True, exist_ok=True)

        fmt = audio_format.lower()
        if output_path:
            p = Path(output_path).expanduser()
            if p.is_absolute() or len(p.parts) > 1:
                target_path = p.resolve()
            else:
                target_path = dest_folder / p.name
        else:
            safe_name = sanitize_filename(f"{artist} - {title}.{fmt}")
            target_path = dest_folder / safe_name

        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_dir = Path(tempfile.mkdtemp(prefix="vdown_apple_"))
        raw_audio = temp_dir / "stream.webm"
        cover_file = temp_dir / "cover.jpg"

        try:
            # 1. Download cover art image
            has_cover = False
            if cover_url:
                try:
                    c_resp = requests.get(cover_url, headers=self.DEFAULT_HEADERS, timeout=10)
                    if c_resp.status_code == 200 and len(c_resp.content) > 0:
                        with open(cover_file, "wb") as cf:
                            cf.write(c_resp.content)
                        has_cover = True
                except Exception:
                    has_cover = False

            # 2. Download highest quality audio stream via yt-dlp
            import yt_dlp
            from simple_downloader.progress import create_download_progress

            self.console.print(
                f"[bold cyan]Fetching audio stream:[/bold cyan] [bold white]{artist} - {title}[/bold white]"
            )

            progress = create_download_progress()
            task_id = progress.add_task(f"🎵 [bold cyan]{artist} - {title}[/bold cyan]", total=100)

            def ydl_hook(d):
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                    downloaded = d.get("downloaded_bytes", 0)
                    progress.update(task_id, total=total, completed=downloaded)
                elif d["status"] == "finished":
                    progress.update(task_id, completed=progress.tasks[task_id].total)

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(raw_audio),
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [ydl_hook],
            }

            with progress:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([source_url])

            if not raw_audio.exists():
                candidates = list(temp_dir.glob("stream.*"))
                if candidates:
                    raw_audio = candidates[0]
                else:
                    raise RuntimeError("Failed to fetch raw audio stream.")

            # 3. Transcode to desired format with embedded tags and cover art
            cmd = ["ffmpeg", "-y", "-i", str(raw_audio)]

            if has_cover and fmt in ("mp3", "flac", "m4a", "aac"):
                cmd += ["-i", str(cover_file), "-map", "0:a", "-map", "1:v"]
                cmd += ["-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
            else:
                cmd += ["-map", "0:a"]

            # Codec settings
            if fmt == "flac":
                cmd += ["-c:a", "flac", "-sample_fmt", "s32"]
            elif fmt == "wav":
                cmd += ["-c:a", "pcm_s16le"]
            elif fmt == "mp3":
                q = audio_quality or "320"
                if q == "0":
                    cmd += ["-c:a", "libmp3lame", "-q:a", "0"]
                else:
                    cmd += ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
            elif fmt in ("m4a", "aac"):
                q = audio_quality or "320"
                cmd += ["-c:a", "aac", "-b:a", f"{q}k"]
            elif fmt in ("opus", "ogg"):
                q = audio_quality or "320"
                cmd += ["-c:a", "libopus" if fmt == "opus" else "libvorbis", "-b:a", f"{q}k"]
                if has_cover:
                    b64_pic = build_vorbis_picture_block(str(cover_file))
                    if b64_pic:
                        cmd += ["-metadata", f"METADATA_BLOCK_PICTURE={b64_pic}"]
            else:
                cmd += ["-c:a", "copy"]

            # Metadata tags
            cmd += [
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
                "-metadata", f"album_artist={artist}",
                "-metadata", f"track={track_num}",
            ]
            if album:
                cmd += ["-metadata", f"album={album}"]

            cmd.append(str(target_path))

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                fallback_cmd = ["ffmpeg", "-y", "-i", str(raw_audio)]
                if fmt == "flac":
                    fallback_cmd += ["-c:a", "flac"]
                elif fmt == "wav":
                    fallback_cmd += ["-c:a", "pcm_s16le"]
                elif fmt == "mp3":
                    fallback_cmd += ["-c:a", "libmp3lame", "-b:a", f"{audio_quality}k"]
                else:
                    fallback_cmd += ["-c:a", "copy"]
                fallback_cmd.append(str(target_path))
                subprocess.run(fallback_cmd, capture_output=True, text=True)

            if has_cover and fmt == "wav" and os.path.exists(str(target_path)):
                embed_wav_cover_art(str(target_path), str(cover_file))

            return str(target_path)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def download_collection(
        self,
        info: Dict[str, Any],
        base_dest: Path,
        playlist_items: Optional[str] = None,
        audio_format: str = "flac",
        audio_quality: str = "320",
    ) -> str:
        """Download full album or playlist with track numbering and folder cover.jpg."""
        entries = info.get("entries", [])
        if not entries:
            raise RuntimeError("No tracks found in collection.")

        selected_entries = list(entries)
        if playlist_items:
            try:
                selected_indices = set()
                for part in playlist_items.split(","):
                    part = part.strip()
                    if "-" in part:
                        start_str, end_str = part.split("-", 1)
                        s = int(start_str)
                        e = len(entries) if end_str == "end" else int(end_str)
                        selected_indices.update(range(s, e + 1))
                    else:
                        selected_indices.add(int(part))
                selected_entries = [
                    e for idx, e in enumerate(entries, 1) if idx in selected_indices
                ]
            except Exception:
                selected_entries = entries

        col_title = info.get("album_title") or info.get("title") or "Apple Music Collection"
        folder = base_dest / sanitize_filename(col_title)
        folder.mkdir(parents=True, exist_ok=True)

        cover_url = info.get("thumbnail")
        if cover_url:
            col_cover_dest = folder / "cover.jpg"
            if not col_cover_dest.exists():
                try:
                    c_resp = requests.get(cover_url, headers=self.DEFAULT_HEADERS, timeout=10)
                    if c_resp.status_code == 200 and len(c_resp.content) > 0:
                        with open(col_cover_dest, "wb") as pf:
                            pf.write(c_resp.content)
                except Exception:
                    pass

        total_selected = len(selected_entries)
        col_type = "Album" if info.get("apple_music_type") == "album" else "Playlist"
        self.console.print(
            f"\n[bold cyan]Downloading Apple Music {col_type}:[/bold cyan] [bold white]{col_title}[/bold white] "
            f"[dim]({total_selected} tracks) -> {folder}[/dim]\n"
        )

        fmt = audio_format.lower()
        for idx, entry in enumerate(selected_entries, 1):
            artist = entry.get("artist") or "Unknown Artist"
            track_title = entry.get("track_title") or entry.get("title") or f"Track {idx}"
            self.console.print(
                f"\n[bold yellow][{idx}/{total_selected}][/bold yellow] [bold white]{artist} - {track_title}[/bold white]"
            )

            track_filename = sanitize_filename(f"{idx:02d} - {artist} - {track_title}.{fmt}")
            dest_track_path = folder / track_filename

            if dest_track_path.exists():
                self.console.print(f"[green]✔ Already downloaded:[/green] [dim]{track_filename}[/dim]")
                continue

            entry["track_number"] = idx
            self.download_track(
                track_info=entry,
                output_path=str(dest_track_path),
                output_dir=str(folder),
                audio_format=audio_format,
                audio_quality=audio_quality,
            )

        return str(folder)
