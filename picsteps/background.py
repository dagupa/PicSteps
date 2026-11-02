"""Eliminación local de fondos con el modelo ONNX Silueta."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .config import resource_path
from .fileops import TEMP_MARKER, _replace

MODEL_NAME = "silueta.onnx"
MODEL_SIZE = 320
MODEL_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
MODEL_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
WHITE = (255, 255, 255)


class BackgroundError(Exception):
    """Error controlado al quitar el fondo de una imagen."""


def model_path() -> str:
    override = os.environ.get("PICSTEPS_BACKGROUND_MODEL", "").strip()
    candidates = [
        override,
        resource_path("models", MODEL_NAME),
        resource_path("packaging", "models", MODEL_NAME),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise BackgroundError(
        "No se encontró el modelo de fondo.\n"
        "Vuelve a generar el portátil o coloca silueta.onnx en la carpeta "
        "models del programa."
    )


@lru_cache(maxsize=1)
def _session():
    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise BackgroundError(
            "Falta el componente onnxruntime para quitar fondos."
        ) from exc

    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, min(4, os.cpu_count() or 2))
    try:
        return ort.InferenceSession(
            model_path(),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
        raise BackgroundError(
            f"No se pudo cargar el modelo de fondo:\n{exc}"
        ) from exc


def _flatten_white(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA"):
        background = Image.new("RGBA", image.size, (*WHITE, 255))
        return Image.alpha_composite(
            background,
            image.convert("RGBA"),
        ).convert("RGB")
    return image.convert("RGB")


def _mask_for(image: Image.Image) -> Image.Image:
    source = _flatten_white(image)
    resized = source.resize(
        (MODEL_SIZE, MODEL_SIZE),
        Image.Resampling.LANCZOS,
    )
    data = np.asarray(resized, dtype=np.float32)
    data = data / np.maximum(data.max(axis=(0, 1), keepdims=True), 1.0)
    data = (data - MODEL_MEAN) / MODEL_STD
    tensor = np.transpose(data, (2, 0, 1))[None, ...]

    try:
        session = _session()
        outputs = session.run(
            None,
            {session.get_inputs()[0].name: tensor},
        )
    except BackgroundError:
        raise
    except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
        raise BackgroundError(
            f"No se pudo procesar la imagen:\n{exc}"
        ) from exc

    prediction = outputs[0][0, 0]
    minimum = float(prediction.min())
    maximum = float(prediction.max())
    if maximum - minimum < 1e-6:
        raise BackgroundError(
            "No se detectó un objeto claro en la imagen."
        )
    prediction = (prediction - minimum) / (maximum - minimum)
    mask = Image.fromarray(
        np.clip(prediction * 255.0, 0, 255).astype(np.uint8),
    )
    mask = mask.resize(image.size, Image.Resampling.LANCZOS)
    radius = 1.0 if min(image.size) >= 900 else 0.6
    return mask.filter(ImageFilter.GaussianBlur(radius))


def remove_background_to_white(image: Image.Image) -> Image.Image:
    """Devuelve la imagen recortada sobre fondo blanco."""
    if getattr(image, "n_frames", 1) > 1:
        raise BackgroundError(
            "No se puede quitar el fondo de imágenes animadas o multipágina."
        )
    source = ImageOps.exif_transpose(image)
    source.load()
    mask = _mask_for(source)
    foreground = _flatten_white(source)
    white = Image.new("RGB", foreground.size, WHITE)
    return Image.composite(foreground, white, mask)


def remove_background_file(path: str) -> Image.Image:
    try:
        with Image.open(path) as image:
            image.load()
            return remove_background_to_white(image)
    except BackgroundError:
        raise
    except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
        raise BackgroundError(
            f"No se pudo abrir la imagen:\n{exc}"
        ) from exc


def background_copy_path(path: str) -> str:
    folder, name = os.path.split(os.path.abspath(path))
    stem, extension = os.path.splitext(name)
    if extension.lower() == ".gif":
        extension = ".png"
    candidate = os.path.join(folder, f"{stem}_sinfondo{extension}")
    number = 2
    while os.path.exists(candidate):
        candidate = os.path.join(
            folder,
            f"{stem}_sinfondo_{number}{extension}",
        )
        number += 1
    return candidate


def save_background_copy(
    source_path: str,
    result: Image.Image,
    target_path: str | None = None,
) -> str:
    """Guarda el resultado como copia nueva sin tocar el original."""
    source_path = os.path.abspath(source_path)
    target = os.path.abspath(
        target_path or background_copy_path(source_path)
    )
    if os.path.exists(target):
        raise BackgroundError(f"Ya existe el archivo:\n{target}")

    extension = os.path.splitext(target)[1].lower()
    image_format = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".bmp": "BMP",
        ".webp": "WEBP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }.get(extension)
    if image_format is None:
        target = os.path.splitext(target)[0] + ".png"
        extension = ".png"
        image_format = "PNG"

    output = result.convert("RGB")
    kwargs: dict = {}
    if image_format == "JPEG":
        kwargs.update(quality=95, optimize=True)
    elif image_format == "PNG":
        kwargs.update(optimize=True)
    elif image_format == "WEBP":
        kwargs.update(lossless=True, method=6)
    elif image_format == "TIFF":
        kwargs.update(compression="tiff_lzw")

    try:
        with Image.open(source_path) as source:
            icc_profile = source.info.get("icc_profile")
            exif = source.getexif()
    except Exception:  # noqa: BLE001 - la copia puede guardarse sin metadatos
        icc_profile = None
        exif = None
    if icc_profile:
        kwargs["icc_profile"] = icc_profile
    if image_format == "JPEG" and exif:
        exif[274] = 1
        kwargs["exif"] = exif.tobytes()

    descriptor, temporary = tempfile.mkstemp(
        prefix=TEMP_MARKER,
        suffix=extension,
        dir=os.path.dirname(target),
    )
    os.close(descriptor)
    try:
        output.save(temporary, format=image_format, **kwargs)
        _replace(temporary, target)
    except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
        raise BackgroundError(
            f"No se pudo guardar la copia:\n{exc}"
        ) from exc
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
    return target
