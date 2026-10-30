from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from picsteps.browser import ThumbnailView
from picsteps.fileops import (
    FolderContent,
    apply_rename_plan,
    build_rename_plan,
    undo_moves,
)
from picsteps.models import GridModel, MIME_TYPE
from picsteps.thumbs import ThumbnailProvider


class DragReorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="picsteps_reorder_")
        self.folder = os.path.join(self.temp_dir, "fotos")
        os.makedirs(self.folder)
        self.paths = []
        for number in range(1, 8):
            path = os.path.join(self.folder, f"{number:02d}_foto.jpg")
            Image.new("RGB", (20 + number, 10 + number)).save(path)
            self.paths.append(path)

        content = FolderContent(self.folder, [], self.paths, [])
        self.provider = ThumbnailProvider()
        self.model = GridModel(self.provider)
        self.model.set_content(content)
        self.view = ThumbnailView()
        self.view.setModel(self.model)
        self.view.resize(1000, 700)
        self.view.show()
        for _ in range(15):
            self.app.processEvents()
            time.sleep(0.01)

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
        self.provider.shutdown()
        self.app.processEvents()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _drop_before_row(self, sources: str | list[str], target_row: int) -> None:
        if isinstance(sources, str):
            sources = [sources]
        rect = self.view.visualRect(self.model.index(target_row, 0))
        self.assertTrue(rect.isValid())
        position = QPointF(rect.left() + 2, rect.center().y())
        mime = QMimeData()
        mime.setData(MIME_TYPE, json.dumps(sources).encode("utf-8"))
        event = QDropEvent(
            position,
            Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.dropEvent(event)
        self.assertTrue(event.isAccepted())

    def test_drop_seventh_before_third_renumbers_all(self) -> None:
        self._drop_before_row(self.paths[6], 2)

        order = self.model.image_paths()
        self.assertEqual(
            [os.path.basename(path) for path in order],
            [
                "01_foto.jpg",
                "02_foto.jpg",
                "07_foto.jpg",
                "03_foto.jpg",
                "04_foto.jpg",
                "05_foto.jpg",
                "06_foto.jpg",
            ],
        )

        moves = apply_rename_plan(build_rename_plan(order))
        self.assertEqual(len(moves), 5)
        expected_sizes = {
            "01_foto.jpg": (21, 11),
            "02_foto.jpg": (22, 12),
            "03_foto.jpg": (27, 17),
            "04_foto.jpg": (23, 13),
            "05_foto.jpg": (24, 14),
            "06_foto.jpg": (25, 15),
            "07_foto.jpg": (26, 16),
        }
        for name, size in expected_sizes.items():
            with Image.open(os.path.join(self.folder, name)) as image:
                self.assertEqual(image.size, size)

        undo_moves(moves)
        self.assertEqual(
            sorted(os.listdir(self.folder)),
            [f"{number:02d}_foto.jpg" for number in range(1, 8)],
        )

    def test_drop_block_before_third_keeps_internal_order(self) -> None:
        self._drop_before_row([self.paths[5], self.paths[6]], 2)

        order = self.model.image_paths()
        self.assertEqual(
            [os.path.basename(path) for path in order],
            [
                "01_foto.jpg",
                "02_foto.jpg",
                "06_foto.jpg",
                "07_foto.jpg",
                "03_foto.jpg",
                "04_foto.jpg",
                "05_foto.jpg",
            ],
        )

        moves = apply_rename_plan(build_rename_plan(order))
        self.assertEqual(len(moves), 5)
        expected_sizes = {
            "03_foto.jpg": (26, 16),
            "04_foto.jpg": (27, 17),
            "05_foto.jpg": (23, 13),
            "06_foto.jpg": (24, 14),
            "07_foto.jpg": (25, 15),
        }
        for name, size in expected_sizes.items():
            with Image.open(os.path.join(self.folder, name)) as image:
                self.assertEqual(image.size, size)


if __name__ == "__main__":
    unittest.main()
