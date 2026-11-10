"""Dedicated YouTube module supporting videos, playlists, and YouTube Shorts."""

import logging
import re
import urllib.parse
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Domains associated with YouTube
YOUTUBE_DOMAINS = [
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "m.youtube.com",
    "www.youtube.com",
    "music.youtube.com",
]

# Patterns for extracting video ID from YouTube URLs
SHORTS_REGEX = re.compile(
    r"(?:https?://)?(?:(?:www|m)\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    re.IGNORECASE,
)

YOUTUBE_ID_PATTERNS = [
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(r"youtube\.com/watch\?(?:.*&)?v=([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(r"youtu\.be/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(r"youtube\.com/embed/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(r"youtube\.com/v/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
    re.compile(r"youtube\.com/live/([a-zA-Z0-9_-]{11})", re.IGNORECASE),
]


def is_youtube_url(url: str) -> bool:
    """Check if the URL belongs to YouTube (standard video, shorts, playlist, music, etc.)."""
    if not url:
        return False
    u = url.lower()
    return any(domain in u for domain in YOUTUBE_DOMAINS)


def is_youtube_shorts_url(url: str) -> bool:
    """Check if the URL is specifically a YouTube Shorts link."""
    if not url:
        return False
    clean = url.strip().strip("'\"")
    return bool(SHORTS_REGEX.search(clean))


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract standard 11-character video ID from any YouTube URL (shorts, watch, youtu.be)."""
    if not url:
        return None
    clean = url.strip().strip("'\"")
    for pattern in YOUTUBE_ID_PATTERNS:
        match = pattern.search(clean)
        if match:
            return match.group(1)
    return None


def normalize_youtube_url(url: str) -> str:
    """Normalize YouTube URLs: strip tracking tokens (?si=..., ?feature=share) while preserving video ID and playlist.

    If it's a Shorts URL, normalizes it to a clean canonical shorts URL:
    https://www.youtube.com/shorts/{id}
    """
    if not url:
        return url
    clean = url.strip().strip("'\"")
    video_id = extract_youtube_id(clean)

    if is_youtube_shorts_url(clean) and video_id:
        return f"https://www.youtube.com/shorts/{video_id}"

    if video_id and ("watch" in clean or "youtu.be" in clean):
        parsed = urllib.parse.urlparse(clean)
        qs = urllib.parse.parse_qs(parsed.query)
        if "list" in qs:
            return f"https://www.youtube.com/watch?v={video_id}&list={qs['list'][0]}"
        return f"https://www.youtube.com/watch?v={video_id}"

    return clean


def to_watch_url(url_or_id: str) -> str:
    """Convert a YouTube Shorts URL or video ID into a standard watch URL."""
    vid = extract_youtube_id(url_or_id) or url_or_id.strip()
    return f"https://www.youtube.com/watch?v={vid}"


def to_shorts_url(url_or_id: str) -> str:
    """Convert a YouTube URL or video ID into a Shorts URL."""
    vid = extract_youtube_id(url_or_id) or url_or_id.strip()
    return f"https://www.youtube.com/shorts/{vid}"


def get_shorts_format_selector(quality: Optional[str] = "best") -> str:
    """Construct format selector optimized for YouTube Shorts (vertical 9:16 aspect ratio).

    For YouTube Shorts (vertical videos):
      - 1080p is 1080x1920 (width 1080, height 1920)
      - 720p is 720x1280 (width 720, height 1280)
      - 480p is 480x854 (width 480, height 854)
      - 360p is 360x640 (width 360, height 640)

    Using width<=1080 first guarantees 1080p vertical videos are selected properly,
    while falling back to height<=1080 if given a landscape video.
    """
    q = (quality or "best").lower()
    if q in ("4k", "2160p"):
        return "bestvideo[width<=2160]+bestaudio/bestvideo[height<=2160]+bestaudio/best[width<=2160]/best"
    elif q == "1440p":
        return "bestvideo[width<=1440]+bestaudio/bestvideo[height<=1440]+bestaudio/best[width<=1440]/best"
    elif q == "1080p":
        return "bestvideo[width<=1080]+bestaudio/bestvideo[height<=1080]+bestaudio/best[width<=1080]/best"
    elif q == "720p":
        return "bestvideo[width<=720]+bestaudio/bestvideo[height<=720]+bestaudio/best[width<=720]/best"
    elif q == "480p":
        return "bestvideo[width<=480]+bestaudio/bestvideo[height<=480]+bestaudio/best[width<=480]/best"
    elif q == "360p":
        return "bestvideo[width<=360]+bestaudio/bestvideo[height<=360]+bestaudio/best[width<=360]/best"
    elif q == "worst":
        return "worstvideo+worstaudio/worst"
    else:
        return "bestvideo+bestaudio/best"


class YouTubeDownloader:
    """Specialized handler for YouTube videos and Shorts with client-fallback handling."""

    def __init__(self):
        pass

    def get_info(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch video information with YouTube-specific anti-bot and client fallback options."""
        import yt_dlp
        from simple_downloader.engine import _build_base_ydl_opts

        clean_url = normalize_youtube_url(url)
        is_short = is_youtube_shorts_url(url)

        ydl_opts = _build_base_ydl_opts(
            browser=browser,
            cookie_file=cookie_file,
            proxy=proxy,
            user_agent=user_agent,
            referer=referer,
        )
        ydl_opts.update({
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web", "mweb", "ios"],
                }
            },
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(clean_url, download=False)
                if info:
                    w = info.get("width") or 0
                    h = info.get("height") or 0
                    duration = info.get("duration") or 0
                    if is_short or (h > w and 0 < duration <= 180):
                        info["is_youtube_shorts"] = True
                        info["is_short"] = True
                    return info
        except Exception as e:
            logger.debug(f"Direct yt-dlp extract failed on YouTube URL: {e}")
            if is_short:
                # Fallback: try watch URL variant if shorts route had issue
                watch_url = to_watch_url(clean_url)
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(watch_url, download=False)
                        if info:
                            info["is_youtube_shorts"] = True
                            info["is_short"] = True
                            return info
                except Exception:
                    pass
        return None
