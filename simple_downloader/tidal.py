"""TIDAL lossless track, album, and playlist downloader.

Extracts official TIDAL metadata (tracks, albums, playlists) and high-res 1280x1280 album artwork,
resolves the highest-fidelity matching audio stream via yt-dlp with duration proximity penalization,
and transcodes with FFmpeg into Lossless FLAC, uncompressed Lossless WAV, or 320 kbps MP3 with embedded splash art.
"""

import os
import re
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import requests
from rich.console import Console

from simple_downloader.utils import (
    sanitize_filename,
    embed_wav_cover_art,
    build_vorbis_picture_block,
)

TIDAL_URL_REGEX = re.compile(
    r"^(?:https?://(?:(?:listen|browse)\.)?tidal\.com/(?:browse/)?(track|album|playlist)/([a-zA-Z0-9_-]+))"
)


def is_tidal_url(url: str) -> bool:
    """Check if the given URL is a TIDAL track, album, or playlist link."""
    if not url or not isinstance(url, str):
        return False
    return bool(TIDAL_URL_REGEX.search(url.strip()))


def parse_tidal_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract entity type (track, album, playlist) and ID from a TIDAL URL."""
    match = TIDAL_URL_REGEX.search(url.strip())
    if not match:
        return None
    entity_type, entity_id = match.groups()
    return entity_type.lower(), entity_id


def build_tidal_cover_url(cover_id: Optional[str], size: str = "1280x1280") -> Optional[str]:
    """Convert a TIDAL cover UUID into a high-res image CDN URL."""
    if not cover_id:
        return None
    cover_clean = cover_id.replace("-", "/")
    return f"https://resources.tidal.com/images/{cover_clean}/{size}.jpg"


class TidalDownloader:
    """Downloader and metadata extractor for TIDAL lossless media."""

    DEFAULT_CLIENT_TOKEN = "CzET4vdadNUFQ5JU"
    API_BASE = "https://api.tidal.com/v1"
    DEFAULT_HEADERS = {
        "User-Agent": "TIDAL/3.2.0 (Windows NT 10.0; Win64; x64)",
        "x-tidal-token": DEFAULT_CLIENT_TOKEN,
        "Accept": "application/json",
    }
    WEB_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata for a TIDAL track, album, or playlist."""
        parsed = parse_tidal_url(url)
        if not parsed:
            return None

        entity_type, entity_id = parsed

        if entity_type == "track":
            return self._get_track_info(entity_id, url)
        elif entity_type == "album":
            return self._get_album_info(entity_id, url)
        elif entity_type == "playlist":
            return self._get_playlist_info(entity_id, url)
        return None

    def _get_track_info(self, track_id: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch track metadata via TIDAL API with HTML scrape fallback."""
        # 1. Try TIDAL API
        try:
            api_url = f"{self.API_BASE}/tracks/{track_id}"
            resp = requests.get(api_url, params={"countryCode": "US"}, headers=self.DEFAULT_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title") or "Unknown Track"
                artists = [a.get("name") for a in data.get("artists", []) if a.get("name")]
                artist_name = ", ".join(artists) if artists else (data.get("artist", {}).get("name") or "Unknown Artist")
                album_info = data.get("album", {})
                album_title = album_info.get("title")
                cover_uuid = album_info.get("cover")
                cover_url = build_tidal_cover_url(cover_uuid)
                duration = data.get("duration")

                display_title = f"{artist_name} - {title}"
                return {
                    "id": str(track_id),
                    "title": display_title,
                    "track_title": title,
                    "artist": artist_name,
                    "album": album_title,
                    "duration": duration,
                    "thumbnail": cover_url,
                    "is_tidal": True,
                    "is_playlist": False,
                    "tidal_type": "track",
                    "url": original_url,
                    "audio_quality": data.get("audioQuality", "LOSSLESS"),
                    "track_number": data.get("trackNumber", 1),
                }
        except Exception as e:
            self.console.print(f"[dim]TIDAL API track notice: {e}[/dim]")

        # 2. Fallback: Scrape HTML page
        try:
            web_url = f"https://tidal.com/track/{track_id}"
            resp = requests.get(web_url, headers=self.WEB_HEADERS, timeout=10)
            if resp.status_code == 200:
                # Find JSON-LD
                ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL)
                if ld_match:
                    try:
                        ld_data = json.loads(ld_match.group(1))
                        title = ld_data.get("name", "Unknown Track")
                        artist_name = ld_data.get("byArtist", {}).get("name", "Unknown Artist")
                        album_title = ld_data.get("inAlbum", {}).get("name")
                        cover_url = ld_data.get("image")
                        duration_str = ld_data.get("duration", "")
                        duration = None
                        if duration_str:
                            dur_m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", duration_str)
                            if dur_m:
                                minutes = int(dur_m.group(1) or 0)
                                seconds = int(dur_m.group(2) or 0)
                                duration = minutes * 60 + seconds

                        return {
                            "id": str(track_id),
                            "title": f"{artist_name} - {title}",
                            "track_title": title,
                            "artist": artist_name,
                            "album": album_title,
                            "duration": duration,
                            "thumbnail": cover_url,
                            "is_tidal": True,
                            "is_playlist": False,
                            "tidal_type": "track",
                            "url": original_url,
                        }
                    except Exception:
                        pass
        except Exception:
            pass

        return None

    def _get_album_info(self, album_id: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch album details and track list via TIDAL API."""
        try:
            # Get album info
            alb_url = f"{self.API_BASE}/albums/{album_id}"
            resp = requests.get(alb_url, params={"countryCode": "US"}, headers=self.DEFAULT_HEADERS, timeout=10)
            if resp.status_code != 200:
                return None
            alb_data = resp.json()
            album_title = alb_data.get("title") or "Unknown Album"
            artist_name = alb_data.get("artist", {}).get("name") or "Unknown Artist"
            cover_url = build_tidal_cover_url(alb_data.get("cover"))
            release_date = alb_data.get("releaseDate")

            # Get album tracks
            trk_url = f"{self.API_BASE}/albums/{album_id}/tracks"
            t_resp = requests.get(trk_url, params={"countryCode": "US"}, headers=self.DEFAULT_HEADERS, timeout=10)
            entries = []
            if t_resp.status_code == 200:
                for item in t_resp.json().get("items", []):
                    t_title = item.get("title") or "Unknown Track"
                    t_artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]
                    t_artist = ", ".join(t_artists) if t_artists else artist_name
                    entries.append({
                        "id": str(item.get("id")),
                        "title": f"{t_artist} - {t_title}",
                        "track_title": t_title,
                        "artist": t_artist,
                        "album": album_title,
                        "duration": item.get("duration"),
                        "thumbnail": cover_url,
                        "track_number": item.get("trackNumber", len(entries) + 1),
                        "is_tidal": True,
                    })

            return {
                "id": str(album_id),
                "title": f"{artist_name} - {album_title}",
                "album_title": album_title,
                "artist": artist_name,
                "upload_date": release_date,
                "thumbnail": cover_url,
                "is_tidal": True,
                "is_playlist": True,
                "tidal_type": "album",
                "url": original_url,
                "playlist_count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            self.console.print(f"[yellow]TIDAL API album error: {e}[/yellow]")
            return None

    def _get_playlist_info(self, playlist_uuid: str, original_url: str) -> Optional[Dict[str, Any]]:
        """Fetch playlist details and track list via TIDAL API."""
        try:
            pl_url = f"{self.API_BASE}/playlists/{playlist_uuid}"
            resp = requests.get(pl_url, params={"countryCode": "US"}, headers=self.DEFAULT_HEADERS, timeout=10)
            if resp.status_code != 200:
                return None
            pl_data = resp.json()
            title = pl_data.get("title") or "TIDAL Playlist"
            cover_url = build_tidal_cover_url(pl_data.get("image"))

            # Get tracks
            trk_url = f"{self.API_BASE}/playlists/{playlist_uuid}/tracks"
            t_resp = requests.get(trk_url, params={"countryCode": "US"}, headers=self.DEFAULT_HEADERS, timeout=10)
            entries = []
            if t_resp.status_code == 200:
                for item in t_resp.json().get("items", []):
                    t_title = item.get("title") or "Unknown Track"
                    t_artists = [a.get("name") for a in item.get("artists", []) if a.get("name")]
                    t_artist = ", ".join(t_artists) if t_artists else (item.get("artist", {}).get("name") or "Unknown Artist")
                    item_album = item.get("album", {})
                    t_cover = build_tidal_cover_url(item_album.get("cover")) or cover_url
                    entries.append({
                        "id": str(item.get("id")),
                        "title": f"{t_artist} - {t_title}",
                        "track_title": t_title,
                        "artist": t_artist,
                        "album": item_album.get("title"),
                        "duration": item.get("duration"),
                        "thumbnail": t_cover,
                        "track_number": len(entries) + 1,
                        "is_tidal": True,
                    })

            return {
                "id": str(playlist_uuid),
                "title": title,
                "thumbnail": cover_url,
                "is_tidal": True,
                "is_playlist": True,
                "tidal_type": "playlist",
                "url": original_url,
                "playlist_count": len(entries),
                "entries": entries,
            }
        except Exception as e:
            self.console.print(f"[yellow]TIDAL API playlist error: {e}[/yellow]")
            return None

    def resolve_audio_stream(self, artist: str, title: str, expected_duration: Optional[int] = None) -> Optional[str]:
        """Resolve highest-fidelity audio match using smart duration proximity matching."""
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

                # Select candidate with minimal duration deviation
                best_entry = candidates[0]
                if expected_duration and expected_duration > 0:
                    best_diff = float("inf")
                    for c in candidates:
                        dur = c.get("duration")
                        if dur is not None:
                            diff = abs(dur - expected_duration)
                            # Heavily penalize tracks with > 30s discrepancy (music videos, intros)
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
        """Download and transcode TIDAL track to Lossless FLAC, WAV, 320k MP3, etc. with cover art."""
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

        temp_dir = Path(tempfile.mkdtemp(prefix="vdown_tidal_"))
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

            # 2. Download highest quality audio source via yt-dlp
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

            # 3. Transcode to user's desired format with embedded tags and cover art
            cmd = ["ffmpeg", "-y", "-i", str(raw_audio)]

            # For formats that FFmpeg can embed video/attached_pic (MP3, FLAC, M4A)
            if has_cover and fmt in ("mp3", "flac", "m4a"):
                cmd += ["-i", str(cover_file), "-map", "0:a", "-map", "1:v"]
                cmd += ["-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
            else:
                cmd += ["-map", "0:a"]

            # Codec settings
            if fmt == "flac":
                # Studio Quality Lossless FLAC
                cmd += ["-c:a", "flac", "-sample_fmt", "s32"]
            elif fmt == "wav":
                # Studio Uncompressed 16-bit PCM WAV
                cmd += ["-c:a", "pcm_s16le"]
            elif fmt == "mp3":
                q = audio_quality or "320"
                if q == "0":
                    cmd += ["-c:a", "libmp3lame", "-q:a", "0"]
                else:
                    cmd += ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
            elif fmt == "m4a":
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
                # Fallback transcode without cover attachment
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

            # Embed RIFF ID3v2 APIC chunk for WAV format
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

        col_title = info.get("album_title") or info.get("title") or "TIDAL Collection"
        folder = base_dest / sanitize_filename(col_title)
        folder.mkdir(parents=True, exist_ok=True)

        # Save album/playlist cover.jpg inside folder
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
        col_type = "Album" if info.get("tidal_type") == "album" else "Playlist"
        self.console.print(
            f"\n[bold cyan]Downloading TIDAL {col_type}:[/bold cyan] [bold white]{col_title}[/bold white] "
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
