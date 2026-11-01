from __future__ import annotations

import unittest

from picsteps.annotations import (
    DEFAULT_COLOR,
    inverse_rotate_point,
    make_shape,
    normalize_annotations,
    rotate_point,
)


class AnnotationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
