"""Spotify track and playlist downloader with best-quality audio extraction.

Extracts track/playlist metadata from Spotify embed endpoints, resolves the highest
fidelity audio match via yt-dlp, and transcodes via FFmpeg to Lossless FLAC, Lossless
WAV, 320 kbps MP3, M4A, or OPUS with embedded metadata and album cover art.
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

from simple_downloader.utils import sanitize_filename

SPOTIFY_URL_REGEX = re.compile(
    r"^(?:https?://(?:open\.)?spotify\.com/(?:intl-[a-zA-Z_-]+/)?(track|playlist|album)/([a-zA-Z0-9]+)"
    r"|spotify:(track|playlist|album):([a-zA-Z0-9]+))"
)


def is_spotify_url(url: str) -> bool:
    """Check if the given URL is a Spotify track, playlist, or album link."""
    if not url or not isinstance(url, str):
        return False
    return bool(SPOTIFY_URL_REGEX.search(url.strip()))


def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract entity type (track, playlist, album) and ID from a Spotify URL."""
    match = SPOTIFY_URL_REGEX.search(url.strip())
    if not match:
        return None
    groups = match.groups()
    if groups[0] and groups[1]:
        return groups[0].lower(), groups[1]
    if groups[2] and groups[3]:
        return groups[2].lower(), groups[3]
    return None


