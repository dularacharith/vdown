"""Main Window implementation for VDown Desktop Application."""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices, QClipboard, QAction
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QComboBox,
    QRadioButton,
    QButtonGroup,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QFrame,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGridLayout,
    QSizePolicy,
)

from simple_downloader import __version__
from simple_downloader.browser_cookies import (
    detect_available_browsers,
    get_best_browser,
    get_browser_cookie_summary,
)
from simple_downloader.gui.styles import DARK_THEME_QSS
from simple_downloader.gui.workers import InspectWorker, DownloadWorker
from simple_downloader.utils import format_bytes, format_duration


HISTORY_FILE = Path.home() / ".vdown" / "history.json"
SETTINGS_FILE = Path.home() / ".vdown" / "settings.json"


def _open_file_in_system(filepath: str):
    """Open file with default system player / application."""
    p = Path(filepath).resolve()
    if not p.exists():
        return
    try:
        if platform.system() == "Windows":
            os.startfile(str(p))
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            subprocess.run(["xdg-open", str(p)], check=False)
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def _reveal_in_file_manager(filepath: str):
    """Open containing folder and select file in OS file manager."""
    p = Path(filepath).resolve()
    if not p.exists():
        p = p.parent
    if not p.exists():
        return
    try:
        if platform.system() == "Windows":
            subprocess.run(["explorer", f"/select,{str(p)}"], check=False)
        elif platform.system() == "Darwin":
            subprocess.run(["open", "-R", str(p)], check=False)
        else:
            folder = p.parent if p.is_file() else p
            subprocess.run(["xdg-open", str(folder)], check=False)
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))


