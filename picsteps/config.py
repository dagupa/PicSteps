"""Constantes y rutas de datos de PicSteps (sin dependencias de Qt)."""

from __future__ import annotations

import os

APP_NAME = "PicSteps"
ORG_NAME = "PicSteps"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
}

THUMB_MIN = 80
THUMB_MAX = 400
THUMB_DEFAULT = 180
THUMB_STEP = 10

MAX_UNDO_LEVELS = 20


def app_data_dir() -> str:
    """Carpeta de datos de la aplicación, creada si no existe."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def rotations_path() -> str:
    return os.path.join(app_data_dir(), "rotations.json")


def log_path() -> str:
    return os.path.join(app_data_dir(), "picsteps.log")
