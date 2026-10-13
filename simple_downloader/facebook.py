"""Dedicated Facebook module supporting videos, reels, and mobile share links."""

import re
import urllib.parse
from typing import Optional, Dict, Any, List
import requests
import yt_dlp

from simple_downloader.utils import sanitize_filename


def is_facebook_url(url: str) -> bool:
    """Check if the URL belongs to Facebook (videos, reels, watch, or share links)."""
    if not url:
        return False
    u = url.lower()
    return any(domain in u for domain in [
        "facebook.com",
        "fb.watch",
        "fb.gg",
        "m.facebook.com",
        "web.facebook.com",
    ])


def normalize_facebook_url(url: str) -> str:
    """Normalize Facebook mobile share links, shortlinks, and tracking parameters."""
    if not url:
        return url

    clean_url = url.strip().strip("'\"")

    # 1. Expand /share/r/<token> into standard reel URL
    m_reel = re.search(r"facebook\.com/share/r/([a-zA-Z0-9_-]+)", clean_url, re.IGNORECASE)
    if m_reel:
        token = m_reel.group(1)
        if token.isdigit():
            return f"https://www.facebook.com/reel/{token}/"

    # 2. Expand /share/v/<token> into standard watch URL
    m_video = re.search(r"facebook\.com/share/v/([a-zA-Z0-9_-]+)", clean_url, re.IGNORECASE)
    if m_video:
        token = m_video.group(1)
        if token.isdigit():
            return f"https://www.facebook.com/watch/?v={token}"

    # 3. For shortlinks like fb.watch or alphanumeric share links, follow redirects
    if "fb.watch" in clean_url.lower() or "/share/r/" in clean_url.lower() or "/share/v/" in clean_url.lower():
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Mode": "navigate",
            }
            resp = requests.get(clean_url, headers=headers, allow_redirects=True, timeout=8)
            final_url = resp.url
            if final_url:
                parsed = urllib.parse.urlparse(final_url)
                if "reel/" in parsed.path:
                    reel_m = re.search(r"/reel/([a-zA-Z0-9_-]+)", parsed.path)
                    if reel_m:
                        return f"https://www.facebook.com/reel/{reel_m.group(1)}/"
                elif "watch" in parsed.path:
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "v" in qs:
                        return f"https://www.facebook.com/watch/?v={qs['v'][0]}"
                elif "story.php" in parsed.path:
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "story_fbid" in qs:
                        return f"https://www.facebook.com/watch/?v={qs['story_fbid'][0]}"
                return final_url
        except Exception:
            pass

    return clean_url


