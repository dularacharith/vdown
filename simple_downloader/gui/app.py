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

    from PyQt6.QtGui import QIcon
    icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
