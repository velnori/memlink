"""Canonical-v1 serialization and transport identity, independent of target shape."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timezone

from .models import Memory, Relationship, Source
from .serialization import sanitize


def parse_time(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        dt = datetime.fromtimestamp(value, timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def memory_dict(memory: Memory) -> dict:
    result = sanitize(asdict(memory))
    for field in ("created_at", "updated_at"):
        value = getattr(memory, field)
        normalized = parse_time(value)
        result[field] = normalized.isoformat() if normalized is not None else None
    return result


def memory_from_dict(data: dict) -> Memory:
    if data.get("schema_version") != "1":
        raise ValueError("Unknown canonical schema version")
    values = {k: v for k, v in data.items() if k in Memory.__dataclass_fields__}
    for field in ("created_at", "updated_at"):
        values[field] = parse_time(values.get(field))
    if values.get("source") is not None:
        values["source"] = Source(**values["source"])
    values["relationships"] = [Relationship(**r) for r in values.get("relationships", [])]
    return Memory(**values)


def stable_json(data) -> str:
    return json.dumps(sanitize(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def scope_of(memory: Memory) -> dict:
    memlink = memory.metadata.get("memlink")
    original = memlink.get("original", {}) if isinstance(memlink, dict) else {}
    if not isinstance(original, dict):
        original = {}
    scope = {
        key: original[key] for key in ("user_id", "agent_id", "run_id", "session_id") if original.get(key) is not None
    }
    if memory.extensions.get("zep_session_id") is not None:
        scope["session_id"] = memory.extensions["zep_session_id"]
    return scope or {"scope": "unknown"}


def identity(memory: Memory, namespace: str | None = None) -> dict:
    stored = memory.metadata.get("_memlink_identity")
    if (
        namespace is None
        and isinstance(stored, dict)
        and isinstance(stored.get("namespace"), str)
        and isinstance(stored.get("scope"), dict)
        and isinstance(stored.get("native_id"), str)
    ):
        return dict(stored)
    return {
        "namespace": namespace or (memory.source.format if memory.source else "library:unknown"),
        "scope": scope_of(memory),
        "native_id": memory.id,
    }


def identity_key(memory: Memory) -> str:
    return stable_json(identity(memory))


def attach_identity(memory: Memory, namespace: str) -> None:
    derived = identity(memory, namespace)
    stored = memory.metadata.get("_memlink_identity")
    if stored is not None and stored != derived:
        memory.metadata["_claimed_identity"] = stored
    memory.metadata["_memlink_identity"] = derived


def content_checksum(body: str | None) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()
