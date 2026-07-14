"""Local filesystem storage abstraction.

Every write goes through `StorageBackend` so a future S3-compatible backend
can be dropped in without touching calling code (build spec §5: "Design a
storage interface that can later support S3-compatible storage without
changing business logic"). Only `LocalFileStorage` exists for now.
"""

import re
import uuid
from pathlib import Path
from typing import Literal, Protocol

from app.config import get_settings

StorageCategory = Literal["projects", "uploads", "crawls", "exports", "quarantine"]

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(original_filename: str) -> str:
    """Strip any path components and collapse unsafe characters.

    The sanitized name is for display/audit only — the file is actually
    stored under a randomized name (see `LocalFileStorage.save_bytes`) so a
    crafted filename can never influence where content lands on disk.
    """
    name = Path(original_filename).name  # drops any directory traversal component
    name = _UNSAFE_CHARS.sub("_", name).strip("._")
    return name[:200] or "unnamed"


class StorageBackend(Protocol):
    def save_bytes(self, category: StorageCategory, content: bytes, *, suffix: str = "") -> str:
        """Persist content, returning a backend-relative path (never an absolute host path)."""
        ...

    def read_bytes(self, relative_path: str) -> bytes: ...

    def delete(self, relative_path: str) -> None: ...

    def exists(self, relative_path: str) -> bool: ...

    def abs_path(self, relative_path: str) -> Path: ...


class LocalFileStorage:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().storage_path

    def _category_dir(self, category: StorageCategory) -> Path:
        path = self.root / category
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_bytes(self, category: StorageCategory, content: bytes, *, suffix: str = "") -> str:
        safe_suffix = _UNSAFE_CHARS.sub("_", suffix)[:20]
        filename = f"{uuid.uuid4().hex}{safe_suffix}"
        target = self._category_dir(category) / filename
        target.write_bytes(content)
        return f"{category}/{filename}"

    def read_bytes(self, relative_path: str) -> bytes:
        return self.abs_path(relative_path).read_bytes()

    def delete(self, relative_path: str) -> None:
        path = self.abs_path(relative_path)
        if path.exists():
            path.unlink()

    def exists(self, relative_path: str) -> bool:
        return self.abs_path(relative_path).exists()

    def abs_path(self, relative_path: str) -> Path:
        resolved = (self.root / relative_path).resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise ValueError(f"Path escapes storage root: {relative_path!r}")
        return resolved


_default_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _default_backend
    if _default_backend is None:
        _default_backend = LocalFileStorage()
    return _default_backend
