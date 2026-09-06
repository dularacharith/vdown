"""Universal webpage scraper for embedded videos and streaming links."""

import re
import urllib.parse
from typing import List, Dict, Optional, Any
import requests


class WebpageVideoScraper:
    """Scrapes HTML pages for embedded video links, OpenGraph tags, HTML5 video, and streaming manifests."""

    COMMON_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def __init__(self, timeout: int = 15, headers: Optional[dict] = None):
        self.timeout = timeout
        self.headers = headers or self.COMMON_HEADERS

    def find_videos(self, page_url: str) -> List[Dict[str, Any]]:
        """Fetch webpage and extract potential video/media stream URLs."""
        try:
            resp = requests.get(page_url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            html = resp.text
        except Exception:
            return []

        candidates: List[Dict[str, Any]] = []
        seen_urls = set()

        def add_candidate(media_url: str, source: str, label: str = ""):
            if not media_url:
                return
            media_url = urllib.parse.urljoin(page_url, media_url.strip())
            # Basic validation
            if media_url in seen_urls or not media_url.startswith(("http://", "https://")):
                return
            seen_urls.add(media_url)
            candidates.append({
                "url": media_url,
                "source": source,
                "label": label or source,
            })

        # 1. OpenGraph & Twitter Card video tags
        og_matches = re.findall(
            r'<meta\s+(?:property|name)=["\'](?:og:video|og:video:url|og:video:secure_url|twitter:player:stream)["\']\s+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        for url in og_matches:
            add_candidate(url, "OpenGraph / Twitter Card", "Webpage Video Embed")

        # Reverse attribute order: content="..." property="..."
        og_reverse = re.findall(
            r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\'](?:og:video|og:video:url|og:video:secure_url|twitter:player:stream)["\']',
            html,
            re.IGNORECASE,
        )
        for url in og_reverse:
            add_candidate(url, "OpenGraph / Twitter Card", "Webpage Video Embed")

        # 2. HTML5 <video> and <source> tags
        video_srcs = re.findall(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for url in video_srcs:
            add_candidate(url, "HTML5 <video>", "Direct Video")

        source_srcs = re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        for url in source_srcs:
            add_candidate(url, "HTML5 <source>", "Direct Video Source")

        # 3. JSON-LD VideoObject metadata
        json_ld_matches = re.findall(r'"contentUrl"\s*:\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
        for url in json_ld_matches:
            add_candidate(url, "JSON-LD Metadata", "VideoObject contentUrl")

        # 4. Regex scan for streaming manifests (.m3u8, .mpd) in scripts or html
        m3u8_matches = re.findall(r'["\'](https?://[^"\']+\.m3u8[^"\']*)["\']', html, re.IGNORECASE)
        for url in m3u8_matches:
            add_candidate(url, "HLS Manifest", "HLS Playlist (.m3u8)")

        mpd_matches = re.findall(r'["\'](https?://[^"\']+\.mpd[^"\']*)["\']', html, re.IGNORECASE)
        for url in mpd_matches:
            add_candidate(url, "DASH Manifest", "DASH Manifest (.mpd)")

        # 5. Regex scan for direct video files (.mp4, .webm) inside script strings
        media_regex = re.findall(r'["\'](https?://[^"\']+\.(?:mp4|webm|mkv)[^"\']*)["\']', html, re.IGNORECASE)
        for url in media_regex:
            add_candidate(url, "Embedded Stream", "Direct Video URL")

        return candidates
