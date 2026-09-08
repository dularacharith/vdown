"""Direct HTTP/HTTPS streaming downloader with resume support and rich progress bar."""

import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable
import requests
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)

from simple_downloader.utils import (
    get_filename_from_headers_or_url,
    sanitize_filename,
    format_bytes,
)


class DirectDownloader:
    """Downloader for direct HTTP/HTTPS media and file links."""

    def __init__(
        self,
        chunk_size: int = 64 * 1024,
        timeout: int = 30,
        rate_limit: Optional[int] = None,
        headers: Optional[dict] = None,
    ):
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.rate_limit = rate_limit  # bytes per second
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }

    def download(
        self,
        url: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = "downloads",
        expected_size: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
        show_progress: bool = True,
    ) -> str:
        """Download file with support for resume and live rich progress display."""
        session = requests.Session()
        session.headers.update(self.headers)

        # 1. Inspect URL headers via HEAD or GET stream
        total_size: Optional[int] = expected_size if (expected_size and expected_size > 0) else None
        accept_ranges = False
        response_headers = {}

        try:
            head_resp = session.head(url, allow_redirects=True, timeout=self.timeout)
            if head_resp.status_code < 400:
                response_headers = head_resp.headers
                if "content-length" in head_resp.headers:
                    cl = int(head_resp.headers["content-length"])
                    if cl > 0:
                        total_size = cl
                accept_ranges = (
                    head_resp.headers.get("accept-ranges", "").lower() == "bytes"
                )
        except Exception:
            pass

        # 2. Determine target destination and filename
        if output_path:
            p = Path(output_path).expanduser()
            if p.is_absolute() or len(p.parts) > 1:
                target_file = p.resolve()
            else:
                dest_dir = Path(output_dir or "downloads").expanduser().resolve()
                target_file = dest_dir / p.name
        else:
            filename = get_filename_from_headers_or_url(url, response_headers)
            dest_dir = Path(output_dir or "downloads").expanduser().resolve()
            dest_dir.mkdir(parents=True, exist_ok=True)
            target_file = dest_dir / filename

        target_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = target_file.with_suffix(target_file.suffix + ".part")

        # 3. Check for existing partial file for resume
        downloaded_bytes = 0
        req_headers = dict(self.headers)

        if temp_file.exists():
            downloaded_bytes = temp_file.stat().st_size
            if accept_ranges or downloaded_bytes > 0:
                req_headers["Range"] = f"bytes={downloaded_bytes}-"

        # 4. Stream GET request
        resp = session.get(url, headers=req_headers, stream=True, timeout=self.timeout)

        # Handle 416 Range Not Satisfiable (file may already be fully downloaded)
        if resp.status_code == 416:
            if temp_file.exists() and total_size and temp_file.stat().st_size == total_size:
                temp_file.rename(target_file)
                return str(target_file)
            # Reset resume if server refused range
            downloaded_bytes = 0
            req_headers.pop("Range", None)
            resp = session.get(url, headers=req_headers, stream=True, timeout=self.timeout)

        # If server returns 200 OK instead of 206 Partial Content, restart from 0
        if resp.status_code == 200:
            downloaded_bytes = 0
            if "content-length" in resp.headers:
                cl = int(resp.headers["content-length"])
                if cl > 0:
                    total_size = cl
        elif resp.status_code == 206:
            content_range = resp.headers.get("content-range", "")
            if "/" in content_range:
                try:
                    cl = int(content_range.split("/")[-1])
                    if cl > 0:
                        total_size = cl
                except ValueError:
                    pass
        elif resp.status_code >= 400:
            resp.raise_for_status()

        # Update filename if not explicitly provided and we now have better response headers
        if not output_path and not response_headers:
            better_name = get_filename_from_headers_or_url(url, resp.headers)
            if better_name != target_file.name:
                target_file = target_file.parent / better_name
                temp_file = target_file.with_suffix(target_file.suffix + ".part")

        # 5. Write chunks with progress
        write_mode = "ab" if downloaded_bytes > 0 else "wb"

        from simple_downloader.progress import create_download_progress

        progress = create_download_progress(show_progress=show_progress)
        task_total = total_size if (total_size and total_size > 0) else None

        with progress:
            task_id = progress.add_task(
                f"{target_file.name}",
                total=task_total,
                completed=downloaded_bytes,
            )

            with open(temp_file, write_mode) as f:
                start_time = time.time()
                bytes_in_window = 0
                last_time = start_time
                last_bytes = downloaded_bytes

                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    chunk_len = len(chunk)
                    downloaded_bytes += chunk_len
                    bytes_in_window += chunk_len

                    now = time.time()
                    dt = now - last_time
                    if dt >= 0.25:
                        speed = (downloaded_bytes - last_bytes) / dt
                        last_time = now
                        last_bytes = downloaded_bytes
                        eta = (task_total - downloaded_bytes) / speed if (task_total and speed > 0 and task_total > downloaded_bytes) else None
                        progress.update(task_id, completed=downloaded_bytes, total=task_total, speed=speed, eta=eta)
                    else:
                        progress.update(task_id, completed=downloaded_bytes, total=task_total)

                    if progress_callback:
                        progress_callback(downloaded_bytes, total_size)

                    # Rate limiter logic
                    if self.rate_limit and self.rate_limit > 0:
                        elapsed = time.time() - start_time
                        expected_time = bytes_in_window / self.rate_limit
                        if expected_time > elapsed:
                            time.sleep(expected_time - elapsed)

        # 6. Finalize file name
        if temp_file.exists():
            if target_file.exists():
                target_file.unlink()
            temp_file.rename(target_file)

        return str(target_file)
