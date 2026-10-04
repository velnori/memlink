"""Offline JSON variants with record accounting and complete raw transcript transport."""

from __future__ import annotations

from pathlib import Path

from .codec import parse_time
from .models import JSONValue, Memory, Source
from .plugin import ReadResult
from .read_support import check_records, load_json, pick_json, relative, stats_init


def read_json_format(fmt: str, path: Path) -> ReadResult:
    preferred = {
        "mem0": ("memories.json",),
        "zep": ("facts.json", "memories.json"),
        "chatgpt": ("conversations.json",),
        "claude_export": ("conversations.json",),
    }[fmt]
    result = ReadResult([], stats=stats_init())
    try:
        file, excluded = pick_json(path, preferred)
        rel = relative(file, path)
        result.files.extend({"path": relative(f, path), "outcome": "excluded"} for f in excluded)
        data = load_json(file)
        session = data.get("session_id") if isinstance(data, dict) else None
        if fmt in {"chatgpt", "claude_export"}:
            records = check_records(data)
            result.variant = fmt + "-transcript-json"
        elif fmt == "mem0":
            records = check_records(data if isinstance(data, list) else data["results"])
            result.variant = "mem0-results" if isinstance(data, dict) else "mem0-array"
        else:
            if isinstance(data, list):
                records = data
                result.variant = "zep-facts-array"
            elif isinstance(data, dict) and "facts" in data:
                records = data["facts"]
                result.variant = "zep-facts"
            elif isinstance(data, dict) and "results" in data:
                records = data["results"]
                result.variant = "zep-results"
            elif isinstance(data, dict) and "messages" in data and "summary" in data:
                if not isinstance(data["summary"], dict):
                    raise ValueError("Zep session summary must be an object")
                records = [data["summary"]]
                result.variant = "zep-session-summary"
                session = data.get("session_id", (data.get("summary", {}).get("metadata") or {}).get("session_id"))
            else:
                raise ValueError("Unknown Zep top-level JSON shape")
            records = check_records(records)
        result.valid_empty = records == []
        for index, record in enumerate(records):
            try:
                if not isinstance(record, dict):
                    raise ValueError("Record must be an object")
                id_value = record.get("uuid", record.get("id")) if fmt in {"zep", "claude_export"} else record.get("id")
                if id_value is None or id_value == "":
                    raise ValueError("Missing uuid/id")
                mid = str(id_value)
                extensions: dict[str, JSONValue] = {}
                original = dict(record)
                if fmt in {"mem0", "zep"} and isinstance(data, dict):
                    export_fields = {
                        k: v for k, v in data.items() if k not in {"results", "facts", "messages", "summary"}
                    }
                    if export_fields:
                        extensions[fmt + "_export_fields"] = export_fields
                if fmt == "mem0":
                    body = record.get("memory")
                    if not isinstance(body, str):
                        raise ValueError("Missing or invalid memory field")
                    name = _truncate_name(body, 60)
                    metadata = record.get("metadata") or {}
                    if not isinstance(metadata, dict):
                        raise ValueError("metadata must be an object")
                    name = metadata.get("_memlink_name", name)
                    clean = {k: v for k, v in metadata.items() if k != "_memlink_name"}
                    if clean:
                        extensions["mem0_metadata"] = clean
                    known = {
                        "id",
                        "memory",
                        "metadata",
                        "categories",
                        "created_at",
                        "updated_at",
                        "user_id",
                        "agent_id",
                        "run_id",
                        "status",
                        "domains",
                    }
                    unknown = {k: v for k, v in record.items() if k not in known}
                    if unknown:
                        extensions["mem0_record"] = unknown
                    tags = record.get("categories", [])
                    if not isinstance(tags, list):
                        raise ValueError("categories must be an array")
                    domains = record.get("domains", [])
                    source_uri = f"mem0://scope/{mid}"
                elif fmt == "zep":
                    body = record.get("fact", record.get("content"))
                    if not isinstance(body, str):
                        raise ValueError("Missing fact/content")
                    name = _truncate_name(body, 60)
                    metadata = record.get("metadata") or {}
                    if not isinstance(metadata, dict):
                        raise ValueError("metadata must be an object")
                    name = metadata.get("_memlink_name", name)
                    clean = {k: v for k, v in metadata.items() if k != "_memlink_name"}
                    if clean:
                        extensions["zep_metadata"] = clean
                    sid = record.get("session_id", session if session is not None else metadata.get("session_id"))
                    if sid is not None:
                        extensions["zep_session_id"] = sid
                        original["session_id"] = sid
                    if result.variant == "zep-session-summary":
                        extensions["zep_session_export"] = data
                    known = {
                        "uuid",
                        "id",
                        "fact",
                        "content",
                        "created_at",
                        "updated_at",
                        "metadata",
                        "session_id",
                        "status",
                        "domains",
                    }
                    unknown = {k: v for k, v in record.items() if k not in known}
                    if unknown:
                        extensions["zep_record"] = unknown
                    tags = []
                    domains = record.get("domains", [])
                    source_uri = f"zep://scope/{mid}"
                elif fmt == "chatgpt":
                    name = _truncate_name(str(record.get("title") or "Untitled"), 60)
                    body, notes = _chatgpt_body(record)
                    result.warnings.extend(f"{mid}: {w}" for w in notes)
                    extensions["chatgpt_transcript"] = record
                    tags = []
                    domains = []
                    source_uri = f"chatgpt://transcript/{mid}"
                else:
                    name = _truncate_name(str(record.get("name") or "Untitled"), 60)
                    body, notes = _claude_body(record)
                    result.warnings.extend(f"{mid}: {w}" for w in notes)
                    extensions["claude_transcript"] = record
                    tags = []
                    domains = []
                    source_uri = f"claude://transcript/{mid}"
                if fmt in {"chatgpt", "claude_export"} and not body:
                    result.stats["skipped"] += 1
                    result.stats["unsupported"] += 1
                    result.records.append(
                        {"index": index, "id": mid, "outcome": "unsupported", "reason": "No supported transcript text"}
                    )
                    result.warnings.append(f"No user/assistant messages in conversation {mid}")
                    continue
                created = record.get("create_time") if fmt == "chatgpt" else record.get("created_at")
                updated = record.get("update_time") if fmt == "chatgpt" else record.get("updated_at")
                status = record.get("status", "active")
                if status not in {"active", "archived"}:
                    raise ValueError("Unsupported status")
                if not isinstance(domains, list):
                    raise ValueError("domains must be an array")
                memory = Memory(
                    id=mid,
                    name=name,
                    body=body,
                    kind="dynamic",
                    status=status,
                    tags=[str(t) for t in tags],
                    domains=[str(d) for d in domains],
                    created_at=parse_time(created),
                    updated_at=parse_time(updated),
                    extensions=extensions,
                    source=Source(fmt, rel, source_uri),
                    metadata={
                        "memlink": {
                            "source": {"format": fmt, "version": "1.0"},
                            "schema_version": "1",
                            "original": original,
                        }
                    },
                )
                result.memories.append(memory)
                result.records.append({"index": index, "id": mid, "outcome": "parsed"})
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                result.stats["invalid"] += 1
                result.records.append({"index": index, "outcome": "invalid", "reason": str(exc)})
                result.warnings.append(f"{rel} record {index}: {exc}")
        result.files.append({"path": rel, "outcome": "parsed" if result.memories or result.valid_empty else "invalid"})
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        result.errors.append(str(exc))
        result.warnings.append(str(exc))
        result.stats["invalid"] += 1
    result.stats["parsed"] = len(result.memories)
    return result