class MainWindow(QMainWindow):
    """VDown Desktop Main Application Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VDown - Universal Media Downloader")
        self.resize(1000, 750)
        self.setMinimumSize(820, 600)
        self.setStyleSheet(DARK_THEME_QSS)

        self.current_inspect_worker: Optional[InspectWorker] = None
        self.current_download_worker: Optional[DownloadWorker] = None
        self.active_media_info: Optional[Dict[str, Any]] = None
        self.download_history: List[Dict[str, Any]] = self._load_history()
        self.settings: Dict[str, Any] = self._load_settings()

        self._init_ui()
        self._refresh_cookie_badge()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Header Frame
        header = self._build_header()
        main_layout.addWidget(header)

        # 2. Main Tab Widget
        self.tabs = QTabWidget()
        self.tab_downloader = self._build_downloader_tab()
        self.tab_library = self._build_library_tab()
        self.tab_settings = self._build_settings_tab()

        self.tabs.addTab(self.tab_downloader, "📥 Downloader")
        self.tabs.addTab(self.tab_library, "📚 Library & History")
        self.tabs.addTab(self.tab_settings, "⚙️ Settings")

        main_layout.addWidget(self.tabs)

    # -------------------------------------------------------------------------
    # Header UI
    # -------------------------------------------------------------------------
    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("HeaderFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(16)

        # App Brand Title
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("🎬 VDown")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Universal Video & Audio Downloader")
        subtitle.setObjectName("SubText")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        # Version Badge
        ver_badge = QLabel(f"v{__version__} Desktop")
        ver_badge.setObjectName("Badge")
        layout.addWidget(ver_badge)

        layout.addStretch()

        # Cookie detection indicator
        self.cookie_status_label = QLabel("Checking browser cookies...")
        self.cookie_status_label.setObjectName("CookieBadge")
        layout.addWidget(self.cookie_status_label)

        # Refresh Cookies button
        btn_refresh_cookies = QPushButton("🔄 Refresh Cookies")
        btn_refresh_cookies.setObjectName("SecondaryButton")
        btn_refresh_cookies.setToolTip("Re-scan system for browser cookies (Firefox, Chrome, Brave, Edge)")
        btn_refresh_cookies.clicked.connect(self._refresh_cookie_badge)
        layout.addWidget(btn_refresh_cookies)

        return frame

    def _refresh_cookie_badge(self):
        browsers = detect_available_browsers(force_refresh=True)
        available = [b for b in browsers if b.get("available")]
        firefox = next((b for b in available if b["browser"] == "firefox"), None)

        if firefox:
            count = firefox["cookies_count"]
            self.cookie_status_label.setText(f"🦊 Firefox Cookies Active ({count})")
            self.cookie_status_label.setObjectName("SuccessBadge")
        elif available:
            b = available[0]
            self.cookie_status_label.setText(f"🌐 {b['name']} Cookies Active ({b['cookies_count']})")
            self.cookie_status_label.setObjectName("SuccessBadge")
        else:
            self.cookie_status_label.setText("⚠️ No Browser Cookies Detected")
            self.cookie_status_label.setObjectName("CookieBadge")

        self.cookie_status_label.style().unpolish(self.cookie_status_label)
        self.cookie_status_label.style().polish(self.cookie_status_label)

        # Update cookie combo box if initialized
        if hasattr(self, "combo_browser"):
            current_choice = self.combo_browser.currentData()
            self.combo_browser.clear()
            self.combo_browser.addItem("Auto-Detect Browser Cookies (Recommended)", "auto")
            for b in browsers:
                status = f" ({b['cookies_count']} cookies)" if b.get("available") else " (Not found)"
                self.combo_browser.addItem(f"{b['name']}{status}", b["browser"])
            self.combo_browser.addItem("None (No session cookies)", "none")

            idx = self.combo_browser.findData(current_choice)
            if idx >= 0:
                self.combo_browser.setCurrentIndex(idx)

    # -------------------------------------------------------------------------
    # Tab 1: Downloader
    # -------------------------------------------------------------------------
    def _build_downloader_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 1. URL Input Card
        url_card = self._build_url_input_card()
        layout.addWidget(url_card)

        # 2. Media Info Card (hidden initially until inspected)
        self.info_card = self._build_media_info_card()
        self.info_card.setVisible(False)
        layout.addWidget(self.info_card)

        # 3. Options Card
        options_card = self._build_options_card()
        layout.addWidget(options_card)

        # 4. Download Action & Live Progress Card
        action_card = self._build_action_and_progress_card()
        layout.addWidget(action_card)

        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    def _build_url_input_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CardFrame")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        lbl = QLabel("Enter Video or Media Link")
        lbl.setObjectName("SectionHeader")
        header_layout.addWidget(lbl)

        self.platform_chip = QLabel("Universal Link")
        self.platform_chip.setObjectName("Badge")
        header_layout.addWidget(self.platform_chip)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube, TikTok, Facebook, Instagram, Twitter/X, or direct media URL...")
        self.url_input.textChanged.connect(self._on_url_changed)
        self.url_input.returnPressed.connect(self._start_inspect)
        input_layout.addWidget(self.url_input)

        btn_paste = QPushButton("📋 Paste")
        btn_paste.setObjectName("SecondaryButton")
        btn_paste.clicked.connect(self._paste_clipboard)
        input_layout.addWidget(btn_paste)

        btn_clear = QPushButton("✖")
        btn_clear.setObjectName("SecondaryButton")
        btn_clear.setToolTip("Clear link input")
        btn_clear.clicked.connect(lambda: self.url_input.clear())
        input_layout.addWidget(btn_clear)

        self.btn_inspect = QPushButton("🔍 Inspect")
        self.btn_inspect.setObjectName("SecondaryButton")
        self.btn_inspect.clicked.connect(self._start_inspect)
        input_layout.addWidget(self.btn_inspect)

        layout.addLayout(input_layout)
        return card

    def _build_media_info_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HighlightCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        self.lbl_info_title = QLabel("Media Title")
        self.lbl_info_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        self.lbl_info_title.setWordWrap(True)
        layout.addWidget(self.lbl_info_title)

        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(12)

        self.lbl_info_uploader = QLabel("Uploader: Unknown")
        self.lbl_info_uploader.setObjectName("SubText")
        meta_layout.addWidget(self.lbl_info_uploader)

        self.lbl_info_duration = QLabel("Duration: --:--")
        self.lbl_info_duration.setObjectName("SubText")
        meta_layout.addWidget(self.lbl_info_duration)

        self.lbl_info_type = QLabel("Format: Video")
        self.lbl_info_type.setObjectName("Badge")
        meta_layout.addWidget(self.lbl_info_type)

        meta_layout.addStretch()
        layout.addLayout(meta_layout)
        return card

    def _build_options_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CardFrame")
        layout = QVBoxLayout(card)
        layout.setSpacing(14)

        header = QLabel("Download Options & Settings")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        # Mode Selection: Video vs Audio
        lbl_mode = QLabel("Mode:")
        lbl_mode.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_mode, 0, 0)

        mode_layout = QHBoxLayout()
        self.radio_video = QRadioButton("🎬 Video (MP4)")
        self.radio_audio = QRadioButton("🎵 Audio Only")
        self.radio_video.setChecked(True)
        self.radio_video.toggled.connect(self._on_mode_toggled)

        mode_group = QButtonGroup(self)
        mode_group.addButton(self.radio_video)
        mode_group.addButton(self.radio_audio)
        mode_layout.addWidget(self.radio_video)
        mode_layout.addWidget(self.radio_audio)
        mode_layout.addStretch()
        grid.addLayout(mode_layout, 0, 1)

        # Video Quality Dropdown
        self.lbl_quality = QLabel("Video Quality:")
        self.lbl_quality.setStyleSheet("font-weight: 600;")
        grid.addWidget(self.lbl_quality, 1, 0)

        self.combo_quality = QComboBox()
        self.combo_quality.addItem("Best Available (Highest Resolution)", "best")
        self.combo_quality.addItem("4K Ultra HD (2160p)", "4k")
        self.combo_quality.addItem("2K Quad HD (1440p)", "1440p")
        self.combo_quality.addItem("Full HD (1080p)", "1080p")
        self.combo_quality.addItem("HD (720p)", "720p")
        self.combo_quality.addItem("Standard Definition (480p)", "480p")
        self.combo_quality.addItem("Compact (360p)", "360p")
        grid.addWidget(self.combo_quality, 1, 1)

        # Audio Format Dropdown
        self.lbl_audio_format = QLabel("Audio Format:")
        self.lbl_audio_format.setStyleSheet("font-weight: 600;")
        grid.addWidget(self.lbl_audio_format, 2, 0)

        self.combo_audio_format = QComboBox()
        self.combo_audio_format.addItem("MP3 (320 kbps Extreme)", "mp3")
        self.combo_audio_format.addItem("FLAC (Lossless Studio Audio)", "flac")
        self.combo_audio_format.addItem("M4A / AAC (High Fidelity)", "m4a")
        self.combo_audio_format.addItem("WAV (Lossless PCM)", "wav")
        self.combo_audio_format.addItem("OPUS (Modern Low-Bitrate)", "opus")
        grid.addWidget(self.combo_audio_format, 2, 1)

        # Browser Cookies Dropdown
        lbl_browser = QLabel("Session Cookies:")
        lbl_browser.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_browser, 3, 0)

        self.combo_browser = QComboBox()
        grid.addWidget(self.combo_browser, 3, 1)

        # Destination Directory Picker
        lbl_dest = QLabel("Save Destination:")
        lbl_dest.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_dest, 4, 0)

        dest_layout = QHBoxLayout()
        default_dir = self.settings.get("download_dir", str(Path.home() / "Downloads" / "vdown"))
        self.txt_dest_dir = QLineEdit(default_dir)
        dest_layout.addWidget(self.txt_dest_dir)

        btn_browse = QPushButton("📁 Browse")
        btn_browse.setObjectName("SecondaryButton")
        btn_browse.clicked.connect(self._browse_destination_dir)
        dest_layout.addWidget(btn_browse)
        grid.addLayout(dest_layout, 4, 1)

        # Playlist Items Range (optional)
        self.lbl_playlist = QLabel("Playlist Range:")
        self.lbl_playlist.setStyleSheet("font-weight: 600;")
        grid.addWidget(self.lbl_playlist, 5, 0)

        self.txt_playlist_items = QLineEdit()
        self.txt_playlist_items.setPlaceholderText("Leave blank for all, or specify e.g. 1-10 or 1,3,5")
        grid.addWidget(self.txt_playlist_items, 5, 1)

        layout.addLayout(grid)
        self._on_mode_toggled()
        return card

    def _build_action_and_progress_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("CardFrame")
        layout = QVBoxLayout(card)
        layout.setSpacing(14)

        # Button Row
        btn_row = QHBoxLayout()
        self.btn_download = QPushButton("🚀 Download Now")
        self.btn_download.setObjectName("PrimaryButton")
        self.btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self.btn_download)

        self.btn_cancel = QPushButton("🛑 Cancel")
        self.btn_cancel.setObjectName("DangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_download)
        btn_row.addWidget(self.btn_cancel)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Live Progress Section
        self.progress_container = QWidget()
        prog_layout = QVBoxLayout(self.progress_container)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)

        # Status text & stats row
        stats_row = QHBoxLayout()
        self.lbl_progress_status = QLabel("Ready to download")
        self.lbl_progress_status.setStyleSheet("font-weight: 600; font-size: 13px;")
        stats_row.addWidget(self.lbl_progress_status)

        stats_row.addStretch()

        self.lbl_progress_speed = QLabel("")
        self.lbl_progress_speed.setObjectName("Badge")
        self.lbl_progress_speed.setVisible(False)
        stats_row.addWidget(self.lbl_progress_speed)

        self.lbl_progress_eta = QLabel("")
        self.lbl_progress_eta.setObjectName("Badge")
        self.lbl_progress_eta.setVisible(False)
        stats_row.addWidget(self.lbl_progress_eta)

        prog_layout.addLayout(stats_row)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        prog_layout.addWidget(self.progress_bar)

        # Success Banner with Action Buttons
        self.success_frame = QFrame()
        self.success_frame.setStyleSheet("background-color: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 10px;")
        success_layout = QHBoxLayout(self.success_frame)
        success_layout.setContentsMargins(10, 8, 10, 8)

        self.lbl_success_message = QLabel("✔ Download completed!")
        self.lbl_success_message.setStyleSheet("color: #34d399; font-weight: 700;")
        success_layout.addWidget(self.lbl_success_message)

        success_layout.addStretch()

        self.btn_open_file = QPushButton("▶ Open File")
        self.btn_open_file.setObjectName("SecondaryButton")
        self.btn_open_file.clicked.connect(self._open_completed_file)
        success_layout.addWidget(self.btn_open_file)

        self.btn_show_folder = QPushButton("📁 Show in Folder")
        self.btn_show_folder.setObjectName("SecondaryButton")
        self.btn_show_folder.clicked.connect(self._show_completed_folder)
        success_layout.addWidget(self.btn_show_folder)

        self.success_frame.setVisible(False)
        prog_layout.addWidget(self.success_frame)

        layout.addWidget(self.progress_container)
        return card

    # -------------------------------------------------------------------------
    # Tab 2: Library & History
    # -------------------------------------------------------------------------
    def _build_library_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        header = QLabel("Downloaded Media Library")
        header.setObjectName("SectionHeader")
        header_layout.addWidget(header)

        header_layout.addStretch()

        btn_clear = QPushButton("🗑 Clear History")
        btn_clear.setObjectName("DangerButton")
        btn_clear.clicked.connect(self._clear_history)
        header_layout.addWidget(btn_clear)
        layout.addLayout(header_layout)

        self.table_history = QTableWidget()
        self.table_history.setColumnCount(5)
        self.table_history.setHorizontalHeaderLabels(["Title / Filename", "Type", "Size", "Date", "Actions"])
        self.table_history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_history.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_history.verticalHeader().setVisible(False)
        self.table_history.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_history.setAlternatingRowColors(True)

        layout.addWidget(self.table_history)
        self._refresh_history_table()
        return container

    # -------------------------------------------------------------------------
    # Tab 3: Settings
    # -------------------------------------------------------------------------
    def _build_settings_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        card = QFrame()
        card.setObjectName("CardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        header = QLabel("Application Preferences")
        header.setObjectName("SectionHeader")
        card_layout.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        # Default Directory
        lbl_dir = QLabel("Default Downloads Directory:")
        lbl_dir.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_dir, 0, 0)

        dir_box = QHBoxLayout()
        self.txt_settings_dir = QLineEdit(self.settings.get("download_dir", str(Path.home() / "Downloads" / "vdown")))
        dir_box.addWidget(self.txt_settings_dir)
        btn_browse_settings = QPushButton("📁 Browse")
        btn_browse_settings.setObjectName("SecondaryButton")
        btn_browse_settings.clicked.connect(self._browse_settings_dir)
        dir_box.addWidget(btn_browse_settings)
        grid.addLayout(dir_box, 0, 1)

        # Default Video Quality
        lbl_q = QLabel("Default Video Quality:")
        lbl_q.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_q, 1, 0)
        self.combo_settings_quality = QComboBox()
        self.combo_settings_quality.addItem("Best Available", "best")
        self.combo_settings_quality.addItem("1080p (Full HD)", "1080p")
        self.combo_settings_quality.addItem("720p (HD)", "720p")
        self.combo_settings_quality.setCurrentText(self.settings.get("default_quality", "Best Available"))
        grid.addWidget(self.combo_settings_quality, 1, 1)

        # Default Audio Format
        lbl_a = QLabel("Default Audio Format:")
        lbl_a.setStyleSheet("font-weight: 600;")
        grid.addWidget(lbl_a, 2, 0)
        self.combo_settings_audio = QComboBox()
        self.combo_settings_audio.addItem("MP3 (320 kbps)", "mp3")
        self.combo_settings_audio.addItem("FLAC (Lossless)", "flac")
        self.combo_settings_audio.addItem("M4A", "m4a")
        self.combo_settings_audio.setCurrentText(self.settings.get("default_audio", "MP3 (320 kbps)"))
        grid.addWidget(self.combo_settings_audio, 2, 1)

        card_layout.addLayout(grid)

        # Save Settings button
        btn_save = QPushButton("💾 Save Preferences")
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._save_settings)
        card_layout.addWidget(btn_save)

        layout.addWidget(card)
        layout.addStretch()
        return container

    # -------------------------------------------------------------------------
    # UI Event Handlers
    # -------------------------------------------------------------------------
    def _on_url_changed(self, text: str):
        url = text.strip()
        chip_text = "Universal Link"
        if not url:
            chip_text = "Universal Link"
        elif "youtube.com" in url or "youtu.be" in url:
            chip_text = "📺 YouTube"
        elif "tiktok.com" in url:
            chip_text = "🎵 TikTok"
        elif "facebook.com" in url or "fb.watch" in url:
            chip_text = "📘 Facebook"
        elif "instagram.com" in url:
            chip_text = "📸 Instagram"
        elif "twitter.com" in url or "x.com" in url:
            chip_text = "🐦 X / Twitter"
        elif "reddit.com" in url:
            chip_text = "🤖 Reddit"
        elif "vimeo.com" in url:
            chip_text = "🎥 Vimeo"
        elif url.endswith((".mp4", ".mp3", ".m4a", ".flac", ".mkv", ".webm", ".wav")):
            chip_text = "⚡ Direct Media File"

        self.platform_chip.setText(chip_text)

    def _paste_clipboard(self):
        clipboard = QClipboard()
        text = clipboard.text().strip()
        if text:
            self.url_input.setText(text)
            self._start_inspect()

    def _browse_destination_dir(self):
        curr = self.txt_dest_dir.text()
        chosen = QFileDialog.getExistingDirectory(self, "Select Download Directory", curr or str(Path.home() / "Downloads"))
        if chosen:
            self.txt_dest_dir.setText(chosen)

    def _browse_settings_dir(self):
        curr = self.txt_settings_dir.text()
        chosen = QFileDialog.getExistingDirectory(self, "Select Default Directory", curr or str(Path.home() / "Downloads"))
        if chosen:
            self.txt_settings_dir.setText(chosen)

    def _on_mode_toggled(self):
        is_audio = self.radio_audio.isChecked()
        self.lbl_quality.setVisible(not is_audio)
        self.combo_quality.setVisible(not is_audio)
        self.lbl_audio_format.setVisible(is_audio)
        self.combo_audio_format.setVisible(is_audio)

    # -------------------------------------------------------------------------
    # Media Inspection Logic
    # -------------------------------------------------------------------------
    def _start_inspect(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL Provided", "Please enter or paste a video link first.")
            return

        self.btn_inspect.setEnabled(False)
        self.btn_inspect.setText("🔍 Inspecting...")
        self.info_card.setVisible(False)
        self.lbl_progress_status.setText("Inspecting link details and stream formats...")

        browser_choice = self.combo_browser.currentData()
        if browser_choice == "none":
            browser_choice = None

        self.current_inspect_worker = InspectWorker(url=url, browser=browser_choice)
        self.current_inspect_worker.info_ready.connect(self._on_inspect_success)
        self.current_inspect_worker.error.connect(self._on_inspect_error)
        self.current_inspect_worker.start()

    def _on_inspect_success(self, info: dict):
        self.btn_inspect.setEnabled(True)
        self.btn_inspect.setText("🔍 Inspect")
        self.active_media_info = info

        title = info.get("title") or "Unknown Media"
        uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Unknown"
        duration_sec = info.get("duration")
        duration_str = format_duration(duration_sec) if duration_sec else "--:--"

        self.lbl_info_title.setText(title)
        self.lbl_info_uploader.setText(f"👤 {uploader}")
        self.lbl_info_duration.setText(f"⏱ {duration_str}")

        is_playlist = info.get("is_playlist", False)
        if is_playlist:
            count = info.get("playlist_count", len(info.get("entries", [])))
            self.lbl_info_type.setText(f"📑 Playlist ({count} items)")
        else:
            self.lbl_info_type.setText("🎬 Single Video")

        self.info_card.setVisible(True)
        self.lbl_progress_status.setText(f"Ready: {title}")

    def _on_inspect_error(self, err_msg: str):
        self.btn_inspect.setEnabled(True)
        self.btn_inspect.setText("🔍 Inspect")
        self.lbl_progress_status.setText("Inspection failed.")

        # Friendly error dialog with tips
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Media Analysis Error")
        box.setText("Could not analyze or extract media from this link.")
        box.setInformativeText(f"{err_msg}\n\nTip: If this platform requires login or anti-bot verification, ensure session cookies are selected (e.g. Firefox or Chrome).")
        box.exec()

    # -------------------------------------------------------------------------
    # Download Execution Logic
    # -------------------------------------------------------------------------
    def _start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a media URL before starting download.")
            return

        dest_dir = self.txt_dest_dir.text().strip() or str(Path.home() / "Downloads" / "vdown")
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        is_audio = self.radio_audio.isChecked()
        quality = self.combo_quality.currentData() if not is_audio else None
        audio_fmt = self.combo_audio_format.currentData() if is_audio else "mp3"
        playlist_items = self.txt_playlist_items.text().strip() or None

        browser_choice = self.combo_browser.currentData()
        if browser_choice == "none":
            browser_choice = None

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.success_frame.setVisible(False)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Initializing download...")
        self.lbl_progress_speed.setVisible(True)
        self.lbl_progress_eta.setVisible(True)
        self.lbl_progress_speed.setText("Connecting...")
        self.lbl_progress_eta.setText("--:--")

        self.current_download_worker = DownloadWorker(
            url=url,
            output_dir=dest_dir,
            quality=quality,
            audio_only=is_audio,
            audio_format=audio_fmt,
            audio_quality="320",
            playlist_items=playlist_items,
            browser=browser_choice,
        )

        self.current_download_worker.progress_updated.connect(self._on_download_progress)
        self.current_download_worker.download_finished.connect(self._on_download_finished)
        self.current_download_worker.download_error.connect(self._on_download_error)
        self.current_download_worker.start()

    def _cancel_download(self):
        if self.current_download_worker:
            self.current_download_worker.cancel()
            self.lbl_progress_status.setText("Cancelling download...")
            self.btn_cancel.setEnabled(False)

    def _on_download_progress(self, data: dict):
        percent = int(data.get("percent", 0))
        self.progress_bar.setValue(percent)

        downloaded_str = data.get("downloaded_str", "0 B")
        total_str = data.get("total_str", "Unknown")
        speed_str = data.get("speed_str")
        eta_str = data.get("eta_str")
        filename = data.get("filename") or "Media"

        status = data.get("status")
        if status == "finished":
            self.lbl_progress_status.setText(f"Processing & Finalizing {filename}...")
        else:
            self.lbl_progress_status.setText(f"Downloading: {percent}% • {downloaded_str} / {total_str}")

        if speed_str:
            self.lbl_progress_speed.setText(f"⚡ {speed_str}")
        if eta_str:
            self.lbl_progress_eta.setText(f"⏳ ETA: {eta_str}")

    def _on_download_finished(self, filepath: str):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(100)

        self.lbl_progress_status.setText(f"✔ Download Complete: {Path(filepath).name}")
        self.lbl_progress_speed.setVisible(False)
        self.lbl_progress_eta.setVisible(False)

        self.last_downloaded_path = filepath
        self.lbl_success_message.setText(f"✔ Saved: {Path(filepath).name}")
        self.success_frame.setVisible(True)

        # Add to history
        entry = {
            "title": Path(filepath).stem,
            "filename": Path(filepath).name,
            "path": str(filepath),
            "size": format_bytes(Path(filepath).stat().st_size) if Path(filepath).exists() else "Unknown",
            "type": Path(filepath).suffix.lstrip(".").upper(),
            "date": "Just now",
        }
        self.download_history.insert(0, entry)
        self._save_history()
        self._refresh_history_table()

    def _on_download_error(self, err_msg: str):
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.lbl_progress_status.setText("Download failed.")
        self.lbl_progress_speed.setVisible(False)
        self.lbl_progress_eta.setVisible(False)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Download Error")
        box.setText("Failed to download media.")
        box.setInformativeText(err_msg)
        box.exec()

    def _open_completed_file(self):
        if hasattr(self, "last_downloaded_path") and self.last_downloaded_path:
            _open_file_in_system(self.last_downloaded_path)

    def _show_completed_folder(self):
        if hasattr(self, "last_downloaded_path") and self.last_downloaded_path:
            _reveal_in_file_manager(self.last_downloaded_path)

    # -------------------------------------------------------------------------
    # History & Library Management
    # -------------------------------------------------------------------------
    def _refresh_history_table(self):
        self.table_history.setRowCount(0)
        for i, item in enumerate(self.download_history):
            self.table_history.insertRow(i)
            self.table_history.setItem(i, 0, QTableWidgetItem(item.get("title", item.get("filename", "Media"))))
            self.table_history.setItem(i, 1, QTableWidgetItem(item.get("type", "MP4")))
            self.table_history.setItem(i, 2, QTableWidgetItem(item.get("size", "Unknown")))
            self.table_history.setItem(i, 3, QTableWidgetItem(item.get("date", "")))

            # Action buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            path = item.get("path", "")
            btn_play = QPushButton("▶ Open")
            btn_play.setObjectName("SecondaryButton")
            btn_play.clicked.connect(lambda checked, p=path: _open_file_in_system(p))
            actions_layout.addWidget(btn_play)

            btn_folder = QPushButton("📁 Folder")
            btn_folder.setObjectName("SecondaryButton")
            btn_folder.clicked.connect(lambda checked, p=path: _reveal_in_file_manager(p))
            actions_layout.addWidget(btn_folder)

            self.table_history.setCellWidget(i, 4, actions_widget)

    def _load_history(self) -> List[Dict[str, Any]]:
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.download_history[:100], f, indent=2)
        except Exception:
            pass

    def _clear_history(self):
        if QMessageBox.question(self, "Clear History", "Clear all download history records?") == QMessageBox.StandardButton.Yes:
            self.download_history.clear()
            self._save_history()
            self._refresh_history_table()

    # -------------------------------------------------------------------------
    # Settings Management
    # -------------------------------------------------------------------------
    def _load_settings(self) -> Dict[str, Any]:
        default_settings = {
            "download_dir": str(Path.home() / "Downloads" / "vdown"),
            "default_quality": "best",
            "default_audio": "mp3",
        }
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_settings.update(data)
            except Exception:
                pass
        return default_settings

    def _save_settings(self):
        self.settings["download_dir"] = self.txt_settings_dir.text().strip()
        self.settings["default_quality"] = self.combo_settings_quality.currentData()
        self.settings["default_audio"] = self.combo_settings_audio.currentData()
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
            self.txt_dest_dir.setText(self.settings["download_dir"])
            QMessageBox.information(self, "Settings Saved", "Preferences saved successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Error Saving Settings", str(e))
