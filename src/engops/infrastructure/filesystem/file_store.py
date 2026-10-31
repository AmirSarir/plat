"""Managed local file storage.

Rules: originals are never modified (we only read them), stored files are never
overwritten (every file gets its own unique folder), and every copy is hashed.
Layout:  <root>/<category>/<file-uuid>/<sanitized original name>
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from engops.domain.common import new_id

ALLOWED_CATEGORIES = ("inputs", "outputs", "documents")

_CHUNK = 1024 * 1024
_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class FileStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredFileInfo:
    file_id: str
    rel_path: str
    original_name: str
    size_bytes: int
    sha256: str


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Safe Windows-friendly file name. Keeps Unicode (e.g. Persian) characters."""
    base = Path(name.replace("\\", "/")).name
    base = _BAD_CHARS.sub("_", base).strip(" .")
    if not base:
        return "file"
    path = Path(base)
    stem, suffix = path.stem, path.suffix[:20]
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    stem = stem[: max(1, max_length - len(suffix))]
    return (stem or "file") + suffix


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_with_hash(source: Path, dest: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as src, dest.open("xb") as dst:  # "x": never overwrite
        while chunk := src.read(_CHUNK):
            digest.update(chunk)
            dst.write(chunk)
            size += len(chunk)
        dst.flush()
        os.fsync(dst.fileno())
    return digest.hexdigest(), size


class FileStore:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def add_file(self, source: Path, category: str) -> StoredFileInfo:
        """Copy `source` into the store. The source file is only read."""
        if category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Unknown file category {category!r}; use one of {ALLOWED_CATEGORIES}")
        source = Path(source)
        if not source.is_file():
            raise FileStoreError(f"Source file not found: {source}")

        file_id = new_id()
        rel = PurePosixPath(category, file_id, sanitize_filename(source.name))
        dest = self._root.joinpath(*rel.parts)
        dest.parent.mkdir(parents=True, exist_ok=False)
        part = dest.with_name(dest.name + ".part")
        try:
            sha256, size = _copy_with_hash(source, part)
            if size != source.stat().st_size:
                raise FileStoreError(f"{source} changed while it was being copied")
            os.replace(part, dest)
        except BaseException:
            shutil.rmtree(dest.parent, ignore_errors=True)
            raise
        return StoredFileInfo(file_id, rel.as_posix(), source.name, size, sha256)

    def path_of(self, rel_path: str) -> Path:
        """Absolute path of a stored file; refuses anything outside the store."""
        root = self._root.resolve()
        candidate = (root / rel_path).resolve()
        if root not in candidate.parents:
            raise FileStoreError(f"Path escapes the file store: {rel_path}")
        return candidate

    def verify(self, rel_path: str, sha256: str, size_bytes: int) -> bool:
        """True if the stored file still exists and matches its recorded size and hash."""
        path = self.path_of(rel_path)
        if not path.is_file() or path.stat().st_size != size_bytes:
            return False
        return sha256_of(path) == sha256

    def discard(self, rel_path: str) -> None:
        """Remove one stored file's folder (used only to clean up after a failed import)."""
        folder = self.path_of(rel_path).parent
        if folder.parent.parent != self._root.resolve():
            raise FileStoreError(f"Refusing to remove unexpected folder: {folder}")
        shutil.rmtree(folder, ignore_errors=True)