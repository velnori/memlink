"""Snapshot only the explicitly approved OpenClaw memory surface.

The existing Reader runs against a bounded copy, never a home/config discovery.
The source is checked before/after copying, parsing, and committing the bundle.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .codec import attach_identity, identity, memory_dict, stable_json
from .converter import read_source
from .registry import get_reader
from .safety import MAX_FILE_BYTES, MAX_FILES, MAX_TOTAL_BYTES, checked_root, file_key, is_link, safe_child
from .transaction import TransactionError


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_sha(data) -> str:
    return sha(stable_json(data).encode("utf-8"))


def scope_rules(include_user: bool = False, include_dreams: bool = False) -> list[str]:
    return [
        "MEMORY.md",
        "memory/**/*.md",
        *(["USER.md"] if include_user else []),
        *(["DREAMS.md"] if include_dreams else []),
    ]


def approved_path(relative: str, rules: list[str]) -> bool:
    # Check components on both platforms; JSON paths always use forward slashes.
    if not relative or "\\" in relative or relative.startswith("/"):
        return False
    if any(x in {"", ".", "..", ".git"} or ":" in x for x in relative.split("/")):
        return False
    return relative in rules or (
        "memory/**/*.md" in rules and relative.startswith("memory/") and relative.lower().endswith(".md")
    )


def discover(root: Path, rules: list[str]) -> list[str]:
    root = checked_root(root)
    if not root.is_dir():
        raise ValueError("OpenClaw input must be an explicit workspace directory")
    found = []
    for name in rules:
        if "*" in name:
            continue
        path = root / name
        if path.exists() or is_link(path):
            checked_root(path)
            if not path.is_file():
                raise ValueError("Approved memory entry is not a regular file")
            found.append(name)
    memory = checked_root(root / "memory")
    if memory.exists():
        if not memory.is_dir():
            raise ValueError("memory must be a directory")
        for base, dirs, names in os.walk(memory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d != ".git")
            for name in dirs:
                checked_root(Path(base) / name)
            for name in sorted(names):
                if name.lower().endswith(".md"):
                    path = checked_root(Path(base) / name)
                    if not path.is_file():
                        raise ValueError("Approved note is not a regular file")
                    found.append(path.relative_to(root).as_posix())
    if len(found) > MAX_FILES:
        raise ValueError("Approved memory file limit exceeded")
    if len({file_key(p) for p in found}) != len(found):
        raise ValueError("Case/Unicode collision in approved memory paths")
    return sorted(found)


def source_snapshot(root: Path, rules: list[str]) -> tuple[dict, dict[str, bytes]]:
    content = {}
    entries = {}
    total = 0
    for relative in discover(root, rules):
        file = safe_child(root, relative)
        before = file.stat()
        if before.st_nlink > 1 or before.st_size > MAX_FILE_BYTES:
            raise ValueError("Hardlinked or oversized approved note")
        raw = file.read_bytes()
        after = file.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ino,
        ) or len(raw) != after.st_size:
            raise TransactionError("Source changed during snapshot", {}, 4)
        total += len(raw)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Approved memory byte limit exceeded")
        content[relative] = raw
        entries[relative] = {"sha256": sha(raw), "bytes": len(raw), "mtime_ns": after.st_mtime_ns}
    return entries, content


def assert_source(root: Path, rules: list[str], expected: dict) -> None:
    try:
        actual, _ = source_snapshot(root, rules)
    except (OSError, ValueError) as exc:
        raise TransactionError("Approved source changed or became unreadable", {}, 4) from exc
    if actual != expected:
        raise TransactionError("Approved source changed; retry with a new snapshot", {}, 4)


def source_ref(relative: str) -> str:
    return "s-" + sha(relative.encode("utf-8"))[:24]


def _structure(memory) -> dict:
    fm = memory.extensions.get("openclaw_frontmatter", {})
    original = memory.metadata.get("memlink", {})
    if not isinstance(fm, dict) or not fm:
        fm = original.get("original", {}) if isinstance(original, dict) else {}
    return fm if isinstance(fm, dict) else {}


def labels(memory) -> dict:
    """Only existing structured fields: never classify prose with a model/heuristic."""
    fm = _structure(memory)
    meta = fm.get("metadata", {})
    meta = meta if isinstance(meta, dict) else {}
    tags = list(memory.tags)
    for value in (fm.get("tags"), meta.get("tags")):
        if isinstance(value, list) and all(isinstance(t, str) for t in value):
            tags.extend(value)
        elif isinstance(value, str):
            tags.extend(t.strip() for t in value.split(",") if t.strip())
    project = fm.get("project", meta.get("project"))
    state = fm.get("status", meta.get("status", memory.status))
    return {
        "tags": sorted(set(tags)),
        "project": project if isinstance(project, str) else None,
        "state": state if isinstance(state, str) else memory.status,
    }


def parse_view(view: Path, namespace: str, rules: list[str]) -> tuple[list[dict], dict]:
    reader = get_reader("openclaw", include_user="USER.md" in rules, include_dreams="DREAMS.md" in rules)
    memories, context, _, _ = read_source(reader, view, all=True)
    if context["stats"].get("invalid", 0) or context["stats"].get("unsupported", 0):
        raise ValueError("Invalid/unsupported approved records; no completed pack was created")
    from .openclaw_reader import _is_index_only

    for entry in context["files"]:
        if entry["outcome"] in {"invalid", "unsupported"} and not (
            entry["path"] == "MEMORY.md" and _is_index_only((view / "MEMORY.md").read_text(encoding="utf-8"))
        ):
            raise ValueError("An approved memory file could not be parsed; no completed pack was created")
    records = []
    counts: dict[str, int] = {}
    for memory in memories:
        original_claim = memory.metadata.get("_claimed_identity")
        attach_identity(memory, namespace)
        # The temporary copy's identity is an implementation detail, not source data.
        memory.metadata.pop("_claimed_identity", None)
        if original_claim is not None:
            memory.metadata["_claimed_identity"] = original_claim
        ident = identity(memory)
        key = stable_json(ident)
        ordinal = counts.get(key, 0)
        counts[key] = ordinal + 1
        relative = getattr(memory, "_native_path", memory.source.path.split("#")[0] if memory.source else "")
        relative = relative.replace("\\", "/")
        if not approved_path(relative, rules):
            raise ValueError("Reader record leaves approved memory scope")
        records.append(
            {
                "record_id": "r-" + object_sha([ident, ordinal]),
                "identity": ident,
                "occurrence": ordinal,
                "source_ref": source_ref(relative),
                "labels": labels(memory),
                "memory": memory_dict(memory),
            }
        )
    return records, context


def capture(root: Path, rules: list[str]) -> tuple[list[dict], dict, dict, dict[str, bytes]]:
    root = checked_root(root)
    before, content = source_snapshot(root, rules)
    namespace = "openclaw:" + sha(str(root.resolve()).encode("utf-8"))[:20]
    with tempfile.TemporaryDirectory(prefix="memlink-memory-view-") as name:
        view = Path(name).resolve(strict=True)
        for relative, raw in content.items():
            out = safe_child(view, relative)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(raw)
        assert_source(root, rules, before)
        records, context = parse_view(view, namespace, rules)
        assert_source(root, rules, before)
    return records, context, before, content
