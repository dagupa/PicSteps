from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import SPLASH_SIZE, build_icon, build_splash
from picsteps.config import resource_path


class AppIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_uses_bundled_image(self) -> None:
        self.assertTrue(os.path.isfile(resource_path("assets", "picsteps.png")))
        icon = build_icon()
        self.assertFalse(icon.isNull())
        self.assertTrue(icon.availableSizes())

    def test_splash_uses_bundled_image(self) -> None:
        splash = build_splash()
        self.addCleanup(splash.close)
        pixmap = splash.pixmap()
        self.assertFalse(pixmap.isNull())
        self.assertEqual(max(pixmap.width(), pixmap.height()), SPLASH_SIZE)


if __name__ == "__main__":
    unittest.main()
