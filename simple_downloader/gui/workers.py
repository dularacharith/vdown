"""Asynchronous background worker threads for URL inspection and media downloading."""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal

from simple_downloader.engine import DownloadEngine
from simple_downloader.utils import format_bytes, format_duration


class InspectWorker(QThread):
    """Background worker thread to inspect media links without blocking the GUI."""

    info_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.browser = browser
        self.cookie_file = cookie_file
        self.proxy = proxy

    def run(self):
        try:
            engine = DownloadEngine()
            info = engine.get_media_info(
                self.url,
                browser=self.browser,
                cookie_file=self.cookie_file,
                proxy=self.proxy,
            )
            if not info:
                self.error.emit("No media stream or metadata found for the provided link.")
                return
            self.info_ready.emit(info)
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QThread):
    """Background worker thread to perform media downloads with real-time progress signals."""

    progress_updated = pyqtSignal(dict)
    download_finished = pyqtSignal(str)
    download_error = pyqtSignal(str)

    def __init__(
        self,
        url: str,
        output_dir: str = "downloads",
        output_path: Optional[str] = None,
        quality: Optional[str] = "best",
        format_id: Optional[str] = None,
        audio_only: bool = False,
        audio_format: str = "mp3",
        audio_quality: str = "320",
        video_format: Optional[str] = None,
        playlist: bool = False,
        playlist_items: Optional[str] = None,
        browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None,
        rate_limit: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.output_path = output_path
        self.quality = quality
        self.format_id = format_id
        self.audio_only = audio_only
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.video_format = video_format
        self.playlist = playlist
        self.playlist_items = playlist_items
        self.browser = browser
        self.cookie_file = cookie_file
        self.proxy = proxy
        self.rate_limit = rate_limit
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def _on_progress(self, d: Dict[str, Any]):
        if self.is_cancelled:
            raise RuntimeError("Download cancelled by user.")

        status = d.get("status")
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("speed") or 0.0
        eta = d.get("eta")

        percent = 0.0
        if total > 0:
            percent = min(100.0, (downloaded / total) * 100.0)

        speed_str = ""
        if speed > 0:
            mb_s = speed / (1024 * 1024)
            mbps = (speed * 8) / (1024 * 1024)
            speed_str = f"{mb_s:.2f} MB/s ({mbps:.1f} Mbps)"

        eta_str = format_duration(eta) if eta is not None else "--:--"

        raw_fn = d.get("filename") or ""
        filename = Path(raw_fn).name if raw_fn else ""

        progress_data = {
            "status": status,
            "percent": percent,
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "downloaded_str": format_bytes(downloaded),
            "total_str": format_bytes(total) if total > 0 else "Unknown",
            "speed_str": speed_str,
            "eta_str": eta_str,
            "filename": filename,
        }

        self.progress_updated.emit(progress_data)

    def run(self):
        try:
            engine = DownloadEngine()
            result = engine.download(
                url=self.url,
                output_path=self.output_path,
                output_dir=self.output_dir,
                quality=self.quality,
                format_id=self.format_id,
                audio_only=self.audio_only,
                audio_format=self.audio_format,
                audio_quality=self.audio_quality,
                video_format=self.video_format,
                playlist=self.playlist,
                playlist_items=self.playlist_items,
                browser=self.browser,
                cookie_file=self.cookie_file,
                proxy=self.proxy,
                rate_limit=self.rate_limit,
                show_progress=False,
                progress_callback=self._on_progress,
            )

            if not result:
                self.download_error.emit("Download did not produce any output file.")
                return

            self.download_finished.emit(str(result))
        except Exception as e:
            if not self.is_cancelled:
                self.download_error.emit(str(e))
