"""Canonical Memory → OpenClaw writer.

Supports two output modes:
  - "daily-notes": Native OpenClaw format (memory/YYYY-MM-DD.md + curated MEMORY.md)
  - "structured":  ID-indexed format (memory/<id>.md + MEMORY.md index)

Uses mtime+size for concurrent modification detection.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

import yaml

from .models import Memory, sanitize_id
from .plugin import Capabilities, FormatPlugin

_OUTPUT_MODES = ("daily-notes", "structured")


class OpenClawWriter(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        importance_label=False,
        preserve_unknown_fields=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def __init__(self, output_mode: str = "daily-notes"):
        if output_mode not in _OUTPUT_MODES:
            raise ValueError(f"Unknown output mode: {output_mode}. Choose from {_OUTPUT_MODES}")
        self.output_mode = output_mode

    def read(self, path):
        raise NotImplementedError("OpenClawWriter is write-only")

    # ── Public API ──────────────────────────────────────────────────

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        """Write Canonical memories into OpenClaw format."""
        memories = [m for m in memories if m.status != "archived"]
        if self.output_mode == "daily-notes":
            return self._write_daily_notes(memories, path)
        return self._write_structured(memories, path)

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path)

    # ── Daily Notes mode (native OpenClaw) ─────────────────────────

    def _write_daily_notes(self, memories: list[Memory], root: Path) -> list[str]:
        """Write memories grouped by date into memory/YYYY-MM-DD.md.

        MEMORY.md gets curated permanent + high-importance facts.
        DREAMS.md gets emotion memories.
        """
        memory_dir = root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []

        # Group by date
        by_date: dict[str, list[Memory]] = {}
        undated: list[Memory] = []
        permanent: list[Memory] = []
        emotion: list[Memory] = []

        for mem in memories:
            if mem.kind == "emotion":
                emotion.append(mem)
            elif mem.kind == "permanent":
                permanent.append(mem)

            dt = _best_date(mem)
            if dt is not None:
                key = dt.strftime("%Y-%m-%d")
                by_date.setdefault(key, []).append(mem)
            else:
                undated.append(mem)

        # Write daily files
        for day_key in sorted(by_date):
            day_mems = by_date[day_key]
            content = _format_daily_file(day_key, day_mems)
            filepath = memory_dir / f"{day_key}.md"
            filepath.write_text(content, encoding="utf-8")

        # Write undated as a single file
        if undated:
            content = _format_daily_file("undated", undated)
            (memory_dir / "undated.md").write_text(content, encoding="utf-8")
            warnings.append(f"{len(undated)} memories without dates written to memory/undated.md")

        # Write MEMORY.md (curated long-term facts)
        _write_curated_memory_md(root, permanent, emotions=emotion)

        # Write DREAMS.md (emotion / dream diary)
        if emotion:
            _write_dreams_md(root, emotion)

        return warnings

    # ── Structured mode (ID-indexed) ────────────────────────────────

    def _write_structured(self, memories: list[Memory], root: Path) -> list[str]:
        """Write one file per memory: memory/<id>.md + MEMORY.md index."""
        memory_dir = root / "memory"
        feels_dir = memory_dir / "feels"
        memory_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        new_entries: list[tuple[str, str | None]] = []

        for mem in memories:
            if mem.kind == "emotion":
                feels_dir.mkdir(parents=True, exist_ok=True)
                filepath = feels_dir / f"{sanitize_id(mem.id)}.md"
            else:
                filepath = memory_dir / f"{sanitize_id(mem.id)}.md"

            fm = _build_structured_frontmatter(mem)
            fm_yaml = yaml.dump(fm, allow_unicode=True, sort_keys=True, default_flow_style=False)
            filepath.write_text(f"---\n{fm_yaml}---\n\n{mem.body or ''}", encoding="utf-8")

            idx_path = str(filepath.relative_to(root)).replace("\\", "/")
            new_entries.append((idx_path, mem.summary))

        idx_warnings = _update_memory_index(root, new_entries)
        warnings.extend(idx_warnings)
        return warnings


# ═══════════════════════════════════════════════════════════════════
# Daily Notes helpers
# ═══════════════════════════════════════════════════════════════════


def _best_date(mem: Memory) -> date | None:
    if mem.created_at is not None:
        return mem.created_at.date()
    # Try metadata
    raw = mem.metadata.get("_created_raw")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw).date()
        except (ValueError, TypeError):
            pass
    return None


def _format_daily_file(day_key: str, memories: list[Memory]) -> str:
    """Format a single daily notes file with all that day's memories."""
    lines = [
        "---",
        f"title: {day_key}",
        f"created_at: {day_key if day_key != 'undated' else ''}",
        "---",
        "",
    ]
    for mem in memories:
        heading = mem.name or mem.id
        lines.append(f"## {heading}")
        lines.append("")
        if mem.summary:
            lines.append(f"_{mem.summary}_")
            lines.append("")
        if mem.tags:
            lines.append(f"tags: {', '.join(sorted(mem.tags))}")
            lines.append("")
        if mem.body:
            lines.append(mem.body.strip())
            lines.append("")
        lines.append("---")  # YAML frontmatter blocks
        lines.append("")
        # Embed machine-readable metadata as HTML comment (human-invisible, roundtrip-safe)
        if mem.metadata.get("memlink"):
            _embed_roundtrip_block(lines, mem)
    return "\n".join(lines)


