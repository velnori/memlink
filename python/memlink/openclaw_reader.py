"""OpenClaw → Canonical Memory reader.

Reads MEMORY.md index + memory/*.md files.
6-step pipeline: discover → parse → map → recover → validate → ReadResult.

Never raises — parse failures become warnings and skipped files.
MEMORY.md损坏 → warning + fallback递归扫描.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from ._frontmatter import parse_frontmatter as _parse_frontmatter
from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult


class OpenClawReader(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        importance_label=True,  # "high"/"medium"/"low"
        preserve_unknown_fields=True,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path) -> ReadResult:
        memories: list[Memory] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "invalid": 0}

        # Step 1: Discover files
        if (path / "MEMORY.md").exists():
            index = _parse_memory_index(path / "MEMORY.md")
            if index:
                indexed_files = set(index.keys())
            else:
                warnings.append("MEMORY.md exists but contains no entries; falling back to recursive scan")
                indexed_files = set()
        else:
            indexed_files = set()
            warnings.append("MEMORY.md not found; scanning memory/ directory recursively")

        # Step 2-3: Parse + map each file
        memory_dir = path / "memory"
        if memory_dir.exists():
            all_files: set[Path] = set(memory_dir.rglob("*.md"))
            # Deduplicate by resolved path
            seen: set[Path] = set()
            for md_file in sorted(all_files):
                resolved = md_file.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)

                rel = md_file.relative_to(path)
                try:
                    text = md_file.read_text(encoding="utf-8")
                except Exception:
                    stats["skipped"] += 1
                    warnings.append(f"Cannot read {rel}")
                    continue

                fm, body = _parse_frontmatter(text)
                if not isinstance(fm, dict):
                    stats["skipped"] += 1
                    warnings.append(f"No valid frontmatter in {rel}")
                    continue

                name = fm.get("name") or fm.get("title")
                if not name:
                    stats["skipped"] += 1
                    warnings.append(f"Missing name in {rel}")
                    continue

                # Step 3: Map to Canonical
                metadata = fm.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {}

                # ID: prefer original, else filename
                mem_id = _extract_id(md_file, metadata)

                # Kind inference
                kind = _infer_kind(md_file, metadata)

                # Domains
                domains = _infer_domains(metadata)

                # Importance
                imp_score, imp_label = _infer_importance(metadata, fm)

                # Time
                created_at = _parse_time(metadata.get("created_at") or fm.get("created_at"))

                # Step 4: Recover original from memlink metadata
                original = metadata.get("memlink", {}).get("original", {})
                restored_kind = None
                restored_status = None
                restored_domains = None
                if isinstance(original, dict) and original:
                    if original.get("id"):
                        mem_id = str(original["id"])
                    # Ombre stores "type" in frontmatter → map to kind
                    if original.get("kind"):
                        restored_kind = original["kind"]
                    elif original.get("type") and original["type"] != "feel":
                        restored_kind = original["type"]  # dynamic/permanent pass through
                    elif original.get("type") == "feel":
                        restored_kind = "emotion"
                    if original.get("status"):
                        restored_status = original["status"]
                    if original.get("domains"):
                        restored_domains = original["domains"]
                    if original.get("importance") is not None:
                        orig_imp = original["importance"]
                        if isinstance(orig_imp, (int, float)) and not isinstance(orig_imp, bool):
                            imp_score = float(orig_imp)
                            imp_label = None
                        else:
                            imp_label = str(orig_imp)
                            imp_score = None

                # Step 5: Build Memory
                # kind priority: original > path-based inference
                memory = Memory(
                    id=str(mem_id),
                    name=str(name) if name else None,
                    source=Source(
                        format="openclaw",
                        path=str(rel),
                        uri=f"openclaw://{str(rel).replace(chr(92), '/')}",
                    ),
                    summary=fm.get("description"),
                    body=body if body and body.strip() else None,
                    kind=restored_kind or kind,
                    status=restored_status or "active",
                    tags=_parse_tags(metadata),
                    domains=restored_domains or domains,
                    created_at=created_at,
                    valence=_to_float(metadata.get("valence")),
                    arousal=_to_float(metadata.get("arousal")),
                    importance_score=imp_score,
                    importance_label=imp_label,
                    pinned=bool(metadata.get("pinned", False)),
                    checksum=metadata.get("checksum"),
                    metadata={"memlink": metadata.get("memlink", {})} if metadata.get("memlink") else {},
                    extensions=metadata.get("extensions", {}),
                )

                # Recover daily-notes roundtrip comment
                _recover_roundtrip_comment(body, memory, warnings)

                memories.append(memory)
                stats["parsed"] += 1

        # Parse DREAMS.md (feel entries not stored in memory/)
        dreams_path = path / "DREAMS.md"
        if dreams_path.exists():
            existing_ids = {m.id for m in memories}
            dreams_memories = _parse_dreams_file(dreams_path, path, warnings, stats)
            for dm in dreams_memories:
                if dm.id not in existing_ids:
                    memories.append(dm)
                    existing_ids.add(dm.id)

        # Warn about unindexed files
        if indexed_files:
            actual = {str(f.relative_to(path)).replace("\\", "/") for f in all_files}
            unindexed = actual - indexed_files
            if unindexed:
                warnings.append(f"{len(unindexed)} files not in MEMORY.md (will still be read)")

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("OpenClawReader is read-only")

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path)


# ── Pipeline helpers ───────────────────────────────────────────────


def _parse_memory_index(path: Path) -> dict[str, str]:
    """Parse MEMORY.md index, supporting multiple format variants."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    result: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- memory/"):
            continue
        entry = stripped[2:]
        if " — " in entry:
            p, desc = entry.split(" — ", 1)
            result[p.strip()] = desc.strip()
        else:
            result[entry.strip()] = ""
    return result


