from __future__ import annotations

import unittest

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from picsteps.annotations import (
    DEFAULT_COLOR,
    annotation_bounds,
    hit_test_annotations,
    inverse_rotate_point,
    make_shape,
    normalize_annotations,
    paint_annotations,
    rotate_point,
    translate_annotation,
)


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_normalize_filters_invalid_items(self) -> None:
        items = normalize_annotations(
            [
                None,
                {"type": "unknown"},
                {"type": "arrow", "points": [[0.1, 0.2]]},
                {
                    "type": "rect",
                    "color": "not-a-color",
                    "width": 10,
                    "points": [[-1, 0.2], [0.8, 1.5]],
                },
                {"type": "text", "points": [[0.5, 0.5]], "text": "  "},
            ]
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "rect")
        self.assertEqual(items[0]["color"], DEFAULT_COLOR)
        self.assertEqual(items[0]["width"], 0.03)
        self.assertEqual(items[0]["points"], [(0.0, 0.2), (0.8, 1.0)])

    def test_make_shape_rejects_invalid(self) -> None:
        self.assertEqual(make_shape("arrow", [(0.1, 0.2)]), {})
        shape = make_shape("text", [(0.2, 0.3)], text="Hola")
        self.assertEqual(shape["type"], "text")
        self.assertEqual(shape["text"], "Hola")
        self.assertEqual(len(shape["points"]), 1)

    def test_rotation_round_trips(self) -> None:
        point = (0.13, 0.78)
        for rotation in (0, 90, 180, 270):
            rotated = rotate_point(point, rotation)
            restored = inverse_rotate_point(rotated, rotation)
            self.assertAlmostEqual(restored[0], point[0])
            self.assertAlmostEqual(restored[1], point[1])

    def test_known_rotations(self) -> None:
        self.assertEqual(rotate_point((0.0, 0.0), 90), (1.0, 0.0))
        self.assertEqual(rotate_point((0.0, 0.0), 180), (1.0, 1.0))
        self.assertEqual(rotate_point((0.0, 0.0), 270), (0.0, 1.0))

    def test_hit_test_selects_topmost_annotation(self) -> None:
        items = [
            make_shape("rect", [(0.1, 0.1), (0.8, 0.8)]),
            make_shape("ellipse", [(0.2, 0.2), (0.7, 0.7)]),
        ]
        self.assertEqual(hit_test_annotations(items, (0.5, 0.5)), 1)
        self.assertEqual(hit_test_annotations(items, (0.95, 0.95)), -1)

    def test_hit_test_arrow_uses_distance_to_line(self) -> None:
        arrow = make_shape("arrow", [(0.1, 0.1), (0.9, 0.9)])
        self.assertEqual(hit_test_annotations([arrow], (0.5, 0.5)), 0)
        self.assertEqual(hit_test_annotations([arrow], (0.5, 0.8)), -1)

    def test_hit_test_text_uses_rendered_bounds(self) -> None:
        text = make_shape("text", [(0.2, 0.3)], text="Paso")
        self.assertEqual(hit_test_annotations([text], (0.22, 0.32)), 0)
        self.assertGreater(annotation_bounds(text).width(), 0.02)

    def test_text_renders_without_background_fill(self) -> None:
        image = QImage(400, 200, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        paint_annotations(
            painter,
            QRectF(0, 0, 400, 200),
            [
                make_shape(
                    "text",
                    [(0.1, 0.1)],
                    "#ff0000",
                    text="Hola",
                    font_size=0.1,
                )
            ],
        )
        painter.end()
        self.assertEqual(image.pixelColor(38, 20), QColor("white"))
        pixels = [
            image.pixelColor(x, y)
            for x in range(40, 110)
            for y in range(15, 45)
        ]
        self.assertTrue(
            any(
                color.red() > color.green() + 30
                and color.red() > color.blue() + 30
                for color in pixels
            )
        )

    def test_text_bounds_follow_render_reference(self) -> None:
        text = make_shape(
            "text",
            [(0.2, 0.3)],
            text="Paso",
            font_size=0.05,
        )
        small = annotation_bounds(text, 100).width()
        large = annotation_bounds(text, 1000).width()
        bigger = annotation_bounds(text, 2000).width()
        self.assertGreater(small, large)
        self.assertAlmostEqual(large, bigger, delta=0.005)

    def test_translate_clamps_shape_inside_image(self) -> None:
        shape = make_shape("rect", [(0.8, 0.8), (0.9, 0.9)])
        moved = translate_annotation(shape, 0.5, 0.5)
        self.assertEqual(moved["points"], [(0.9, 0.9), (1.0, 1.0)])

    def test_translate_clamps_text_anchor(self) -> None:
        text = make_shape("text", [(0.9, 0.9)], text="Hola")
        moved = translate_annotation(text, 0.5, -0.2)
        self.assertEqual(moved["points"], [(1.0, 0.7)])


if __name__ == "__main__":
    unittest.main()