def _embed_roundtrip_block(lines: list[str], mem: Memory) -> None:
    """Embed roundtrip metadata as an HTML comment block."""
    import json

    rt = {
        "id": mem.id,
        "kind": mem.kind,
        "importance_score": mem.importance_score,
        "importance_label": mem.importance_label,
        "valence": mem.valence,
        "arousal": mem.arousal,
        "pinned": mem.pinned,
        "domains": mem.domains,
        "tags": mem.tags,
        "source_uri": mem.source.uri if mem.source else None,
        "checksum": mem.checksum,
        "memlink": mem.metadata.get("memlink"),
    }
    lines.append("<!-- memlink-roundtrip")
    lines.append(json.dumps(rt, indent=2, ensure_ascii=False, default=str))
    lines.append("-->")


def _write_curated_memory_md(root: Path, permanent: list[Memory], emotions: list[Memory] | None = None) -> None:
    """Write MEMORY.md as curated long-term memory (OpenClaw native style).

    Contains: durable facts from permanent memories + high-importance items.
    """
    lines = [
        "---",
        "title: Curated Memory",
        "description: Durable facts, preferences, and decisions",
        "---",
        "",
        "> Auto-generated by [memlink](https://github.com/velnori/memlink).",
        "> This file contains curated long-term memories. Daily notes are in memory/.",
        "",
    ]

    # Sort: permanent first, then by importance
    all_curated = sorted(permanent, key=lambda m: (0 if m.kind == "permanent" else 1, -(m.importance_score or 0)))

    for mem in all_curated:
        heading = mem.name or mem.id
        lines.append(f"## {heading}")
        lines.append("")
        if mem.summary:
            lines.append(f"_{mem.summary}_")
            lines.append("")
        if mem.body:
            lines.append(mem.body.strip())
            lines.append("")
        if mem.tags:
            lines.append(f"tags: {', '.join(sorted(mem.tags))}")
            lines.append("")
        _embed_roundtrip_block(lines, mem)

    (root / "MEMORY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_dreams_md(root: Path, emotion: list[Memory]) -> None:
    """Write DREAMS.md with emotion/feel memories (OpenClaw style)."""
    lines = [
        "---",
        "title: Dream Diary",
        "description: Dreaming sweep summaries and emotional memories",
        "---",
        "",
    ]
    for mem in emotion:
        heading = mem.name or mem.id
        lines.append(f"## {heading}")
        lines.append("")
        if mem.summary:
            lines.append(f"_{mem.summary}_")
            lines.append("")
        if mem.body:
            lines.append(mem.body.strip())
            lines.append("")
        if mem.valence is not None or mem.arousal is not None:
            lines.append(f"valence: {mem.valence} / arousal: {mem.arousal}")
            lines.append("")
        _embed_roundtrip_block(lines, mem)

    (root / "DREAMS.md").write_text("\n".join(lines), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════
# Structured helpers (ID-indexed)
# ═══════════════════════════════════════════════════════════════════


def _build_structured_frontmatter(mem: Memory) -> dict:
    fm: dict = {}
    if mem.name:
        fm["name"] = mem.name
    fm["description"] = mem.summary or _first_paragraph(mem.body or "", 120)

    meta: dict = {}
    if mem.domains:
        meta["domain"] = ", ".join(mem.domains)
    # No domain field when empty — preserves original behavior
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
    if mem.metadata.get("memlink"):
        meta["memlink"] = mem.metadata["memlink"]

    if meta:
        fm["metadata"] = meta
    return fm


def _update_memory_index(root: Path, new_entries: list[tuple[str, str | None]]) -> list[str]:
    index_path = root / "MEMORY.md"
    existing: dict[str, str] = {}
    if index_path.exists():
        stat_before = (int(index_path.stat().st_mtime * 1000), index_path.stat().st_size)
        existing = _parse_memory_index(index_path.read_text(encoding="utf-8"))
    else:
        stat_before = None

    for rel_path, desc in new_entries:
        stem = Path(rel_path).stem
        for k in [k for k in existing if Path(k).stem == stem]:
            del existing[k]
        existing[rel_path] = desc or ""

    lines = ["# Memory Index", ""]
    for rel_path in sorted(existing):
        desc = existing[rel_path]
        lines.append(f"- {rel_path} — {desc}" if desc else f"- {rel_path}")

    # Concurrent modification check
    if index_path.exists() and stat_before is not None:
        st = index_path.stat()
        if (int(st.st_mtime * 1000), st.st_size) != stat_before:
            raise ConcurrentModificationError(
                "MEMORY.md was modified during conversion.\n  Please re-run or use --rebuild-index."
            )

    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return []


def _parse_memory_index(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- memory/"):
            continue
        entry = stripped[2:]
        if " — " in entry:
            path, desc = entry.split(" — ", 1)
            result[path.strip()] = desc.strip()
        else:
            result[entry.strip()] = ""
    return result


def _first_paragraph(text: str, max_chars: int) -> str:
    para = text.split("\n\n")[0].replace("\n", " ").strip()
    if len(para) <= max_chars:
        return para
    return para[: max_chars - 3].rsplit(" ", 1)[0] + "..."


class ConcurrentModificationError(RuntimeError):
    """Raised when MEMORY.md is modified by another process during conversion."""
