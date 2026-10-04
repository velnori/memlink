"""Plain Markdown / optional YAML frontmatter; no application-specific semantics."""

from __future__ import annotations

from pathlib import Path

from ._frontmatter import parse_frontmatter
from .codec import memory_from_dict, parse_time
from .plugin import Capabilities, FormatPlugin, ReadResult
from .read_support import markdown_files, relative, stats_init
from .serialization import sanitize

_KNOWN = {
    "id",
    "title",
    "name",
    "tags",
    "category",
    "folder",
    "type",
    "kind",
    "status",
    "description",
    "summary",
    "created",
    "date",
    "updated",
    "pinned",
    "domains",
    "metadata",
    "extensions",
    "source",
    "schema_version",
    "valence",
    "arousal",
    "importance_score",
    "importance_label",
    "relationships",
    "checksum",
    "_memlink_body_length",
}
_TYPE_TO_KIND = {
    "permanent": "permanent",
    "pinned": "permanent",
    "emotion": "emotion",
    "feel": "emotion",
    "journal": "emotion",
    "archived": "dynamic",
    "draft": "dynamic",
}


class GenericReader(FormatPlugin):
    name = "generic"
    version_supported = ">=1,<3"
    capabilities = Capabilities(emotion=True, relationships=True, importance_label=True)

    def read(self, path: Path) -> ReadResult:
        result = ReadResult([], stats=stats_init(), variant="plain-markdown+yaml-frontmatter")
        for file in markdown_files(path):
            rel = relative(file, path)
            try:
                text = file.read_bytes().decode("utf-8")
                fm, body = parse_frontmatter(text)
                raw_tags = fm.get("tags", [])
                tags = (
                    raw_tags
                    if isinstance(raw_tags, list)
                    else [s.strip() for s in str(raw_tags).split(",") if s.strip()]
                )
                status = fm.get("status", "archived" if "archived" in tags else "active")
                if status not in {"active", "archived"}:
                    raise ValueError("Unsupported status")
                domain = fm.get("category", fm.get("folder", fm.get("type")))
                domains = fm.get("domains")
                if domains is None:
                    domains = (
                        [domain.strip()]
                        if isinstance(domain, str)
                        else [Path(rel).parts[0]]
                        if len(Path(rel).parts) > 1
                        else []
                    )
                if not isinstance(domains, list):
                    raise ValueError("domains must be an array")
                body_value = body.strip() or None
                if "_memlink_body_length" in fm:
                    length = fm["_memlink_body_length"]
                    body_value = None if length is None else body.removeprefix("\n\n")[: int(length)]
                data = {
                    "schema_version": fm.get("schema_version", "1"),
                    "id": str(fm.get("id", fm.get("title", file.stem))),
                    "name": fm.get("name", fm.get("title", file.stem.replace("-", " ").replace("_", " "))),
                    "body": body_value,
                    "summary": fm.get("description", fm.get("summary")),
                    "kind": fm.get("kind", _infer_kind(fm, tags)),
                    "status": status,
                    "tags": sorted(str(t) for t in tags),
                    "domains": [str(d) for d in domains],
                    "created_at": parse_time(fm.get("created", fm.get("date"))),
                    "updated_at": parse_time(fm.get("updated")),
                    "pinned": fm.get("pinned", False),
                    "source": fm.get("source") or {"format": "generic", "path": rel},
                    "metadata": fm.get("metadata") or {},
                    "extensions": fm.get("extensions")
                    or {str(k): sanitize(v) for k, v in fm.items() if k not in _KNOWN},
                }
                for field in (
                    "valence",
                    "arousal",
                    "importance_score",
                    "importance_label",
                    "relationships",
                    "checksum",
                ):
                    if field in fm:
                        data[field] = fm[field]
                if "_memlink_body_length" not in fm and fm:
                    data["metadata"] = {
                        "memlink": {
                            "source": {"format": "generic", "version": "1.0"},
                            "schema_version": "1",
                            "original": sanitize(fm),
                        }
                    }
                memory = memory_from_dict(data)
                setattr(memory, "_native_path", rel)  # noqa: B010 - transient path; canonical schema stays frozen.
                result.memories.append(memory)
                result.files.append({"path": rel, "outcome": "parsed"})
            except (ValueError, TypeError, OSError, KeyError) as exc:
                result.stats["invalid"] += 1
                result.warnings.append(f"Invalid YAML/record in {rel}: {exc}")
                result.files.append({"path": rel, "outcome": "invalid"})
        return result

    def write(self, memories, path):
        raise NotImplementedError("GenericReader is read-only")

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)


def _infer_kind(fm: dict, tags: list[str]) -> str:
    value = str(fm.get("type") or "").lower()
    if value in _TYPE_TO_KIND:
        return _TYPE_TO_KIND[value]
    if str(fm.get("status", "")).lower() in _TYPE_TO_KIND:
        return _TYPE_TO_KIND[str(fm["status"]).lower()]
    if {str(t).lower() for t in tags} & {"journal", "emotion"}:
        return "emotion"
    return "permanent" if "permanent" in tags else "dynamic"


def _parse_optional_datetime(value):
    return parse_time(value)
