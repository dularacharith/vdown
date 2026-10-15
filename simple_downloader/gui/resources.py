"""Resource management and asset resolution for VDown GUI."""

import os
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import Qt


def get_icon_path() -> Optional[str]:
    """Find the path to the application icon across development and frozen environments."""
    candidates = []

    # 1. PyInstaller extraction directory
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / "simple_downloader" / "gui" / "icon.png",
            meipass / "assets" / "icon.png",
            meipass / "icon.png",
            meipass / "assets" / "icon.ico",
        ])

    # 2. Package directory
    pkg_dir = Path(__file__).resolve().parent
    candidates.append(pkg_dir / "icon.png")

    # 3. Repository root / assets
    repo_root = pkg_dir.parents[1]
    candidates.extend([
        repo_root / "assets" / "icon.png",
        repo_root / "assets" / "icon.ico",
    ])

    # 4. Current working directory
    cwd = Path.cwd()
    candidates.extend([
        cwd / "assets" / "icon.png",
        cwd / "icon.png",
    ])

    for p in candidates:
        if p.is_file():
            return str(p)

    return None


def get_app_icon() -> QIcon:
    """Return the application QIcon."""
    icon_path = get_icon_path()
    if icon_path and os.path.isfile(icon_path):
        return QIcon(icon_path)
    return QIcon()


def get_app_pixmap(size: int = 40) -> Optional[QPixmap]:
    """Return a scaled QPixmap of the application icon."""
    icon_path = get_icon_path()
    if icon_path and os.path.isfile(icon_path):
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            return pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return None
