"""Editor de anotaciones no destructivas."""

from __future__ import annotations

import copy
import os
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QPainter,
    QPixmap,
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
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .annotations import (
    DEFAULT_COLOR,
    DEFAULT_WIDTH,
    inverse_rotate_point,
    make_shape,
    normalize_annotations,
    paint_annotations,
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
        self.setMinimumSize(640, 420)
        self.setMouseTracking(True)
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
        if tool in {"arrow", "rect", "ellipse", "text"}:
            self._tool = tool

    def set_color(self, color: str) -> None:
        self._color = color

    def set_width(self, value: int) -> None:
        self._width_value = max(1, int(value))

    def annotations(self) -> list[dict]:
        return copy.deepcopy(self._annotations)

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
        self.update()

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(copy.deepcopy(self._annotations))
        self._annotations = self._redo.pop()
        self._pending = None
        self.update()

    def clear(self) -> None:
        if not self._annotations:
            return
        self._push_undo()
        self._annotations = []
        self.update()

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
        point = self._to_base(event.position())
        if point is None:
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
                    self.update()
            return
        self._start = point
        self._pending = self._shape(point, point)
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._start is None or self._pending is None:
            super().mouseMoveEvent(event)
            return
        point = self._to_base(event.position())
        if point is None:
            return
        self._pending = self._shape(self._start, point)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._start is not None and self._pending is not None:
            start = self._start
            end = self._pending["points"][-1]
            distance = abs(end[0] - start[0]) + abs(end[1] - start[1])
            if distance > 0.005:
                self._push_undo()
                self._annotations.append(self._pending)
        self._start = None
        self._pending = None
        self.update()

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
            ("arrow", "Flecha"),
            ("rect", "Rectángulo"),
            ("ellipse", "Elipse"),
            ("text", "Texto"),
        )
        for tool, label in tool_names:
            button = QToolButton(self)
            button.setText(label)
            button.setCheckable(True)
            if tool == "arrow":
                button.setChecked(True)
            button.clicked.connect(
                lambda checked=False, selected=tool: self.canvas.set_tool(selected)
            )
            self._tool_group.addButton(button)
            tools.addWidget(button)

        tools.addSpacing(12)
        tools.addWidget(QLabel("Color:", self))
        self.color_box = QComboBox(self)
        for name, color in COLORS:
            self.color_box.addItem(_color_icon(color), name, color)
        self.color_box.currentIndexChanged.connect(self._on_color)
        tools.addWidget(self.color_box)

        tools.addSpacing(10)
        tools.addWidget(QLabel("Grosor:", self))
        self.width_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.width_slider.setRange(1, 20)
        self.width_slider.setValue(4)
        self.width_slider.setFixedWidth(110)
        self.width_slider.valueChanged.connect(
            lambda value: self.canvas.set_width(value)
        )
        tools.addWidget(self.width_slider)
        tools.addStretch(1)

        self.undo_button = QPushButton("Deshacer", self)
        self.redo_button = QPushButton("Rehacer", self)
        self.clear_button = QPushButton("Borrar todo", self)
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        tools.addWidget(self.clear_button)
        layout.addLayout(tools)

        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.clear_button.clicked.connect(self.canvas.clear)
        layout.addWidget(self.canvas, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("Guardar anotaciones")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_color(self, index: int) -> None:
        color = self.color_box.itemData(index)
        if isinstance(color, str):
            self.canvas.set_color(color)

    def annotations(self) -> list[dict]:
        return self.canvas.annotations()