def _extract_id(file: Path, metadata: dict) -> str:
    """Extract ID from filename, URL-decoding percent-encoded chars."""
    stem = file.stem  # remove .md
    decoded = unquote(stem)
    # If decoded contains path separators, sanitize
    if "/" in decoded or "\\" in decoded:
        from .models import sanitize_id

        return sanitize_id(decoded)
    return decoded


def _infer_kind(file: Path, metadata: dict) -> str:
    """Infer Canonical kind from path and metadata."""
    rel = str(file).replace("\\", "/")
    if "feels" in rel:
        return "emotion"
    if metadata.get("priority") == "high":
        return "permanent"
    return "dynamic"


def _infer_domains(metadata: dict) -> list[str]:
    """Infer domains from metadata, never using NLP."""
    domain = metadata.get("domain")
    if isinstance(domain, str) and domain.strip():
        return [d.strip() for d in domain.split(",") if d.strip()]
    mtype = metadata.get("type")
    if isinstance(mtype, str) and mtype.strip():
        return [mtype.strip()]
    return []  # No domain info → empty (many formats allow this)


def _infer_importance(metadata: dict, fm: dict) -> tuple[float | None, str | None]:
    """Extract importance score and/or label."""
    imp = metadata.get("importance") or fm.get("importance")
    if imp is None:
        return None, None
    if isinstance(imp, (int, float)) and not isinstance(imp, bool):
        return float(imp), None
    return None, str(imp)


