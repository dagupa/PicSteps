"""Modelo del grid de miniaturas y delegado de dibujo."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractListModel,
    QMimeData,
    QModelIndex,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from .config import THUMB_DEFAULT
from .fileops import FolderContent, step_number
from .thumbs import ThumbnailProvider

MIME_TYPE = "application/x-picsteps-paths"

PathRole = int(Qt.ItemDataRole.UserRole) + 1
IsDirRole = int(Qt.ItemDataRole.UserRole) + 2
IsImageRole = int(Qt.ItemDataRole.UserRole) + 3
StepRole = int(Qt.ItemDataRole.UserRole) + 4
OrderRole = int(Qt.ItemDataRole.UserRole) + 5
TitleRole = int(Qt.ItemDataRole.UserRole) + 6
NoteRole = int(Qt.ItemDataRole.UserRole) + 7
HasAnnotationsRole = int(Qt.ItemDataRole.UserRole) + 8


@dataclass
class GridItem:
    path: str
    name: str
    is_dir: bool
    is_image: bool
    step: int | None = None
    order: int = 0


class GridModel(QAbstractListModel):
    def __init__(self, provider: ThumbnailProvider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self._items: list[GridItem] = []
        self._thumb_size = THUMB_DEFAULT
        self._folder = ""
        self._step_infos: dict[str, dict] = {}
        provider.thumbnailReady.connect(self._on_thumbnail_ready)
        provider.thumbnailFailed.connect(self._on_thumbnail_failed)

    def set_content(self, content: FolderContent, prefix: str = "") -> None:
        self.beginResetModel()
        self._folder = content.folder
        self._step_infos = {}
        items: list[GridItem] = []
        for path in content.folders:
            items.append(
                GridItem(path, os.path.basename(path), True, False)
            )
        order = 0
        for path in content.images:
            order += 1
            name = os.path.basename(path)
            items.append(
                GridItem(
                    path,
                    name,
                    False,
                    True,
                    step_number(name, prefix),
                    order,
                )
            )
        for path in content.others:
            items.append(
                GridItem(path, os.path.basename(path), False, False)
            )
        self._items = items
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def step_info(self, path: str) -> dict:
        key = os.path.normcase(os.path.abspath(path))
        return self._step_infos.get(key, {})

    def set_step_infos(self, infos: dict[str, dict]) -> None:
        self._step_infos = dict(infos)
        if self._items:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._items) - 1, 0),
                [
                    TitleRole,
                    NoteRole,
                    HasAnnotationsRole,
                    Qt.ItemDataRole.ToolTipRole,
                ],
            )

    def set_step_info(self, path: str, info: dict | None) -> None:
        key = os.path.normcase(os.path.abspath(path))
        if info:
            self._step_infos[key] = dict(info)
        else:
            self._step_infos.pop(key, None)
        row = self.row_for_path(path)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(
                index,
                index,
                [
                    TitleRole,
                    NoteRole,
                    HasAnnotationsRole,
                    Qt.ItemDataRole.ToolTipRole,
                ],
            )

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        info = self.step_info(item.path) if item.is_image else {}

        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == Qt.ItemDataRole.DecorationRole:
            if item.is_image:
                return self.provider.get(item.path, self._thumb_size)
            return None
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(self._thumb_size + 26, self._thumb_size + 58)
        if role == Qt.ItemDataRole.ToolTipRole:
            if item.is_dir:
                return f"Carpeta: {item.path}"
            if item.is_image:
                step = f"Paso {item.order}" if item.step is None else f"Paso {item.step}"
                lines = [step]
                title = str(info.get("title", "")).strip()
                note = str(info.get("note", "")).strip()
                if title:
                    lines.append(title)
                if note:
                    lines.append(note)
                lines.append(item.path)
                return "\n".join(lines)
            return item.path
        if role == PathRole:
            return item.path
        if role == IsDirRole:
            return item.is_dir
        if role == IsImageRole:
            return item.is_image
        if role == StepRole:
            return item.step
        if role == OrderRole:
            return item.order
        if role == TitleRole:
            return str(info.get("title", ""))
        if role == NoteRole:
            return str(info.get("note", ""))
        if role == HasAnnotationsRole:
            return bool(info.get("annotations"))
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid() and 0 <= index.row() < len(self._items):
            if self._items[index.row()].is_image:
                base |= Qt.ItemFlag.ItemIsDragEnabled
        return base

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:
        return [MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData | None:
        paths = [
            self._items[index.row()].path
            for index in indexes
            if index.isValid()
            and 0 <= index.row() < len(self._items)
            and self._items[index.row()].is_image
        ]
        if not paths:
            return None
        mime = QMimeData()
        mime.setData(MIME_TYPE, json.dumps(paths).encode("utf-8"))
        return mime

    def set_thumb_size(self, size: int) -> None:
        size = int(size)
        if size == self._thumb_size:
            return
        self._thumb_size = size
        self.layoutChanged.emit()

    @property
    def thumb_size(self) -> int:
        return self._thumb_size

    @property
    def folder(self) -> str:
        return self._folder

    def image_rows(self) -> list[int]:
        return [row for row, item in enumerate(self._items) if item.is_image]

    def image_paths(self) -> list[str]:
        return [item.path for item in self._items if item.is_image]

    def row_for_path(self, path: str) -> int:
        key = os.path.normcase(os.path.abspath(path))
        for row, item in enumerate(self._items):
            if os.path.normcase(os.path.abspath(item.path)) == key:
                return row
        return -1

    def rows_for_paths(self, paths: list[str]) -> list[int]:
        rows = [self.row_for_path(path) for path in paths]
        return sorted(row for row in rows if row >= 0)

    def move_images(self, rows: list[int], destination: int) -> list[str]:
        rows = sorted(set(row for row in rows if 0 <= row < len(self._items)))
        if not rows:
            return self.image_paths()

        moving = [self._items[row] for row in rows]
        row_set = set(rows)
        remaining = [
            item for row, item in enumerate(self._items) if row not in row_set
        ]

        insert = destination - sum(1 for row in rows if row < destination)
        first_image = sum(1 for item in remaining if item.is_dir)
        image_count = sum(1 for item in remaining if item.is_image)
        insert = max(first_image, min(insert, first_image + image_count))

        new_items = remaining[:insert] + moving + remaining[insert:]

        self.beginResetModel()
        self._items = new_items
        self._renumber()
        self.endResetModel()
        return self.image_paths()

    def _renumber(self) -> None:
        order = 0
        for item in self._items:
            if item.is_image:
                order += 1
                item.order = order

    def invalidate(self, path: str) -> None:
        self.provider.invalidate(path)
        row = self.row_for_path(path)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(
                index,
                index,
                [Qt.ItemDataRole.DecorationRole],
            )

    def _on_thumbnail_ready(self, path: str, size: int) -> None:
        if int(size) != self._thumb_size:
            return
        row = self.row_for_path(path)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(
                index,
                index,
                [Qt.ItemDataRole.DecorationRole],
            )

    def _on_thumbnail_failed(self, path: str, _message: str) -> None:
        row = self.row_for_path(path)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(
                index,
                index,
                [Qt.ItemDataRole.DecorationRole],
            )


class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, view: QListView, parent=None):
        super().__init__(parent)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        hint = index.data(Qt.ItemDataRole.SizeHintRole)
        if isinstance(hint, QSize):
            return hint
        return QSize(200, 240)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        palette = option.palette
        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            highlight = QColor(palette.color(QPalette.ColorRole.Highlight))
            dark = (
                palette.color(QPalette.ColorRole.Window).lightness() < 128
            )
            if dark:
                shadow_rect = rect
                shadow_base = highlight
                shadow_layers = ((3, 46), (2, 72))
            else:
                shadow_rect = rect.adjusted(2, 4, 2, 4)
                shadow_base = QColor(0, 0, 0)
                shadow_layers = ((2, 24), (1, 38))
            for spread, alpha in shadow_layers:
                shadow = QColor(shadow_base)
                shadow.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(shadow)
                painter.drawRoundedRect(
                    shadow_rect.adjusted(-spread, -spread, spread, spread),
                    8 + spread,
                    8 + spread,
                )
            fill = QColor(highlight)
            fill.setAlpha(125 if dark else 105)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 8, 8)
            border = QColor(highlight)
            border.setAlpha(235)
            painter.setPen(QPen(border, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 7, 7)
        elif hovered:
            color = QColor(palette.color(QPalette.ColorRole.AlternateBase))
            color.setAlpha(130)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 8, 8)

        side = min(int(self.view.thumbnail_size), rect.width() - 12, rect.height() - 44)
        side = max(40, side)
        square = QRect(
            rect.center().x() - side // 2,
            rect.top() + 6,
            side,
            side,
        )

        is_dir = bool(index.data(IsDirRole))
        is_image = bool(index.data(IsImageRole))

        if is_dir or not is_image:
            icon_type = (
                QStyle.StandardPixmap.SP_DirIcon
                if is_dir
                else QStyle.StandardPixmap.SP_FileIcon
            )
            icon = option.widget.style().standardIcon(icon_type)
            icon_side = min(side, 96)
            pixmap = icon.pixmap(QSize(icon_side, icon_side))
            painter.drawPixmap(
                square.center().x() - pixmap.width() // 2,
                square.center().y() - pixmap.height() // 2,
                pixmap,
            )
        else:
            pixmap = index.data(Qt.ItemDataRole.DecorationRole)
            if isinstance(pixmap, QPixmap) and not pixmap.isNull():
                scaled = pixmap.scaled(
                    square.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                painter.drawPixmap(
                    square.center().x() - scaled.width() // 2,
                    square.center().y() - scaled.height() // 2,
                    scaled,
                )
            else:
                painter.setPen(palette.color(QPalette.ColorRole.Mid))
                painter.setBrush(palette.color(QPalette.ColorRole.AlternateBase))
                painter.drawRoundedRect(square.adjusted(4, 4, -4, -4), 7, 7)
                font = QFont(option.font)
                font.setPointSizeF(max(12, side / 8))
                painter.setFont(font)
                painter.drawText(square, Qt.AlignmentFlag.AlignCenter, "…")

        if is_image:
            number = index.data(StepRole)
            if number is None:
                number = index.data(OrderRole)
            if number:
                text = f"{int(number):02d}" if int(number) < 100 else str(int(number))
                font = QFont(option.font)
                font.setBold(True)
                font.setPointSizeF(max(8.0, min(13.0, side / 13.0)))
                painter.setFont(font)
                metrics = QFontMetrics(font)
                badge_width = metrics.horizontalAdvance(text) + 10
                badge_height = metrics.height() + 4
                badge = QRect(
                    square.left() + 4,
                    square.top() + 4,
                    badge_width,
                    badge_height,
                )
                badge_color = QColor(palette.color(QPalette.ColorRole.Highlight))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(badge_color)
                painter.drawRoundedRect(badge, 5, 5)
                painter.setPen(palette.color(QPalette.ColorRole.HighlightedText))
                painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

        if is_image and bool(index.data(HasAnnotationsRole)):
            marker = QRect(square.right() - 18, square.top() + 4, 14, 14)
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Base), 2))
            painter.setBrush(palette.color(QPalette.ColorRole.Highlight))
            painter.drawEllipse(marker)
            painter.setPen(palette.color(QPalette.ColorRole.HighlightedText))
            font = QFont(option.font)
            font.setBold(True)
            font.setPointSizeF(7.0)
            painter.setFont(font)
            painter.drawText(marker, Qt.AlignmentFlag.AlignCenter, "A")

        text_rect = QRect(
            rect.left() + 4,
            square.bottom() + 5,
            rect.width() - 8,
            max(14, rect.bottom() - square.bottom() - 4),
        )
        font = QFont(option.font)
        font.setPointSizeF(max(8.0, min(10.0, side / 18.0)))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        name = str(index.data(TitleRole) or "").strip()
        if not name:
            name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        elided = metrics.elidedText(
            name, Qt.TextElideMode.ElideMiddle, text_rect.width()
        )
        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            elided,
        )

        painter.restore()
