"""Online Series and TV Show Downloader Module for simple-downloader.

Provides comprehensive support for downloading individual episodes or entire shows
from online streaming platforms (e.g., Roopa Hala, Netflix, and generic web streaming services),
with organized season/episode directory hierarchies, universal splash art embedding,
interactive episode range filtering, and DRM fallback handling.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests
import yt_dlp
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Prompt, Confirm
from rich.table import Table

from simple_downloader.installer import ensure_tool_installed
from simple_downloader.torrent import TorrentDownloader
from simple_downloader.utils import (
    format_bytes,
    format_duration,
    sanitize_filename,
    attach_splash_art,
)

console = Console()

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


@dataclass
class Episode:
    """Represents a single episode of a TV show or series."""
    show_title: str
    season_number: int = 1
    episode_number: int = 1
    title: str = ""
    url: str = ""
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    description: Optional[str] = None
    stream_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    drm_protected: bool = False

    def formatted_title(self) -> str:
        """Formatted display title e.g. 'S01E03 - The Trap' or 'S01E03'."""
        clean_ep_title = self.title.strip() if self.title else ""
        if clean_ep_title and clean_ep_title.lower() != f"episode {self.episode_number}".lower():
            return f"S{self.season_number:02d}E{self.episode_number:02d} - {clean_ep_title}"
        return f"S{self.season_number:02d}E{self.episode_number:02d}"

    def safe_filename(self, ext: str = "mp4") -> str:
        """Standard safe filename: '<Show Title> - S<SS>E<EE> - <Title>.<ext>'."""
        clean_show = sanitize_filename(self.show_title)
        clean_title = sanitize_filename(self.title) if self.title else ""
        if clean_title and clean_title.lower() != f"episode {self.episode_number}".lower():
            fname = f"{clean_show} - S{self.season_number:02d}E{self.episode_number:02d} - {clean_title}.{ext}"
        else:
            fname = f"{clean_show} - S{self.season_number:02d}E{self.episode_number:02d}.{ext}"
        return sanitize_filename(fname)


@dataclass
class Series:
    """Represents a complete TV show or series with multi-season episodes."""
    title: str
    url: str
    seasons: Dict[int, List[Episode]] = field(default_factory=dict)
    poster_url: Optional[str] = None
    description: Optional[str] = None
    platform_name: str = "Online Streaming"
    drm_protected: bool = False

    @property
    def total_episodes(self) -> int:
        """Return total number of episodes across all seasons."""
        return sum(len(eps) for eps in self.seasons.values())

    @property
    def all_episodes(self) -> List[Episode]:
        """Return a flattened, sorted list of all episodes."""
        flat: List[Episode] = []
        for s_num in sorted(self.seasons.keys()):
            for ep in sorted(self.seasons[s_num], key=lambda e: e.episode_number):
                flat.append(ep)
        return flat


# ---------------------------------------------------------------------------
# Range Parser
# ---------------------------------------------------------------------------

def parse_episode_selection(selection_str: str, all_episodes: List[Episode]) -> List[Episode]:
    """Parse a flexible user selection string into a list of Episode objects.

    Supported patterns:
      - 'all', '', or '1-end': All episodes
      - '1-5': Episodes 1 to 5 (1-based global index or episode number)
      - '3': Single episode 3
      - '1, 3, 5': Discrete list of episode numbers
      - 'S01', 's1': All episodes in Season 1
      - 'S01E01-S01E05': Season & Episode range
      - 'S01E03': Single specific episode in Season 1
    """
    if not all_episodes:
        return []

    sel = selection_str.strip().lower()
    if not sel or sel in ("all", "*", "1-end"):
        return list(all_episodes)

    # 1. Season filter: 's01', 's1', 'season 1'
    season_match = re.match(r"^s(?:eason\s*)?(\d+)$", sel)
    if season_match:
        s_target = int(season_match.group(1))
        matched = [ep for ep in all_episodes if ep.season_number == s_target]
        return matched if matched else all_episodes

    # 2. Season/Episode range: 's01e01-s01e05' or 's1e1-s1e5'
    se_range_match = re.match(
        r"^s(\d+)e(\d+)\s*-\s*s(\d+)e(\d+)$", sel
    )
    if se_range_match:
        s1, e1, s2, e2 = (
            int(se_range_match.group(1)),
            int(se_range_match.group(2)),
            int(se_range_match.group(3)),
            int(se_range_match.group(4)),
        )
        selected = []
        for ep in all_episodes:
            val = ep.season_number * 10000 + ep.episode_number
            start_val = s1 * 10000 + e1
            end_val = s2 * 10000 + e2
            if start_val <= val <= end_val:
                selected.append(ep)
        return selected if selected else all_episodes

    # 3. Single S01E03
    single_se = re.match(r"^s(\d+)e(\d+)$", sel)
    if single_se:
        s_num, e_num = int(single_se.group(1)), int(single_se.group(2))
        matched = [ep for ep in all_episodes if ep.season_number == s_num and ep.episode_number == e_num]
        return matched if matched else all_episodes

    # 4. Numeric Range: '1-5'
    num_range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", sel)
    if num_range_match:
        start_idx = int(num_range_match.group(1))
        end_idx = int(num_range_match.group(2))
        selected = []
        for idx, ep in enumerate(all_episodes, start=1):
            if start_idx <= idx <= end_idx:
                selected.append(ep)
        return selected if selected else all_episodes

    # 5. Comma-separated list: '1, 3, 5' or single number '3'
    if "," in sel or sel.isdigit():
        parts = [p.strip() for p in sel.split(",") if p.strip()]
        target_nums = set()
        for p in parts:
            if p.isdigit():
                target_nums.add(int(p))
            elif "-" in p:
                r_match = re.match(r"^(\d+)\s*-\s*(\d+)$", p)
                if r_match:
                    for n in range(int(r_match.group(1)), int(r_match.group(2)) + 1):
                        target_nums.add(n)
        selected = []
        for idx, ep in enumerate(all_episodes, start=1):
            if idx in target_nums:
                selected.append(ep)
        return selected if selected else all_episodes

    return list(all_episodes)


# ---------------------------------------------------------------------------
# Platform Extractors
# ---------------------------------------------------------------------------

class BaseSeriesExtractor:
    """Base class for streaming series extractors."""

    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    def extract_series(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Series:
        raise NotImplementedError

    def resolve_stream(
        self,
        episode: Episode,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Tuple[Optional[str], Dict[str, str]]:
        """Resolve playable stream URL and necessary HTTP headers for an episode."""
        return episode.stream_url, (episode.headers or {})


class RoopaHalaExtractor(BaseSeriesExtractor):
    """Specialized extractor for Roopa Hala (roopahala.com.au / roopahala.lk).

    Handles show catalogs, season/episode cards, CSRF authentication tokens,
    Radiant Media Player / Flowplayer configs, and base64-obfuscated HLS streams.
    """

    ROOPAHALA_DOMAINS = ("roopahala.com.au", "roopahala.lk", "roopahala")

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return any(d in clean for d in self.ROOPAHALA_DOMAINS)

    def _build_session(
        self,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> requests.Session:
        s = session or requests.Session()
        s.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        # If browser cookies requested, extract cookies using yt_dlp cookies mechanism
        if browser:
            try:
                import yt_dlp.cookies
                cj = yt_dlp.cookies.extract_cookies_from_browser(browser)
                if cj:
                    s.cookies.update(cj)
            except Exception:
                pass
        elif cookie_file and os.path.exists(cookie_file):
            try:
                import http.cookiejar
                cj = http.cookiejar.MozillaCookieJar(cookie_file)
                cj.load()
                s.cookies.update(cj)
            except Exception:
                pass
        return s

    def extract_series(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Series:
        sess = self._build_session(browser, cookie_file, session)
        resp = sess.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # 1. Show Title
        title = "Roopa Hala Content"
        title_matches = [
            re.search(r'<h[1-4][^>]*class=["\'][^"\']*(?:movie-name|film-name|movie-title|film-title|title)[^"\']*["\'][^>]*>(.*?)</h[1-4]>', html, re.I | re.DOTALL),
            re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.I),
            re.search(r'<h1[^>]*class=["\'][^"\']*(?:movie-title|film-title|title)[^"\']*["\'][^>]*>(.*?)</h1>', html, re.I | re.DOTALL),
            re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.DOTALL),
            re.search(r'<title>(.*?)</title>', html, re.I),
        ]
        for m in title_matches:
            if m and m.group(1).strip():
                raw = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                # Clean up Roopa Hala branding
                cleaned = re.sub(r"\s*[-|]\s*Roopa\s*Hala.*", "", raw, flags=re.I).strip()
                if cleaned and cleaned.lower() not in ("welcome to roopa hala", "roopa hala"):
                    title = cleaned
                    break

        # 2. Poster image
        poster_url = None
        poster_matches = [
            re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I),
            re.search(r'["\']poster["\']\s*:\s*["\'](https?://[^"\']+)["\']', html, re.I),
            re.search(r'<img[^>]+src=["\'](https?://content\.roopahala\.com\.au/uploads/thumbnail/[^"\']+)["\']', html, re.I),
            re.search(r'<img[^>]+src=["\'](https?://[^"\']*(?:poster|thumbnail)[^"\']*)["\']', html, re.I),
        ]
        for m in poster_matches:
            if m and m.group(1).strip():
                poster_url = m.group(1).strip()
                break

        # 3. CSRF token & Content ID
        csrf_m = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html, re.I)
        csrf_token = csrf_m.group(1) if csrf_m else ""

        cid_m = re.search(r'play(?:Movie|Trailer)Secure\([\'"]([^\'"]+)[\'"]', html)
        if not cid_m:
            cid_m = re.search(r'/new/content/([^/]+)/', url)
        content_id = cid_m.group(1) if cid_m else ""

        # 4. Check for direct obfuscated stream URL in page
        direct_stream_url = None
        obf_m = re.search(r'const\s+obfuscatedUrl\s*=\s*[\'"]([A-Za-z0-9+/=]+)[\'"]', html)
        if obf_m:
            try:
                decoded = base64.b64decode(obf_m.group(1)).decode("utf-8", errors="ignore")
                if decoded.startswith("http") and (".m3u8" in decoded or ".mp4" in decoded):
                    direct_stream_url = decoded
            except Exception:
                pass

        # 5. Extract episodes & seasons
        seasons_dict: Dict[int, List[Episode]] = {}

        # Scan for episode cards / items
        # Pattern e.g. <a href="...episode/X" ...> or data-ep="..." or data-season="..."
        episode_blocks = re.findall(
            r'<(?:div|li|a)[^>]*(?:class|id)=["\'][^"\']*(?:episode|ep-item|film-detail)[^"\']*["\'][^>]*>(.*?)</(?:div|li|a)>',
            html,
            re.DOTALL | re.I,
        )

        ep_idx = 1
        found_episodes = False

        if episode_blocks:
            for block in episode_blocks:
                # Find season & episode number
                s_m = re.search(r'(?:season|s)[\s._-]*(\d+)', block, re.I)
                e_m = re.search(r'(?:episode|ep)[\s._-]*(\d+)', block, re.I)
                season_no = int(s_m.group(1)) if s_m else 1
                episode_no = int(e_m.group(1)) if e_m else ep_idx

                # Title
                ep_title_m = re.search(r'<h\d[^>]*>(.*?)</h\d>', block, re.DOTALL | re.I)
                ep_title = (
                    re.sub(r"<[^>]+>", "", ep_title_m.group(1)).strip()
                    if ep_title_m
                    else f"Episode {episode_no}"
                )

                # Link / URL
                href_m = re.search(r'href=["\']([^"\']+)["\']', block)
                ep_url = urllib.parse.urljoin(url, href_m.group(1)) if href_m else url

                # Thumbnail
                thumb_m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', block)
                ep_thumb = urllib.parse.urljoin(url, thumb_m.group(1)) if thumb_m else poster_url

                ep = Episode(
                    show_title=title,
                    season_number=season_no,
                    episode_number=episode_no,
                    title=ep_title,
                    url=ep_url,
                    thumbnail=ep_thumb,
                    stream_url=direct_stream_url,
                    headers={"Referer": "https://roopahala.com.au/"},
                )
                seasons_dict.setdefault(season_no, []).append(ep)
                ep_idx += 1
                found_episodes = True

        # If no multi-episode markup found, check for embedded JSON / playlist
        if not found_episodes:
            json_playlists = re.findall(r'var\s+(?:episodes|playlist|season_data)\s*=\s*(\[.*?\]);', html, re.DOTALL)
            for raw_json in json_playlists:
                try:
                    data = json.loads(raw_json)
                    if isinstance(data, list) and data:
                        for idx, item in enumerate(data, start=1):
                            s_no = item.get("season", 1)
                            e_no = item.get("episode", idx)
                            e_name = item.get("title") or item.get("name") or f"Episode {e_no}"
                            e_src = item.get("src") or item.get("url") or direct_stream_url
                            e_thumb = item.get("poster") or item.get("thumbnail") or poster_url
                            ep = Episode(
                                show_title=title,
                                season_number=int(s_no),
                                episode_number=int(e_no),
                                title=e_name,
                                url=item.get("page_url", url),
                                thumbnail=e_thumb,
                                stream_url=e_src,
                                headers={"Referer": "https://roopahala.com.au/"},
                            )
                            seasons_dict.setdefault(int(s_no), []).append(ep)
                            found_episodes = True
                except Exception:
                    pass

        # If still no multi-episode structure, treat as single Episode (Season 1, Episode 1 / Movie)
        if not found_episodes:
            single_ep = Episode(
                show_title=title,
                season_number=1,
                episode_number=1,
                title=title,
                url=url,
                thumbnail=poster_url,
                stream_url=direct_stream_url,
                headers={"Referer": "https://roopahala.com.au/"},
            )
            seasons_dict[1] = [single_ep]

        return Series(
            title=title,
            url=url,
            seasons=seasons_dict,
            poster_url=poster_url,
            platform_name="Roopa Hala",
            drm_protected=False,
        )

    def resolve_stream(
        self,
        episode: Episode,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Tuple[Optional[str], Dict[str, str]]:
        """Resolve direct HLS stream for Roopa Hala content."""
        if episode.stream_url:
            return episode.stream_url, (episode.headers or {"Referer": "https://roopahala.com.au/"})

        sess = self._build_session(browser, cookie_file, session)
        target_url = episode.url or "https://roopahala.com.au"
        resp = sess.get(target_url, timeout=15)
        html = resp.text

        # 1. Direct obfuscatedUrl in HTML
        obf_m = re.search(r'const\s+obfuscatedUrl\s*=\s*[\'"]([A-Za-z0-9+/=]+)[\'"]', html)
        if obf_m:
            try:
                decoded = base64.b64decode(obf_m.group(1)).decode("utf-8", errors="ignore")
                if decoded.startswith("http"):
                    return decoded, {"Referer": "https://roopahala.com.au/"}
            except Exception:
                pass

        # 2. Extract CSRF token & Content ID for secure play request
        csrf_m = re.search(r'<meta\s+name=["\']csrf-token["\']\s+content=["\']([^"\']+)["\']', html)
        csrf_token = csrf_m.group(1) if csrf_m else ""

        cid_m = re.search(r'playMovieSecure\([\'"]([^\'"]+)[\'"]', html)
        if not cid_m:
            cid_m = re.search(r'/new/content/([^/]+)/', target_url)
        content_id = cid_m.group(1) if cid_m else ""

        if csrf_token and content_id:
            # First try authenticated movie playback: /get/sec/md -> /sec/play/movie
            try:
                md_resp = sess.post(
                    "https://roopahala.com.au/get/sec/md",
                    data={"_token": csrf_token, "cid": content_id, "type": "movie"},
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": target_url},
                    timeout=10,
                )
                if md_resp.status_code == 200:
                    data = md_resp.json().get("data")
                    if data:
                        data["_token"] = csrf_token
                        play_resp = sess.post(
                            "https://roopahala.com.au/sec/play/movie",
                            data=data,
                            headers={"Referer": target_url},
                            timeout=10,
                        )
                        obf_m2 = re.search(r'const\s+obfuscatedUrl\s*=\s*[\'"]([A-Za-z0-9+/=]+)[\'"]', play_resp.text)
                        if obf_m2:
                            decoded = base64.b64decode(obf_m2.group(1)).decode("utf-8", errors="ignore")
                            if decoded.startswith("http"):
                                return decoded, {"Referer": "https://roopahala.com.au/"}
            except Exception:
                pass

            # Fallback to trailer playback: /get/sec/td -> /sec/play/trailer
            try:
                td_resp = sess.post(
                    "https://roopahala.com.au/get/sec/td",
                    data={"_token": csrf_token, "cid": content_id, "gid": ""},
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": target_url},
                    timeout=10,
                )
                if td_resp.status_code == 200:
                    data = td_resp.json().get("data")
                    if data:
                        data["_token"] = csrf_token
                        play_resp = sess.post(
                            "https://roopahala.com.au/sec/play/trailer",
                            data=data,
                            headers={"Referer": target_url},
                            timeout=10,
                        )
                        obf_m3 = re.search(r'const\s+obfuscatedUrl\s*=\s*[\'"]([A-Za-z0-9+/=]+)[\'"]', play_resp.text)
                        if obf_m3:
                            decoded = base64.b64decode(obf_m3.group(1)).decode("utf-8", errors="ignore")
                            if decoded.startswith("http"):
                                return decoded, {"Referer": "https://roopahala.com.au/"}
            except Exception:
                pass

        return None, {"Referer": "https://roopahala.com.au/"}


class NetflixExtractor(BaseSeriesExtractor):
    """Extractor for Netflix titles and watch URLs.

    Recognizes multi-season rosters, extracts title and episode metadata from
    JSON-LD schemas, detects Widevine DRM encryption, and routes to automated
    unencrypted stream / torrent fallback.
    """

    NETFLIX_PATTERN = re.compile(
        r"https?://(?:www\.)?netflix\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:title|watch)/(\d+)",
        re.I,
    )

    def can_handle(self, url: str) -> bool:
        if not url:
            return False
        return bool(self.NETFLIX_PATTERN.search(url))

    def extract_series(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Series:
        sess = session or requests.Session()
        sess.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })

        match = self.NETFLIX_PATTERN.search(url)
        title_id = match.group(1) if match else "0"
        canonical_url = f"https://www.netflix.com/title/{title_id}"

        title = f"Netflix Title {title_id}"
        poster_url = None
        description = None
        seasons_dict: Dict[int, List[Episode]] = {}

        try:
            resp = sess.get(canonical_url, timeout=12)
            html = resp.text

            # 1. Parse JSON-LD structured data (Netflix provides rich schema on public pages)
            json_ld_matches = re.findall(
                r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                html,
                re.DOTALL | re.I,
            )
            for raw_json in json_ld_matches:
                try:
                    data = json.loads(raw_json)
                    if not isinstance(data, dict):
                        continue
                    schema_type = data.get("@type", "")
                    if schema_type in ("TVSeries", "Movie", "VideoObject"):
                        title = data.get("name") or title
                        poster_url = data.get("image") or poster_url
                        description = data.get("description") or description

                        # Multi-season episodes
                        seasons = data.get("containsSeason", [])
                        if isinstance(seasons, list):
                            for s_data in seasons:
                                s_no = int(s_data.get("seasonNumber", 1))
                                ep_list = s_data.get("episode", [])
                                if isinstance(ep_list, list):
                                    for ep_data in ep_list:
                                        e_no = int(ep_data.get("episodeNumber", 1))
                                        e_name = ep_data.get("name") or f"Episode {e_no}"
                                        e_url = ep_data.get("url") or f"https://www.netflix.com/watch/{title_id}"
                                        e_desc = ep_data.get("description")
                                        ep = Episode(
                                            show_title=title,
                                            season_number=s_no,
                                            episode_number=e_no,
                                            title=e_name,
                                            url=e_url,
                                            thumbnail=poster_url,
                                            description=e_desc,
                                            drm_protected=True,
                                        )
                                        seasons_dict.setdefault(s_no, []).append(ep)
                except Exception:
                    pass

            # 2. Fallback to OpenGraph meta tags
            if title == f"Netflix Title {title_id}":
                og_title_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.I)
                if og_title_m:
                    raw = og_title_m.group(1).strip()
                    cleaned = re.sub(r"\s*\|\s*Netflix.*", "", raw, flags=re.I).strip()
                    cleaned = re.sub(r"^Watch\s+", "", cleaned, flags=re.I).strip()
                    if cleaned:
                        title = cleaned

            if not poster_url:
                og_img_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
                if og_img_m:
                    poster_url = og_img_m.group(1).strip()

        except Exception:
            pass

        # If no episodes parsed from JSON-LD schema, populate default S01E01
        if not seasons_dict:
            seasons_dict[1] = [
                Episode(
                    show_title=title,
                    season_number=1,
                    episode_number=1,
                    title=f"{title} (Episode 1)",
                    url=canonical_url,
                    thumbnail=poster_url,
                    drm_protected=True,
                )
            ]

        return Series(
            title=title,
            url=canonical_url,
            seasons=seasons_dict,
            poster_url=poster_url,
            description=description,
            platform_name="Netflix",
            drm_protected=True,
        )


class GenericSeriesExtractor(BaseSeriesExtractor):
    """Universal extractor for arbitrary web streaming, drama, and anime portals.

    Scrapes episode roster hierarchies, detects multi-season layouts, and extracts
    direct video/HLS manifests or leverages yt-dlp flat playlist extraction.
    """

    def can_handle(self, url: str) -> bool:
        # Catch-all for http/https URLs
        return bool(url and url.startswith(("http://", "https://")))

    def extract_series(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> Series:
        sess = session or requests.Session()
        sess.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })

        title = "Web Series"
        poster_url = None
        seasons_dict: Dict[int, List[Episode]] = {}

        # 1. First test yt-dlp flat playlist extraction (for platforms natively supported by yt-dlp)
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

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = info.get("title") or title
                    poster_url = info.get("thumbnail") or poster_url
                    entries = info.get("entries")
                    if entries:
                        for idx, entry in enumerate(entries, start=1):
                            if not entry:
                                continue
                            ep_title = entry.get("title") or f"Episode {idx}"
                            s_no = entry.get("season_number") or 1
                            e_no = entry.get("episode_number") or idx
                            ep_url = entry.get("url") or entry.get("webpage_url") or url
                            ep_thumb = entry.get("thumbnail") or poster_url
                            ep = Episode(
                                show_title=title,
                                season_number=int(s_no),
                                episode_number=int(e_no),
                                title=ep_title,
                                url=ep_url,
                                thumbnail=ep_thumb,
                                duration=entry.get("duration"),
                            )
                            seasons_dict.setdefault(int(s_no), []).append(ep)
                        if seasons_dict:
                            return Series(
                                title=title,
                                url=url,
                                seasons=seasons_dict,
                                poster_url=poster_url,
                                platform_name="Online Streaming",
                            )
        except Exception:
            pass

        # 2. DOM-based web scraper fallback
        try:
            resp = sess.get(url, timeout=12)
            html = resp.text

            # Title
            og_title = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', html, re.I)
            if og_title:
                title = og_title.group(1).strip()
            else:
                title_tag = re.search(r'<title>(.*?)</title>', html, re.I)
                if title_tag:
                    title = re.sub(r"<[^>]+>", "", title_tag.group(1)).strip()

            # Poster
            og_img = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.I)
            if og_img:
                poster_url = og_img.group(1).strip()

            # Find episode links
            ep_matches = re.findall(
                r'<a[^>]+href=["\']([^"\']*(?:episode|ep|watch)[^"\']*)["\'][^>]*>(.*?)</a>',
                html,
                re.I | re.DOTALL,
            )

            ep_count = 1
            for ep_href, ep_inner in ep_matches:
                inner_text = re.sub(r"<[^>]+>", "", ep_inner).strip()
                s_m = re.search(r's(\d+)', inner_text, re.I) or re.search(r'season\s*(\d+)', inner_text, re.I)
                e_m = re.search(r'e(\d+)', inner_text, re.I) or re.search(r'ep(?:isode)?\s*(\d+)', inner_text, re.I)
                s_no = int(s_m.group(1)) if s_m else 1
                e_no = int(e_m.group(1)) if e_m else ep_count
                ep_full_url = urllib.parse.urljoin(url, ep_href)

                ep = Episode(
                    show_title=title,
                    season_number=s_no,
                    episode_number=e_no,
                    title=inner_text or f"Episode {e_no}",
                    url=ep_full_url,
                    thumbnail=poster_url,
                )
                seasons_dict.setdefault(s_no, []).append(ep)
                ep_count += 1
        except Exception:
            pass

        if not seasons_dict:
            seasons_dict[1] = [
                Episode(
                    show_title=title,
                    season_number=1,
                    episode_number=1,
                    title=title,
                    url=url,
                    thumbnail=poster_url,
                )
            ]

        return Series(
            title=title,
            url=url,
            seasons=seasons_dict,
            poster_url=poster_url,
            platform_name="Web Streaming",
        )


def is_series_url(url: str) -> bool:
    """Check whether a URL points to an online series, TV show, or streaming catalog."""
    if not url:
        return False
    u = url.lower()
    if any(d in u for d in ("roopahala.com.au", "roopahala.lk", "roopahala")):
        return True
    if "netflix.com/" in u and ("/title/" in u or "/watch/" in u):
        return True
    if any(k in u for k in ("/tvshow", "/tv-show", "/series/", "/season/", "/episodes", "/teledrama")):
        return True
    return False


def get_series_extractor(url: str) -> BaseSeriesExtractor:
    """Return the most appropriate series extractor for a URL."""
    roopa = RoopaHalaExtractor()
    if roopa.can_handle(url):
        return roopa

    netflix = NetflixExtractor()
    if netflix.can_handle(url):
        return netflix

    return GenericSeriesExtractor()



# ---------------------------------------------------------------------------
# Series Batch Downloader Engine
# ---------------------------------------------------------------------------

class SeriesDownloader:
    """Manages batch episode queues, directory structures, and media embedding."""

    def __init__(self, console_instance: Optional[Console] = None, console: Optional[Console] = None):
        self.console = console or console_instance or Console()

    def download_series(
        self,
        series: Series,
        episodes: List[Episode],
        output_dir: str = "downloads",
        quality: str = "best",
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        subtitles: bool = False,
        sub_lang: str = "en",
        embed_subs: bool = False,
        embed_thumbnail: bool = True,
        rate_limit: Optional[int] = None,
    ) -> int:
        """Download selected episodes into organized season folders with splash art."""
        if not episodes:
            self.console.print("[yellow]No episodes selected for download.[/yellow]")
            return 0

        # Validate FFmpeg
        if not ensure_tool_installed(
            "ffmpeg",
            purpose="download streaming video segments and embed episode splash art",
            console=self.console,
        ):
            return 1

        clean_show_title = sanitize_filename(series.title)
        total_eps = len(episodes)

        self.console.print(
            Panel(
                f"[bold cyan]Show:[/bold cyan] [bold white]{series.title}[/bold white]\n"
                f"[dim]Platform:[/dim] {series.platform_name} | [dim]Episodes queued:[/dim] [bold green]{total_eps}[/bold green]\n"
                f"[dim]Destination:[/dim] [underline]{os.path.abspath(os.path.join(output_dir, clean_show_title))}[/underline]",
                title="📺 Online Series Download Queue",
                border_style="bright_blue",
            )
        )

        # Pre-download series poster to a temporary file if thumbnail embedding enabled
        series_poster_file: Optional[str] = None
        if embed_thumbnail and series.poster_url:
            series_poster_file = self._download_temp_image(series.poster_url)

        extractor = get_series_extractor(series.url)
        completed_count = 0
        failed_count = 0

        with Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=35),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
        ) as progress:

            overall_task = progress.add_task(
                f"[bold yellow]Overall Progress (0/{total_eps})[/bold yellow]",
                total=total_eps,
            )

            for idx, ep in enumerate(episodes, start=1):
                progress.update(
                    overall_task,
                    description=f"[bold yellow]Overall Progress ({idx}/{total_eps}): {ep.formatted_title()}[/bold yellow]",
                )

                # Format destination folder: <output_dir>/<Show Title>/Season <SS>/
                season_dir = Path(output_dir) / clean_show_title / f"Season {ep.season_number:02d}"
                season_dir.mkdir(parents=True, exist_ok=True)

                dest_file = season_dir / ep.safe_filename("mp4")

                # Check if episode already downloaded
                if dest_file.exists() and dest_file.stat().st_size > 1024 * 1024:
                    self.console.print(
                        f"[dim]✔ [{idx}/{total_eps}] {ep.formatted_title()} already exists. Skipping.[/dim]"
                    )
                    progress.advance(overall_task)
                    completed_count += 1
                    continue

                # Handle DRM-protected episodes
                if ep.drm_protected or series.drm_protected:
                    progress.stop()
                    res = self._handle_drm_protected_episode(
                        ep,
                        dest_file,
                        series_poster_file,
                    )
                    progress.start()
                    if res == 0:
                        completed_count += 1
                    else:
                        failed_count += 1
                    progress.advance(overall_task)
                    continue

                # Resolve playable stream URL
                stream_url, headers = extractor.resolve_stream(
                    ep,
                    browser=browser,
                    cookie_file=cookie_file,
                )

                ep_task = progress.add_task(
                    f"[cyan]Downloading {ep.formatted_title()}[/cyan]",
                    total=None,
                )

                success = False
                try:
                    if stream_url:
                        success = self._download_stream_with_ytdlp(
                            stream_url=stream_url,
                            headers=headers,
                            dest_file=dest_file,
                            quality=quality,
                            subtitles=subtitles,
                            sub_lang=sub_lang,
                            embed_subs=embed_subs,
                            rate_limit=rate_limit,
                            progress=progress,
                            task_id=ep_task,
                        )
                    else:
                        # Fallback to downloading episode page URL with yt-dlp
                        success = self._download_stream_with_ytdlp(
                            stream_url=ep.url or series.url,
                            headers=headers,
                            dest_file=dest_file,
                            quality=quality,
                            browser=browser,
                            cookie_file=cookie_file,
                            subtitles=subtitles,
                            sub_lang=sub_lang,
                            embed_subs=embed_subs,
                            rate_limit=rate_limit,
                            progress=progress,
                            task_id=ep_task,
                        )
                except Exception as e:
                    self.console.print(f"[bold red]Download error for {ep.formatted_title()}:[/bold red] {e}")
                    success = False
                finally:
                    progress.remove_task(ep_task)

                if success and dest_file.exists():
                    # Universal Splash Art Attachment
                    if embed_thumbnail:
                        thumb_to_embed = None
                        if ep.thumbnail:
                            thumb_to_embed = self._download_temp_image(ep.thumbnail)
                        if not thumb_to_embed:
                            thumb_to_embed = series_poster_file

                        if thumb_to_embed:
                            try:
                                attach_splash_art(str(dest_file), thumb_to_embed)
                            except Exception:
                                pass

                    completed_count += 1
                else:
                    failed_count += 1

                progress.advance(overall_task)

        # Cleanup series poster
        if series_poster_file and os.path.exists(series_poster_file):
            try:
                os.remove(series_poster_file)
            except Exception:
                pass

        self.console.print(
            Panel(
                f"[bold green]✔ Series Download Finished![/bold green]\n"
                f"[bold cyan]Succeeded:[/bold cyan] {completed_count}/{total_eps} episodes\n"
                f"[bold white]Output Folder:[/bold white] [underline]{os.path.abspath(os.path.join(output_dir, clean_show_title))}[/underline]",
                border_style="green" if failed_count == 0 else "yellow",
            )
        )
        return 0 if failed_count == 0 else 1

    def _download_stream_with_ytdlp(
        self,
        stream_url: str,
        dest_file: Path,
        headers: Optional[Dict[str, str]] = None,
        quality: str = "best",
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        subtitles: bool = False,
        sub_lang: str = "en",
        embed_subs: bool = False,
        rate_limit: Optional[int] = None,
        progress: Optional[Progress] = None,
        task_id: Optional[Any] = None,
    ) -> bool:
        """Download stream using yt-dlp with live progress hook."""
        out_tmpl = str(dest_file.with_suffix(".%(ext)s"))

        # Map quality
        fmt_string = "bv*+ba/b"
        if quality == "4k":
            fmt_string = "bv*[height<=2160]+ba/b[height<=2160]/best"
        elif quality == "1440p":
            fmt_string = "bv*[height<=1440]+ba/b[height<=1440]/best"
        elif quality == "1080p":
            fmt_string = "bv*[height<=1080]+ba/b[height<=1080]/best"
        elif quality == "720p":
            fmt_string = "bv*[height<=720]+ba/b[height<=720]/best"
        elif quality == "480p":
            fmt_string = "bv*[height<=480]+ba/b[height<=480]/best"

        def progress_hook(d: Dict[str, Any]):
            if not progress or task_id is None:
                return
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                downloaded = d.get("downloaded_bytes", 0)
                if total:
                    progress.update(task_id, total=total, completed=downloaded)
            elif status == "finished":
                if progress and task_id is not None:
                    progress.update(task_id, completed=progress.tasks[task_id].total)

        ydl_opts: Dict[str, Any] = {
            "format": fmt_string,
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
        }

        if headers:
            ydl_opts["http_headers"] = headers
        if browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        if rate_limit:
            ydl_opts["ratelimit"] = rate_limit
        if subtitles:
            ydl_opts["writesubtitles"] = True
            ydl_opts["subtitleslangs"] = [sub_lang]
            if embed_subs:
                ydl_opts["postprocessors"] = [{"key": "FFmpegEmbedSubtitle"}]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([stream_url])

        # If downloaded file has different extension (e.g. .mkv or .mp4), normalize to dest_file
        if not dest_file.exists():
            for cand in dest_file.parent.glob(f"{dest_file.stem}.*"):
                if cand.suffix.lower() in (".mp4", ".mkv", ".webm", ".ts") and not cand.name.endswith(".part"):
                    shutil.move(str(cand), str(dest_file))
                    break

        return dest_file.exists() and dest_file.stat().st_size > 0

    def _handle_drm_protected_episode(
        self,
        episode: Episode,
        dest_file: Path,
        series_poster_file: Optional[str] = None,
    ) -> int:
        """Handle Widevine DRM encrypted streams by searching unencrypted HD releases."""
        self.console.print(
            Panel(
                f"[bold yellow]🔒 DRM Protected Stream Detected[/bold yellow]\n"
                f"[dim]Title:[/dim] [bold white]{episode.formatted_title()}[/bold white]\n"
                f"Direct browser video stream is encrypted with Widevine DRM (L1/L3).\n"
                f"🚀 [bold cyan]vdown Automated Fallback:[/bold cyan] Searching unencrypted high-definition BitTorrent P2P swarms...",
                border_style="yellow",
            )
        )

        # Search query: "<Show Title> S<SS>E<EE>"
        query = f"{episode.show_title} S{episode.season_number:02d}E{episode.episode_number:02d}"
        torrent_dl = TorrentDownloader(self.console)

        # Perform swarm search via public torrent index
        magnet_url = self._search_torrent_magnet(query)
        if not magnet_url:
            self.console.print(
                f"[yellow]No unencrypted swarm release automatically found for query: '{query}'.[/yellow]\n"
                f"[dim]Tip: Pass browser cookies or download via manual magnet link.[/dim]"
            )
            return 1

        self.console.print(f"[bold green]✔ High-speed release located for {query}![/bold green]")
        res = torrent_dl.download(
            target=magnet_url,
            output_dir=str(dest_file.parent),
            stream=False,
            interactive=False,
        )

        # Embed splash art if video arrived
        if res == 0:
            for cand in dest_file.parent.glob(f"*{episode.episode_number:02d}*"):
                if cand.suffix.lower() in (".mp4", ".mkv"):
                    thumb = series_poster_file
                    if thumb:
                        attach_splash_art(str(cand), thumb)
                    break
        return res

    def _search_torrent_magnet(self, query: str) -> Optional[str]:
        """Search public torrent index (Apibay) for high-definition release magnet link."""
        try:
            url = f"https://apibay.org/q.php?q={urllib.parse.quote(query)}"
            headers = {"User-Agent": DEFAULT_USER_AGENT}
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                results = resp.json()
                if isinstance(results, list) and results:
                    best = None
                    for item in results:
                        info_hash = item.get("info_hash", "")
                        if info_hash and info_hash != "0000000000000000000000000000000000000000":
                            seeders = int(item.get("seeders", 0))
                            if best is None or seeders > best.get("seeders", 0):
                                best = item
                    if best:
                        name = best.get("name", query)
                        ih = best.get("info_hash")
                        trackers = "&tr=" + "&tr=".join([
                            urllib.parse.quote("udp://tracker.opentrackr.org:1337/announce"),
                            urllib.parse.quote("udp://open.stealth.si:80/announce"),
                            urllib.parse.quote("udp://tracker.torrent.eu.org:451/announce"),
                        ])
                        return f"magnet:?xt=urn:btih:{ih}&dn={urllib.parse.quote(name)}{trackers}"
        except Exception:
            pass
        return None

    def _download_temp_image(self, url: str) -> Optional[str]:
        """Download an image from a URL to a temporary JPEG file."""
        if not url:
            return None
        try:
            resp = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 100:
                suffix = ".jpg"
                if ".png" in url.lower():
                    suffix = ".png"
                elif ".webp" in url.lower():
                    suffix = ".webp"
                fd, path = tempfile.mkstemp(suffix=suffix)
                with os.fdopen(fd, "wb") as f:
                    f.write(resp.content)
                return path
        except Exception:
            pass
        return None
