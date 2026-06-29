"""Mem0 → Canonical Memory reader.

Reads Mem0 JSON exports (get_all() format).
Never raises — parse failures become warnings and skipped records.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult

_MAX_NAME_LEN = 60


class Mem0Reader(FormatPlugin):
    name = "mem0"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=False,
        importance_label=False,
        supported_kinds={"dynamic"},
    )

    def read(self, path: Path) -> ReadResult:
        memories: list[Memory] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"parsed": 0, "skipped": 0, "invalid": 0}

        # Find JSON file
        json_files = sorted(path.glob("*.json"))
        target = next((f for f in json_files if f.name == "memories.json"), None)
        if target is None and json_files:
            target = json_files[0]
        if target is None:
            return ReadResult(
                memories=[],
                warnings=[f"No JSON file found in {path}"],
                stats=stats,
            )

        # Parse JSON
        rel = target.relative_to(path)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return ReadResult(
                memories=[],
                warnings=[f"Cannot parse {rel}: {e}"],
                stats=stats,
            )

        # Support both {"results": [...]} and [...]
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("results", [])
        else:
            return ReadResult(memories=[], warnings=[f"Unexpected JSON structure in {rel}"], stats=stats)

        for record in records:
            if not isinstance(record, dict):
                stats["skipped"] += 1
                warnings.append(f"Skipping non-dict record in {rel}")
                continue

            mem_id = record.get("id")
            if not mem_id:
                stats["skipped"] += 1
                warnings.append(f"Missing id in {rel}")
                continue

            memory_text = record.get("memory")
            if not memory_text:
                stats["skipped"] += 1
                warnings.append(f"Missing memory field for id={mem_id} in {rel}")
                continue

            # Name: truncate at 60 chars, avoid breaking multi-byte chars
            name = _truncate_name(str(memory_text), _MAX_NAME_LEN)

            # Extensions: metadata → mem0_metadata
            raw_meta = record.get("metadata")
            extensions: dict = {}
            if isinstance(raw_meta, dict) and raw_meta:
                # Recover name from _memlink_name (set by Mem0Writer for roundtrip)
                saved_name = raw_meta.get("_memlink_name")
                if saved_name:
                    name = str(saved_name)
                # Copy remaining metadata (excluding internal _memlink_name)
                clean = {k: v for k, v in raw_meta.items() if k != "_memlink_name"}
                if clean:
                    extensions["mem0_metadata"] = clean

            # Datetime parsing
            created_at = _parse_dt(record.get("created_at"))
            if created_at is None and record.get("created_at"):
                warnings.append(f"Invalid created_at for id={mem_id}: {record['created_at']}")

            updated_at = _parse_dt(record.get("updated_at"))

            # memlink original snapshot
            memlink_original = {
                "id": str(mem_id),
                "user_id": record.get("user_id"),
                "agent_id": record.get("agent_id"),
                "run_id": record.get("run_id"),
            }

            # Checksum of memory text
            checksum = _sha256(str(memory_text))

            user_id = str(record.get("user_id", "unknown"))
            source_uri = f"mem0://{user_id}/{mem_id}"

            memories.append(
                Memory(
                    id=str(mem_id),
                    name=name,
                    body=str(memory_text),
                    kind="dynamic",
                    tags=_safe_list(record.get("categories")),
                    created_at=created_at,
                    updated_at=updated_at,
                    checksum=checksum,
                    extensions=extensions,  # type: ignore[arg-type]
                    source=Source(format="mem0", path=str(rel), uri=source_uri),
                    metadata={
                        "memlink": {
                            "source": {"format": "mem0", "version": "1.0"},
                            "schema_version": "1",
                            "original": memlink_original,
                        },
                    },
                )
            )
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("Mem0Writer not implemented")

    def validate(self, path: Path) -> list:
        from .plugin import Severity, ValidationIssue

        issues: list = []
        json_files = sorted(path.glob("*.json"))
        target = next((f for f in json_files if f.name == "memories.json"), None)
        if target is None and json_files:
            target = json_files[0]
        if target is None:
            issues.append(
                ValidationIssue(
                    code="ML200",
                    severity=Severity.ERROR,
                    path=str(path),
                    message="No JSON file found",
                )
            )
            return issues

        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            issues.append(
                ValidationIssue(
                    code="ML004",
                    severity=Severity.ERROR,
                    path=str(target),
                    message=f"Cannot parse JSON: {e}",
                )
            )
            return issues

        records = data if isinstance(data, list) else data.get("results", [])
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            if not record.get("id"):
                issues.append(
                    ValidationIssue(
                        code="ML002",
                        severity=Severity.ERROR,
                        path=str(target),
                        memory_id=str(i),
                        message=f"Record {i}: missing id",
                    )
                )
            if not record.get("memory"):
                issues.append(
                    ValidationIssue(
                        code="ML005",
                        severity=Severity.ERROR,
                        path=str(target),
                        memory_id=str(record.get("id", i)),
                        message=f"Record {record.get('id', i)}: missing memory field",
                    )
                )
        return issues


# ── Helpers ─────────────────────────────────────────────────────────


def _parse_dt(val) -> datetime | None:
    """Parse ISO datetime string, handling 'Z' suffix by replacing with +00:00."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        s = str(val).replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _truncate_name(text: str, max_len: int) -> str:
    """Truncate text at whitespace to avoid breaking multi-byte characters."""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # Find last whitespace to avoid cutting words
    for sep in (" ", "\n", "\t"):
        idx = truncated.rfind(sep)
        if idx > max_len // 2:
            return truncated[:idx]
    return truncated


def _safe_list(val) -> list[str]:
    if isinstance(val, list):
        return sorted(str(v) for v in val)
    return []


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
