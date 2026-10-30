from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from picsteps import fileops
from picsteps.fileops import (
    FileMove,
    apply_rename_plan,
    build_rename_plan,
    build_step_name,
    list_folder,
    load_undo_journal,
    natural_key,
    padding_for,
    rename_path,
    save_rotation,
    save_undo_journal,
    split_step_name,
    undo_moves,
    validate_rename_plan,
    RenameError,
)


class NaturalSortTests(unittest.TestCase):
    def test_natural_key(self):
        names = ["foto10.jpg", "foto2.jpg", "Foto1.jpg", "foto20.jpg"]
        ordered = sorted(names, key=natural_key)
        self.assertEqual(ordered, ["Foto1.jpg", "foto2.jpg", "foto10.jpg", "foto20.jpg"])


class StepNameTests(unittest.TestCase):
    def test_split_default_prefix(self):
        self.assertEqual(split_step_name("01_foto.jpg"), ("foto", 1, ".jpg"))
        self.assertEqual(split_step_name("001_foto.JPG"), ("foto", 1, ".JPG"))

    def test_year_is_not_a_step(self):
        self.assertEqual(
            split_step_name("2024_foto.jpg"), ("2024_foto", None, ".jpg")
        )

    def test_custom_prefix(self):
        self.assertEqual(
            split_step_name("PASO_03_foto.png", "PASO_"), ("foto", 3, ".png")
        )
        self.assertEqual(
            split_step_name("03_foto.png", "PASO_"), ("foto", 3, ".png")
        )

    def test_name_with_number_not_at_start(self):
        self.assertEqual(
            split_step_name("foto_01.jpg"), ("foto_01", None, ".jpg")
        )

    def test_build_step_name(self):
        self.assertEqual(
            build_step_name("IMG_1234.jpg", 3, 2), "03_IMG_1234.jpg"
        )
        self.assertEqual(
            build_step_name("2024_foto.jpg", 1, 2), "01_2024_foto.jpg"
        )
        self.assertEqual(
            build_step_name("foto.png", 2, 2, "PASO_"), "PASO_02_foto.png"
        )

    def test_padding(self):
        self.assertEqual(padding_for(7), 2)
        self.assertEqual(padding_for(99), 2)
        self.assertEqual(padding_for(100), 3)
        self.assertEqual(padding_for(1200), 4)


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, *names: str) -> list[str]:
        paths = []
        for name in names:
            path = self.folder / name
            path.write_bytes(b"contenido")
            paths.append(str(path))
        return paths

    def test_build_plan_swaps_names(self):
        paths = self.make("02_b.jpg", "01_a.jpg")
        plan = build_rename_plan(paths)
        self.assertEqual(Path(plan[0].target).name, "01_b.jpg")
        self.assertEqual(Path(plan[1].target).name, "02_a.jpg")

    def test_plan_with_same_base_swapped_is_valid(self):
        paths = self.make("01_a.jpg", "02_a.jpg")
        plan = build_rename_plan(list(reversed(paths)))
        validate_rename_plan(plan)
        apply_rename_plan(plan)
        self.assertTrue((self.folder / "01_a.jpg").exists())
        self.assertTrue((self.folder / "02_a.jpg").exists())

    def test_apply_and_undo(self):
        paths = self.make("IMG_2.jpg", "IMG_1.jpg")
        plan = build_rename_plan(paths)
        moves = apply_rename_plan(plan)
        self.assertEqual(len(moves), 2)
        self.assertEqual(
            sorted(path.name for path in self.folder.iterdir()),
            ["01_IMG_2.jpg", "02_IMG_1.jpg"],
        )
        undo_moves(moves)
        self.assertEqual(
            sorted(path.name for path in self.folder.iterdir()),
            ["IMG_1.jpg", "IMG_2.jpg"],
        )

    def test_collision_aborts_without_changes(self):
        paths = self.make("foto.jpg")
        (self.folder / "01_foto.jpg").write_bytes(b"otro")
        plan = build_rename_plan(paths)
        with self.assertRaises(RenameError):
            apply_rename_plan(plan)
        self.assertTrue((self.folder / "foto.jpg").exists())
        self.assertTrue((self.folder / "01_foto.jpg").exists())

    def test_rollback_on_failure(self):
        paths = self.make("a.jpg", "b.jpg")
        plan = [
            FileMove(paths[0], str(self.folder / "x.jpg")),
            FileMove(paths[1], str(self.folder / "y.jpg")),
        ]
        real_rename = fileops._rename
        calls = []

        def failing_rename(source, target):
            calls.append((source, target))
            if len(calls) == 3:
                raise OSError("fallo simulado")
            real_rename(source, target)

        fileops._rename = failing_rename
        try:
            with self.assertRaises(RenameError):
                apply_rename_plan(plan)
        finally:
            fileops._rename = real_rename

        self.assertTrue((self.folder / "a.jpg").exists())
        self.assertTrue((self.folder / "b.jpg").exists())
        self.assertFalse(any(fileops.TEMP_MARKER in name for name in os.listdir(self.folder)))

    def test_case_only_rename(self):
        paths = self.make("foto.jpg")
        rename_path(paths[0], "Foto.jpg")
        self.assertIn("Foto.jpg", os.listdir(self.folder))

    def test_journal_roundtrip(self):
        paths = self.make("02_a.jpg", "01_b.jpg")
        moves = apply_rename_plan(build_rename_plan(paths))
        self.assertEqual(len(moves), 2)
        with tempfile.TemporaryDirectory() as data_dir:
            original = fileops.app_data_dir
            fileops.app_data_dir = lambda: data_dir
            try:
                save_undo_journal(str(self.folder), moves)
                record = load_undo_journal(str(self.folder))
                self.assertIsNotNone(record)
                self.assertEqual(len(record.moves), 2)
                self.assertEqual(Path(record.moves[0].source).name, "02_a.jpg")
                self.assertEqual(Path(record.moves[0].target).name, "01_a.jpg")
            finally:
                fileops.app_data_dir = original

    def test_list_folder(self):
        self.make("foto10.jpg", "foto2.jpg", "nota.txt")
        (self.folder / "Subcarpeta").mkdir()
        content = list_folder(str(self.folder))
        self.assertEqual([Path(p).name for p in content.images], ["foto2.jpg", "foto10.jpg"])
        self.assertEqual([Path(p).name for p in content.folders], ["Subcarpeta"])
        self.assertEqual(content.others, [])
        content_all = list_folder(str(self.folder), show_all=True)
        self.assertEqual([Path(p).name for p in content_all.others], ["nota.txt"])


