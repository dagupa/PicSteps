from __future__ import annotations

import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton

from picsteps.annotationdialog import AnnotationDialog
from picsteps.annotations import make_shape


class AnnotationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="picsteps_annot_")
        self.path = os.path.join(self.temp_dir, "paso.jpg")
        Image.new("RGB", (400, 300), (240, 240, 240)).save(self.path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_toolbar_is_icon_only(self) -> None:
        dialog = AnnotationDialog(self.path)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        dialog.show()
        QTest.qWait(30)

        self.assertEqual(set(dialog._tool_buttons), {
            "move", "arrow", "rect", "ellipse", "text",
        })
        for button in dialog.findChildren(QToolButton):
            self.assertEqual(button.text(), "")
            self.assertFalse(button.icon().isNull())
            self.assertTrue(button.toolTip())
        for button in dialog.findChildren(QPushButton):
            self.assertEqual(button.text(), "")
            self.assertFalse(button.icon().isNull())
        self.assertEqual(dialog.color_box.itemText(0), "")

    def test_move_tool_drags_annotation_and_can_undo(self) -> None:
        shape = make_shape("rect", [(0.2, 0.2), (0.4, 0.4)])
        dialog = AnnotationDialog(self.path, annotations=[shape])
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        dialog.show()
        QTest.qWait(30)

        canvas = dialog.canvas
        dialog._tool_buttons["move"].click()
        rect = canvas._image_rect()
        start = QPoint(
            int(rect.left() + 0.3 * rect.width()),
            int(rect.top() + 0.3 * rect.height()),
        )
        end = QPoint(
            int(rect.left() + 0.5 * rect.width()),
            int(rect.top() + 0.5 * rect.height()),
        )
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, end, delay=10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(20)

        points = canvas.annotations()[0]["points"]
        self.assertAlmostEqual(points[0][0], 0.4, places=2)
        self.assertAlmostEqual(points[0][1], 0.4, places=2)
        self.assertTrue(canvas.can_undo())

        canvas.undo()
        restored = canvas.annotations()[0]["points"]
        self.assertAlmostEqual(restored[0][0], 0.2, places=2)
        self.assertAlmostEqual(restored[0][1], 0.2, places=2)


if __name__ == "__main__":
    unittest.main()