class SpotifyDownloader:
    """Downloader and metadata extractor for Spotify media."""

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract metadata for a Spotify track, playlist, or album."""
        parsed = parse_spotify_url(url)
        if not parsed:
            return None

        entity_type, entity_id = parsed

        # 1. Fetch the Spotify embed page which embeds __NEXT_DATA__
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
        try:
            resp = requests.get(embed_url, headers=self.DEFAULT_HEADERS, timeout=15)
            if resp.status_code == 200:
                match = re.search(
                    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                    resp.text,
                    re.DOTALL,
                )
                if match:
                    data = json.loads(match.group(1))
                    entity = (
                        data.get("props", {})
                        .get("pageProps", {})
                        .get("state", {})
                        .get("data", {})
                        .get("entity", {})
                    )
                    if entity:
                        return self._parse_entity(entity, entity_type, entity_id, url)
        except Exception as e:
            self.console.print(f"[yellow]Spotify embed fetch warning: {e}[/yellow]")

        # 2. Fallback: Spotify oEmbed endpoint for basic metadata
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={url}"
            resp = requests.get(oembed_url, headers=self.DEFAULT_HEADERS, timeout=10)
            if resp.status_code == 200:
                oe = resp.json()
                title = oe.get("title", "Spotify Media")
                thumbnail = oe.get("thumbnail_url")
                is_pl = entity_type in ("playlist", "album")
                return {
                    "id": entity_id,
                    "title": title,
                    "track_title": title,
                    "artist": "Spotify Artist",
                    "album": title if is_pl else None,
                    "duration": None,
                    "upload_date": None,
                    "thumbnail": thumbnail,
                    "is_spotify": True,
                    "is_playlist": is_pl,
                    "spotify_type": entity_type,
                    "url": url,
                    "entries": [] if is_pl else None,
                }
        except Exception:
            pass

        return None

    def _parse_entity(
        self, entity: Dict[str, Any], entity_type: str, entity_id: str, url: str
    ) -> Dict[str, Any]:
        """Parse raw __NEXT_DATA__ entity into normalized metadata."""
        if entity_type == "track":
            title = entity.get("name") or entity.get("title") or "Unknown Track"
            artists_list = [a.get("name") for a in entity.get("artists", []) if a.get("name")]
            artist_str = ", ".join(artists_list) if artists_list else "Unknown Artist"
            album_name = entity.get("album", {}).get("name")
            duration_ms = entity.get("duration") or 0
            duration_sec = int(duration_ms // 1000) if duration_ms else None

            # Release date
            release_date = None
            rd = entity.get("releaseDate")
            if isinstance(rd, dict) and rd.get("isoString"):
                release_date = rd["isoString"][:10]

            # Cover art
            cover_url = None
            images = entity.get("visualIdentity", {}).get("image", [])
            if images and isinstance(images, list):
                # Pick largest
                images_sorted = sorted(images, key=lambda x: x.get("maxHeight", 0), reverse=True)
                cover_url = images_sorted[0].get("url")

            full_title = f"{artist_str} - {title}"
            return {
                "id": entity_id,
                "title": full_title,
                "track_title": title,
                "artist": artist_str,
                "album": album_name,
                "duration": duration_sec,
                "upload_date": release_date,
                "thumbnail": cover_url,
                "is_spotify": True,
                "is_playlist": False,
                "spotify_type": "track",
                "url": url,
            }

        else:
            # Playlist or Album
            title = entity.get("name") or entity.get("title") or "Spotify Playlist"
            subtitle = entity.get("subtitle") or entity.get("authors") or ""
            cover_url = None
            images = entity.get("visualIdentity", {}).get("image", [])
            if images and isinstance(images, list):
                images_sorted = sorted(images, key=lambda x: x.get("maxHeight", 0), reverse=True)
                cover_url = images_sorted[0].get("url")

            raw_tracks = entity.get("trackList", [])
            parsed_tracks: List[Dict[str, Any]] = []

            for idx, t in enumerate(raw_tracks, 1):
                t_title = t.get("title") or t.get("name") or f"Track {idx}"
                t_artist = t.get("subtitle") or ""
                t_dur_ms = t.get("duration") or 0
                t_dur_sec = int(t_dur_ms // 1000) if t_dur_ms else None
                t_uri = t.get("uri") or ""
                t_id = t_uri.split(":")[-1] if ":" in t_uri else f"track_{idx}"
                t_url = f"https://open.spotify.com/track/{t_id}" if t_id else url

                parsed_tracks.append({
                    "id": t_id,
                    "title": f"{t_artist} - {t_title}" if t_artist else t_title,
                    "track_title": t_title,
                    "artist": t_artist or "Unknown Artist",
                    "album": title if entity_type == "album" else None,
                    "duration": t_dur_sec,
                    "track_number": idx,
                    "thumbnail": cover_url,
                    "is_spotify": True,
                    "is_playlist": False,
                    "spotify_type": "track",
                    "url": t_url,
                })

            return {
                "id": entity_id,
                "title": title,
                "uploader": subtitle,
                "thumbnail": cover_url,
                "is_spotify": True,
                "is_playlist": True,
                "playlist_count": len(parsed_tracks),
                "entries": parsed_tracks,
                "spotify_type": entity_type,
                "url": url,
            }

    def search_best_audio_match(
        self, artist: str, title: str, expected_duration: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Search and match the best audio stream using yt-dlp."""
        import yt_dlp

        # Clean title (remove featuring / remastered noise for cleaner query if needed)
        clean_title = re.sub(r"\s*-\s*(Remastered|20\d\d Remaster).*", "", title, flags=re.IGNORECASE)
        query = f"{artist} - {clean_title}"

        search_queries = [
            f"ytsearch5:{query} official audio",
            f"ytsearch5:{query} audio",
            f"ytsearch5:{query}",
        ]

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "noplaylist": True,
        }

        best_candidate = None
        best_score = float("inf")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for sq in search_queries:
                try:
                    res = ydl.extract_info(sq, download=False)
                    entries = res.get("entries", []) if res else []
                    if not entries:
                        continue

                    for entry in entries:
                        if not entry or not entry.get("id"):
                            continue

                        cand_title = (entry.get("title") or "").lower()
                        cand_dur = entry.get("duration")

                        # Duration difference penalty
                        dur_diff = 0
                        if expected_duration and cand_dur:
                            dur_diff = abs(cand_dur - expected_duration)

                        # Negative keywords penalty
                        penalty = 0
                        bad_keywords = ["live", "cover", "concert", "reaction", "karaoke", "instrumental", "parody"]
                        for bad in bad_keywords:
                            if bad in cand_title and bad not in title.lower():
                                penalty += 50

                        # Positive keywords bonus
                        if "audio" in cand_title or "topic" in (entry.get("uploader") or "").lower():
                            penalty -= 5

                        score = dur_diff + penalty
                        if score < best_score:
                            best_score = score
                            best_candidate = entry

                    if best_candidate and best_score <= 5:
                        # Found a near-perfect duration match!
                        break
                except Exception:
                    continue

        return best_candidate

    def download_track(
        self,
        info: Dict[str, Any],
        output_path: Optional[str] = None,
        output_dir: Optional[str] = "downloads",
        audio_format: str = "mp3",
        audio_quality: str = "320",
        rate_limit: Optional[int] = None,
        show_progress: bool = True,
        track_number: Optional[int] = None,
        total_tracks: Optional[int] = None,
    ) -> str:
        """Download and transcode a single Spotify track."""
        import yt_dlp

        title = info.get("track_title") or info.get("title") or "Track"
        artist = info.get("artist") or "Artist"
        album = info.get("album") or ""
        expected_dur = info.get("duration")
        cover_url = info.get("thumbnail")
        release_date = info.get("upload_date") or ""

        dest_dir = Path(output_dir or "downloads").expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Determine target file path
        if output_path:
            p = Path(output_path).expanduser()
            target_path = p.resolve() if (p.is_absolute() or len(p.parts) > 1) else (dest_dir / p.name)
        else:
            clean_artist = sanitize_filename(artist)
            clean_title = sanitize_filename(title)
            if track_number is not None:
                fname = f"{track_number:02d} - {clean_artist} - {clean_title}.{audio_format.lower()}"
            else:
                fname = f"{clean_artist} - {clean_title}.{audio_format.lower()}"
            target_path = dest_dir / fname

        # 1. Search for best audio match
        if show_progress:
            self.console.print(f"[cyan]Searching best audio match for:[/cyan] [bold white]{artist} - {title}[/bold white]")

        candidate = self.search_best_audio_match(artist, title, expected_dur)
        if not candidate or not candidate.get("id"):
            raise RuntimeError(f"Could not find matching audio source for '{artist} - {title}' on YouTube.")

        video_id = candidate.get("id")
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # 2. Download raw audio using yt-dlp into a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="vdown_spotify_")
        try:
            raw_audio_template = os.path.join(temp_dir, "audio.%(ext)s")
            ydl_opts: Dict[str, Any] = {
                "format": "bestaudio/best",
                "outtmpl": raw_audio_template,
                "quiet": not show_progress,
                "no_warnings": True,
                "noplaylist": True,
            }
            if rate_limit:
                ydl_opts["ratelimit"] = rate_limit

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Locate downloaded raw audio file
            downloaded_files = [
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if os.path.isfile(os.path.join(temp_dir, f)) and not f.endswith(".jpg")
            ]
            if not downloaded_files:
                raise RuntimeError("Failed to retrieve raw audio stream.")
            raw_audio_file = downloaded_files[0]

            # 3. Download album cover art if available
            cover_file = None
            if cover_url:
                try:
                    c_resp = requests.get(cover_url, headers=self.DEFAULT_HEADERS, timeout=10)
                    if c_resp.status_code == 200 and len(c_resp.content) > 0:
                        cover_file = os.path.join(temp_dir, "cover.jpg")
                        with open(cover_file, "wb") as cf:
                            cf.write(c_resp.content)
                except Exception:
                    cover_file = None

            # 4. Transcode to requested format with FFmpeg
            if not shutil.which("ffmpeg"):
                # If ffmpeg is missing, simply move the raw file
                shutil.move(raw_audio_file, str(target_path))
                return str(target_path)

            cmd = ["ffmpeg", "-y", "-i", raw_audio_file]
            has_cover = bool(cover_file and os.path.exists(cover_file))

            if has_cover and audio_format.lower() in ("mp3", "flac", "m4a"):
                cmd += ["-i", cover_file, "-map", "0:a", "-map", "1:v"]
            else:
                cmd += ["-map", "0:a"]

            # Codec & Bitrate parameters
            fmt = audio_format.lower()
            if fmt == "flac":
                cmd += ["-c:a", "flac"]
                if has_cover:
                    cmd += ["-c:v", "mjpeg", "-disposition:v:0", "attached_pic"]
            elif fmt == "wav":
                cmd += ["-c:a", "pcm_s16le"]
            elif fmt == "mp3":
                q = audio_quality.rstrip("kK") if audio_quality else "320"
                if q == "0":
                    cmd += ["-c:a", "libmp3lame", "-q:a", "0"]
                else:
                    cmd += ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
                if has_cover:
                    cmd += [
                        "-c:v", "mjpeg",
                        "-id3v2_version", "3",
                        "-metadata:s:v", "title=Album cover",
                        "-metadata:s:v", "comment=Cover (front)",
                    ]
            elif fmt in ("m4a", "aac"):
                q = audio_quality.rstrip("kK") if audio_quality else "320"
                cmd += ["-c:a", "aac", "-b:a", f"{q}k"]
                if has_cover:
                    cmd += ["-c:v", "copy", "-disposition:v:0", "attached_pic"]
            elif fmt == "opus":
                q = audio_quality.rstrip("kK") if audio_quality else "320"
                cmd += ["-c:a", "libopus", "-b:a", f"{q}k"]
            else:
                cmd += ["-c:a", "copy"]

            # Metadata tags
            cmd += [
                "-metadata", f"title={title}",
                "-metadata", f"artist={artist}",
            ]
            if album:
                cmd += ["-metadata", f"album={album}"]
            if release_date:
                year = release_date[:4]
                cmd += ["-metadata", f"date={year}"]
            if track_number is not None:
                tr_str = f"{track_number}/{total_tracks}" if total_tracks else str(track_number)
                cmd += ["-metadata", f"track={tr_str}"]

            cmd.append(str(target_path))

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                self.console.print(f"[yellow]FFmpeg warning: {proc.stderr}. Falling back to standard conversion...[/yellow]")
                # Fallback conversion without cover art if cover muxing failed
                fallback_cmd = ["ffmpeg", "-y", "-i", raw_audio_file, "-vn"]
                if fmt == "flac":
                    fallback_cmd += ["-c:a", "flac"]
                elif fmt == "wav":
                    fallback_cmd += ["-c:a", "pcm_s16le"]
                elif fmt == "mp3":
                    q = audio_quality.rstrip("kK") if audio_quality else "320"
                    fallback_cmd += ["-c:a", "libmp3lame", "-b:a", f"{q}k"]
                fallback_cmd.append(str(target_path))
                subprocess.run(fallback_cmd, capture_output=True, text=True)

            return str(target_path)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def download_playlist(
        self,
        info: Dict[str, Any],
        output_dir: Optional[str] = "downloads",
        audio_format: str = "mp3",
        audio_quality: str = "320",
        playlist_items: Optional[str] = None,
        rate_limit: Optional[int] = None,
        show_progress: bool = True,
    ) -> str:
        """Download all or selected tracks from a Spotify playlist or album."""
        pl_title = info.get("title") or "Spotify Playlist"
        entries = info.get("entries") or []

        if not entries:
            raise RuntimeError(f"No tracks found in Spotify playlist '{pl_title}'.")

        # Parse playlist items (e.g. 1-10, 1,3,5)
        selected_indices = set()
        if playlist_items:
            for part in playlist_items.split(","):
                part = part.strip()
                if "-" in part:
                    start_s, end_s = part.split("-", 1)
                    try:
                        start_i = int(start_s)
                        end_i = int(end_s)
                        selected_indices.update(range(start_i, end_i + 1))
                    except ValueError:
                        pass
                else:
                    try:
                        selected_indices.add(int(part))
                    except ValueError:
                        pass

        selected_entries = []
        for idx, entry in enumerate(entries, 1):
            if not selected_indices or idx in selected_indices:
                selected_entries.append((idx, entry))

        if not selected_entries:
            raise RuntimeError(f"No tracks matched the selection '--playlist-items {playlist_items}'.")

        base_dest = Path(output_dir or "downloads").expanduser().resolve()
        playlist_folder = base_dest / sanitize_filename(pl_title)
        playlist_folder.mkdir(parents=True, exist_ok=True)

        total_selected = len(selected_entries)
        self.console.print(
            f"\n[bold cyan]Downloading Spotify Playlist:[/bold cyan] [bold white]{pl_title}[/bold white] "
            f"({total_selected} tracks) -> [underline]{playlist_folder}[/underline]\n"
        )

        downloaded_paths = []
        for count, (track_idx, track_info) in enumerate(selected_entries, 1):
            t_name = track_info.get("title") or f"Track {track_idx}"
            self.console.print(
                f"[bold yellow][{count}/{total_selected}][/bold yellow] Processing [white]{t_name}[/white]..."
            )
            try:
                res_path = self.download_track(
                    info=track_info,
                    output_dir=str(playlist_folder),
                    audio_format=audio_format,
                    audio_quality=audio_quality,
                    rate_limit=rate_limit,
                    show_progress=show_progress,
                    track_number=track_idx,
                    total_tracks=len(entries),
                )
                downloaded_paths.append(res_path)
            except Exception as e:
                self.console.print(f"[bold red]Failed to download '{t_name}':[/bold red] {e}")

        return str(playlist_folder)
