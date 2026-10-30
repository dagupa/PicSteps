from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from picsteps.presentation import PresentationWindow


class PresentationStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, paths: list[str], start_index: int) -> PresentationWindow:
        window = PresentationWindow(paths, {}, start_index=start_index)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_starts_at_requested_image(self) -> None:
        window = self._window(["a.jpg", "b.jpg", "c.jpg"], 2)
        self.assertEqual(window._index, 2)

    def test_start_index_is_clamped(self) -> None:
        window = self._window(["a.jpg", "b.jpg"], 99)
        self.assertEqual(window._index, 1)

    def test_empty_list_uses_first_index(self) -> None:
        window = self._window([], 5)
        self.assertEqual(window._index, 0)


if __name__ == "__main__":
    unittest.main()
