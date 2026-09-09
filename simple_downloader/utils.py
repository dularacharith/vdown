"""Utility functions for simple-downloader."""

import base64
import os
import re
import shutil
import struct
import subprocess
import urllib.parse
from pathlib import Path
from typing import Optional, Dict


def format_bytes(size: Optional[float]) -> str:
    """Format byte size into human readable string."""
    if size is None or size < 0:
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds into HH:MM:SS or MM:SS."""
    if seconds is None or seconds < 0:
        return "Unknown"
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    remaining_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{remaining_secs:02d}"
    return f"{minutes:02d}:{remaining_secs:02d}"


WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename to be safe on all operating systems (Windows, Linux, macOS)."""
    if not filename:
        return "download"
    # Remove directory traversal and illegal characters
    cleaned = re.sub(r'[\\/*?:"<>|\0]', "_", filename)
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "download"
    # Truncate if too long while keeping extension
    if len(cleaned) > max_length:
        parts = cleaned.rsplit(".", 1)
        if len(parts) == 2 and len(parts[1]) <= 10:
            name_part, ext_part = parts
            cleaned = name_part[: max_length - len(ext_part) - 1] + "." + ext_part
        else:
            cleaned = cleaned[:max_length]
    # Check Windows reserved names
    base = cleaned.split(".")[0].upper()
    if base in WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def get_filename_from_headers_or_url(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """Extract a reasonable filename from HTTP headers or URL path."""
    if headers:
        cd = headers.get("content-disposition") or headers.get("Content-Disposition") or ""
        if cd:
            # Check for RFC 5987 / 6266 filename*
            match_star = re.search(r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
            if match_star:
                val = match_star.group(1).strip("\"' ")
                return sanitize_filename(urllib.parse.unquote(val))
            match = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.IGNORECASE)
            if not match:
                match = re.search(r"filename\s*=\s*([^;]+)", cd, re.IGNORECASE)
            if match:
                val = match.group(1).strip("\"' ")
                return sanitize_filename(urllib.parse.unquote(val))

    # Fallback to URL path
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path.rstrip("/"))
    basename = path.split("/")[-1] if path else ""
    if basename and "." in basename:
        return sanitize_filename(basename)

    # Determine extension from content-type if available
    ext = ""
    if headers:
        ct = (headers.get("content-type") or headers.get("Content-Type") or "").lower()
        if "video/mp4" in ct:
            ext = ".mp4"
        elif "video/webm" in ct:
            ext = ".webm"
        elif "video/x-matroska" in ct:
            ext = ".mkv"
        elif "audio/mpeg" in ct or "audio/mp3" in ct:
            ext = ".mp3"
        elif "audio/mp4" in ct or "audio/m4a" in ct:
            ext = ".m4a"

    if basename:
        base = sanitize_filename(basename)
        return f"{base}{ext}" if ext and not base.endswith(ext) else base

    return f"media_download{ext or '.bin'}"


MEDIA_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v",
    ".ts", ".3gp", ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg",
    ".opus", ".alac", ".wma"
}


