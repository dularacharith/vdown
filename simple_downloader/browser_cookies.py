"""Browser cookie detection and session management for simple-downloader."""

import concurrent.futures
import logging
import shutil
import sys
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# Order of browsers to prioritize (Safari is first on macOS, Firefox on others)
if sys.platform == "darwin":
    PRIORITY_BROWSERS = [
        "safari",
        "chrome",
        "brave",
        "firefox",
        "edge",
        "chromium",
        "opera",
        "vivaldi",
    ]
else:
    PRIORITY_BROWSERS = [
        "firefox",
        "chrome",
        "brave",
        "edge",
        "chromium",
        "opera",
        "vivaldi",
    ]

_CACHED_RESULTS: Optional[List[Dict[str, Any]]] = None


CHROMIUM_KEYCHAINS = {
    "chrome": ("Chrome Safe Storage", "Chrome"),
    "brave": ("Brave Safe Storage", "Brave"),
    "edge": ("Microsoft Edge Safe Storage", "Microsoft Edge"),
    "chromium": ("Chromium Safe Storage", "Chromium"),
    "opera": ("Opera Safe Storage", "Opera"),
    "vivaldi": ("Vivaldi Safe Storage", "Vivaldi"),
}


def _can_access_mac_keychain(service: str, account: str, timeout: float = 0.3) -> bool:
    """Check if macOS Keychain item can be read without blocking on an interactive prompt."""
    import subprocess
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-w", "-a", account, "-s", service],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(["killall", "-9", "security"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass
        return False
    except Exception:
        return False


def _extract_browser_cookies_safe(browser: str, timeout: float = 2.0) -> Any:
    """Safely extract browser cookies with a timeout and macOS Keychain check."""
    import yt_dlp.cookies

    # On macOS, avoid hanging on Keychain prompts for Chromium-based browsers
    if sys.platform == "darwin" and browser in CHROMIUM_KEYCHAINS:
        service, account = CHROMIUM_KEYCHAINS[browser]
        if not _can_access_mac_keychain(service, account, timeout=0.3):
            logger.debug(f"Skipping {browser}: macOS Keychain authorization requires prompt.")
            return None

    try:
        return yt_dlp.cookies.extract_cookies_from_browser(browser)
    except Exception as e:
        logger.debug(f"Cookie extraction for {browser} failed: {e}")
        return None


def detect_available_browsers(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Scan the system for installed browsers and check if session cookies can be extracted.
    
    Returns a list of dicts:
    [
        {
            "browser": "firefox",
            "name": "Firefox",
            "available": True,
            "cookies_count": 236,
            "has_auth": True,
            "error": None
        },
        ...
    ]
    """
    global _CACHED_RESULTS
    if _CACHED_RESULTS is not None and not force_refresh:
        return _CACHED_RESULTS

    results = []

    try:
        import yt_dlp.cookies
    except ImportError:
        logger.warning("yt_dlp.cookies module not available.")
        return results

    display_names = {
        "firefox": "Mozilla Firefox",
        "chrome": "Google Chrome",
        "brave": "Brave Browser",
        "edge": "Microsoft Edge",
        "chromium": "Chromium",
        "opera": "Opera",
        "vivaldi": "Vivaldi",
        "safari": "Apple Safari",
    }

    for browser in PRIORITY_BROWSERS:
        browser_info: Dict[str, Any] = {
            "browser": browser,
            "name": display_names.get(browser, browser.capitalize()),
            "available": False,
            "cookies_count": 0,
            "has_auth": False,
            "error": None,
        }

        try:
            cj = _extract_browser_cookies_safe(browser, timeout=2.0)
            if cj is not None:
                count = len(cj)
                browser_info["available"] = count > 0
                browser_info["cookies_count"] = count
                if count > 0:
                    # Check if relevant video domains have cookies
                    auth_domains = ["youtube", "google", "facebook", "instagram", "tiktok", "twitter", "x.com"]
                    has_auth = any(
                        any(domain in (c.domain or "").lower() for domain in auth_domains)
                        for c in cj
                    )
                    browser_info["has_auth"] = has_auth
        except Exception as e:
            err_msg = str(e)
            browser_info["error"] = err_msg

        results.append(browser_info)

    _CACHED_RESULTS = results
    return results


def get_best_browser(force_refresh: bool = False) -> Optional[str]:
    """Return the name of the best available browser with cookies (prioritizing Firefox)."""
    browsers = detect_available_browsers(force_refresh=force_refresh)
    
    # 1. First preference: Browsers with authentication cookies for social/media domains
    for b in browsers:
        if b.get("available") and b.get("has_auth"):
            return b["browser"]

    # 2. Second preference: Any browser with cookies available
    for b in browsers:
        if b.get("available") and b.get("cookies_count", 0) > 0:
            return b["browser"]

    return None


def get_browser_cookie_summary() -> str:
    """Return a short readable summary of detected browser cookies."""
    browsers = detect_available_browsers()
    available = [b for b in browsers if b.get("available")]
    if not available:
        return "No browser cookies detected."

    parts = [f"{b['name']} ({b['cookies_count']} cookies)" for b in available]
    return ", ".join(parts)
