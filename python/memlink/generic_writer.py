"""Canonical → plain Markdown / MemLink frontmatter variant, offline only."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from .codec import memory_dict
from .models import Memory, sanitize_id
from .plugin import Capabilities, FormatPlugin


class GenericWriter(FormatPlugin):
    name = "generic"
    version_supported = ">=1,<3"
    capabilities = Capabilities(emotion=True, relationships=True, importance_label=True)

    def read(self, path):
        raise NotImplementedError("Use GenericReader")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        out = path / "notes"
        out.mkdir(parents=True, exist_ok=True)
        for memory in memories:
            data = memory_dict(memory)
            body = data.pop("body")
            fm = {
                "id": memory.id,
                "title": memory.name,
                "type": memory.kind,
                "category": memory.domains[0] if memory.domains else None,
                **data,
                "_memlink_body_length": len(body) if body is not None else None,
            }
            if memory.status == "active":
                fm.pop("status")
            fm["created"] = fm.pop("created_at")
            fm["updated"] = fm.pop("updated_at")
            fm["description"] = fm.pop("summary")
            reserved = set(fm) | {"status", "summary", "created_at", "updated_at", "body"}
            for key, value in memory.extensions.items():
                if key not in reserved:
                    fm[key] = value
            text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False)
            (out / (sanitize_id(memory.id) + ".md")).write_text(
                f"---\n{text}---\n\n{body or ''}", encoding="utf-8", newline=""
            )
        return []

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)


def _format_dt(dt):
    return dt.isoformat()
