"""Dedicated TikTok module supporting videos, photo carousels, and watermark-free downloads."""

import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from rich.console import Console

from simple_downloader.direct_downloader import DirectDownloader
from simple_downloader.progress import create_download_progress
from simple_downloader.utils import sanitize_filename, format_bytes, format_duration

console = Console()


def is_tiktok_url(url: str) -> bool:
    """Check if the URL is a TikTok video, photo, or short link."""
    if not url:
        return False
    u = url.lower()
    return any(domain in u for domain in [
        "tiktok.com",
        "vt.tiktok.com",
        "vm.tiktok.com",
        "tiktokv.com",
    ])


class TikTokDownloader:
    """Specialized downloader for TikTok supporting watermark-free video and photo posts."""

    API_URL = "https://www.tikwm.com/api/"

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }

    def get_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch media details for a TikTok URL without watermark."""
        try:
            resp = requests.post(
                self.API_URL,
                data={"url": url, "hd": 1},
                headers=self.headers,
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0 or not data.get("data"):
                return None

            raw = data["data"]
            author_data = raw.get("author") or {}
            author = author_data.get("nickname") or author_data.get("unique_id") or "TikTok"
            video_id = str(raw.get("id") or "media")

            raw_title = (raw.get("title") or "").strip()
            music_info = raw.get("music_info") or {}
            music_title = (music_info.get("title") or "").strip()

            # Accurate title resolution
            if raw_title:
                display_title = raw_title
            elif music_title:
                display_title = f"{author} - {music_title}"
            else:
                display_title = f"TikTok - {author} [{video_id}]"

            # Accurate duration resolution
            duration = raw.get("duration") or 0
            if duration == 0 and music_info.get("duration"):
                duration = music_info.get("duration")

            # Accurate upload date resolution
            create_time = raw.get("create_time")
            upload_date = None
            if create_time:
                try:
                    upload_date = datetime.fromtimestamp(create_time).strftime("%Y-%m-%d")
                except Exception:
                    pass

            # File size
            file_size = raw.get("hd_size") or raw.get("size")
            if file_size == 0:
                file_size = None

            is_photo_post = bool(raw.get("images"))
            video_url = raw.get("hdplay") or raw.get("play")
            music_url = raw.get("music") or raw.get("play")
            images = raw.get("images") or []

            formats = []
            if not is_photo_post and video_url:
                formats.append({
                    "format_id": "no-watermark-hd",
                    "ext": "mp4",
                    "resolution": "HD (No Watermark)",
                    "fps": None,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "filesize": file_size,
                    "tbr": None,
                    "url": video_url,
                })
            elif is_photo_post:
                formats.append({
                    "format_id": "slideshow-mp4",
                    "ext": "mp4",
                    "resolution": f"Photo Slideshow ({len(images)} slides + audio)",
                    "fps": None,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "filesize": None,
                    "tbr": None,
                })

            if music_url:
                formats.append({
                    "format_id": "audio-only",
                    "ext": "mp3",
                    "resolution": "Audio Soundtrack Only",
                    "fps": None,
                    "vcodec": None,
                    "acodec": "mp3",
                    "filesize": None,
                    "tbr": 192,
                    "url": music_url,
                })

            return {
                "id": video_id,
                "title": display_title,
                "raw_title": raw_title,
                "author": author,
                "uploader": author,
                "duration": duration,
                "upload_date": upload_date,
                "view_count": raw.get("play_count"),
                "filesize": file_size,
                "is_photo": is_photo_post,
                "images": images,
                "video_url": video_url,
                "music_url": music_url,
                "is_direct": False,
                "is_tiktok": True,
                "formats": formats,
            }

        except Exception:
            return None

    def download(
        self,
        info: Dict[str, Any],
        output_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        audio_only: bool = False,
        audio_format: str = "mp3",
        rate_limit: Optional[int] = None,
        show_progress: bool = True,
    ) -> str:
        """Download TikTok media without watermark and with live progress feedback."""
        dest_dir = Path(output_dir or ".").expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        is_photo = info.get("is_photo", False)
        author = info.get("author") or "TikTok"
        raw_t = (info.get("raw_title") or "").strip()
        disp_t = (info.get("title") or "").strip()
        if raw_t:
            name_part = raw_t if raw_t.lower().startswith(author.lower()) else f"{author} - {raw_t}"
        elif disp_t:
            name_part = disp_t if disp_t.lower().startswith(author.lower()) else f"{author} - {disp_t}"
        else:
            name_part = f"{author} - {info.get('id', 'video')}"
        clean_name = sanitize_filename(f"[TikTok] {name_part}")

        # Case 1: Audio Only
        if audio_only:
            music_url = info.get("music_url") or info.get("video_url")
            if not music_url:
                raise RuntimeError("No audio stream available for this TikTok post.")

            target_filename = f"{clean_name}.{audio_format}" if not output_path else output_path
            target_path = dest_dir / Path(target_filename).name

            downloader = DirectDownloader(rate_limit=rate_limit)
            return downloader.download(
                url=music_url,
                output_path=str(target_path),
                output_dir=str(dest_dir),
                show_progress=show_progress,
            )

        # Case 2: Standard Video without watermark
        if not is_photo:
            video_url = info.get("video_url")
            if not video_url:
                raise RuntimeError("No watermark-free video URL available for this TikTok.")

            target_filename = f"{clean_name}.mp4" if not output_path else output_path
            target_path = dest_dir / Path(target_filename).name

            downloader = DirectDownloader(rate_limit=rate_limit)
            return downloader.download(
                url=video_url,
                output_path=str(target_path),
                output_dir=str(dest_dir),
                expected_size=info.get("filesize"),
                show_progress=show_progress,
            )

        # Case 3: Photo post / Carousel with audio
        images = info.get("images", [])
        music_url = info.get("music_url")
        if not images:
            raise RuntimeError("No images found in TikTok photo post.")

        target_filename = f"{clean_name}.mp4" if not output_path else output_path
        target_path = dest_dir / Path(target_filename).name

        temp_workspace = tempfile.mkdtemp(prefix="vdown_tiktok_")
        try:
            local_images = []
            progress = create_download_progress(show_progress=show_progress)

            with progress:
                # 1. Download all slide images with progress
                for idx, img_url in enumerate(images):
                    img_path = Path(temp_workspace) / f"slide_{idx:03d}.jpeg"
                    slide_label = f"Slide {idx + 1}/{len(images)}" if len(images) > 1 else "Photo Slide"
                    task_id = progress.add_task(f"Downloading {slide_label}...", total=None)

                    r_img = requests.get(img_url, headers=self.headers, stream=True, timeout=15)
                    r_img.raise_for_status()
                    total_img = int(r_img.headers.get("content-length", 0)) or None
                    progress.update(task_id, total=total_img)

                    downloaded = 0
                    t0 = time.time()
                    last_time = t0
                    last_bytes = 0

                    with open(img_path, "wb") as f:
                        for chunk in r_img.iter_content(chunk_size=16384):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            dt = now - last_time
                            if dt >= 0.2:
                                speed = (downloaded - last_bytes) / dt
                                last_time = now
                                last_bytes = downloaded
                                eta = (total_img - downloaded) / speed if total_img and speed > 0 else None
                                progress.update(task_id, completed=downloaded, speed=speed, eta=eta)
                            else:
                                progress.update(task_id, completed=downloaded)

                    progress.update(task_id, description=f"[bold green]✔ {slide_label} Downloaded[/bold green]")
                    local_images.append(img_path)

                # 2. Download soundtrack audio with progress
                audio_path = Path(temp_workspace) / "audio.mp3"
                if music_url:
                    task_aud = progress.add_task("Downloading Soundtrack...", total=None)
                    r_aud = requests.get(music_url, headers=self.headers, stream=True, timeout=15)
                    r_aud.raise_for_status()
                    total_aud = int(r_aud.headers.get("content-length", 0)) or None
                    progress.update(task_aud, total=total_aud)

                    downloaded = 0
                    t0 = time.time()
                    last_time = t0
                    last_bytes = 0

                    with open(audio_path, "wb") as f:
                        for chunk in r_aud.iter_content(chunk_size=16384):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            dt = now - last_time
                            if dt >= 0.2:
                                speed = (downloaded - last_bytes) / dt
                                last_time = now
                                last_bytes = downloaded
                                eta = (total_aud - downloaded) / speed if total_aud and speed > 0 else None
                                progress.update(task_aud, completed=downloaded, speed=speed, eta=eta)
                            else:
                                progress.update(task_aud, completed=downloaded)

                    progress.update(task_aud, description="[bold green]✔ Audio Soundtrack Downloaded[/bold green]")

            # 3. Assemble vertical HD video with audio using ffmpeg
            with console.status("[bold cyan]Assembling vertical HD video with audio...[/bold cyan]"):
                if len(local_images) == 1:
                    cmd = [
                        "ffmpeg", "-y",
                        "-loop", "1", "-i", str(local_images[0]),
                    ]
                    if audio_path.exists():
                        cmd += ["-i", str(audio_path)]
                    cmd += [
                        "-c:v", "libx264", "-tune", "stillimage",
                        "-pix_fmt", "yuv420p",
                    ]
                    if audio_path.exists():
                        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
                    cmd.append(str(target_path))
                else:
                    duration_per_slide = 3.0
                    concat_list = Path(temp_workspace) / "slides.txt"
                    with open(concat_list, "w", encoding="utf-8") as f:
                        for img in local_images:
                            f.write(f"file '{img.name}'\n")
                            f.write(f"duration {duration_per_slide}\n")
                        f.write(f"file '{local_images[-1].name}'\n")

                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "concat", "-safe", "0",
                        "-i", str(concat_list),
                    ]
                    if audio_path.exists():
                        cmd += ["-i", str(audio_path)]
                    cmd += [
                        "-c:v", "libx264",
                        "-pix_fmt", "yuv420p",
                    ]
                    if audio_path.exists():
                        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
                    cmd.append(str(target_path))

                proc = subprocess.run(cmd, capture_output=True, text=True, cwd=temp_workspace)
                if proc.returncode != 0:
                    raise RuntimeError(f"FFmpeg failed to create slideshow video: {proc.stderr}")

            return str(target_path)

        finally:
            shutil.rmtree(temp_workspace, ignore_errors=True)
