from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolBar

from picsteps.mainwindow import MainWindow


class ToolbarIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.mkdtemp(prefix="picsteps_toolbar_")
        cls.old_localappdata = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = cls.temp_dir
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            cls.temp_dir,
        )
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.old_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = cls.old_localappdata
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_toolbar_uses_icons_only(self) -> None:
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.navigate(self.temp_dir)

        toolbar = window.findChild(QToolBar, "mainToolBar")
        self.assertIsNotNone(toolbar)
        self.assertEqual(
            toolbar.toolButtonStyle(),
            Qt.ToolButtonStyle.ToolButtonIconOnly,
        )

        expected = (
            window.act_back,
            window.act_forward,
            window.act_up,
            window.act_refresh,
            window.act_new_folder,
            window.act_rename,
            window.act_delete,
            window.act_open,
            window.act_presentation,
            window.act_theme,
            window.act_help,
        )
        for action in expected:
            self.assertIn(action, toolbar.actions())
            self.assertFalse(action.icon().isNull())

        self.assertNotIn(window.act_undo, toolbar.actions())
        self.assertNotIn(window.act_renumber, toolbar.actions())

    def _window(self) -> MainWindow:
        window = MainWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        self.addCleanup(QApplication.clipboard().clear)
        return window

    def _folders(self) -> tuple[Path, Path]:
        root = Path(
            tempfile.mkdtemp(prefix="clip_", dir=self.temp_dir)
        )
        source = root / "origen"
        destination = root / "destino"
        source.mkdir()
        destination.mkdir()
        return source, destination

    def test_copy_and_paste_files(self):
        source, destination = self._folders()
        image = source / "foto.jpg"
        image.write_bytes(b"foto")
        window = self._window()

        window.navigate(str(source))
        window.view.select_paths([str(image)])
        self.assertEqual(window.act_copy.shortcut().toString(), "Ctrl+C")
        self.assertEqual(
            window.act_copy.shortcutContext(),
            Qt.ShortcutContext.WidgetWithChildrenShortcut,
        )
        window.act_copy.trigger()

        window.navigate(str(destination))
        window.act_paste.trigger()

        self.assertTrue(image.exists())
        self.assertTrue((destination / "foto.jpg").exists())

    def test_cut_and_paste_files(self):
        source, destination = self._folders()
        image = source / "foto.jpg"
        image.write_bytes(b"foto")
        window = self._window()

        window.navigate(str(source))
        window.view.select_paths([str(image)])
        self.assertEqual(window.act_cut.shortcut().toString(), "Ctrl+X")
        window.act_cut.trigger()

        window.navigate(str(destination))
        window.act_paste.trigger()

        self.assertFalse(image.exists())
        self.assertTrue((destination / "foto.jpg").exists())
        mime = QApplication.clipboard().mimeData()
        self.assertFalse(mime is not None and mime.hasUrls())


if __name__ == "__main__":
    unittest.main()