def _truncate_name(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    chunk = text[:max_len]
    for sep in (" ", "\n", "\t"):
        i = chunk.rfind(sep)
        if i > max_len // 2:
            return chunk[:i]
    return chunk


def _chatgpt_body(conv: dict) -> tuple[str, list[str]]:
    mapping = conv.get("mapping")
    if not isinstance(mapping, dict):
        raise ValueError("mapping must be an object")
    notes = []
    current = conv.get("current_node")
    if current is None:
        # Only infer a unique rooted chain, never merge alternative branches by time.
        parents = {key: node.get("parent") for key, node in mapping.items() if isinstance(node, dict)}
        roots = [key for key, value in parents.items() if value is None]
        child_counts = {key: sum(p == key for p in parents.values()) for key in parents}
        leaves = [key for key, n in child_counts.items() if n == 0]
        if len(roots) != 1 or len(leaves) != 1 or any(n > 1 for n in child_counts.values()):
            raise ValueError("Missing active path in a branched/orphan transcript")
        current = leaves[0]
        notes.append("current_node absent; inferred the sole rooted chain")
    active = []
    seen = set()
    while current is not None:
        if current in seen:
            raise ValueError("Cycle in active transcript path")
        if current not in mapping or not isinstance(mapping[current], dict):
            raise ValueError("Missing active transcript node/parent")
        seen.add(current)
        active.append(current)
        current = mapping[current].get("parent")
    active.reverse()
    if set(mapping) - seen:
        notes.append(f"{len(set(mapping) - seen)} non-active nodes retained only in transcript archive")
    turns = []
    for key in active:
        msg = mapping[key].get("message")
        if msg is None:
            continue
        if not isinstance(msg, dict):
            raise ValueError("Invalid active message")
        author = msg.get("author") or {}
        if not isinstance(author, dict):
            raise ValueError("Active author must be an object")
        role = author.get("role")
        content = msg.get("content") or {}
        if not isinstance(content, dict):
            notes.append(f"node {key}: unsupported content shape retained in transcript archive")
            continue
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if not isinstance(parts, list):
            raise ValueError("Active content.parts must be an array")
        text = " ".join(p for p in parts if isinstance(p, str))
        if role in {"user", "assistant"} and text:
            turns.append((role, text))
        if (
            role not in {"user", "assistant"}
            or content.get("content_type") != "text"
            or any(not isinstance(p, str) for p in parts)
        ):
            notes.append(f"node {key}: tool/unknown/attachment data retained in transcript archive")
    return "\n\n".join(f"{role}: {text}" for role, text in turns), notes


def _claude_body(conv: dict) -> tuple[str, list[str]]:
    messages = check_records(conv.get("chat_messages", []))
    notes = []
    turns = []
    for index, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise ValueError("Invalid chat message")
        role = msg.get("sender")
        blocks = msg.get("content")
        if isinstance(blocks, list):
            texts = []
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
                else:
                    notes.append(f"message {index}: unknown/tool block retained in transcript archive")
            text = "\n".join(texts)
            # Preserve a different parallel text representation, without pretending it was selected.
            if msg.get("text") and msg["text"] != text:
                notes.append(f"message {index}: alternate text retained in transcript archive")
        else:
            text = msg.get("text", "")
        if role in {"human", "assistant"} and isinstance(text, str) and text:
            turns.append((role, text))
        elif role not in {"human", "assistant"}:
            notes.append(f"message {index}: unknown sender retained in transcript archive")
        if msg.get("attachments") or msg.get("files"):
            notes.append(f"message {index}: attachments retained as data; no OCR or binary fetch")
    return "\n\n".join(f"{role}: {text}" for role, text in turns), notes
