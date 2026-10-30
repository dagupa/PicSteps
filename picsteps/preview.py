"""Panel de vista previa con giro no destructivo."""

from __future__ import annotations

import os

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from .fileops import format_bytes, format_mtime


class _PreviewSignals(QObject):
    loaded = Signal(int, str, QImage, dict)
    failed = Signal(int, str, str)


class _PreviewWorker(QRunnable):
    def __init__(
        self,
        token: int,
        path: str,
        rotation: int,
        max_size: int,
        signals: _PreviewSignals,
    ):
        super().__init__()
        self.token = token
        self.path = path
        self.rotation = int(rotation) % 360
        self.max_size = max_size
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            with Image.open(self.path) as image:
                image = ImageOps.exif_transpose(image)
                if self.rotation:
                    image = image.rotate(-self.rotation, expand=True)
                width, height = image.size
                image.thumbnail(
                    (self.max_size, self.max_size),
                    Image.Resampling.LANCZOS,
                )
                rgba = image.convert("RGBA")
                data = rgba.tobytes("raw", "RGBA")
                qimage = QImage(
                    data,
                    rgba.width,
                    rgba.height,
                    rgba.width * 4,
                    QImage.Format.Format_RGBA8888,
                ).copy()
            self.signals.loaded.emit(
                self.token,
                self.path,
                qimage,
                {"width": width, "height": height},
            )
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.signals.failed.emit(self.token, self.path, str(exc))


class PreviewPanel(QFrame):
    rotateRequested = Signal(int)
    saveRotationRequested = Signal()
    openRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("previewPanel")
        self._path: str | None = None
        self._rotation = 0
        self._qimage: QImage | None = None
        self._info: dict = {}
        self._token = 0
        self._signals = _PreviewSignals(self)
        self._signals.loaded.connect(self._on_loaded)
        self._signals.failed.connect(self._on_failed)
        self._pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(9, 9, 9, 9)
        layout.setSpacing(7)

        title = QLabel("Vista previa")
        title.setObjectName("previewTitle")
        layout.addWidget(title)

        self.image_label = QLabel("Selecciona una imagen para verla")
        self.image_label.setObjectName("previewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(220, 240)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.image_label.setWordWrap(True)
        layout.addWidget(self.image_label, 1)

        self.info_label = QLabel("")
        self.info_label.setObjectName("mutedLabel")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.info_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Minimum,
        )
        layout.addWidget(self.info_label)

        rotate_layout = QHBoxLayout()
        rotate_layout.setSpacing(6)
        self.rotate_left = QPushButton("Girar izq.")
        self.rotate_left.setToolTip("Girar 90° a la izquierda (solo en pantalla)")
        self.rotate_right = QPushButton("Girar der.")
        self.rotate_right.setToolTip("Girar 90° a la derecha (solo en pantalla)")
        rotate_layout.addWidget(self.rotate_left)
        rotate_layout.addWidget(self.rotate_right)
        layout.addLayout(rotate_layout)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)
        self.save_button = QPushButton("Guardar giro")
        self.save_button.setObjectName("accentButton")
        self.save_button.setToolTip(
            "Aplicar el giro al archivo original (pide confirmación)"
        )
        self.open_button = QPushButton("Abrir")
        self.open_button.setToolTip("Abrir con el visor predeterminado de Windows")
        action_layout.addWidget(self.save_button, 1)
        action_layout.addWidget(self.open_button)
        layout.addLayout(action_layout)

        self.rotate_left.clicked.connect(lambda: self.rotateRequested.emit(-90))
        self.rotate_right.clicked.connect(lambda: self.rotateRequested.emit(90))
        self.save_button.clicked.connect(self.saveRotationRequested.emit)
        self.open_button.clicked.connect(self.openRequested.emit)

        self._update_buttons()

    @property
    def current_path(self) -> str | None:
        return self._path

    def set_image(self, path: str | None, rotation: int = 0) -> None:
        if not path:
            self.clear()
            return
        rotation = int(rotation) % 360
        if path == self._path and rotation == self._rotation and self._qimage:
            return
        self._path = path
        self._rotation = rotation
        self._token += 1
        self._qimage = None
        self._info = {}
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("Cargando…")
        self.info_label.setText("Cargando imagen…")
        self._update_buttons()
        worker = _PreviewWorker(
            self._token,
            path,
            rotation,
            2200,
            self._signals,
        )
        self._pool.start(worker)

    def set_rotation(self, rotation: int) -> None:
        if self._path:
            self.set_image(self._path, rotation)

    def clear(self) -> None:
        self._token += 1
        self._path = None
        self._rotation = 0
        self._qimage = None
        self._info = {}
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("Selecciona una imagen para verla")
        self.info_label.setText("")
        self._update_buttons()

    def _on_loaded(
        self, token: int, path: str, image: QImage, info: dict
    ) -> None:
        if token != self._token or path != self._path:
            return
        self._qimage = image
        self._info = info
        self.image_label.setText("")
        self._update_info()
        self._update_pixmap()
        self._update_buttons()

    def _on_failed(self, token: int, path: str, message: str) -> None:
        if token != self._token or path != self._path:
            return
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("No se pudo mostrar esta imagen")
        self.info_label.setText(message)

    def _update_info(self) -> None:
        if not self._path:
            return
        try:
            size = os.path.getsize(self._path)
            mtime = os.path.getmtime(self._path)
        except OSError:
            size = 0
            mtime = 0
        width = int(self._info.get("width", 0))
        height = int(self._info.get("height", 0))
        parts = [
            f"<b>{os.path.basename(self._path)}</b>",
            f"{width} × {height} px · {format_bytes(size)}",
            f"Modificado: {format_mtime(mtime)}",
        ]
        if self._rotation % 360:
            parts.append(f"Giro sin guardar: {self._rotation % 360}°")
        self.info_label.setText("<br>".join(parts))

    def _update_pixmap(self) -> None:
        if self._qimage is None:
            return
        target = self.image_label.size()
        if target.width() < 20 or target.height() < 20:
            return
        dpr = self.devicePixelRatioF()
        target_px = QSize(
            max(1, int(target.width() * dpr)),
            max(1, int(target.height() * dpr)),
        )
        pixmap = QPixmap.fromImage(self._qimage).scaled(
            target_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(dpr)
        self.image_label.setPixmap(pixmap)

    def shutdown(self) -> None:
        self._token += 1
        QThreadPool.globalInstance().clear()
        QThreadPool.globalInstance().waitForDone(1500)

    def _update_buttons(self) -> None:
        has_image = self._path is not None
        self.rotate_left.setEnabled(has_image)
        self.rotate_right.setEnabled(has_image)
        self.open_button.setEnabled(has_image)
        self.save_button.setEnabled(has_image and bool(self._rotation % 360))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_pixmap()
