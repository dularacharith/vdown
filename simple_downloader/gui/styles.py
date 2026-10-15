"""Modern Dark / AMOLED stylesheet and themes for VDown Desktop GUI."""

DARK_THEME_QSS = """
/* Global Window & Widget Settings */
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #6366f1;
    selection-color: #ffffff;
}

QMainWindow {
    background-color: #0d1117;
}

/* Header & Panels */
QFrame#HeaderFrame {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 12px 20px;
}

QFrame#CardFrame {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 16px;
}

QFrame#CardFrame:hover {
    border: 1px solid #484f58;
}

QFrame#HighlightCard {
    background-color: #161f38;
    border: 1px solid #4338ca;
    border-radius: 12px;
    padding: 16px;
}

/* Tab Bar */
QTabWidget::pane {
    border: none;
    background-color: #0d1117;
}

QTabBar::tab {
    background-color: #161b22;
    color: #8b949e;
    font-weight: 600;
    font-size: 13px;
    padding: 10px 24px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border: 1px solid transparent;
}

QTabBar::tab:hover {
    color: #f0f6fc;
    background-color: #21262d;
}

QTabBar::tab:selected {
    color: #ffffff;
    background-color: #6366f1;
    border-bottom: 2px solid #818cf8;
}

/* Labels */
QLabel {
    background-color: transparent;
    color: #e6edf3;
}

QLabel#AppTitle {
    font-size: 20px;
    font-weight: 800;
    color: #f0f6fc;
    letter-spacing: -0.5px;
}

QLabel#SectionHeader {
    font-size: 15px;
    font-weight: 700;
    color: #f0f6fc;
}

QLabel#SubText {
    color: #8b949e;
    font-size: 12px;
}

QLabel#Badge {
    background-color: #21262d;
    color: #58a6ff;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#SuccessBadge {
    background-color: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#CookieBadge {
    background-color: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

/* Text Inputs */
QLineEdit {
    background-color: #0d1117;
    color: #f0f6fc;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
}

QLineEdit:focus {
    border: 1px solid #6366f1;
    background-color: #161b22;
}

/* Buttons */
QPushButton {
    background-color: #21262d;
    color: #f0f6fc;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}

QPushButton:pressed {
    background-color: #161b22;
}

QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
    border-color: #21262d;
}

/* Primary Action Button (Download) */
QPushButton#PrimaryButton {
    background-color: #6366f1;
    color: #ffffff;
    border: 1px solid #4f46e5;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 28px;
    border-radius: 8px;
}

QPushButton#PrimaryButton:hover {
    background-color: #7c3aed;
    border-color: #6d28d9;
}

QPushButton#PrimaryButton:pressed {
    background-color: #4c1d95;
}

QPushButton#PrimaryButton:disabled {
    background-color: #312e81;
    color: #818cf8;
    border-color: #3730a3;
}

/* Secondary Button */
QPushButton#SecondaryButton {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    padding: 9px 16px;
    border-radius: 8px;
}

QPushButton#SecondaryButton:hover {
    background-color: #30363d;
}

/* Danger Button */
QPushButton#DangerButton {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 8px;
    padding: 9px 16px;
    font-weight: 600;
}

QPushButton#DangerButton:hover {
    background-color: rgba(239, 68, 68, 0.25);
    border-color: #ef4444;
}

/* Combo Box */
QComboBox {
    background-color: #0d1117;
    color: #f0f6fc;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    min-height: 20px;
}

QComboBox:focus, QComboBox:hover {
    border: 1px solid #6366f1;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    selection-background-color: #6366f1;
    selection-color: #ffffff;
    padding: 4px;
}

/* Radio Buttons */
QRadioButton {
    background-color: transparent;
    color: #e6edf3;
    font-size: 13px;
    font-weight: 500;
    spacing: 8px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid #8b949e;
    background-color: #0d1117;
}

QRadioButton::indicator:checked {
    border: 2px solid #6366f1;
    background-color: #6366f1;
}

QRadioButton::indicator:hover {
    border-color: #a5b4fc;
}

/* Checkbox */
QCheckBox {
    background-color: transparent;
    color: #e6edf3;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 2px solid #8b949e;
    background-color: #0d1117;
}

QCheckBox::indicator:checked {
    border: 2px solid #6366f1;
    background-color: #6366f1;
}

/* Progress Bar */
QProgressBar {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 700;
    font-size: 11px;
    height: 14px;
}

QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #a855f7);
    border-radius: 5px;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #0d1117;
    width: 10px;
    margin: 0px;
    border-radius: 5px;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484f58;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Table View */
QTableWidget, QTreeWidget, QListWidget {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    gridline-color: #21262d;
    color: #e6edf3;
}

QHeaderView::section {
    background-color: #0d1117;
    color: #8b949e;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #30363d;
    font-weight: 600;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #21262d;
    color: #f0f6fc;
}
"""
