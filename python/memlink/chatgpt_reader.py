"""ChatGPT export → Canonical Memory reader.

Reads ChatGPT official export JSON (conversations.json).
Each conversation becomes one Canonical Memory. Never raises.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult

_MAX_NAME_LEN = 60


class ChatGPTReader(FormatPlugin):
    name = "chatgpt"
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

            conv_id = conv.get("id")
            if not conv_id:
                stats["skipped"] += 1
                warnings.append(f"Missing id in {rel}")
                continue

            name = _truncate_name(str(conv.get("title") or "Untitled"), _MAX_NAME_LEN)
            created_at = _from_unix(conv.get("create_time"))
            updated_at = _from_unix(conv.get("update_time"))

            # Extract messages from mapping tree
            mapping = conv.get("mapping", {})
            turns = _extract_chatgpt_messages(mapping)

            if not turns:
                stats["skipped"] += 1
                warnings.append(f"No user/assistant messages in conversation {conv_id}")
                continue

            body = _format_messages(turns)
            checksum = _sha256(body)
            source_uri = f"chatgpt://export/{conv_id}"

            memories.append(
                Memory(
                    id=str(conv_id),
                    name=name,
                    body=body,
                    kind="dynamic",
                    created_at=created_at,
                    updated_at=updated_at,
                    checksum=checksum,
                    source=Source(format="chatgpt", path=str(rel), uri=source_uri),
                    metadata={
                        "memlink": {
                            "source": {"format": "chatgpt", "version": "1.0"},
                            "schema_version": "1",
                            "original": {"id": str(conv_id), "title": str(conv.get("title") or "")},
                        },
                    },
                )
            )
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("ChatGPTReader is read-only")

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
                ValidationIssue(code="ML004", severity=Severity.ERROR, path=str(target), message=f"Cannot parse JSON: {e}")
            )
            return issues

        if not isinstance(data, list):
            return issues

        for i, conv in enumerate(data):
            if not isinstance(conv, dict):
                continue
            if not conv.get("id"):
                issues.append(
                    ValidationIssue(
                        code="ML002", severity=Severity.ERROR, path=str(target),
                        memory_id=str(i), message=f"Conversation {i}: missing id",
                    )
                )
        return issues


def _extract_chatgpt_messages(mapping: dict) -> list[tuple[str, str]]:
    """Extract user/assistant messages from ChatGPT mapping tree, sorted by time."""
    messages: list[tuple[float, str, str]] = []  # (timestamp, role, text)

    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            continue
        msg = node.get("message")
        if not isinstance(msg, dict) or msg is None:
            continue
        role = (msg.get("author") or {}).get("role", "")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", {})
        if not isinstance(content, dict):
            continue
        if content.get("content_type") != "text":
            continue
        parts = content.get("parts", [])
        if not parts:
            continue
        text = " ".join(str(p) for p in parts if isinstance(p, str))
        if not text.strip():
            continue
        ts = msg.get("create_time") or 0
        messages.append((float(ts), role, text))

    messages.sort(key=lambda x: x[0])
    return [(role, text) for _, role, text in messages]


def _format_messages(turns: list[tuple[str, str]]) -> str:
    lines = [f"{role}: {text.strip()}" for role, text in turns]
    return "\n\n".join(lines)


def _from_unix(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
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