def is_direct_media_url(url: str) -> bool:
    """Check if the URL path ends with a common media file extension."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    for ext in MEDIA_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


def parse_speed_limit(limit_str: Optional[str]) -> Optional[int]:
    """Parse speed limit string like '5M', '500K', '1000' to bytes per second."""
    if not limit_str:
        return None
    limit_str = limit_str.strip().upper()
    units = {"K": 1024, "KB": 1024, "M": 1024 * 1024, "MB": 1024 * 1024, "G": 1024 * 1024 * 1024, "GB": 1024 * 1024 * 1024}
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Z]*)$", limit_str)
    if not match:
        try:
            return int(limit_str)
        except ValueError:
            return None
    number, unit = match.groups()
    multiplier = units.get(unit, 1)
    return int(float(number) * multiplier)


def embed_wav_cover_art(wav_path: str, cover_path: str) -> bool:
    """Embed an ID3v2 APIC chunk containing the cover splash art into a WAV file."""
    try:
        with open(cover_path, "rb") as cf:
            img_data = cf.read()
        if not img_data:
            return False

        mime = b"image/png\x00" if img_data.startswith(b"\x89PNG") else b"image/jpeg\x00"
        apic_payload = b"\x00" + mime + b"\x03\x00" + img_data
        apic_frame = b"APIC" + struct.pack(">I", len(apic_payload)) + b"\x00\x00" + apic_payload
        id3_len = len(apic_frame)
        syncsafe_size = (
            ((id3_len >> 21) & 0x7F) << 24
            | ((id3_len >> 14) & 0x7F) << 16
            | ((id3_len >> 7) & 0x7F) << 8
            | (id3_len & 0x7F)
        )
        id3_tag = b"ID3\x03\x00\x00" + struct.pack(">I", syncsafe_size) + apic_frame
        id3_chunk = b"id3 " + struct.pack("<I", len(id3_tag)) + id3_tag
        if len(id3_tag) % 2 == 1:
            id3_chunk += b"\x00"

        with open(wav_path, "rb") as wf:
            wav_data = wf.read()

        if len(wav_data) < 12 or wav_data[:4] != b"RIFF" or wav_data[8:12] != b"WAVE":
            return False

        new_riff_size = len(wav_data) - 8 + len(id3_chunk)
        tagged_wav = wav_data[:4] + struct.pack("<I", new_riff_size) + wav_data[8:] + id3_chunk

        with open(wav_path, "wb") as wf:
            wf.write(tagged_wav)
        return True
    except Exception:
        return False


def build_vorbis_picture_block(cover_path: str) -> Optional[str]:
    """Build a base64-encoded METADATA_BLOCK_PICTURE for Vorbis/Opus comment embedding."""
    try:
        with open(cover_path, "rb") as cf:
            img_data = cf.read()
        if not img_data:
            return None

        mime = b"image/png" if img_data.startswith(b"\x89PNG") else b"image/jpeg"
        width, height = 640, 640
        if mime == b"image/jpeg" and len(img_data) > 4:
            idx = 2
            while idx < len(img_data) - 8:
                if img_data[idx] == 0xFF:
                    marker = img_data[idx + 1]
                    if marker in (0xC0, 0xC2):
                        height, width = struct.unpack(">HH", img_data[idx + 5 : idx + 9])
                        break
                    elif marker not in (0xD8, 0xD9, 0x00, 0xFF):
                        length = struct.unpack(">H", img_data[idx + 2 : idx + 4])[0]
                        idx += 2 + length
                        continue
                idx += 1
        elif mime == b"image/png" and len(img_data) >= 24:
            width, height = struct.unpack(">II", img_data[16:24])

        desc = b"Cover (front)"
        block = (
            struct.pack(">I", 3)
            + struct.pack(">I", len(mime))
            + mime
            + struct.pack(">I", len(desc))
            + desc
            + struct.pack(">IIII", width, height, 24, 0)
            + struct.pack(">I", len(img_data))
            + img_data
        )
        return base64.b64encode(block).decode("ascii")
    except Exception:
        return None


def attach_splash_art(media_path: str, thumbnail_path: Optional[str] = None) -> bool:
    """Attach/embed splash cover art into an audio or video file.

    Supports:
      - FLAC (.flac): Bit-perfect stream copy with attached_pic MJPEG
      - MP3 (.mp3): Bit-perfect stream copy with ID3v2.3 APIC front cover
      - WAV (.wav): Bit-perfect RIFF ID3v2 APIC chunk
      - M4A / AAC (.m4a, .aac): Bit-perfect stream copy with attached_pic
      - OPUS / OGG (.opus, .ogg): OggOpus metadata_block_picture via mutagen
      - MP4 / M4V / MOV (.mp4, .m4v, .mov): MP4 container cover stream copy
      - MKV (.mkv): Matroska cover attachment

    Cleans up standalone intermediate thumbnail images upon successful embedding.
    """
    if not media_path or not os.path.exists(media_path):
        return False

    p = Path(media_path)
    if p.is_dir():
        return False

    # If no thumbnail path given, find sibling image with same stem
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            candidate = p.with_suffix(ext)
            if candidate.exists() and candidate != p:
                thumbnail_path = str(candidate)
                break

    if not thumbnail_path or not os.path.exists(thumbnail_path):
        return False

    ext = p.suffix.lower()
    thumb_path = Path(thumbnail_path)

    # Ensure thumbnail is JPEG format for universal compatibility across media players
    cover_jpg = thumbnail_path
    temp_jpg = None
    if thumb_path.suffix.lower() not in (".jpg", ".jpeg"):
        temp_jpg = str(p.parent / f"{p.stem}_converted_cover.jpg")
        conv_res = subprocess.run(
            ["ffmpeg", "-y", "-i", thumbnail_path, "-frames:v", "1", temp_jpg],
            capture_output=True,
            text=True,
        )
        if conv_res.returncode == 0 and os.path.exists(temp_jpg):
            cover_jpg = temp_jpg

    success = False
    try:
        if ext == ".flac":
            tmp_out = str(p.parent / f"{p.stem}.tmp.flac")
            cmd = [
                "ffmpeg", "-y", "-i", str(p), "-i", cover_jpg,
                "-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-disposition:v:0", "attached_pic",
                tmp_out,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, str(p))
                success = True
            elif os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except Exception:
                    pass

        elif ext == ".mp3":
            tmp_out = str(p.parent / f"{p.stem}.tmp.mp3")
            cmd = [
                "ffmpeg", "-y", "-i", str(p), "-i", cover_jpg,
                "-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-id3v2_version", "3",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
                tmp_out,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, str(p))
                success = True
            elif os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except Exception:
                    pass

        elif ext == ".wav":
            success = embed_wav_cover_art(str(p), cover_jpg)

        elif ext in (".m4a", ".aac"):
            tmp_out = str(p.parent / f"{p.stem}.tmp.m4a")
            cmd = [
                "ffmpeg", "-y", "-i", str(p), "-i", cover_jpg,
                "-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-disposition:v:0", "attached_pic",
                tmp_out,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, str(p))
                success = True
            elif os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except Exception:
                    pass

        elif ext in (".opus", ".ogg"):
            try:
                from mutagen.oggopus import OggOpus
                from mutagen.flac import Picture
                audio = OggOpus(str(p))
                pic = Picture()
                with open(cover_jpg, "rb") as cf:
                    pic.data = cf.read()
                pic.type = 3
                pic.mime = "image/jpeg"
                pic.desc = "front cover"
                audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
                audio.save()
                success = True
            except Exception:
                pass

        elif ext in (".mp4", ".m4v", ".mov"):
            tmp_out = str(p.parent / f"{p.stem}.tmp.mp4")
            cmd = [
                "ffmpeg", "-y", "-i", str(p), "-i", cover_jpg,
                "-map", "0", "-map", "1",
                "-c", "copy",
                "-disposition:v:1", "attached_pic",
                tmp_out,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, str(p))
                success = True
            elif os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except Exception:
                    pass

        elif ext == ".mkv":
            tmp_out = str(p.parent / f"{p.stem}.tmp.mkv")
            cmd = [
                "ffmpeg", "-y", "-i", str(p),
                "-attach", cover_jpg,
                "-metadata:s:t", "mimetype=image/jpeg",
                "-metadata:s:t", "filename=cover.jpg",
                "-c", "copy",
                tmp_out,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
                os.replace(tmp_out, str(p))
                success = True
            elif os.path.exists(tmp_out):
                try:
                    os.remove(tmp_out)
                except Exception:
                    pass

        # Cleanup standalone thumbnail file if embedding succeeded
        if success:
            if os.path.exists(thumbnail_path) and thumbnail_path != media_path:
                try:
                    os.remove(thumbnail_path)
                except Exception:
                    pass

        return success

    finally:
        if temp_jpg and os.path.exists(temp_jpg):
            try:
                os.remove(temp_jpg)
            except Exception:
                pass

