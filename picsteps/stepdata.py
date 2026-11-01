"""Metadatos por carpeta: títulos, notas y anotaciones no destructivas."""

from __future__ import annotations

import copy
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Iterable

SIDECAR_NAME = ".picsteps.json"
SIDECAR_VERSION = 1


def sidecar_path(folder: str) -> str:
    return os.path.join(os.path.abspath(folder), SIDECAR_NAME)


@dataclass
class StepEntry:
    title: str = ""
    note: str = ""
    annotations: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: object) -> "StepEntry":
        if not isinstance(raw, dict):
            return cls()
        title = raw.get("title", "")
        note = raw.get("note", "")
        annotations = raw.get("annotations", [])
        return cls(
            title=title.strip() if isinstance(title, str) else "",
            note=note.strip() if isinstance(note, str) else "",
            annotations=copy.deepcopy(annotations)
            if isinstance(annotations, list)
            else [],
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "note": self.note,
            "annotations": copy.deepcopy(self.annotations),
        }

    def is_empty(self) -> bool:
        return not self.title and not self.note and not self.annotations


def _load_entries(folder: str) -> dict[str, StepEntry]:
    path = sidecar_path(folder)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError) as exc:
        logging.warning("No se pudo leer %s: %s", path, exc)
        return {}

    if not isinstance(raw, dict):
        return {}
    files = raw.get("files")
    if not isinstance(files, dict):
        return {}

    entries: dict[str, StepEntry] = {}
    for name, value in files.items():
        if not isinstance(name, str) or not name:
            continue
        entry = StepEntry.from_dict(value)
        if not entry.is_empty():
            entries[name] = entry
    return entries


def _save_entries(folder: str, entries: dict[str, StepEntry]) -> None:
    path = sidecar_path(folder)
    temporary = path + ".tmp"
    if not entries:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        try:
            os.remove(temporary)
        except FileNotFoundError:
            pass
        return

    payload = {
        "version": SIDECAR_VERSION,
        "files": {
            name: entry.to_dict()
            for name, entry in entries.items()
            if not entry.is_empty()
        },
    }
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
        os.replace(temporary, path)
    except OSError:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass
        raise


class StepDataError(Exception):
    """Error controlado al guardar metadatos de pasos."""


class StepStore:
    """Caché y persistencia de los metadatos de cada carpeta."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, StepEntry]] = {}

    @staticmethod
    def _folder_key(folder: str) -> str:
        return os.path.normcase(os.path.abspath(folder))

    def _entries(self, folder: str) -> dict[str, StepEntry]:
        key = self._folder_key(folder)
        entries = self._cache.get(key)
        if entries is None:
            entries = _load_entries(folder)
            self._cache[key] = entries
        return entries

    def reload(self, folder: str) -> None:
        self._cache[self._folder_key(folder)] = _load_entries(folder)

    def _commit(
        self,
        folder: str,
        entries: dict[str, StepEntry],
    ) -> None:
        key = self._folder_key(folder)
        previous = self._cache.get(key)
        try:
            _save_entries(folder, entries)
        except OSError as exc:
            if previous is not None:
                self._cache[key] = previous
            else:
                self._cache.pop(key, None)
            raise StepDataError(
                f"No se pudieron guardar los datos del paso:\n{exc}"
            ) from exc
        self._cache[key] = entries

    def get(self, path: str) -> StepEntry:
        folder, name = os.path.split(os.path.abspath(path))
        entry = self._entries(folder).get(name)
        return copy.deepcopy(entry) if entry is not None else StepEntry()

    def annotations(self, path: str) -> list[dict]:
        return self.get(path).annotations

    def as_dict(self, path: str) -> dict:
        return self.get(path).to_dict()

    def has_annotations(self, path: str) -> bool:
        return bool(self.annotations(path))

    def set_notes(self, path: str, title: str, note: str) -> None:
        folder, name = os.path.split(os.path.abspath(path))
        entries = copy.deepcopy(self._entries(folder))
        entry = entries.get(name, StepEntry())
        entry.title = (title or "").strip()
        entry.note = (note or "").strip()
        if entry.is_empty():
            entries.pop(name, None)
        else:
            entries[name] = entry
        self._commit(folder, entries)

    def set_annotations(self, path: str, annotations: list[dict]) -> None:
        folder, name = os.path.split(os.path.abspath(path))
        entries = copy.deepcopy(self._entries(folder))
        entry = entries.get(name, StepEntry())
        entry.annotations = copy.deepcopy(list(annotations))
        if entry.is_empty():
            entries.pop(name, None)
        else:
            entries[name] = entry
        self._commit(folder, entries)

    def set_entry(self, path: str, entry: StepEntry) -> None:
        folder, name = os.path.split(os.path.abspath(path))
        entries = copy.deepcopy(self._entries(folder))
        if entry.is_empty():
            entries.pop(name, None)
        else:
            entries[name] = copy.deepcopy(entry)
        self._commit(folder, entries)

    def remove(self, path: str) -> None:
        self.remove_many([path])

    def remove_many(self, paths: Iterable[str]) -> None:
        grouped: dict[str, list[str]] = {}
        for path in paths:
            folder, name = os.path.split(os.path.abspath(path))
            grouped.setdefault(folder, []).append(name)
        for folder, names in grouped.items():
            entries = copy.deepcopy(self._entries(folder))
            changed = False
            for name in names:
                if name in entries:
                    entries.pop(name, None)
                    changed = True
            if changed:
                self._commit(folder, entries)

    def move(self, old_path: str, new_path: str) -> None:
        old_folder, old_name = os.path.split(os.path.abspath(old_path))
        new_folder, new_name = os.path.split(os.path.abspath(new_path))
        if os.path.normcase(old_folder) == os.path.normcase(new_folder):
            entries = copy.deepcopy(self._entries(old_folder))
            entry = entries.pop(old_name, None)
            if entry is None:
                return
            entries[new_name] = entry
            self._commit(old_folder, entries)
            return

        entry = self.get(old_path)
        if entry.is_empty():
            return
        self.set_entry(new_path, entry)
        self.remove(old_path)

    def move_many(self, moves: Iterable[tuple[str, str]]) -> None:
        pairs = list(moves)
        if not pairs:
            return
        folders = {
            os.path.normcase(os.path.dirname(os.path.abspath(old)))
            for old, _new in pairs
        }
        destinations = {
            os.path.normcase(os.path.dirname(os.path.abspath(new)))
            for _old, new in pairs
        }
        if len(folders) == 1 and destinations == folders:
            folder = os.path.dirname(os.path.abspath(pairs[0][0]))
            original = copy.deepcopy(self._entries(folder))
            old_names = {
                os.path.basename(os.path.abspath(old)) for old, _new in pairs
            }
            entries = {
                name: entry
                for name, entry in original.items()
                if name not in old_names
            }
            for old, new in pairs:
                old_name = os.path.basename(os.path.abspath(old))
                new_name = os.path.basename(os.path.abspath(new))
                entry = original.get(old_name)
                if entry is not None:
                    entries[new_name] = entry
            self._commit(folder, entries)
            return
        for old, new in pairs:
            self.move(old, new)

    def copy(self, old_path: str, new_path: str) -> None:
        entry = self.get(old_path)
        if entry.is_empty():
            return
        self.set_entry(new_path, entry)

    def infos(self, folder: str) -> dict[str, dict]:
        folder = os.path.abspath(folder)
        infos: dict[str, dict] = {}
        for name, entry in self._entries(folder).items():
            path = os.path.normcase(os.path.join(folder, name))
            infos[path] = entry.to_dict()
        return infos
