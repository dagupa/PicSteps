"""Diálogo de vista previa para quitar el fondo de una imagen."""

from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressBar,
    QVBoxLayout,
)

from . import icons
from .background import (
    BackgroundError,
    remove_background_file,
    save_background_copy,
)


class _Signals(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)


class _Worker(QRunnable):
    def __init__(self, path: str, signals: _Signals):
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = remove_background_file(self.path)
            self.signals.finished.emit(self.path, result)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.signals.failed.emit(self.path, str(exc))


def _qimage(image: Image.Image) -> QImage:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    return QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


class BackgroundDialog(QDialog):
    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.result_image: Image.Image | None = None
        self.saved_path: str | None = None
        self._signals = _Signals()
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)

        self.setWindowTitle(f"Quitar fondo — {os.path.basename(path)}")
        self.setModal(True)
        self.resize(900, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel(
            "Vista previa sobre fondo blanco. El original no se modificará.",
            self,
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        self.preview = QLabel("Procesando imagen…", self)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(520, 420)
        self.preview.setStyleSheet(
            "background: #ffffff; color: #444444; border: 1px solid #999999;"
        )
        layout.addWidget(self.preview, 1)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.info = QLabel("Se guardará una copia nueva junto al original.", self)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.save_button = buttons.button(
            QDialogButtonBox.StandardButton.Save
        )
        if self.save_button is not None:
            self.save_button.setIcon(icons.themed_icon("save", self))
            self.save_button.setIconSize(QSize(18, 18))
            self.save_button.setText("")
            self.save_button.setToolTip("Guardar copia sin fondo")
            self.save_button.setAccessibleName("Guardar copia sin fondo")
            self.save_button.setEnabled(False)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setIcon(icons.themed_icon("cancel", self))
            cancel_button.setIconSize(QSize(18, 18))
            cancel_button.setText("")
            cancel_button.setToolTip("Cancelar")
            cancel_button.setAccessibleName("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._worker = _Worker(path, self._signals)
        QThreadPool.globalInstance().start(self._worker)

    def _on_finished(self, path: str, result: object) -> None:
        self._worker = None
        if path != self.path or not isinstance(result, Image.Image):
            return
        self.result_image = result
        self.progress.hide()
        image = _qimage(result)
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                QSize(820, 560),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.preview.setPixmap(pixmap)
        self.info.setText(
            "Vista previa lista. Se guardará una copia nueva junto al original."
        )
        if self.save_button is not None:
            self.save_button.setEnabled(True)

    def _on_failed(self, path: str, message: str) -> None:
        self._worker = None
        if path != self.path:
            return
        self.progress.hide()
        self.preview.setText("No se pudo quitar el fondo")
        self.info.setText(message)
        self.info.setStyleSheet("color: #c62828;")

    def accept(self) -> None:
        if self.result_image is None:
            return
        try:
            self.saved_path = save_background_copy(
                self.path,
                self.result_image,
            )
        except BackgroundError as exc:
            QMessageBox.critical(self, "PicSteps", str(exc))
            return
        super().accept()