class FacebookDownloader:
    """Specialized downloader for Facebook videos and reels."""

    COMMON_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, headers: Optional[dict] = None):
        self.headers = headers or self.COMMON_HEADERS

    def get_info(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Extract metadata and formats for Facebook video/reel."""
        normalized_url = normalize_facebook_url(url)

        # 1. Try yt-dlp first
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
        }
        if browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(normalized_url, download=False)
                if info and info.get("formats"):
                    info["is_facebook"] = True
                    info["normalized_url"] = normalized_url
                    return info
        except Exception:
            pass

        # 2. Fallback to direct HTML stream extraction
        try:
            direct_info = self._extract_direct_streams(normalized_url)
            if direct_info:
                return direct_info
        except Exception:
            pass

        return None

    def _extract_direct_streams(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract stream URLs directly from Facebook HTML without requiring login."""
        variants = [url]
        target_id = None
        reel_id_m = re.search(r"reel/([a-zA-Z0-9_-]+)", url)
        if reel_id_m:
            target_id = reel_id_m.group(1)
        else:
            v_m = re.search(r"[?&]v=([a-zA-Z0-9_-]+)", url)
            if v_m:
                target_id = v_m.group(1)
            else:
                s_m = re.search(r"story_fbid=([a-zA-Z0-9_-]+)", url)
                if s_m:
                    target_id = s_m.group(1)
                else:
                    sr_m = re.search(r"share/r/([a-zA-Z0-9_-]+)", url)
                    if sr_m:
                        target_id = sr_m.group(1)
                    else:
                        sv_m = re.search(r"share/v/([a-zA-Z0-9_-]+)", url)
                        if sv_m:
                            target_id = sv_m.group(1)

        if target_id:
            variants.append(f"https://m.facebook.com/watch/?v={target_id}&_rdr")
            variants.append(f"https://www.facebook.com/reel/{target_id}/")
            variants.append(f"https://www.facebook.com/watch/?v={target_id}")
            variants.append(f"https://m.facebook.com/story.php?story_fbid={target_id}")
            variants.append(f"https://m.facebook.com/share/r/{target_id}/")

        for page_url in variants:
            try:
                resp = requests.get(page_url, headers=self.headers, timeout=12)
                html = resp.text

                hd_matches = (
                    re.findall(r"\"browser_native_hd_url\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"\"playable_url_quality_hd\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"hd_src\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"\"hd_src_no_ratelimit\"\s*:\s*\"([^\"]+)\"", html)
                )
                sd_matches = (
                    re.findall(r"\"browser_native_sd_url\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"\"playable_url\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"sd_src\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"\"sd_src_no_ratelimit\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"<meta\s+(?:property|name)=[\"'](?:og:video|og:video:url|og:video:secure_url)[\"']\s+content=[\"']([^\"']+)[\"']", html)
                    or re.findall(r"\"video_url\"\s*:\s*\"([^\"]+)\"", html)
                    or re.findall(r"(https?:\\/\\/[a-zA-Z0-9.-]*fbcdn\.net\\/[^\"'\s]+\.mp4[^\"'\s]*)", html)
                    or re.findall(r"(https?://[a-zA-Z0-9.-]*fbcdn\.net/[^\"'\s]+\.mp4[^\"'\s]*)", html)
                )

                if not hd_matches and not sd_matches:
                    continue

                def decode_json_url(u: str) -> str:
                    return u.replace(r"\/", "/").replace(r"\u0026", "&").replace("&amp;", "&")

                hd_url = decode_json_url(hd_matches[0]) if hd_matches else None
                sd_url = decode_json_url(sd_matches[0]) if sd_matches else None

                import html as html_lib
                title_matches = re.findall(r"<meta\s+(?:property|name)=[\"']og:title[\"']\s+content=[\"']([^\"']+)[\"']", html)
                title = html_lib.unescape(title_matches[0].strip()) if title_matches else "Facebook Video"
                title = sanitize_filename(title)

                image_matches = re.findall(r"<meta\s+(?:property|name)=[\"']og:image[\"']\s+content=[\"']([^\"']+)[\"']", html)
                thumbnail = image_matches[0] if image_matches else None

                formats = []
                if hd_url:
                    formats.append({
                        "format_id": "hd",
                        "format_note": "HD Video",
                        "ext": "mp4",
                        "resolution": "HD (720p/1080p)",
                        "url": hd_url,
                        "vcodec": "h264",
                        "acodec": "aac",
                    })
                if sd_url:
                    formats.append({
                        "format_id": "sd",
                        "format_note": "SD Video",
                        "ext": "mp4",
                        "resolution": "SD (Standard)",
                        "url": sd_url,
                        "vcodec": "h264",
                        "acodec": "aac",
                    })

                primary_url = hd_url or sd_url
                formats.append({
                    "format_id": "audio-only",
                    "format_note": "Audio Soundtrack",
                    "ext": "mp3",
                    "resolution": "Audio Only",
                    "url": primary_url,
                    "vcodec": "none",
                    "acodec": "mp3",
                })

                return {
                    "id": f"fb_{abs(hash(url)) % 100000000}",
                    "title": title,
                    "url": primary_url,
                    "thumbnail": thumbnail,
                    "uploader": "Facebook",
                    "is_direct": True,
                    "is_playlist": False,
                    "is_facebook": True,
                    "formats": formats,
                }
            except Exception:
                continue

        return None
