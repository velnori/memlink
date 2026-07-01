"""Canonical → Generic Markdown writer.

Outputs one .md file per memory with YAML frontmatter + body.
Compatible with Obsidian, Logseq, Bear, iA Writer, and plain Markdown notes.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .models import sanitize_id
from .plugin import Capabilities, FormatPlugin

if TYPE_CHECKING:
    from .models import Memory


class GenericWriter(FormatPlugin):
    name = "generic"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        preserve_unknown_fields=True,
        supported_kinds=None,
    )

    def read(self, path):
        raise NotImplementedError("Use GenericReader for reading")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        warnings: list[str] = []
        out_dir = path / "notes"
        out_dir.mkdir(parents=True, exist_ok=True)

        for mem in memories:
            fm: dict[str, object] = {
                "id": mem.id,
                "title": mem.name or mem.id,
            }

            if mem.tags:
                fm["tags"] = sorted(mem.tags)
            if mem.domains:
                fm["category"] = sorted(mem.domains)[0]
            if mem.kind:
                fm["type"] = mem.kind
            if mem.status and mem.status != "active":
                fm["status"] = mem.status
            if mem.summary:
                fm["description"] = mem.summary
            if mem.created_at:
                fm["created"] = _format_dt(mem.created_at)
            if mem.updated_at:
                fm["updated"] = _format_dt(mem.updated_at)
            if mem.pinned:
                fm["pinned"] = True

            # Extensions → frontmatter (reader sends unknown fields back to extensions)
            if mem.extensions:
                for k, v in mem.extensions.items():
                    fm[str(k)] = v

            frontmatter = yaml.dump(dict(fm), allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
            body = mem.body or ""
            content = f"---\n{frontmatter}\n---\n\n{body}\n"

            filepath = out_dir / f"{sanitize_id(mem.id)}.md"
            filepath.write_text(content, encoding="utf-8")

        return warnings

    def validate(self, path):
        return []


def _format_dt(dt: datetime) -> str:
    return dt.isoformat()
