from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from picsteps.background import (
    BackgroundError,
    background_copy_path,
    model_path,
    remove_background_to_white,
    save_background_copy,
)


class BackgroundTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="picsteps_background_")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_copy_path_uses_sinfondo_suffix(self) -> None:
        source = os.path.join(self.temp_dir, "PASO_01.jpg")
        self.assertEqual(
            background_copy_path(source),
            os.path.join(self.temp_dir, "PASO_01_sinfondo.jpg"),
        )
        open(os.path.join(self.temp_dir, "PASO_01_sinfondo.jpg"), "wb").close()
        self.assertEqual(
            background_copy_path(source),
            os.path.join(self.temp_dir, "PASO_01_sinfondo_2.jpg"),
        )

    def test_gif_copy_uses_png(self) -> None:
        source = os.path.join(self.temp_dir, "anim.gif")
        self.assertTrue(background_copy_path(source).endswith(".png"))

    def test_save_background_copy_does_not_touch_original(self) -> None:
        source = os.path.join(self.temp_dir, "PASO_01.jpg")
        Image.new("RGB", (24, 18), (10, 20, 30)).save(source)
        original = Path(source).read_bytes()
        result = Image.new("RGB", (24, 18), (255, 255, 255))
        target = save_background_copy(source, result)
        self.assertTrue(target.endswith("PASO_01_sinfondo.jpg"))
        self.assertTrue(os.path.exists(target))
        self.assertEqual(Path(source).read_bytes(), original)

    def test_save_resets_exif_orientation(self) -> None:
        source = os.path.join(self.temp_dir, "PASO_01.jpg")
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (24, 18), (10, 20, 30)).save(source, exif=exif)
        target = save_background_copy(
            source,
            Image.new("RGB", (24, 18), (255, 255, 255)),
        )
        with Image.open(target) as saved:
            self.assertEqual(saved.getexif().get(274), 1)

    def test_animated_images_are_rejected(self) -> None:
        path = os.path.join(self.temp_dir, "anim.gif")
        first = Image.new("RGB", (12, 12), (255, 0, 0))
        second = Image.new("RGB", (12, 12), (0, 255, 0))
        first.save(path, save_all=True, append_images=[second], duration=100)
        with Image.open(path) as image:
            with self.assertRaises(BackgroundError):
                remove_background_to_white(image)

    def test_model_runs_on_real_image(self) -> None:
        try:
            model_path()
        except BackgroundError:
            self.skipTest("Modelo Silueta no disponible")
        source = Image.new("RGB", (96, 96), (245, 245, 245))
        for x in range(24, 72):
            for y in range(24, 72):
                source.putpixel((x, y), (180, 30, 20))
        result = remove_background_to_white(source)
        self.assertEqual(result.size, source.size)
        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
