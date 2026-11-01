from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from picsteps.stepdata import StepStore, sidecar_path


class StepStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="picsteps_steps_"))
        self.image = self.folder / "paso-01.jpg"
        self.image.write_bytes(b"foto")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.folder, ignore_errors=True)

    def test_notes_and_annotations_persist(self) -> None:
        store = StepStore()
        store.set_notes(str(self.image), "Preparar", "Mezclar bien")
        store.set_annotations(
            str(self.image),
            [
                {
                    "type": "arrow",
                    "color": "#ff3b30",
                    "width": 0.004,
                    "points": [[0.1, 0.2], [0.8, 0.9]],
                }
            ],
        )

        reloaded = StepStore()
        entry = reloaded.get(str(self.image))
        self.assertEqual(entry.title, "Preparar")
        self.assertEqual(entry.note, "Mezclar bien")
        self.assertEqual(len(entry.annotations), 1)
        self.assertTrue(os.path.exists(sidecar_path(str(self.folder))))

    def test_empty_entry_removes_sidecar(self) -> None:
        store = StepStore()
        store.set_notes(str(self.image), "Temporal", "")
        self.assertTrue(os.path.exists(sidecar_path(str(self.folder))))
        store.set_notes(str(self.image), "", "")
        self.assertFalse(os.path.exists(sidecar_path(str(self.folder))))

    def test_invalid_sidecar_is_ignored(self) -> None:
        sidecar_path(str(self.folder))
        with open(sidecar_path(str(self.folder)), "w", encoding="utf-8") as fh:
            fh.write("{no es json")
        store = StepStore()
        with self.assertLogs(level="WARNING"):
            self.assertTrue(store.get(str(self.image)).is_empty())

    def test_move_swap_preserves_both_entries(self) -> None:
        second = self.folder / "paso-02.jpg"
        second.write_bytes(b"foto")
        store = StepStore()
        store.set_notes(str(self.image), "Uno", "primera")
        store.set_notes(str(second), "Dos", "segunda")

        store.move_many(
            [
                (str(self.image), str(second)),
                (str(second), str(self.image)),
            ]
        )

        self.assertEqual(store.get(str(self.image)).title, "Dos")
        self.assertEqual(store.get(str(second)).title, "Uno")

    def test_copy_and_remove(self) -> None:
        second = self.folder / "copia.jpg"
        second.write_bytes(b"foto")
        store = StepStore()
        store.set_notes(str(self.image), "Original", "nota")
        store.copy(str(self.image), str(second))
        self.assertEqual(store.get(str(second)).title, "Original")

        store.remove_many([str(self.image), str(second)])
        self.assertTrue(store.get(str(self.image)).is_empty())
        self.assertFalse(os.path.exists(sidecar_path(str(self.folder))))

    def test_sidecar_shape(self) -> None:
        store = StepStore()
        store.set_notes(str(self.image), "Título", "Nota")
        with open(sidecar_path(str(self.folder)), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["files"]["paso-01.jpg"]["title"], "Título")
        self.assertEqual(data["files"]["paso-01.jpg"]["note"], "Nota")


if __name__ == "__main__":
    unittest.main()
