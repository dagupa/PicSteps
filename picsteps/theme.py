"""Temas claro y oscuro de PicSteps."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "window": "#f4f5f7",
    "base": "#ffffff",
    "alternate": "#eef1f5",
    "text": "#1f2328",
    "muted": "#5f6673",
    "border": "#d4d9e1",
    "hover": "#e7ebf1",
    "accent": "#2f6feb",
    "accent_text": "#ffffff",
    "selection": "#dbe7ff",
    "menu": "#ffffff",
    "tooltip": "#2b2f36",
    "tooltip_text": "#ffffff",
    "disabled": "#9aa1ac",
}

DARK = {
    "window": "#1b1d21",
    "base": "#23262b",
    "alternate": "#282b31",
    "text": "#e8eaed",
    "muted": "#a0a6b0",
    "border": "#3a3f47",
    "hover": "#30343b",
    "accent": "#4c8dff",
    "accent_text": "#ffffff",
    "selection": "#2c3d5c",
    "menu": "#24272c",
    "tooltip": "#3a3f47",
    "tooltip_text": "#ffffff",
    "disabled": "#6f757f",
}


def effective_mode(mode: str) -> str:
    if mode in {"light", "dark"}:
        return mode
    try:
        hints = QApplication.styleHints()
        if hints.colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
    except (AttributeError, RuntimeError):
        pass
    return "light"


def build_palette(mode: str) -> QPalette:
    colors = DARK if mode == "dark" else LIGHT
    palette = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    palette.setColor(role.Window, QColor(colors["window"]))
    palette.setColor(role.WindowText, QColor(colors["text"]))
    palette.setColor(role.Base, QColor(colors["base"]))
    palette.setColor(role.AlternateBase, QColor(colors["alternate"]))
    palette.setColor(role.ToolTipBase, QColor(colors["tooltip"]))
    palette.setColor(role.ToolTipText, QColor(colors["tooltip_text"]))
    palette.setColor(role.Text, QColor(colors["text"]))
    palette.setColor(role.Button, QColor(colors["base"]))
    palette.setColor(role.ButtonText, QColor(colors["text"]))
    palette.setColor(role.BrightText, QColor("#ffffff"))
    palette.setColor(role.Highlight, QColor(colors["accent"]))
    palette.setColor(role.HighlightedText, QColor(colors["accent_text"]))
    palette.setColor(role.Link, QColor(colors["accent"]))
    palette.setColor(role.LinkVisited, QColor(colors["accent"]))
    palette.setColor(role.PlaceholderText, QColor(colors["muted"]))
    palette.setColor(role.Mid, QColor(colors["border"]))
    palette.setColor(role.Midlight, QColor(colors["hover"]))
    palette.setColor(role.Dark, QColor(colors["border"]))
    palette.setColor(role.Light, QColor(colors["base"]))

    for disabled_role in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(group.Disabled, disabled_role, QColor(colors["disabled"]))
    palette.setColor(group.Disabled, role.Highlight, QColor(colors["border"]))
    palette.setColor(group.Disabled, role.HighlightedText, QColor(colors["disabled"]))
    return palette


def stylesheet(mode: str) -> str:
    c = DARK if mode == "dark" else LIGHT
    return f"""
    QMainWindow, QDialog {{
        background: {c["window"]};
    }}
    QToolBar {{
        background: {c["window"]};
        border: none;
        spacing: 3px;
        padding: 5px 6px;
    }}
    QToolBar::separator {{
        background: {c["border"]};
        width: 1px;
        margin: 5px 4px;
    }}
    QToolButton {{
        background: transparent;
        color: {c["text"]};
        border: 1px solid transparent;
        border-radius: 5px;
        padding: 5px 7px;
    }}
    QToolButton:hover {{
        background: {c["hover"]};
    }}
    QToolButton:checked {{
        background: {c["accent"]};
        color: {c["accent_text"]};
    }}
    QToolButton:disabled {{
        color: {c["disabled"]};
    }}
    QLineEdit, QComboBox {{
        background: {c["base"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 5px;
        padding: 4px 7px;
        selection-background-color: {c["accent"]};
        selection-color: {c["accent_text"]};
    }}
    QLineEdit:focus {{
        border: 1px solid {c["accent"]};
    }}
    QTreeView, QListView {{
        background: {c["base"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 7px;
        outline: none;
        selection-background-color: {c["selection"]};
        selection-color: {c["text"]};
    }}
    QTreeView::item {{
        padding: 3px 2px;
        border-radius: 4px;
    }}
    QTreeView::item:hover {{
        background: {c["hover"]};
    }}
    QTreeView::item:selected {{
        background: {c["selection"]};
        color: {c["text"]};
    }}
    QHeaderView::section {{
        background: {c["window"]};
        color: {c["muted"]};
        border: none;
        padding: 4px;
    }}
    QSplitter::handle {{
        background: transparent;
    }}
    QSplitter::handle:horizontal {{
        width: 6px;
    }}
    QSplitter::handle:vertical {{
        height: 6px;
    }}
    QStatusBar {{
        background: {c["window"]};
        color: {c["muted"]};
    }}
    QStatusBar::item {{
        border: none;
    }}
    QMenuBar {{
        background: {c["window"]};
        color: {c["text"]};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 5px 9px;
    }}
    QMenuBar::item:selected {{
        background: {c["hover"]};
        border-radius: 4px;
    }}
    QMenu {{
        background: {c["menu"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 26px 6px 22px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background: {c["accent"]};
        color: {c["accent_text"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c["border"]};
        margin: 4px 8px;
    }}
    QPushButton {{
        background: {c["base"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 5px;
        padding: 5px 12px;
    }}
    QPushButton:hover {{
        background: {c["hover"]};
    }}
    QPushButton:pressed {{
        background: {c["selection"]};
    }}
    QPushButton:disabled {{
        color: {c["disabled"]};
    }}
    QPushButton#accentButton {{
        background: {c["accent"]};
        color: {c["accent_text"]};
        border: none;
        font-weight: 600;
    }}
    QPushButton#accentButton:disabled {{
        background: {c["alternate"]};
        color: {c["disabled"]};
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {c["border"]};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {c["accent"]};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {c["accent"]};
        width: 13px;
        margin: -5px 0;
        border-radius: 6px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border"]};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QCheckBox {{
        color: {c["text"]};
        spacing: 6px;
    }}
    QLabel {{
        color: {c["text"]};
    }}
    QLabel#mutedLabel {{
        color: {c["muted"]};
    }}
    QLabel#previewImage {{
        background: {c["alternate"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
    }}
    QLabel#previewTitle {{
        font-size: 13px;
        font-weight: 600;
    }}
    QTextBrowser {{
        background: {c["base"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
        padding: 6px;
    }}
    QToolTip {{
        background: {c["tooltip"]};
        color: {c["tooltip_text"]};
        border: 1px solid {c["border"]};
        padding: 4px;
    }}
    """


def apply_theme(app: QApplication, mode: str) -> str:
    effective = effective_mode(mode)
    app.setStyle("Fusion")
    app.setPalette(build_palette(effective))
    app.setStyleSheet(stylesheet(effective))
    return effective
