"""Iconos vectoriales de la interfaz de PicSteps."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

_PATHS = {
    "back": '<path d="M19 12H5"/><path d="m11 18-6-6 6-6"/>',
    "forward": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "up": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    "refresh": (
        '<path d="M20 11a8 8 0 1 0-2.3 5.7"/>'
        '<path d="M20 5v6h-6"/>'
    ),
    "new_folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8'
        'a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<path d="M12 11v6"/><path d="M9 14h6"/>'
    ),
    "rename": (
        '<path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3z"/>'
        '<path d="m13.5 6.5 3 3"/>'
    ),
    "delete": (
        '<path d="M4 7h16"/><path d="M9 7V4h6v3"/>'
        '<path d="m6 7 1 13h10l1-13"/>'
        '<path d="M10 11v6"/><path d="M14 11v6"/>'
    ),
    "open": (
        '<path d="M14 4h6v6"/><path d="m20 4-9 9"/>'
        '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7'
        'a1 1 0 0 1 1-1h5"/>'
    ),
    "copy": (
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8'
        'a2 2 0 0 0 2 2h2"/>'
    ),
    "cut": (
        '<circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/>'
        '<path d="m8.2 8.2 11.8 9.8"/><path d="M8.2 15.8 20 6"/>'
    ),
    "paste": (
        '<rect x="5" y="4" width="14" height="17" rx="2"/>'
        '<path d="M9 4V2h6v2"/><path d="M8 10h8"/>'
        '<path d="M8 14h8"/><path d="M8 18h5"/>'
    ),
    "presentation": (
        '<rect x="3" y="4" width="18" height="12" rx="2"/>'
        '<path d="M8 20h8"/><path d="M12 16v4"/>'
        '<path d="m10 8 5 3-5 3z"/>'
    ),
    "dark": '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2"/><path d="M12 20v2"/>'
        '<path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/>'
        '<path d="M2 12h2"/><path d="M20 12h2"/>'
        '<path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/>'
    ),
    "help": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.8.6-1.5 1-1.5 2"/>'
        '<path d="M12 17h.01"/>'
    ),
    "undo": (
        '<path d="M9 7H4v5"/>'
        '<path d="M4 12a8 8 0 1 0 2.3-5.7"/>'
    ),
    "redo": (
        '<path d="M15 7h5v5"/>'
        '<path d="M20 12a8 8 0 1 1-2.3-5.7"/>'
    ),
    "move": (
        '<path d="M12 3v18"/><path d="M3 12h18"/>'
        '<path d="m9 6 3-3 3 3"/><path d="m9 18 3 3 3-3"/>'
        '<path d="m6 9-3 3 3 3"/><path d="m18 9 3 3-3 3"/>'
    ),
    "arrow": (
        '<path d="M5 19 19 5"/><path d="M11 5h8v8"/>'
    ),
    "rect": '<rect x="4" y="5" width="16" height="14" rx="1"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="8" ry="7"/>',
    "text": (
        '<path d="M5 5h14"/><path d="M12 5v14"/>'
        '<path d="M9 19h6"/>'
    ),
    "palette": (
        '<path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4H13'
        'a2 2 0 0 1 0-4h3a5 5 0 0 0 0-10z"/>'
        '<circle cx="7.5" cy="10" r="1"/>'
        '<circle cx="10" cy="6.8" r="1"/>'
        '<circle cx="14" cy="6.8" r="1"/>'
    ),
    "line_width": (
        '<path d="M4 6h16"/><path d="M4 12h16"/>'
        '<path d="M4 18h16"/>'
    ),
    "save": (
        '<path d="M5 3h11l3 3v15H5z"/>'
        '<path d="M8 3v6h8V3"/><path d="M8 21v-7h8v7"/>'
    ),
    "cancel": '<path d="m6 6 12 12"/><path d="m18 6-12 12"/>',
    "clear": (
        '<path d="M4 7h16"/><path d="m6 7 1 13h10l1-13"/>'
        '<path d="M9 7V4h6v3"/>'
        '<path d="M10 11v6"/><path d="M14 11v6"/>'
    ),
    "background": (
        '<path d="m15 4 5 5L9 20l-5-5z"/>'
        '<path d="M5 4v3"/><path d="M3.5 5.5h3"/>'
        '<path d="M19 14v3"/><path d="M17.5 15.5h3"/>'
    ),
    "rotate_left": (
        '<path d="M4 12a8 8 0 1 1 2.3 5.7"/>'
        '<path d="M4 5v7h7"/>'
    ),
    "rotate_right": (
        '<path d="M20 12a8 8 0 1 0-2.3 5.7"/>'
        '<path d="M20 5v7h-7"/>'
    ),
    "annotate": (
        '<path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3z"/>'
        '<path d="m14.5 7.5 3 3"/>'
    ),
    "renumber": (
        '<path d="M4 6h2v4"/><path d="M4 10h4"/>'
        '<path d="M4 14h4"/><path d="M4 18h4"/>'
        '<path d="M12 6h8"/><path d="M12 12h8"/><path d="M12 18h8"/>'
    ),
}


@lru_cache(maxsize=128)
def icon(name: str, color: str) -> QIcon:
    """Devuelve un icono vectorial coloreado y adaptado a pantallas HiDPI."""
    body = _PATHS.get(name)
    if body is None:
        return QIcon()

    svg = _SVG.format(color=color, body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64):
        for scale in (1, 2):
            pixels = size * scale
            pixmap = QPixmap(pixels, pixels)
            pixmap.setDevicePixelRatio(scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            renderer.render(painter, QRectF(0, 0, pixels, pixels))
            painter.end()
            result.addPixmap(pixmap)
    return result


def themed_icon(name: str, widget) -> QIcon:
    """Devuelve un icono con el color de texto del widget."""
    color = widget.palette().color(QPalette.ColorRole.WindowText).name()
    return icon(name, color)
