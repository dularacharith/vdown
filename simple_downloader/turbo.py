"""High-speed multi-connection segmented turbo downloader (IDM-style).

Splits downloads into parallel concurrent byte-range connections to bypass
server/ISP bandwidth throttling and maximize throughput.
"""

import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Callable
import requests

from simple_downloader.utils import (
    get_filename_from_headers_or_url,
    sanitize_filename,
    format_bytes,
)
from simple_downloader.direct_downloader import DirectDownloader
from simple_downloader.progress import create_download_progress


class TurboDownloader:
    """Multi-connection segmented downloader inspired by IDM (Internet Download Manager)."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        connections: int = 16,
        timeout: int = 30,
        headers: Optional[dict] = None,
    ):
        self.connections = max(1, min(connections, 32))
        self.timeout = timeout
        self.headers = headers or {"User-Agent": self.DEFAULT_USER_AGENT}

    def probe(self, url: str) -> Tuple[bool, Optional[int], Dict[str, str], Optional[str]]:
        """Probe remote server to check Range support, Content-Length, and filename.

        Returns:
            (supports_ranges, total_size, headers, resolved_filename)
        """
        session = requests.Session()
        session.headers.update(self.headers)

        supports_ranges = False
        total_size: Optional[int] = None
        resp_headers: Dict[str, str] = {}
        filename: Optional[str] = None

        # 1. Try HEAD request
        try:
            head = session.head(url, allow_redirects=True, timeout=self.timeout)
            if head.status_code < 400:
                resp_headers = dict(head.headers)
                if "content-length" in head.headers:
                    try:
                        total_size = int(head.headers["content-length"])
                    except ValueError:
                        pass
                if head.headers.get("accept-ranges", "").lower() == "bytes":
                    supports_ranges = True
                filename = get_filename_from_headers_or_url(url, head.headers)
        except Exception:
            pass

        # 2. If range support not verified or size unknown, probe with Range: bytes=0-0
        if not supports_ranges or not total_size:
            try:
                test_headers = dict(self.headers)
                test_headers["Range"] = "bytes=0-0"
                get_test = session.get(url, headers=test_headers, stream=True, timeout=self.timeout)
                if get_test.status_code == 206:
                    supports_ranges = True
                    resp_headers = dict(get_test.headers)
                    cr = get_test.headers.get("content-range", "")
                    if "/" in cr:
                        try:
                            total_size = int(cr.split("/")[-1])
                        except ValueError:
                            pass
                    if not filename:
                        filename = get_filename_from_headers_or_url(url, get_test.headers)
            except Exception:
                pass

        if not filename:
            filename = get_filename_from_headers_or_url(url, resp_headers)

        return supports_ranges, total_size, resp_headers, filename

    @staticmethod
    def calculate_chunks(total_size: int, num_connections: int) -> List[Tuple[int, int]]:
        """Compute [start, end] byte ranges for N parallel connections."""
        if num_connections <= 1 or total_size <= 0:
            return [(0, max(0, total_size - 1))]

        chunks = []
        chunk_size = total_size // num_connections
        for i in range(num_connections):
            start = i * chunk_size
            end = (i + 1) * chunk_size - 1 if i < num_connections - 1 else total_size - 1
            chunks.append((start, end))
        return chunks

    def download(
        self,
        url: str,
        output_path: Optional[str] = None,
        output_dir: Optional[str] = "downloads",
        connections: Optional[int] = None,
        show_progress: bool = True,
        console=None,
    ) -> str:
        """Download file with high-speed multi-connection turbo acceleration."""
        num_connections = connections or self.connections
        supports_ranges, total_size, headers, probed_filename = self.probe(url)

        # Resolve destination path
        if output_path:
            p = Path(output_path).expanduser()
            if p.is_absolute() or len(p.parts) > 1:
                target_file = p.resolve()
            else:
                dest_dir = Path(output_dir or "downloads").expanduser().resolve()
                target_file = dest_dir / p.name
        else:
            filename = probed_filename or "downloaded_file"
            dest_dir = Path(output_dir or "downloads").expanduser().resolve()
            dest_dir.mkdir(parents=True, exist_ok=True)
            target_file = dest_dir / filename

        target_file.parent.mkdir(parents=True, exist_ok=True)

        # Fallback to single connection if range not supported or small file (< 512 KB)
        if not supports_ranges or not total_size or total_size < 512 * 1024 or num_connections <= 1:
            if show_progress and console:
                if not supports_ranges:
                    console.print("[dim]⚡ Server does not support byte-ranges; using direct streaming.[/dim]")
            direct = DirectDownloader(timeout=self.timeout, headers=self.headers)
            return direct.download(
                url=url,
                output_path=str(target_file),
                expected_size=total_size,
                show_progress=show_progress,
            )

        # Multi-connection segmented turbo download
        chunks = self.calculate_chunks(total_size, num_connections)
        parts_dir = target_file.parent / f".vdown_parts_{abs(hash(str(target_file)))}"
        parts_dir.mkdir(parents=True, exist_ok=True)

        if show_progress and console:
            console.print(
                f"[bold cyan]🚀 Turbo Multi-Connection Accelerator Active:[/bold cyan] "
                f"[bold white]{len(chunks)} parallel streams[/bold white] "
                f"[dim]({format_bytes(total_size)})[/dim]"
            )

        progress = create_download_progress(show_progress=show_progress)
        task_id = progress.add_task(
            f"⚡ [bold cyan]{target_file.name}[/bold cyan]",
            total=total_size,
            completed=0,
        )

        progress_lock = threading.Lock()
        active_error: List[Exception] = []

        def download_chunk(index: int, start: int, end: int):
            part_path = parts_dir / f"part_{index}.tmp"
            existing_size = part_path.stat().st_size if part_path.exists() else 0

            # If this part is already completely downloaded, count it and return
            expected_part_size = end - start + 1
            if existing_size >= expected_part_size:
                with progress_lock:
                    progress.update(task_id, advance=expected_part_size)
                return

            current_start = start + existing_size
            if existing_size > 0:
                with progress_lock:
                    progress.update(task_id, advance=existing_size)

            req_headers = dict(self.headers)
            req_headers["Range"] = f"bytes={current_start}-{end}"

            session = requests.Session()
            session.headers.update(req_headers)

            mode = "ab" if existing_size > 0 else "wb"
            try:
                with session.get(url, stream=True, timeout=self.timeout) as resp:
                    if resp.status_code not in (200, 206):
                        raise RuntimeError(f"HTTP {resp.status_code} on chunk {index}")

                    with open(part_path, mode) as pf:
                        for chunk in resp.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            pf.write(chunk)
                            with progress_lock:
                                progress.update(task_id, advance=len(chunk))
            except Exception as e:
                with progress_lock:
                    active_error.append(e)
                raise

        # Execute parallel downloads with ThreadPoolExecutor
        try:
            with progress:
                with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
                    futures = [
                        executor.submit(download_chunk, idx, c_start, c_end)
                        for idx, (c_start, c_end) in enumerate(chunks)
                    ]
                    for future in as_completed(futures):
                        future.result()

            # Assemble segments in order
            with open(target_file, "wb") as final_out:
                for idx in range(len(chunks)):
                    part_file = parts_dir / f"part_{idx}.tmp"
                    if not part_file.exists():
                        raise FileNotFoundError(f"Missing chunk {idx} at {part_file}")
                    with open(part_file, "rb") as pf:
                        shutil.copyfileobj(pf, final_out, length=1024 * 1024)

            # Clean up temporary parts
            shutil.rmtree(parts_dir, ignore_errors=True)

            if show_progress and console:
                console.print(
                    f"✨ [bold green]Turbo Download Complete:[/bold green] "
                    f"[bold white]{target_file}[/bold white] "
                    f"([green]{format_bytes(target_file.stat().st_size)}[/green])"
                )

            return str(target_file)

        except Exception as e:
            # Fallback to direct download if parallel download failed
            if show_progress and console:
                console.print(f"[yellow]⚠️ Turbo download encountered an issue ({e}); falling back to direct stream.[/yellow]")
            shutil.rmtree(parts_dir, ignore_errors=True)
            direct = DirectDownloader(timeout=self.timeout, headers=self.headers)
            return direct.download(
                url=url,
                output_path=str(target_file),
                expected_size=total_size,
                show_progress=show_progress,
            )
