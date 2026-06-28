"""Canonical Memory → OpenClaw writer.

Writes memory/<id>.md files + updates MEMORY.md index.
Uses mtime+size for concurrent modification detection (O(1), no SHA256 overhead).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import yaml

from .models import Memory, sanitize_id
from .plugin import Capabilities, FormatPlugin


class OpenClawWriter(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        importance_label=False,
        preserve_unknown_fields=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path):
        raise NotImplementedError("OpenClawWriter is write-only")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        """Write Canonical memories into OpenClaw format."""
        memories = list(memories)
        warnings: list[str] = []
        memory_dir = path / "memory"
        feels_dir = memory_dir / "feels"
        memory_dir.mkdir(parents=True, exist_ok=True)

        new_entries: list[tuple[str, str | None]] = []  # (path, description)

        for mem in memories:
            # Route by kind + status
            if mem.status == "archived":
                continue

            if mem.kind == "emotion":
                feels_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{sanitize_id(mem.id)}.md"
                filepath = feels_dir / filename
            elif mem.kind == "permanent":
                filename = f"{sanitize_id(mem.id)}.md"
                filepath = memory_dir / filename
            else:
                filename = f"{sanitize_id(mem.id)}.md"
                filepath = memory_dir / filename

            # Build frontmatter
            description = mem.summary or _first_paragraph(mem.body or "", 120)
            fm: dict = {}
            if mem.name:
                fm["name"] = mem.name
            fm["description"] = description

            meta: dict = {}
            if mem.domains:
                meta["domain"] = ", ".join(mem.domains)
            if mem.tags:
                meta["tags"] = sorted(mem.tags)
            if mem.importance_label:
                meta["importance"] = mem.importance_label
            elif mem.importance_score is not None:
                meta["importance"] = mem.importance_score
            if mem.valence is not None:
                meta["valence"] = mem.valence
            if mem.arousal is not None:
                meta["arousal"] = mem.arousal
            if mem.created_at is not None:
                meta["created_at"] = mem.created_at.isoformat()
            if mem.pinned:
                meta["pinned"] = True
            if mem.source and mem.source.uri:
                meta["source_uri"] = mem.source.uri
            if mem.checksum:
                meta["checksum"] = mem.checksum
            # Preserve memlink roundtrip metadata
            if mem.metadata:
                memlink_data = mem.metadata.get("memlink")
                if memlink_data is not None:
                    if not isinstance(meta.get("memlink"), dict):
                        meta["memlink"] = {}
                    meta["memlink"] = memlink_data  # type: ignore[assignment]

            if meta:
                fm["metadata"] = meta

            # Serialize
            fm_yaml = yaml.dump(fm, allow_unicode=True, sort_keys=True, default_flow_style=False)
            content = f"---\n{fm_yaml}---\n\n{mem.body or ''}"
            filepath.write_text(content, encoding="utf-8")

            # Track for index
            idx_path = str(filepath.relative_to(path))
            idx_path = idx_path.replace("\\", "/")
            new_entries.append((idx_path, description if mem.summary else None))

        # Update MEMORY.md index
        index_warnings = _update_memory_index(path, new_entries)
        warnings.extend(index_warnings)
        return warnings

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path)


# ── MEMORY.md helpers ───────────────────────────────────────────────


def _update_memory_index(root: Path, new_entries: list[tuple[str, str | None]]) -> list[str]:
    """Update MEMORY.md with incremental entries. Detects concurrent modification."""
    index_path = root / "MEMORY.md"
    warnings: list[str] = []

    # Read existing index
    existing: dict[str, str] = {}  # path → description
    if index_path.exists():
        stat_before = _stat_tuple(index_path)
        text_before = index_path.read_text(encoding="utf-8")
        existing = _parse_memory_index(text_before)
    else:
        stat_before = None
        text_before = None

    # Merge: new entries overwrite existing with same basename
    for rel_path, desc in new_entries:
        stem = Path(rel_path).stem  # abc123
        # Find and remove any existing entry with same stem
        keys_to_remove = [k for k in existing if Path(k).stem == stem]
        for k in keys_to_remove:
            del existing[k]
        existing[rel_path] = desc or ""

    # Generate new index
    new_lines = ["# Memory Index", ""]
    for rel_path in sorted(existing):
        desc = existing[rel_path]
        if desc:
            new_lines.append(f"- {rel_path} — {desc}")
        else:
            new_lines.append(f"- {rel_path}")

    new_content = "\n".join(new_lines) + "\n"

    # Concurrent modification check
    if index_path.exists() and stat_before is not None:
        stat_now = _stat_tuple(index_path)
        if stat_now != stat_before:
            raise ConcurrentModificationError(
                f"MEMORY.md was modified during conversion.\n"
                f"  Before: mtime={stat_before[0]}, size={stat_before[1]}\n"
                f"  Now:    mtime={stat_now[0]}, size={stat_now[1]}\n"
                f"  Please re-run or use --rebuild-index."
            )

    index_path.write_text(new_content, encoding="utf-8")
    return warnings


def _parse_memory_index(content: str) -> dict[str, str]:
    """Parse MEMORY.md index into {path: description} dict."""
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("- memory/"):
            continue
        entry = line[2:]  # strip "- "
        if " — " in entry:
            path, desc = entry.split(" — ", 1)
            result[path.strip()] = desc.strip()
        else:
            result[entry.strip()] = ""
    return result


def _stat_tuple(p: Path) -> tuple[int, int]:
    st = p.stat()
    return (int(st.st_mtime * 1000), st.st_size)


def _first_paragraph(text: str, max_chars: int) -> str:
    """Extract first paragraph up to max_chars."""
    para = text.split("\n\n")[0].replace("\n", " ").strip()
    if len(para) <= max_chars:
        return para
    return para[:max_chars - 3].rsplit(" ", 1)[0] + "..."


class ConcurrentModificationError(RuntimeError):
    """Raised when MEMORY.md is modified by another process during conversion."""
