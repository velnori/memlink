"""Zep → Canonical Memory reader.

Reads Zep JSON exports (facts, array, and session formats).
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


class ZepReader(FormatPlugin):
    name = "zep"
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
        target = None
        for preferred in ("facts.json", "memories.json"):
            for f in json_files:
                if f.name == preferred:
                    target = f
                    break
            if target:
                break
        if target is None and json_files:
            target = json_files[0]
        if target is None:
            return ReadResult(memories=[], warnings=[f"No JSON file found in {path}"], stats=stats)

        # Parse JSON
        rel = target.relative_to(path)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return ReadResult(memories=[], warnings=[f"Cannot parse {rel}: {e}"], stats=stats)

        # Identify format
        records: list[dict] = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            if "facts" in data:
                records = data["facts"]
            elif "messages" in data and "summary" in data:
                # Session format: treat summary as single record
                summary = data.get("summary")
                if isinstance(summary, dict):
                    records = [summary]
            elif "results" in data:
                records = data["results"]
            else:
                return ReadResult(memories=[], warnings=[f"Unknown Zep JSON format in {rel}"], stats=stats)
        else:
            return ReadResult(memories=[], warnings=[f"Unexpected JSON structure in {rel}"], stats=stats)

        for record in records:
            if not isinstance(record, dict):
                stats["skipped"] += 1
                warnings.append(f"Skipping non-dict record in {rel}")
                continue

            mem_id = record.get("uuid") or record.get("id")
            if not mem_id:
                stats["skipped"] += 1
                warnings.append(f"Missing uuid/id in {rel}")
                continue

            body_text = record.get("fact") or record.get("content")
            if not body_text:
                stats["skipped"] += 1
                warnings.append(f"Missing fact/content for id={mem_id} in {rel}")
                continue

            name = _truncate_name(str(body_text), _MAX_NAME_LEN)
            created_at = _parse_dt(record.get("created_at"))
            if created_at is None and record.get("created_at"):
                warnings.append(f"Invalid created_at for id={mem_id}: {record['created_at']}")
            updated_at = _parse_dt(record.get("updated_at"))

            extensions: dict[str, object] = {}
            raw_meta = record.get("metadata")
            if isinstance(raw_meta, dict) and raw_meta:
                extensions["zep_metadata"] = raw_meta
            session_id = record.get("session_id")
            if not session_id and isinstance(data, dict):
                summary = data.get("summary")
                if isinstance(summary, dict):
                    session_id = (summary.get("metadata") or {}).get("session_id")
            if session_id:
                extensions["zep_session_id"] = str(session_id)

            checksum = _sha256(str(body_text))
            source_uri = f"zep://facts/{mem_id}"

            memories.append(
                Memory(
                    id=str(mem_id),
                    name=name,
                    body=str(body_text),
                    kind="dynamic",
                    created_at=created_at,
                    updated_at=updated_at,
                    checksum=checksum,
                    extensions=extensions,  # type: ignore[arg-type]
                    source=Source(format="zep", path=str(rel), uri=source_uri),
                    metadata={
                        "memlink": {
                            "source": {"format": "zep", "version": "1.0"},
                            "schema_version": "1",
                            "original": {"uuid": str(mem_id), "body": str(body_text)},
                        },
                    },
                )
            )
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("ZepWriter not implemented")

    def validate(self, path: Path) -> list:
        from .plugin import Severity, ValidationIssue

        issues: list = []
        json_files = sorted(path.glob("*.json"))
        target = next((f for f in json_files if f.name == "facts.json"), None)
        if target is None and json_files:
            target = json_files[0]
        if target is None:
            issues.append(
                ValidationIssue(code="ML200", severity=Severity.ERROR, path=str(path), message="No JSON file found")
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

        records = data if isinstance(data, list) else data.get("facts", data.get("results", []))
        for i, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            rec_id = record.get("uuid") or record.get("id")
            if not rec_id:
                issues.append(
                    ValidationIssue(
                        code="ML002",
                        severity=Severity.ERROR,
                        path=str(target),
                        memory_id=str(i),
                        message=f"Record {i}: missing uuid/id",
                    )
                )
            if not (record.get("fact") or record.get("content")):
                issues.append(
                    ValidationIssue(
                        code="ML005",
                        severity=Severity.ERROR,
                        path=str(target),
                        memory_id=str(rec_id or i),
                        message=f"Record {rec_id or i}: missing fact/content",
                    )
                )
        return issues


# ── Helpers ─────────────────────────────────────────────────────────


def _parse_dt(val) -> datetime | None:
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
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    for sep in (" ", "\n", "\t"):
        idx = truncated.rfind(sep)
        if idx > max_len // 2:
            return truncated[:idx]
    return truncated


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
