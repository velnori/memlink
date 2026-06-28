"""Generic Markdown → Canonical Memory reader.

Reads any directory of .md files with optional YAML frontmatter.
Supports Obsidian, Logseq, Bear, iA Writer, and plain Markdown notes.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path

import yaml

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult
from .serialization import sanitize

# Known frontmatter fields — others go to extensions
_KNOWN_FIELDS = frozenset({
    "id", "title", "name", "tags", "category", "folder", "type", "status",
    "description", "summary", "created", "date", "updated", "pinned",
})

# Type/status → kind mapping
_TYPE_TO_KIND: dict[str, str] = {
    "permanent": "permanent", "pinned": "permanent",
    "emotion": "emotion", "feel": "emotion", "journal": "emotion",
    "archived": "dynamic", "draft": "dynamic",
}


class GenericReader(FormatPlugin):
    name = "generic"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        preserve_unknown_fields=True,
        supported_kinds=None,
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

            # No frontmatter → whole file as body, filename as title
            if not text.startswith("---"):
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

            # Tags
            raw_tags = fm.get("tags", [])
            if isinstance(raw_tags, str):
                tags = sorted(t.strip() for t in raw_tags.split(",") if t.strip())
            elif isinstance(raw_tags, list):
                tags = sorted(str(t) for t in raw_tags)
            else:
                tags = []

            # Domain
            domain = fm.get("category") or fm.get("folder") or fm.get("type")
            if isinstance(domain, str):
                domains = [domain.strip()]
            else:
                domains = [rel.parts[0]] if len(rel.parts) > 1 else []

            # Kind: infer from type/status fields
            kind = _infer_kind(fm, tags)

            # Status
            status_tags = {str(t).lower() for t in tags}
            status = "archived" if "archived" in status_tags else "active"

            # Timestamps
            created_at = _parse_optional_datetime(fm.get("created") or fm.get("date"))
            updated_at = _parse_optional_datetime(fm.get("updated"))

            # Extensions: unknown fields, sanitized for JSON compatibility
            extensions = {}
            for k, v in fm.items():
                if k not in _KNOWN_FIELDS:
                    try:
                        extensions[str(k)] = sanitize(v)
                    except Exception:
                        pass

            # Original metadata snapshot
            memlink_original = {}
            for k, v in fm.items():
                try:
                    memlink_original[str(k)] = sanitize(v)
                except Exception:
                    memlink_original[str(k)] = str(v)

            memories.append(Memory(
                id=mem_id,
                name=name,
                summary=fm.get("description") or fm.get("summary"),
                body=body.strip() or None,
                kind=kind,
                status=status,
                tags=tags,
                domains=domains,
                created_at=created_at,
                updated_at=updated_at,
                pinned=bool(fm.get("pinned", False)),
                checksum=_sha256(body),
                extensions=extensions,  # type: ignore[arg-type]
                source=Source(format="generic", path=str(rel)),
                metadata={
                    "memlink": {
                        "source": {"format": "generic", "version": "1.0"},
                        "schema_version": "1",
                        "original": memlink_original,
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


# ── Helpers ─────────────────────────────────────────────────────────

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _infer_kind(fm: dict, tags: list[str]) -> str:
    """Infer Canonical kind from frontmatter type/status fields."""
    raw_type = str(fm.get("type") or "").lower()
    raw_status = str(fm.get("status") or "").lower()

    # Direct type match
    if raw_type in _TYPE_TO_KIND:
        return _TYPE_TO_KIND[raw_type]

    # Status-based inference
    if raw_status in _TYPE_TO_KIND:
        return _TYPE_TO_KIND[raw_status]

    # Tag-based inference
    tag_set = {t.lower() for t in tags}
    if "journal" in tag_set or "emotion" in tag_set:
        return "emotion"
    if "permanent" in tag_set:
        return "permanent"

    return "dynamic"


def _parse_optional_datetime(val) -> datetime | None:
    """Parse an optional datetime from string, date, or datetime object."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None
