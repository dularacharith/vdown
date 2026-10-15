"""Application launcher for VDown Desktop GUI."""

import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from simple_downloader.gui.main_window import MainWindow
from simple_downloader.gui.resources import get_app_icon


def main():
    """Main desktop GUI entry point."""
    # Ensure Windows taskbar groups and shows the custom app icon
    if sys.platform == "win32":
        try:
            import ctypes
            myappid = "dularacharith.vdown.desktop.2.0.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    # Enable High DPI scaling
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QApplication(sys.argv)
    app.setApplicationName("VDown")
    app.setApplicationDisplayName("VDown - Universal Media Downloader")
    app.setOrganizationName("VDown")

    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
