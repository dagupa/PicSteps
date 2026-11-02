"""Editor de anotaciones no destructivas."""

from __future__ import annotations

import copy
import os
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QTransform,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .annotations import (
    DEFAULT_COLOR,
    DEFAULT_WIDTH,
    hit_test_annotations,
    inverse_rotate_point,
    make_shape,
    normalize_annotations,
    paint_annotations,
    paint_selection,
    translate_annotation,
)

COLORS = (
    ("Rojo", "#ff3b30"),
    ("Amarillo", "#ffd60a"),
    ("Verde", "#34c759"),
    ("Azul", "#0a84ff"),
    ("Blanco", "#ffffff"),
    ("Negro", "#111111"),
)


def _color_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class AnnotationCanvas(QWidget):
    contentChanged = Signal()
    selectionChanged = Signal(bool)

    def __init__(
        self,
        path: str,
        rotation: int = 0,
        annotations: Iterable[dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.rotation = int(rotation) % 360
        self._annotations = normalize_annotations(list(annotations or []))
        self._image = QImage()
        self._base_size = QSize()
        self._tool = "arrow"
        self._color = DEFAULT_COLOR
        self._width_value = 4
        self._start: tuple[float, float] | None = None
        self._pending: dict | None = None
        self._undo: list[list[dict]] = []
        self._redo: list[list[dict]] = []
        self._selected: int | None = None
        self._drag_index: int | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_original: list[dict] | None = None
        self._drag_changed = False
        self.setMinimumSize(640, 420)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_cursor()
        self._load_image()

    def _load_image(self) -> None:
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        image = reader.read()
        if image.isNull():
            raise ValueError(reader.errorString() or "No se pudo abrir la imagen.")
        self._base_size = image.size()
        if self.rotation:
            image = image.transformed(
                QTransform().rotate(self.rotation),
                Qt.TransformationMode.SmoothTransformation,
            )
        limit = 2200
        if image.width() > limit or image.height() > limit:
            image = image.scaled(
                limit,
                limit,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._image = image

    def sizeHint(self) -> QSize:
        return QSize(900, 600)

    def set_tool(self, tool: str) -> None:
        if tool in {"move", "arrow", "rect", "ellipse", "text"}:
            self._tool = tool
            self._drag_index = None
            self._drag_start = None
            self._drag_original = None
            self._update_cursor()

    def set_color(self, color: str) -> None:
        self._color = color

    def set_width(self, value: int) -> None:
        self._width_value = max(1, int(value))

    def annotations(self) -> list[dict]:
        return copy.deepcopy(self._annotations)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def has_annotations(self) -> bool:
        return bool(self._annotations)

    def has_selection(self) -> bool:
        return self._selected is not None

    def _update_cursor(self) -> None:
        if self._drag_index is not None:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._tool == "move":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def _set_selected(self, index: int | None) -> None:
        if index is not None and not 0 <= index < len(self._annotations):
            index = None
        changed = index != self._selected
        self._selected = index
        if changed:
            self.selectionChanged.emit(index is not None)
        self.update()

    def clear_selection(self) -> None:
        self._set_selected(None)

    def delete_selected(self) -> None:
        if self._selected is None:
            return
        self._push_undo()
        del self._annotations[self._selected]
        self._selected = None
        self._notify_changed()
        self.selectionChanged.emit(False)
        self.update()

    def _notify_changed(self) -> None:
        self.contentChanged.emit()
        self.update()

    def _image_rect(self) -> QRectF:
        if self._image.isNull():
            return QRectF()
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if area.width() <= 1 or area.height() <= 1:
            return QRectF()
        scaled = QSize(self._image.size())
        scaled.scale(
            int(area.width()),
            int(area.height()),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        return QRectF(
            area.center().x() - scaled.width() / 2,
            area.center().y() - scaled.height() / 2,
            scaled.width(),
            scaled.height(),
        )

    def _to_base(self, position: QPointF) -> tuple[float, float] | None:
        rect = self._image_rect()
        if rect.isEmpty() or not rect.contains(position):
            return None
        u = (position.x() - rect.left()) / rect.width()
        v = (position.y() - rect.top()) / rect.height()
        return inverse_rotate_point(
            (
                max(0.0, min(1.0, u)),
                max(0.0, min(1.0, v)),
            ),
            self.rotation,
        )

    def _push_undo(self) -> None:
        self._undo.append(copy.deepcopy(self._annotations))
        del self._undo[:-50]
        self._redo.clear()

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(copy.deepcopy(self._annotations))
        self._annotations = self._undo.pop()
        self._pending = None
        self._set_selected(None)
        self._notify_changed()

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(copy.deepcopy(self._annotations))
        self._annotations = self._redo.pop()
        self._pending = None
        self._set_selected(None)
        self._notify_changed()

    def clear(self) -> None:
        if not self._annotations:
            return
        self._push_undo()
        self._annotations = []
        self._set_selected(None)
        self._notify_changed()

    def _shape(self, start, end) -> dict:
        return make_shape(
            self._tool,
            [start, end],
            self._color,
            self._width_value / 1000.0,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        rect = self._image_rect()
        point = self._to_base(event.position())
        if point is None:
            return
        if self._tool == "move":
            index = hit_test_annotations(
                self._annotations,
                point,
                reference=min(rect.width(), rect.height()),
            )
            if index < 0:
                self._set_selected(None)
                return
            self._set_selected(index)
            self._drag_index = index
            self._drag_start = point
            self._drag_original = copy.deepcopy(self._annotations)
            self._drag_changed = False
            self._update_cursor()
            return
        if self._tool == "text":
            text, accepted = QInputDialog.getText(
                self,
                "Texto de la anotación",
                "Texto:",
            )
            if accepted and text.strip():
                shape = make_shape(
                    "text",
                    [point],
                    self._color,
                    self._width_value / 1000.0,
                    text.strip(),
                )
                if shape:
                    self._push_undo()
                    self._annotations.append(shape)
                    self._set_selected(len(self._annotations) - 1)
                    self._notify_changed()
            return
        self._start = point
        self._pending = self._shape(point, point)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index is not None and self._drag_start is not None:
            point = self._to_base(event.position())
            if point is None or self._drag_original is None:
                return
            dx = point[0] - self._drag_start[0]
            dy = point[1] - self._drag_start[1]
            original = self._drag_original[self._drag_index]
            moved = translate_annotation(original, dx, dy)
            if moved:
                self._annotations[self._drag_index] = moved
                self._drag_changed = (
                    moved["points"] != original["points"]
                )
                self.update()
            return
        if self._start is not None and self._pending is not None:
            point = self._to_base(event.position())
            if point is None:
                return
            self._pending = self._shape(self._start, point)
            self.update()
            return
        if self._tool == "move":
            point = self._to_base(event.position())
            if point is not None:
                rect = self._image_rect()
                index = hit_test_annotations(
                    self._annotations,
                    point,
                    reference=min(rect.width(), rect.height()),
                )
                self.setCursor(
                    Qt.CursorShape.OpenHandCursor
                    if index >= 0
                    else Qt.CursorShape.ArrowCursor
                )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._drag_index is not None:
            if self._drag_changed and self._drag_original is not None:
                self._undo.append(self._drag_original)
                del self._undo[:-50]
                self._redo.clear()
                self._notify_changed()
            self._drag_index = None
            self._drag_start = None
            self._drag_original = None
            self._drag_changed = False
            self._update_cursor()
            return
        if self._start is not None and self._pending is not None:
            start = self._start
            end = self._pending["points"][-1]
            distance = abs(end[0] - start[0]) + abs(end[1] - start[1])
            if distance > 0.005:
                self._push_undo()
                self._annotations.append(self._pending)
                self._set_selected(len(self._annotations) - 1)
                self._notify_changed()
        self._start = None
        self._pending = None
        self.update()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selected is not None:
                self.delete_selected()
                return
        if event.key() == Qt.Key.Key_Escape:
            self._set_selected(None)
            return
        if (
            self._selected is not None
            and event.key() in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
            )
        ):
            step = 0.005
            dx = -step if event.key() == Qt.Key.Key_Left else step if event.key() == Qt.Key.Key_Right else 0.0
            dy = -step if event.key() == Qt.Key.Key_Up else step if event.key() == Qt.Key.Key_Down else 0.0
            original = copy.deepcopy(self._annotations)
            moved = translate_annotation(
                self._annotations[self._selected],
                dx,
                dy,
            )
            if moved:
                self._undo.append(original)
                del self._undo[:-50]
                self._redo.clear()
                self._annotations[self._selected] = moved
                self._notify_changed()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#171717"))
        rect = self._image_rect()
        if rect.isEmpty():
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(rect, self._image)
        paint_annotations(
            painter,
            rect,
            self._annotations,
            self.rotation,
        )
        if self._pending:
            paint_annotations(
                painter,
                rect,
                [self._pending],
                self.rotation,
            )
        if self._selected is not None and 0 <= self._selected < len(
            self._annotations
        ):
            paint_selection(
                painter,
                rect,
                self._annotations[self._selected],
                self.rotation,
            )
        painter.end()


class AnnotationDialog(QDialog):
    def __init__(
        self,
        path: str,
        rotation: int = 0,
        annotations: Iterable[dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Anotaciones — {os.path.basename(path)}")
        self.resize(1050, 760)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.canvas = AnnotationCanvas(path, rotation, annotations, self)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        tool_names = (
            ("move", "Mover anotación", "move"),
            ("arrow", "Flecha", "arrow"),
            ("rect", "Rectángulo", "rect"),
            ("ellipse", "Elipse", "ellipse"),
            ("text", "Texto", "text"),
        )
        self._tool_buttons: dict[str, QToolButton] = {}
        for tool, tooltip, icon_name in tool_names:
            button = QToolButton(self)
            button.setIcon(icons.themed_icon(icon_name, self))
            button.setIconSize(QSize(20, 20))
            button.setToolTip(tooltip)
            button.setAccessibleName(tooltip)
            button.setCheckable(True)
            button.setAutoRaise(True)
            if tool == "arrow":
                button.setChecked(True)
            button.clicked.connect(
                lambda checked=False, selected=tool: self.canvas.set_tool(selected)
            )
            self._tool_group.addButton(button)
            self._tool_buttons[tool] = button
            tools.addWidget(button)

        tools.addSpacing(12)
        self.color_box = QComboBox(self)
        self.color_box.setIconSize(QSize(16, 16))
        self.color_box.setFixedWidth(46)
        self.color_box.setToolTip("Color de la anotación")
        self.color_box.setAccessibleName("Color de la anotación")
        for index, (name, color) in enumerate(COLORS):
            self.color_box.addItem(_color_icon(color), "", color)
            self.color_box.setItemData(
                index,
                name,
                Qt.ItemDataRole.ToolTipRole,
            )
        self.color_box.currentIndexChanged.connect(self._on_color)
        tools.addWidget(self.color_box)

        tools.addSpacing(10)
        width_icon = QLabel(self)
        width_icon.setPixmap(
            icons.themed_icon("line_width", self).pixmap(16, 16)
        )
        width_icon.setToolTip("Grosor de la anotación")
        tools.addWidget(width_icon)
        self.width_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.width_slider.setRange(1, 20)
        self.width_slider.setValue(4)
        self.width_slider.setFixedWidth(110)
        self.width_slider.setToolTip("Grosor de la anotación")
        self.width_slider.valueChanged.connect(
            lambda value: self.canvas.set_width(value)
        )
        tools.addWidget(self.width_slider)
        tools.addStretch(1)

        self.undo_button = self._icon_button(
            "undo",
            "Deshacer (Ctrl+Z)",
        )
        self.redo_button = self._icon_button(
            "redo",
            "Rehacer (Ctrl+Shift+Z)",
        )
        self.delete_button = self._icon_button(
            "delete",
            "Eliminar la anotación seleccionada (Supr)",
        )
        self.clear_button = self._icon_button(
            "clear",
            "Borrar todas las anotaciones",
        )
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        tools.addWidget(self.delete_button)
        tools.addWidget(self.clear_button)
        layout.addLayout(tools)

        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.delete_button.clicked.connect(self.canvas.delete_selected)
        self.clear_button.clicked.connect(self.canvas.clear)
        self.canvas.contentChanged.connect(self._update_buttons)
        self.canvas.selectionChanged.connect(self._update_buttons)
        layout.addWidget(self.canvas, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setIcon(icons.themed_icon("save", self))
            save_button.setIconSize(QSize(18, 18))
            save_button.setText("")
            save_button.setToolTip("Guardar anotaciones")
            save_button.setAccessibleName("Guardar anotaciones")
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

        self._shortcuts = [
            QShortcut(QKeySequence("Ctrl+Z"), self),
            QShortcut(QKeySequence("Ctrl+Shift+Z"), self),
            QShortcut(QKeySequence("Ctrl+Y"), self),
        ]
        self._shortcuts[0].activated.connect(self.canvas.undo)
        self._shortcuts[1].activated.connect(self.canvas.redo)
        self._shortcuts[2].activated.connect(self.canvas.redo)
        self._update_buttons()

    def _icon_button(self, name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(icons.themed_icon(name, self))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        return button

    def _update_buttons(self, *_args) -> None:
        self.undo_button.setEnabled(self.canvas.can_undo())
        self.redo_button.setEnabled(self.canvas.can_redo())
        self.delete_button.setEnabled(self.canvas.has_selection())
        self.clear_button.setEnabled(self.canvas.has_annotations())

    def _on_color(self, index: int) -> None:
        color = self.color_box.itemData(index)
        if isinstance(color, str):
            self.canvas.set_color(color)

    def annotations(self) -> list[dict]:
        return self.canvas.annotations()
