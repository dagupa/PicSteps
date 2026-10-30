"""Árbol de carpetas y grid de miniaturas con arrastre interno."""

from __future__ import annotations

import json
import os

from PySide6.QtCore import (
    QDir,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDrag, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileSystemModel,
    QListView,
    QTreeView,
)

from .config import THUMB_DEFAULT
from .models import (
    MIME_TYPE,
    IsImageRole,
    PathRole,
    ThumbnailDelegate,
)


class FolderTree(QTreeView):
    folderActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setFilter(
            QDir.Filter.AllDirs
            | QDir.Filter.NoDotAndDotDot
            | QDir.Filter.Drives
        )
        self.fs_model.setRootPath("")
        self.setModel(self.fs_model)
        for column in range(1, 4):
            self.hideColumn(column)
        self.setHeaderHidden(True)
        self.setAnimated(False)
        self.setIndentation(14)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)
        self.doubleClicked.connect(self._on_double_clicked)
        self.activated.connect(self._on_double_clicked)

    def _on_double_clicked(self, index: QModelIndex) -> None:
        path = self.fs_model.filePath(index)
        if path and os.path.isdir(path):
            self.folderActivated.emit(path)

    def set_folder(self, path: str) -> None:
        index = self.fs_model.index(path)
        if not index.isValid():
            return
        self.setCurrentIndex(index)
        self._expand_parents(index)
        self.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)
        QTimer.singleShot(0, lambda current=path: self._reveal_path(current))
        QTimer.singleShot(350, lambda current=path: self._reveal_path(current))

    def _expand_parents(self, index: QModelIndex) -> None:
        parent = index.parent()
        while parent.isValid():
            self.expand(parent)
            parent = parent.parent()

    def _reveal_path(self, path: str) -> None:
        index = self.fs_model.index(path)
        if not index.isValid():
            return
        self._expand_parents(index)
        self.scrollTo(
            index,
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )


class ThumbnailView(QListView):
    imagesReordered = Signal(list)
    openRequested = Signal(str)
    zoomRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_size = THUMB_DEFAULT
        self._drop_row = -1
        self._drop_after = False
        self._delegate = ThumbnailDelegate(self, self)

        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.setItemDelegate(self._delegate)
        self.set_thumbnail_size(self._thumb_size)

    @property
    def thumbnail_size(self) -> int:
        return self._thumb_size

    def set_thumbnail_size(self, size: int) -> None:
        self._thumb_size = int(size)
        self.setGridSize(
            QSize(self._thumb_size + 26, self._thumb_size + 58)
        )
        self.viewport().update()

    def select_paths(self, paths: list[str]) -> None:
        model = self.model()
        if model is None:
            return
        selection_model = self.selectionModel()
        selection_model.clearSelection()
        last_index = QModelIndex()
        for path in paths:
            row = model.row_for_path(path)
            if row < 0:
                continue
            index = model.index(row, 0)
            selection_model.select(
                index,
                QItemSelectionModel.SelectionFlag.Select,
            )
            last_index = index
        if last_index.isValid():
            self.setCurrentIndex(last_index)
            self.scrollTo(last_index)

    def startDrag(self, supported_actions) -> None:
        model = self.model()
        if model is None:
            return
        indexes = [
            index
            for index in self.selectedIndexes()
            if index.data(IsImageRole)
        ]
        if not indexes:
            return
        mime = model.mimeData(indexes)
        if mime is None:
            return
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = model.data(indexes[0], Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            scaled = pixmap.scaled(
                QSize(96, 96),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            drag.setPixmap(scaled)
            drag.setHotSpot(scaled.rect().center())
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat(MIME_TYPE):
            event.ignore()
            return
        row, after = self._compute_target(event.position().toPoint())
        self._drop_row = row
        self._drop_after = after
        self.viewport().update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._drop_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(MIME_TYPE):
            event.ignore()
            return
        try:
            paths = json.loads(
                bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8")
            )
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return

        row, after = self._compute_target(event.position().toPoint())
        self._drop_row = -1
        self.viewport().update()

        model = self.model()
        rows = model.rows_for_paths(paths)
        if not rows:
            event.ignore()
            return

        old_order = model.image_paths()
        destination = row + (1 if after else 0)
        new_order = model.move_images(rows, destination)
        if new_order == old_order:
            self.select_paths(paths)
            event.accept()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.imagesReordered.emit(new_order)

    def _compute_target(self, position: QPoint) -> tuple[int, bool]:
        model = self.model()
        image_rows = model.image_rows() if model is not None else []
        if not image_rows:
            return -1, False
        index = self.indexAt(position)
        if not index.isValid():
            return image_rows[-1], True
        if not index.data(IsImageRole):
            return image_rows[-1], True
        rect = self.visualRect(index)
        after = position.x() > rect.center().x()
        return index.row(), after

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_row < 0:
            return
        model = self.model()
        image_rows = model.image_rows() if model is not None else []
        if not image_rows:
            return
        row = min(max(self._drop_row, image_rows[0]), image_rows[-1])
        index = model.index(row, 0)
        rect = self.visualRect(index)
        if not rect.isValid():
            return
        x = rect.left() - 2 if not self._drop_after else rect.right() + 2
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(
            QPen(self.palette().color(QPalette.ColorRole.Highlight), 3)
        )
        painter.drawLine(x, rect.top() + 4, x, rect.bottom() - 4)

    def mouseDoubleClickEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            path = index.data(PathRole)
            if path:
                self.openRequested.emit(path)
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            index = self.currentIndex()
            if index.isValid():
                path = index.data(PathRole)
                if path:
                    self.openRequested.emit(path)
                    return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoomRequested.emit(event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)