def _parse_time(val) -> datetime | None:
    """Parse ISO datetime string to UTC datetime."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def _parse_tags(metadata: dict) -> list[str]:
    tags = metadata.get("tags", [])
    if isinstance(tags, list):
        return sorted(str(t) for t in tags)
    if isinstance(tags, str):
        return sorted(t.strip() for t in tags.split(",") if t.strip())
    return []


def _to_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── Daily-notes roundtrip recovery ─────────────────────────────────

_ROUNDTRIP_RE = re.compile(r"<!-- memlink-roundtrip\s*\n(.*?)\n\s*-->", re.DOTALL)


_DREAMS_SECTION_RE = re.compile(
    r"^## ([0-9a-fA-F]{12,}|dream-\d{4}-\d{2}-\d{2}(?:-\d+)?)\s*$",
    re.MULTILINE,
)


def _parse_dreams_file(
    dreams_path: Path,
    workspace_root: Path,
    warnings: list[str],
    stats: dict[str, int],
) -> list[Memory]:
    """Parse DREAMS.md multi-entry file into Memory objects.

    Each entry starts with ## <hex-id>. Metadata comes exclusively from
    the memlink-roundtrip JSON block embedded as an HTML comment.
    Entries without a roundtrip block are skipped with a warning.
    """
    try:
        text = dreams_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.append(f"Cannot read DREAMS.md: {e}")
        return []

    rel = str(dreams_path.relative_to(workspace_root)).replace("\\", "/")
    memories: list[Memory] = []
    seen_ids: set[str] = set()

    splits = list(_DREAMS_SECTION_RE.finditer(text))
    for i, match in enumerate(splits):
        entry_id = match.group(1)
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        section_text = text[start:end]

        rt_match = _ROUNDTRIP_RE.search(section_text)
        if not rt_match:
            # No roundtrip block — try fallback: extract valence/arousal from text
            valence_match = re.search(r"valence:\s*([\d.]+)", section_text)
            if not valence_match:
                stats["skipped"] += 1
                warnings.append(f"DREAMS.md entry {entry_id}: no roundtrip block and no valence, skipped")
                continue

            arousal_match = re.search(r"arousal:\s*([\d.]+)", section_text)
            date_match = re.match(r"dream-(\d{4}-\d{2}-\d{2})", entry_id)
            created_at = _parse_time(date_match.group(1) + "T00:00:00") if date_match else None

            body_raw = re.sub(r"\nvalence:.*$", "", section_text.rstrip(), flags=re.MULTILINE).strip()
            body = body_raw if body_raw else None

            memory = Memory(
                id=entry_id,
                name=entry_id,
                source=Source(format="openclaw", path=rel, uri=f"openclaw://{rel}#{entry_id}"),
                summary=None,
                body=body,
                kind="emotion",
                status="active",
                tags=[],
                domains=[],
                created_at=created_at,
                valence=float(valence_match.group(1)),
                arousal=float(arousal_match.group(1)) if arousal_match else None,
                importance_score=5.0,
                importance_label=None,
                pinned=False,
                checksum=None,
                metadata={},
                extensions={},
            )
            memories.append(memory)
            stats["parsed"] += 1
            continue

        try:
            data = json.loads(rt_match.group(1))
        except json.JSONDecodeError:
            stats["skipped"] += 1
            warnings.append(f"DREAMS.md entry {entry_id}: invalid JSON in roundtrip block, skipped")
            continue

        if not isinstance(data, dict):
            stats["skipped"] += 1
            continue

        # Dedup by canonical (JSON) id, not heading id
        canonical_id = str(data.get("id", entry_id))
        if canonical_id in seen_ids:
            continue
        seen_ids.add(canonical_id)

        body_raw = section_text[: rt_match.start()]
        body_clean = re.sub(r"\nvalence:.*$", "", body_raw.rstrip(), flags=re.MULTILINE).strip()
        body = body_clean if body_clean else None

        original = data.get("memlink", {}).get("original", {})
        created_at = _parse_time(original.get("created") if original else None)

        memory = Memory(
            id=canonical_id,
            name=str(canonical_id),  # feel entries use id as name
            source=Source(
                format="openclaw",
                path=rel,
                uri=f"openclaw://{rel}#{canonical_id}",
            ),
            summary=None,
            body=body,
            kind=data.get("kind", "emotion"),
            status="active",
            tags=_parse_tags(data),
            domains=list(data.get("domains") or []),
            created_at=created_at,
            valence=_to_float(data.get("valence")),
            arousal=_to_float(data.get("arousal")),
            importance_score=_to_float(data.get("importance_score")),
            importance_label=data.get("importance_label"),
            pinned=bool(data.get("pinned", False)),
            checksum=data.get("checksum"),
            metadata={"memlink": data["memlink"]} if data.get("memlink") else {},
            extensions={},
        )
        memories.append(memory)
        stats["parsed"] += 1

    return memories


def _recover_roundtrip_comment(body: str | None, memory: Memory, warnings: list[str]) -> None:
    """Recover roundtrip metadata from HTML comment blocks in daily-notes files."""
    if not body:
        return
    for match in _ROUNDTRIP_RE.finditer(body):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                # Restore fields that weren't in frontmatter metadata
                if data.get("importance_score") and memory.importance_score is None:
                    memory.importance_score = data["importance_score"]
                if data.get("valence") and memory.valence is None:
                    memory.valence = data["valence"]
                if data.get("arousal") and memory.arousal is None:
                    memory.arousal = data["arousal"]
                # Restore name from roundtrip if current name looks like a date (daily-notes artifact)
                rt_name = data.get("name") or (data.get("memlink", {}).get("original", {}).get("name"))
                if rt_name and memory.name and re.fullmatch(r"\d{4}-\d{2}-\d{2}", memory.name):
                    memory.name = str(rt_name)

                # Strip daily-notes body artifacts: ## heading, tags: line, roundtrip comment, --- separators
                if memory.body and data.get("id"):
                    cleaned = memory.body
                    cleaned = re.sub(r"^\s*## [^\n]+\n*", "", cleaned)
                    cleaned = re.sub(r"^tags:[^\n]*\n*", "", cleaned, flags=re.MULTILINE)
                    cleaned = _ROUNDTRIP_RE.sub("", cleaned)
                    cleaned = re.sub(r"\n---\s*\n", "\n", cleaned)
                    cleaned = cleaned.strip()
                    memory.body = cleaned if cleaned else None

                # Restore tags from roundtrip if lost during daily-notes read
                if data.get("tags") is not None and not memory.tags:
                    memory.tags = sorted(str(t) for t in data["tags"])

                # Restore domains if lost during daily-notes read
                if data.get("domains") is not None and not memory.domains:
                    memory.domains = list(data["domains"])

                # Merge memlink data
                rt_memlink = data.get("memlink")
                if rt_memlink and not memory.metadata.get("memlink"):
                    memory.metadata["memlink"] = rt_memlink  # type: ignore[index]
        except (json.JSONDecodeError, KeyError, TypeError):
            warnings.append(f"Failed to parse roundtrip block for {memory.id}")
