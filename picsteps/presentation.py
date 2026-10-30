"""Modo presentación a pantalla completa."""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap, QTransform
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class PresentationWindow(QWidget):
    closed = Signal()

    def __init__(
        self,
        paths: list[str],
        rotations: dict[str, int],
        parent=None,
        start_index: int = 0,
    ):
        super().__init__(
            parent,
            Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet("background: #000000;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._paths = list(paths)
        self._rotations = dict(rotations)
        self._index = 0
        if self._paths:
            self._index = max(0, min(int(start_index), len(self._paths) - 1))
        self._image: QImage | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #000000;")
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.image_label, 1)

        self.caption = QLabel()
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet(
            "background: #0b0b0b; color: #e6e6e6; padding: 10px; "
            "font-size: 15px;"
        )
        layout.addWidget(self.caption)

    def start(self) -> None:
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self._load_current()

    def _load_current(self) -> None:
        if not self._paths:
            self.close()
            return
        self._index %= len(self._paths)
        path = self._paths[self._index]
        rotation = int(self._rotations.get(path, 0)) % 360

        reader = QImageReader(path)
        reader.setAutoTransform(True)
        screen = self.screen()
        if screen is not None:
            available = screen.size()
            source_size = reader.size()
            if source_size.isValid():
                scaled = source_size.scaled(
                    available,
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
                reader.setScaledSize(scaled)

        image = reader.read()
        if image.isNull():
            self._image = None
            self.image_label.setText(
                "No se pudo mostrar esta imagen\n" + os.path.basename(path)
            )
            self.image_label.setStyleSheet(
                "background: #000000; color: #cccccc; font-size: 18px;"
            )
        else:
            if rotation:
                image = image.transformed(
                    QTransform().rotate(rotation),
                    Qt.TransformationMode.SmoothTransformation,
                )
            self._image = image
            self._update_pixmap()

        name = os.path.basename(path)
        self.caption.setText(
            f"Paso {self._index + 1:02d} de {len(self._paths):02d} · {name}"
            "<br><span style='color:#8f8f8f; font-size:12px;'>"
            "← → para navegar · Esc para salir</span>"
        )

    def _update_pixmap(self) -> None:
        if self._image is None:
            return
        target = self.image_label.size()
        if target.width() < 20 or target.height() < 20:
            return
        dpr = self.devicePixelRatioF()
        target_px = QSize(
            max(1, int(target.width() * dpr)),
            max(1, int(target.height() * dpr)),
        )
        pixmap = QPixmap.fromImage(self._image).scaled(
            target_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(dpr)
        self.image_label.setPixmap(pixmap)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
            return
        if key in (
            Qt.Key.Key_Right,
            Qt.Key.Key_Space,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_Down,
        ):
            self._index += 1
            self._load_current()
            return
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_Up,
        ):
            self._index -= 1
            self._load_current()
            return
        if key == Qt.Key.Key_Home:
            self._index = 0
            self._load_current()
            return
        if key == Qt.Key.Key_End:
            self._index = len(self._paths) - 1
            self._load_current()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)
