"""Offline OpenClaw Markdown writer. Public writes use OutputTransaction."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import yaml

from .codec import memory_dict
from .models import Memory, sanitize_id
from .openclaw_records import render_records
from .plugin import Capabilities, FormatPlugin

_OUTPUT_MODES = ("daily-notes", "structured")


class OpenClawWriter(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True, preserve_unknown_fields=False, supported_kinds={"dynamic", "permanent", "emotion"}
    )

    def __init__(self, output_mode: str = "daily-notes"):
        if output_mode not in _OUTPUT_MODES:
            raise ValueError(f"Unknown output mode: {output_mode}")
        self.output_mode = output_mode

    def read(self, path):
        raise NotImplementedError("Use OpenClawReader")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        memories = list(memories)
        directory = path / "memory"
        directory.mkdir(parents=True, exist_ok=True)
        if self.output_mode == "structured":
            entries = []
            for mem in memories:
                sub = directory / "feels" if mem.kind == "emotion" else directory
                sub.mkdir(parents=True, exist_ok=True)
                data = memory_dict(mem)
                data.pop("body")
                fm = {
                    "name": mem.name or mem.id,
                    "description": mem.summary,
                    "metadata": _build_structured_frontmatter(mem).get("metadata", {}),
                    "_memlink_canonical": data,
                    "_memlink_body_length": len(mem.body) if mem.body is not None else None,
                }
                file = sub / (sanitize_id(mem.id) + ".md")
                file.write_text(
                    "---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + (mem.body or ""),
                    encoding="utf-8",
                    newline="",
                )
                entries.append(file.relative_to(path).as_posix())
            (path / "MEMORY.md").write_text(
                "# Memory Index\n\n" + "\n".join("- " + p for p in sorted(entries)) + "\n", encoding="utf-8", newline=""
            )
        else:
            days: dict[str, list[Memory]] = {}
            permanent: list[Memory] = []
            for mem in memories:
                if mem.kind == "permanent":
                    permanent.append(mem)
                    continue
                day = mem.created_at.date().isoformat() if mem.created_at else "undated"
                days.setdefault(day, []).append(mem)
            for day, records in sorted(days.items()):
                (directory / (day + ".md")).write_text(render_records(records), encoding="utf-8", newline="")
            if permanent:
                (path / "MEMORY.md").write_text(render_records(permanent), encoding="utf-8", newline="")
        return []

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)


def _best_date(mem: Memory) -> date | None:
    return mem.created_at.date() if mem.created_at else None


def _build_structured_frontmatter(mem: Memory) -> dict:
    meta = {
        "domain": ", ".join(mem.domains),
        "tags": mem.tags,
        "importance": mem.importance_label if mem.importance_label is not None else mem.importance_score,
        "valence": mem.valence,
        "arousal": mem.arousal,
        "pinned": mem.pinned,
        "created_at": mem.created_at.isoformat() if mem.created_at else None,
        "memlink": mem.metadata.get("memlink", {}),
    }
    if mem.kind == "permanent":
        meta["priority"] = "high"
    return {"name": mem.name or mem.id, "description": mem.summary, "metadata": meta}


def _first_paragraph(text: str, max_chars: int) -> str:
    return text.split("\n\n")[0][:max_chars]