class RenameRetryTests(unittest.TestCase):
    def test_transient_sharing_violation_is_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "origen.jpg"
            target = Path(folder) / "destino.jpg"
            source.write_bytes(b"foto")
            real_rename = os.rename
            calls = []

            def flaky_rename(src, dst):
                calls.append((src, dst))
                if len(calls) < 3:
                    error = OSError(32, "archivo en uso")
                    error.winerror = 32
                    raise error
                return real_rename(src, dst)

            with mock.patch.object(fileops.os, "rename", side_effect=flaky_rename):
                fileops._rename(str(source), str(target))

            self.assertEqual(len(calls), 3)
            self.assertTrue(target.exists())
            self.assertFalse(source.exists())


class RotationTests(unittest.TestCase):
    def test_rotate_jpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foto.jpg"
            Image.new("RGB", (60, 30), "red").save(path, quality=90)
            save_rotation(str(path), 90)
            with Image.open(path) as image:
                self.assertEqual(image.size, (30, 60))

    def test_rotate_png(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "foto.png"
            Image.new("RGBA", (40, 20), (0, 0, 0, 255)).save(path)
            save_rotation(str(path), 180)
            with Image.open(path) as image:
                self.assertEqual(image.size, (40, 20))


if __name__ == "__main__":
    unittest.main()
