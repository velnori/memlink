"""Generic Markdown → Canonical Memory reader.

Reads any directory of .md files with YAML frontmatter.
Supports Obsidian, Logseq, Bear, iA Writer, and plain Markdown notes.
No specific format fields required — everything maps gracefully to Canonical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult


class GenericReader(FormatPlugin):
    name = "generic"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,           # description field → summary
        preserve_unknown_fields=True,  # unknown frontmatter → extensions
        supported_kinds=None,   # all kinds pass through
    )

    def read(self, path: Path) -> ReadResult:
        memories: list[Memory] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "invalid": 0}

        for md_file in sorted(path.rglob("*.md")):
            rel = md_file.relative_to(path)
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                stats["skipped"] += 1
                continue

            if not text.startswith("---"):
                # No frontmatter → treat whole file as body, filename as title
                mem_id = md_file.stem
                memories.append(Memory(
                    id=mem_id,
                    name=md_file.stem.replace("-", " ").replace("_", " "),
                    body=text.strip() or None,
                    kind="dynamic",
                    source=Source(format="generic", path=str(rel)),
                    checksum=_sha256(text),
                ))
                stats["parsed"] += 1
                continue

            # Parse frontmatter
            parts = text.split("---", 2)
            if len(parts) < 3:
                stats["skipped"] += 1
                continue

            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                stats["skipped"] += 1
                warnings.append(f"Invalid YAML in {rel}")
                continue

            if not isinstance(fm, dict):
                fm = {}

            body = parts[2]
            mem_id = str(fm.get("id") or fm.get("title") or md_file.stem)
            name = str(fm.get("title") or fm.get("name") or md_file.stem.replace("-", " ").replace("_", " "))

            # Tags: list or comma-separated string
            raw_tags = fm.get("tags", [])
            if isinstance(raw_tags, str):
                tags = sorted(t.strip() for t in raw_tags.split(",") if t.strip())
            elif isinstance(raw_tags, list):
                tags = sorted(str(t) for t in raw_tags)
            else:
                tags = []

            # Domain: from "category" / "folder" / "type" or from directory structure
            domain = fm.get("category") or fm.get("folder") or fm.get("type")
            if isinstance(domain, str):
                domains = [domain.strip()]
            else:
                domains = [rel.parts[0]] if len(rel.parts) > 1 else []

            # Status: check for "archived" / "draft" tags
            status = "active"
            status_tags = {str(t).lower() for t in tags}
            if "archived" in status_tags:
                status = "archived"

            # Collect unknown fields into extensions
            known = {"id", "title", "name", "tags", "category", "folder", "type",
                     "description", "summary", "created", "date", "updated", "pinned"}
            ext = {k: v for k, v in fm.items() if k not in known}
            extensions = ext if ext else {}

            memories.append(Memory(
                id=mem_id,
                name=name,
                summary=fm.get("description") or fm.get("summary"),
                body=body.strip() or None,
                kind="dynamic",
                status=status,
                tags=tags,
                domains=domains,
                pinned=bool(fm.get("pinned", False)),
                checksum=_sha256(body),
                extensions=extensions,  # type: ignore[arg-type]
                source=Source(format="generic", path=str(rel)),
                metadata={
                    "memlink": {
                        "source": {"format": "generic", "version": "1.0"},
                        "schema_version": "1",
                        "original": {str(k): _safe_val(v) for k, v in fm.items()},
                    },
                },
            ))
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("GenericReader is read-only")

    def validate(self, path):
        from .validators import validate_schema
        return validate_schema(path)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _safe_val(v):
    from datetime import datetime
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_safe_val(i) for i in v]
    if isinstance(v, dict):
        return {str(k): _safe_val(val) for k, val in v.items()}
    return v
