"""Local filesystem boundaries shared by adapters and transactions."""

from __future__ import annotations

import hashlib
import os
import stat
import unicodedata
from pathlib import Path

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILES = 10000
MAX_RECORDS = 100000


class BoundaryError(ValueError):
    """A path or input exceeds the approved local boundary."""


def is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def checked_root(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if is_link(part):
            raise BoundaryError(f"Symlink/junction path is not allowed: {part.name}")
    return path


def safe_child(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p in {".", ".."} or ":" in p for p in rel.parts):
        raise BoundaryError(f"Invalid output path: {relative}")
    out = checked_root(root / rel)
    if not out.is_relative_to(checked_root(root)):
        raise BoundaryError(f"Path leaves approved root: {relative}")
    return out


def file_key(relative: str) -> str:
    return unicodedata.normalize("NFC", relative.replace("\\", "/")).casefold()


def files_in(root: Path, *, include_control: bool = False) -> list[Path]:
    root = checked_root(root)
    if root.is_file():
        if root.stat().st_size > MAX_FILE_BYTES or root.stat().st_nlink > 1:
            raise BoundaryError("Oversized or hardlinked input file")
        return [root]
    if not root.is_dir():
        raise FileNotFoundError(f"Input root does not exist: {root.name}")
    files: list[Path] = []
    total = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        dirs[:] = [d for d in dirs if d != ".git"]
        if not include_control:
            dirs[:] = [d for d in dirs if d not in {".memlink", ".git"}]
        for name in dirs:
            if is_link(Path(base) / name):
                raise BoundaryError(f"Symlink/junction directory: {(Path(base) / name).relative_to(root)}")
        for name in sorted(names):
            file = Path(base) / name
            if is_link(file) or not file.is_file():
                raise BoundaryError(f"Non-regular input: {file.relative_to(root)}")
            st = file.stat()
            if st.st_nlink > 1:
                raise BoundaryError(f"Hardlink input is not allowed: {file.relative_to(root)}")
            if st.st_size > MAX_FILE_BYTES:
                raise BoundaryError(f"File exceeds {MAX_FILE_BYTES} bytes: {file.name}")
            total += st.st_size
            files.append(file)
            if len(files) > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise BoundaryError("Input resource limit exceeded")
    return sorted(files)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        h = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root: Path, *, include_control: bool = True) -> dict[str, dict]:
    root = checked_root(root)
    if not root.exists():
        return {}
    result: dict[str, dict] = {}
    keys: set[str] = set()
    for file in files_in(root, include_control=include_control):
        relative = file.relative_to(root).as_posix() if root.is_dir() else file.name
        key = file_key(relative)
        if key in keys:
            raise BoundaryError(f"Case/Unicode path collision: {relative}")
        keys.add(key)
        st = file.stat()
        result[relative] = {"sha256": digest(file), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    return result


def check_overlap(sources: list[Path], target: Path) -> None:
    dst = checked_root(target)
    for source in sources:
        src = checked_root(source)
        # A file's parent is the approved containing storage boundary.
        src_root = src.parent if src.is_file() else src
        if dst == src_root or dst.is_relative_to(src_root) or src_root.is_relative_to(dst):
            raise BoundaryError("Source and target storage roots overlap")
