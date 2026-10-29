"""Operaciones de archivos de PicSteps: escaneo, renumerado, deshacer y giro."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from PIL import Image, ImageOps

from .config import IMAGE_EXTENSIONS, app_data_dir

TEMP_MARKER = ".picsteps_tmp_"

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class RenameError(Exception):
    """Error controlado durante un renombrado."""


@dataclass(frozen=True)
class FileMove:
    source: str
    target: str


@dataclass
class FolderContent:
    folder: str
    folders: list[str]
    images: list[str]
    others: list[str]


@dataclass
class UndoRecord:
    folder: str
    moves: list[FileMove]
    timestamp: float


def natural_key(value: str) -> tuple:
    """Clave de orden natural: foto2 antes que foto10."""
    parts = re.split(r"(\d+)", value.casefold())
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in parts
        if part
    )


def sanitize_prefix(prefix: str) -> str:
    prefix = _INVALID_CHARS.sub("", prefix or "").strip()
    if prefix and not prefix.endswith(("_", "-", " ")):
        prefix += "_"
    return prefix


def split_step_name(
    filename: str,
    prefix: str = "",
    max_count: int | None = None,
) -> tuple[str, int | None, str]:
    """Separa nombre base, número de paso y extensión.

    Solo elimina prefijos numéricos propios (2-4 dígitos seguidos de ``_``)
    y evita confundir años como ``2024_`` con un número de paso.
    """
    stem, ext = os.path.splitext(filename)
    patterns = []
    if prefix:
        patterns.append(
            re.compile(rf"^{re.escape(prefix)}(\d{{2,4}})_(.+)$", re.IGNORECASE)
        )
    patterns.append(re.compile(r"^(\d{2,4})_(.+)$"))

    for pattern in patterns:
        match = pattern.match(stem)
        if not match:
            continue
        digits, base = match.group(1), match.group(2)
        number = int(digits)
        limit = max(int(max_count or 0), 999)
        if len(digits) >= 4 and number > limit:
            continue
        if not base.strip():
            continue
        return base, number, ext
    return stem, None, ext


def step_number(filename: str, prefix: str = "") -> int | None:
    return split_step_name(filename, prefix)[1]


def padding_for(count: int) -> int:
    return max(2, len(str(max(count, 1))))


def build_step_name(
    filename: str,
    number: int,
    pad: int,
    prefix: str = "",
    max_count: int | None = None,
) -> str:
    base, _current, ext = split_step_name(filename, prefix, max_count)
    base = base.strip() or "imagen"
    return f"{prefix}{number:0{pad}d}_{base}{ext}"


def image_sort_key(path: str, prefix: str = "") -> tuple:
    name = os.path.basename(path)
    base, number, _ext = split_step_name(name, prefix)
    if number is not None:
        return (0, number, natural_key(base), name.casefold())
    return (1, natural_key(name))


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def _is_hidden(entry: os.DirEntry) -> bool:
    if entry.name.startswith("."):
        return True
    try:
        stat = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    attributes = getattr(stat, "st_file_attributes", 0)
    return bool(attributes & 0x2)


def list_folder(folder: str, show_all: bool = False, prefix: str = "") -> FolderContent:
    folder = os.path.abspath(folder)
    folders: list[str] = []
    images: list[str] = []
    others: list[str] = []

    try:
        with os.scandir(folder) as iterator:
            for entry in iterator:
                if _is_hidden(entry):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        if is_image_file(entry.name):
                            images.append(entry.path)
                        else:
                            others.append(entry.path)
                except OSError:
                    continue
    except OSError as exc:
        raise RenameError(f"No se pudo leer la carpeta:\n{exc}") from exc

    folders.sort(key=lambda path: natural_key(os.path.basename(path)))
    images.sort(key=lambda path: image_sort_key(path, prefix))
    others.sort(key=lambda path: natural_key(os.path.basename(path)))
    if not show_all:
        others = []
    return FolderContent(folder, folders, images, others)


def validate_file_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if _INVALID_CHARS.search(name):
        return False
    if name.endswith((" ", ".")):
        return False
    stem = name.split(".", 1)[0].upper()
    return stem not in _RESERVED_NAMES


def build_rename_plan(
    image_paths: Sequence[str],
    prefix: str = "",
) -> list[FileMove]:
    count = len(image_paths)
    pad = padding_for(count)
    plan: list[FileMove] = []
    for number, path in enumerate(image_paths, start=1):
        folder, name = os.path.split(os.path.abspath(path))
        target_name = build_step_name(name, number, pad, prefix, count)
        plan.append(FileMove(os.path.join(folder, name), os.path.join(folder, target_name)))
    return plan


def _rename(source: str, target: str) -> None:
    """Indirección para poder simular fallos en las pruebas."""
    os.rename(source, target)


def validate_rename_plan(plan: Sequence[FileMove]) -> None:
    sources: set[str] = set()
    targets: set[str] = set()
    normalized: list[tuple[str, str]] = []

    for move in plan:
        source = os.path.abspath(move.source)
        target = os.path.abspath(move.target)
        if not os.path.isfile(source):
            raise RenameError(f"El archivo ya no existe:\n{source}")
        if not validate_file_name(os.path.basename(target)):
            raise RenameError(f"Nombre de archivo no válido:\n{target}")
        if os.path.normcase(os.path.dirname(source)) != os.path.normcase(
            os.path.dirname(target)
        ):
            raise RenameError("El renombrado debe permanecer en la misma carpeta.")
        if len(target) > 259:
            raise RenameError(
                "La ruta resultante es demasiado larga para Windows:\n" + target
            )
        source_key = os.path.normcase(source)
        if source_key in sources:
            raise RenameError(f"Archivo duplicado en la operación:\n{source}")
        sources.add(source_key)
        normalized.append((source, target))

    for source, target in normalized:
        target_key = os.path.normcase(target)
        if target_key in targets:
            raise RenameError(f"Dos archivos tendrían el mismo nombre:\n{target}")
        targets.add(target_key)
        if os.path.exists(target) and target_key not in sources:
            raise RenameError(f"Ya existe un archivo con ese nombre:\n{target}")


def apply_rename_plan(plan: Sequence[FileMove]) -> list[FileMove]:
    """Renombra en dos fases con nombres temporales y rollback ante errores."""
    normalized = [
        FileMove(os.path.abspath(move.source), os.path.abspath(move.target))
        for move in plan
    ]
    if not normalized:
        return []

    validate_rename_plan(normalized)
    changed = [move for move in normalized if move.source != move.target]
    if not changed:
        return []

    performed: list[tuple[str, str]] = []
    try:
        staged: list[tuple[str, str]] = []
        for index, move in enumerate(changed):
            extension = os.path.splitext(move.source)[1]
            while True:
                temporary = os.path.join(
                    os.path.dirname(move.source),
                    f"{TEMP_MARKER}{uuid.uuid4().hex}_{index}{extension}",
                )
                if not os.path.exists(temporary):
                    break
            _rename(move.source, temporary)
            performed.append((move.source, temporary))
            staged.append((temporary, move.target))

        for temporary, target in staged:
            _rename(temporary, target)
            performed.append((temporary, target))
    except Exception as exc:
        rollback_errors: list[str] = []
        for source, target in reversed(performed):
            try:
                if os.path.exists(target):
                    _rename(target, source)
            except OSError as rollback_exc:
                rollback_errors.append(f"{target}: {rollback_exc}")
        message = f"No se pudo completar el renombrado:\n{exc}"
        if rollback_errors:
            message += "\n\nAdemás, falló la restauración de:\n" + "\n".join(
                rollback_errors
            )
        raise RenameError(message) from exc

    return changed


def undo_moves(moves: Sequence[FileMove]) -> list[FileMove]:
    reverse = [FileMove(move.target, move.source) for move in reversed(moves)]
    return apply_rename_plan(reverse)


def rename_path(path: str, new_name: str) -> str:
    """Renombra un archivo o carpeta de forma segura (incluye solo mayúsculas)."""
    path = os.path.abspath(path)
    folder, old_name = os.path.split(path)
    if not validate_file_name(new_name):
        raise RenameError("El nombre no es válido para Windows.")
    target = os.path.join(folder, new_name)
    if target == path:
        return target
    if os.path.normcase(target) == os.path.normcase(path):
        temporary = os.path.join(
            folder, f"{TEMP_MARKER}{uuid.uuid4().hex}{os.path.splitext(path)[1]}"
        )
        _rename(path, temporary)
        try:
            _rename(temporary, target)
        except Exception:
            try:
                _rename(temporary, path)
            except OSError:
                pass
            raise
        return target
    if os.path.exists(target):
        raise RenameError(f"Ya existe:\n{target}")
    _rename(path, target)
    return target


def _journal_path(folder: str) -> str:
    key = os.path.normcase(os.path.abspath(folder)).encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    directory = os.path.join(app_data_dir(), "undo")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{digest}.json")


def save_undo_journal(
    folder: str,
    moves: Sequence[FileMove],
    timestamp: float | None = None,
) -> None:
    path = _journal_path(folder)
    if not moves:
        clear_undo_journal(folder)
        return
    folder = os.path.abspath(folder)
    data = {
        "folder": folder,
        "timestamp": timestamp if timestamp is not None else time.time(),
        "moves": [
            {
                "source": os.path.basename(move.source),
                "target": os.path.basename(move.target),
            }
            for move in moves
        ],
    }
    temporary = path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass


def load_undo_journal(folder: str) -> UndoRecord | None:
    path = _journal_path(folder)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        stored_folder = os.path.abspath(data["folder"])
        if os.path.normcase(stored_folder) != os.path.normcase(os.path.abspath(folder)):
            return None
        moves = [
            FileMove(
                os.path.join(stored_folder, item["source"]),
                os.path.join(stored_folder, item["target"]),
            )
            for item in data["moves"]
        ]
        if not moves:
            return None
        return UndoRecord(stored_folder, moves, float(data.get("timestamp", 0)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def clear_undo_journal(folder: str) -> None:
    path = _journal_path(folder)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def format_mtime(timestamp: float) -> str:
    try:
        return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


def save_rotation(path: str, degrees: int, quality: int = 95) -> float:
    """Aplica un giro de 90/180/270 grados al archivo y devuelve su mtime."""
    degrees = int(degrees) % 360
    if degrees not in (90, 180, 270):
        raise ValueError("El giro debe ser de 90, 180 o 270 grados.")

    path = os.path.abspath(path)
    extension = os.path.splitext(path)[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError("Formato de imagen no soportado.")
    if extension == ".gif":
        raise ValueError(
            "Guardar giros en GIF no está soportado para no perder la animación."
        )

    with Image.open(path) as image:
        image_format = image.format
        if image_format is None:
            raise ValueError("No se pudo determinar el formato de la imagen.")
        if getattr(image, "n_frames", 1) > 1:
            raise ValueError(
                "No se guardan giros en imágenes animadas o multipágina."
            )
        image.load()
        icc_profile = image.info.get("icc_profile")
        exif = image.getexif()
        transposed = ImageOps.exif_transpose(image)
        rotated = transposed.rotate(-degrees, expand=True)

        if image_format == "JPEG" and rotated.mode not in ("RGB", "L"):
            rotated = rotated.convert("RGB")

        exif_bytes = None
        if len(exif):
            exif[0x0112] = 1
            try:
                exif_bytes = exif.tobytes()
            except (OSError, ValueError):
                exif_bytes = None

        kwargs: dict = {}
        if image_format == "JPEG":
            kwargs.update(quality=quality, optimize=True)
        elif image_format == "PNG":
            kwargs.update(optimize=True)
        elif image_format == "WEBP":
            kwargs.update(quality=quality, method=6)
        elif image_format == "TIFF":
            kwargs.update(compression="tiff_lzw")
        if exif_bytes:
            kwargs["exif"] = exif_bytes
        if icc_profile:
            kwargs["icc_profile"] = icc_profile

        descriptor, temporary = tempfile.mkstemp(
            prefix=TEMP_MARKER,
            suffix=extension,
            dir=os.path.dirname(path),
        )
        os.close(descriptor)
        try:
            rotated.save(temporary, format=image_format, **kwargs)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    return os.path.getmtime(path)


def delete_to_recycle_bin(paths: Sequence[str]) -> None:
    """Elimina archivos o carpetas enviándolos a la Papelera de Reciclaje."""
    paths = [os.path.abspath(path) for path in paths]
    if not paths:
        return
    if os.name != "nt":
        raise OSError("La Papelera de reciclaje solo está disponible en Windows.")

    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040
    FOF_NOERRORUI = 0x0400

    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = FO_DELETE
    operation.pFrom = "\0".join(paths) + "\0\0"
    operation.pTo = None
    operation.fFlags = (
        FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    )

    shell32 = ctypes.windll.shell32
    shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
    shell32.SHFileOperationW.restype = ctypes.c_int
    result = shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(
            f"Windows no pudo enviar a la Papelera (código {result}). "
            "Comprueba que los archivos no estén en uso."
        )
