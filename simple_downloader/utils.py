"""Utility functions for simple-downloader."""

import re
import urllib.parse
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


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """Sanitize filename to be safe on all operating systems."""
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
