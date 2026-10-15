"""Application launcher for VDown Desktop GUI."""

import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from simple_downloader.gui.main_window import MainWindow


def main():
    """Main desktop GUI entry point."""
    # Enable High DPI scaling
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("VDown")
    app.setApplicationDisplayName("VDown - Universal Media Downloader")
    app.setOrganizationName("VDown")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
