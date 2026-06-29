"""Claude export → Canonical Memory reader.

Reads Anthropic official export JSON (conversations.json).
Each conversation becomes one Canonical Memory. Never raises.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult

_MAX_NAME_LEN = 60


class ClaudeExportReader(FormatPlugin):
    name = "claude_export"
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

        json_files = sorted(path.glob("*.json"))
        target = next((f for f in json_files if f.name == "conversations.json"), None)
        if target is None and json_files:
            target = json_files[0]
        if target is None:
            return ReadResult(memories=[], warnings=[f"No JSON file found in {path}"], stats=stats)

        rel = target.relative_to(path)
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return ReadResult(memories=[], warnings=[f"Cannot parse {rel}: {e}"], stats=stats)

        if not isinstance(data, list):
            return ReadResult(memories=[], warnings=[f"Expected JSON array in {rel}"], stats=stats)

        for conv in data:
            if not isinstance(conv, dict):
                stats["skipped"] += 1
                continue

            conv_id = conv.get("uuid")
            if not conv_id:
                stats["skipped"] += 1
                warnings.append(f"Missing uuid in {rel}")
                continue

            name = _truncate_name(str(conv.get("name") or "Untitled"), _MAX_NAME_LEN)
            created_at = _parse_dt(conv.get("created_at"))
            updated_at = _parse_dt(conv.get("updated_at"))

            messages = conv.get("chat_messages", [])
            if not isinstance(messages, list):
                messages = []

            turns: list[tuple[str, str]] = []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                sender = msg.get("sender", "")
                role = "human" if sender == "human" else "assistant" if sender == "assistant" else None
                if role is None:
                    continue
                text = msg.get("text", "")
                if not isinstance(text, str) or not text.strip():
                    continue
                turns.append((role, text))

            if not turns:
                stats["skipped"] += 1
                warnings.append(f"No human/assistant messages in conversation {conv_id}")
                continue

            body = _format_messages(turns)
            checksum = _sha256(body)
            source_uri = f"claude://export/{conv_id}"

            memories.append(
                Memory(
                    id=str(conv_id),
                    name=name,
                    body=body,
                    kind="dynamic",
                    created_at=created_at,
                    updated_at=updated_at,
                    checksum=checksum,
                    source=Source(format="claude_export", path=str(rel), uri=source_uri),
                    metadata={
                        "memlink": {
                            "source": {"format": "claude_export", "version": "1.0"},
                            "schema_version": "1",
                            "original": {"uuid": str(conv_id), "name": str(conv.get("name") or "")},
                        },
                    },
                )
            )
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("ClaudeExportReader is read-only")

    def validate(self, path: Path) -> list:
        from .plugin import Severity, ValidationIssue

        issues: list = []
        json_files = sorted(path.glob("*.json"))
        target = next((f for f in json_files if f.name == "conversations.json"), None)
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

        if not isinstance(data, list):
            return issues

        for i, conv in enumerate(data):
            if not isinstance(conv, dict):
                continue
            if not conv.get("uuid"):
                issues.append(
                    ValidationIssue(
                        code="ML002",
                        severity=Severity.ERROR,
                        path=str(target),
                        memory_id=str(i),
                        message=f"Conversation {i}: missing uuid",
                    )
                )
        return issues


def _format_messages(turns: list[tuple[str, str]]) -> str:
    lines = [f"{role}: {text.strip()}" for role, text in turns]
    return "\n\n".join(lines)


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
