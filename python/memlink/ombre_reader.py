"""Ombre Brain → Canonical Memory reader.

Reads ombre-buckets/**/*.md files with YAML frontmatter.
Never raises — parse failures become warnings and skipped files.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from ._frontmatter import parse_frontmatter as _parse_ombre_frontmatter
from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult

# ── Kind mapping ────────────────────────────────────────────────────

_OMBRE_KIND_MAP: dict[str, str] = {
    "dynamic": "dynamic",
    "permanent": "permanent",
    "feel": "emotion",
}


def _map_kind(ombre_type: str) -> str:
    """Map Ombre type to Canonical kind."""
    kind = _OMBRE_KIND_MAP.get(ombre_type)
    if kind is not None:
        return kind
    return ombre_type  # pass through unknown values


# ── Reader ──────────────────────────────────────────────────────────


class OmbreReader(FormatPlugin):
    name = "ombre"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=True,
        importance_label=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path) -> ReadResult:
        """Walk ombre-buckets/**/*.md and parse each file into Canonical Memory."""
        memories: list[Memory] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "invalid": 0}

        md_files = sorted(path.rglob("*.md"))
        for md_file in md_files:
            rel = md_file.relative_to(path)
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                stats["skipped"] += 1
                warnings.append(f"Cannot read {rel}")
                continue

            # Parse frontmatter
            fm, body = _parse_ombre_frontmatter(text)
            if not isinstance(fm, dict) or not fm:
                stats["skipped"] += 1
                warnings.append(f"No frontmatter in {rel}")
                continue

            mem_id = fm.get("bucket_id") or fm.get("id")
            if not mem_id:
                stats["skipped"] += 1
                warnings.append(f"Missing bucket_id in {rel}")
                continue
            mem_id = str(mem_id)

            # Map fields
            memory = Memory(
                id=str(mem_id),
                name=str(fm["name"]) if fm.get("name") is not None else None,
                source=Source(
                    format="ombre",
                    path=str(rel),
                    uri=f"ombre://{_build_ombre_uri_path(fm, rel)}",
                ),
                body=body or fm.get("content"),
                kind=_map_kind(str(fm.get("type", "dynamic"))),
                status="active",
                tags=_parse_ombre_tags(fm),
                domains=_parse_ombre_domains(fm),
                created_at=None,  # Converter sets this from metadata
                valence=_to_float_or_none(fm.get("valence")),
                arousal=_to_float_or_none(fm.get("arousal")),
                importance_score=_to_float_or_none(fm.get("importance")),
                pinned=bool(fm.get("pinned", False)),
                checksum=_sha256(body or ""),
                metadata={
                    "memlink": {
                        "source": {"format": "ombre", "version": "1.0"},
                        "schema_version": "1",
                        "original": {
                            **{k: _serialize_original_value(v) for k, v in fm.items() if k != "content"},
                            "file": str(rel),
                        },
                    },
                },
            )

            # Preserve raw created string in metadata
            created_raw = fm.get("created")
            if isinstance(created_raw, (str, int, float)):
                memory.metadata["_created_raw"] = str(created_raw)  # type: ignore[index]

            memories.append(memory)
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("OmbreReader is read-only")

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path)


# ── Helpers ─────────────────────────────────────────────────────────


def _parse_ombre_tags(fm: dict) -> list[str]:
    raw = fm.get("tags", [])
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _parse_ombre_domains(fm: dict) -> list[str]:
    raw = fm.get("domain", [])
    if isinstance(raw, list):
        return [str(d) for d in raw]
    if isinstance(raw, str):
        return [d.strip() for d in raw.split(",") if d.strip()]
    return []


def _build_ombre_uri_path(fm: dict, rel: Path) -> str:
    """Build URI path from Ombre type/domain/id."""
    ombre_type = str(fm.get("type", "dynamic"))
    domain_raw = fm.get("domain", "unknown")
    if isinstance(domain_raw, list):
        domain_str = domain_raw[0] if domain_raw else "unknown"
    else:
        domain_str = str(domain_raw).split(",")[0].strip()
    bucket_id = str(fm.get("bucket_id", rel.stem))
    return f"{ombre_type}/{domain_str}/{bucket_id}"


def _to_float_or_none(val):
    """Convert value to float if possible, else None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _serialize_original_value(v):
    """Convert a value suitable for JSON-safe storage in metadata.original."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_serialize_original_value(i) for i in v]
    if isinstance(v, dict):
        return {str(k): _serialize_original_value(val) for k, val in v.items()}
    return v
