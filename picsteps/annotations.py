"""Anotaciones vectoriales no destructivas y su pintado."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QLabel

DEFAULT_COLOR = "#ff3b30"
DEFAULT_WIDTH = 0.004
DEFAULT_FONT_SIZE = 0.045
SHAPE_TYPES = {"arrow", "rect", "ellipse", "text"}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _number(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _point(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    return (
        _clamp(_number(value[0], 0.0), 0.0, 1.0),
        _clamp(_number(value[1], 0.0), 0.0, 1.0),
    )


def normalize_annotations(raw: object) -> list[dict]:
    """Valida y normaliza una lista de anotaciones leída de JSON."""
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind not in SHAPE_TYPES:
            continue
        color = item.get("color", DEFAULT_COLOR)
        if not isinstance(color, str) or not _HEX_COLOR.match(color):
            color = DEFAULT_COLOR
        width = _clamp(
            _number(item.get("width"), DEFAULT_WIDTH),
            0.0005,
            0.03,
        )
        points: list[tuple[float, float]] = []
        raw_points = item.get("points")
        if isinstance(raw_points, list):
            for raw_point in raw_points:
                point = _point(raw_point)
                if point is not None:
                    points.append(point)
        if kind == "text":
            text = item.get("text", "")
            text = text.strip() if isinstance(text, str) else ""
            if not text or not points:
                continue
            font_size = _clamp(
                _number(item.get("font_size"), DEFAULT_FONT_SIZE),
                0.01,
                0.2,
            )
            result.append(
                {
                    "type": "text",
                    "color": color,
                    "width": width,
                    "points": [points[0]],
                    "text": text,
                    "font_size": font_size,
                }
            )
            continue
        if len(points) < 2:
            continue
        result.append(
            {
                "type": kind,
                "color": color,
                "width": width,
                "points": points[:2],
                "text": "",
                "font_size": DEFAULT_FONT_SIZE,
            }
        )
    return result


def make_shape(
    kind: str,
    points: Iterable[tuple[float, float]],
    color: str = DEFAULT_COLOR,
    width: float = DEFAULT_WIDTH,
    text: str = "",
    font_size: float = DEFAULT_FONT_SIZE,
) -> dict:
    """Crea una anotación normalizada a partir de datos de la interfaz."""
    normalized = normalize_annotations(
        [
            {
                "type": kind,
                "color": color,
                "width": width,
                "points": list(points),
                "text": text,
                "font_size": font_size,
            }
        ]
    )
    if normalized:
        return normalized[0]
    return {}


def rotate_point(
    point: tuple[float, float],
    rotation: int,
) -> tuple[float, float]:
    """Pasa un punto normalizado de la imagen base al giro de pantalla."""
    u, v = _point(point) or (0.0, 0.0)
    rotation %= 360
    if rotation == 90:
        return (1.0 - v, u)
    if rotation == 180:
        return (1.0 - u, 1.0 - v)
    if rotation == 270:
        return (v, 1.0 - u)
    return (u, v)


def inverse_rotate_point(
    point: tuple[float, float],
    rotation: int,
) -> tuple[float, float]:
    """Pasa un punto de la pantalla girada a la imagen base."""
    u, v = _point(point) or (0.0, 0.0)
    rotation %= 360
    if rotation == 90:
        return (v, 1.0 - u)
    if rotation == 180:
        return (1.0 - u, 1.0 - v)
    if rotation == 270:
        return (1.0 - v, u)
    return (u, v)


def _map_point(
    point: tuple[float, float],
    image_rect: QRectF,
    rotation: int,
) -> QPointF:
    u, v = rotate_point(point, rotation)
    return QPointF(
        image_rect.left() + u * image_rect.width(),
        image_rect.top() + v * image_rect.height(),
    )


def _draw_arrow(
    painter: QPainter,
    start: QPointF,
    end: QPointF,
    color: QColor,
    line_width: float,
) -> None:
    painter.setPen(
        QPen(
            color,
            line_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.drawLine(start, end)
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    head = max(7.0, line_width * 4.0)
    side = head * 0.55
    left = QPointF(
        end.x() - ux * head - uy * side,
        end.y() - uy * head + ux * side,
    )
    right = QPointF(
        end.x() - ux * head + uy * side,
        end.y() - uy * head - ux * side,
    )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF([end, left, right]))


def paint_annotations(
    painter: QPainter,
    image_rect: QRectF,
    annotations: Iterable[dict],
    rotation: int = 0,
) -> None:
    """Pinta anotaciones normalizadas sobre el rectángulo de la imagen."""
    items = normalize_annotations(list(annotations))
    if not items or image_rect.width() <= 1 or image_rect.height() <= 1:
        return

    shortest = min(image_rect.width(), image_rect.height())
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setClipRect(image_rect)
    for item in items:
        kind = item["type"]
        color = QColor(item["color"])
        line_width = max(1.0, item["width"] * shortest)
        points = [
            _map_point(point, image_rect, rotation)
            for point in item["points"]
        ]
        if kind == "arrow":
            _draw_arrow(painter, points[0], points[1], color, line_width)
            continue
        if kind in {"rect", "ellipse"}:
            shape = QRectF(points[0], points[1]).normalized()
            painter.setPen(
                QPen(
                    color,
                    line_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if kind == "rect":
                painter.drawRect(shape)
            else:
                painter.drawEllipse(shape)
            continue
        if kind == "text":
            font = QFont()
            font.setBold(True)
            font.setPixelSize(
                max(9, int(item["font_size"] * shortest))
            )
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            text = item["text"]
            bounds = metrics.boundingRect(text)
            padding = max(3.0, shortest * 0.006)
            background = QRectF(
                points[0].x() - padding,
                points[0].y() - padding,
                bounds.width() + padding * 2,
                bounds.height() + padding * 2,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 165))
            painter.drawRoundedRect(background, padding, padding)
            painter.setPen(color)
            painter.drawText(
                QPointF(points[0].x(), points[0].y() + metrics.ascent()),
                text,
            )
    painter.restore()


class AnnotatedImageLabel(QLabel):
    """QLabel que dibuja encima la capa de anotaciones."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._annotations: list[dict] = []
        self._rotation = 0

    def set_annotations(
        self,
        annotations: Iterable[dict],
        rotation: int = 0,
    ) -> None:
        self._annotations = normalize_annotations(list(annotations))
        self._rotation = int(rotation) % 360
        self.update()

    def annotations(self) -> list[dict]:
        return list(self._annotations)

    def set_rotation(self, rotation: int) -> None:
        self._rotation = int(rotation) % 360
        self.update()

    def image_rect(self) -> QRectF:
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRectF()
        ratio = pixmap.devicePixelRatio() or 1.0
        width = pixmap.width() / ratio
        height = pixmap.height() / ratio
        area = self.contentsRect()
        return QRectF(
            area.left() + (area.width() - width) / 2,
            area.top() + (area.height() - height) / 2,
            width,
            height,
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._annotations:
            return
        rect = self.image_rect()
        if rect.isEmpty():
            return
        painter = QPainter(self)
        paint_annotations(
            painter,
            rect,
            self._annotations,
            self._rotation,
        )
        painter.end()
