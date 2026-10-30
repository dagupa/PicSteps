"""Generación asíncrona y caché de miniaturas."""

from __future__ import annotations

import os
from collections import OrderedDict

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QTransform

from .config import THUMB_DEFAULT

MAX_CACHE_BYTES = 192 * 1024 * 1024


class _WorkerSignals(QObject):
    finished = Signal(str, int, QImage, object)
    failed = Signal(str, int, str)


class _ThumbnailWorker(QRunnable):
    def __init__(self, path: str, size: int, mtime_ns: int, signals: _WorkerSignals):
        super().__init__()
        self.path = path
        self.size = size
        self.mtime_ns = mtime_ns
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            with Image.open(self.path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail((self.size, self.size), Image.Resampling.LANCZOS)
                rgba = image.convert("RGBA")
                data = rgba.tobytes("raw", "RGBA")
                qimage = QImage(
                    data,
                    rgba.width,
                    rgba.height,
                    rgba.width * 4,
                    QImage.Format.Format_RGBA8888,
                ).copy()
            self.signals.finished.emit(self.path, self.size, qimage, self.mtime_ns)
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            self.signals.failed.emit(self.path, self.size, str(exc))


class ThumbnailProvider(QObject):
    thumbnailReady = Signal(str, int)
    thumbnailFailed = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cache: OrderedDict[tuple[str, int, int], QPixmap] = OrderedDict()
        self._cache_bytes = 0
        self._pending: set[tuple[str, int, int]] = set()
        self._failed: set[tuple[str, int, int]] = set()
        self._rotations: dict[str, int] = {}
        self._size = THUMB_DEFAULT
        self._signals = _WorkerSignals(self)
        self._signals.finished.connect(self._on_finished)
        self._signals.failed.connect(self._on_failed)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(6, os.cpu_count() or 4)))

    def set_thumbnail_size(self, size: int) -> None:
        self._size = int(size)

    def set_rotation(self, path: str, degrees: int) -> None:
        degrees = int(degrees) % 360
        key = os.path.normcase(os.path.abspath(path))
        if degrees:
            self._rotations[key] = degrees
        else:
            self._rotations.pop(key, None)
        self.invalidate(path)

    def rotation(self, path: str) -> int:
        return self._rotations.get(os.path.normcase(os.path.abspath(path)), 0)

    def _key(self, path: str, size: int) -> tuple[str, int, int] | None:
        try:
            mtime_ns = os.stat(path).st_mtime_ns
        except OSError:
            return None
        return (os.path.normcase(os.path.abspath(path)), int(size), mtime_ns)

    def get(self, path: str, size: int | None = None) -> QPixmap | None:
        size = int(size or self._size)
        key = self._key(path, size)
        if key is None:
            return None
        pixmap = self._cache.get(key)
        if pixmap is not None:
            self._cache.move_to_end(key)
            return self._apply_rotation(pixmap, path)
        if key in self._failed:
            return None
        if key not in self._pending:
            self._pending.add(key)
            worker = _ThumbnailWorker(path, size, key[2], self._signals)
            self._pool.start(worker)
        return None

    def _apply_rotation(self, pixmap: QPixmap, path: str) -> QPixmap:
        degrees = self.rotation(path)
        if not degrees:
            return pixmap
        return pixmap.transformed(
            QTransform().rotate(degrees),
            Qt.TransformationMode.SmoothTransformation,
        )

    def _on_finished(
        self, path: str, size: int, image: QImage, mtime_ns: object
    ) -> None:
        key = (os.path.normcase(os.path.abspath(path)), int(size), int(mtime_ns))
        self._pending.discard(key)
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            self._failed.add(key)
            self.thumbnailFailed.emit(path, "No se pudo crear la miniatura.")
            return
        self._cache[key] = pixmap
        self._cache_bytes += max(1, pixmap.width() * pixmap.height() * 4)
        self._cache.move_to_end(key)
        while self._cache_bytes > MAX_CACHE_BYTES and len(self._cache) > 1:
            _old_key, old_pixmap = self._cache.popitem(last=False)
            self._cache_bytes -= max(1, old_pixmap.width() * old_pixmap.height() * 4)
        self.thumbnailReady.emit(path, int(size))

    def _on_failed(self, path: str, size: int, message: str) -> None:
        key = self._key(path, int(size))
        if key is not None:
            self._pending.discard(key)
            self._failed.add(key)
        self.thumbnailFailed.emit(path, message)

    def invalidate(self, path: str) -> None:
        key = os.path.normcase(os.path.abspath(path))
        for cache_key in [k for k in self._cache if k[0] == key]:
            pixmap = self._cache.pop(cache_key)
            self._cache_bytes -= max(1, pixmap.width() * pixmap.height() * 4)
        for failed_key in [k for k in self._failed if k[0] == key]:
            self._failed.discard(failed_key)
        for pending_key in [k for k in self._pending if k[0] == key]:
            self._pending.discard(pending_key)

    def clear(self) -> None:
        self._cache.clear()
        self._pending.clear()
        self._failed.clear()
        self._cache_bytes = 0

    def shutdown(self) -> None:
        self._pool.clear()
        self._pool.waitForDone(2000)
