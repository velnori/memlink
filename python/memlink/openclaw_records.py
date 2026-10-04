"""Length-framed Markdown records; arbitrary body headings/comments are literal."""

from __future__ import annotations

import base64
import json
import re

from .codec import memory_dict, memory_from_dict
from .models import Memory, Source
from .read_support import loads_json

HEADER = "# MemLink notes v1\n"
MARKER = re.compile(r"<!-- memlink-record-v1:([A-Za-z0-9_=-]+) -->\n")


def render_records(memories: list[Memory]) -> str:
    sections = [HEADER]
    for memory in memories:
        heading = (memory.name or memory.id).replace("\n", " ").replace("\r", " ")
        prefix = "## " + heading + "\n\n"
        body = memory.body or ""
        payload = prefix + body
        data = memory_dict(memory)
        data.pop("body")
        frame = {
            "version": "1",
            "prefix_length": len(prefix),
            "payload_length": len(payload),
            "body_is_null": memory.body is None,
            "memory": data,
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(frame, ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).decode("ascii")
        sections.append(f"<!-- memlink-record-v1:{encoded} -->\n{payload}\n\n")
    return "\n".join(sections)


def parse_records(text: str, relative: str) -> list[Memory] | None:
    if not text.startswith(HEADER):
        return None
    records = []
    pos = len(HEADER)
    while pos < len(text):
        while pos < len(text) and text[pos] == "\n":
            pos += 1
        if pos == len(text):
            break
        match = MARKER.match(text, pos)
        if match is None:
            raise ValueError("Invalid MemLink Markdown record boundary")
        data = loads_json(base64.urlsafe_b64decode(match.group(1)).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Markdown frame must be an object")
        if data.get("version") != "1":
            raise ValueError("Unknown Markdown record version")
        if type(data.get("body_is_null")) is not bool or not isinstance(data.get("memory"), dict):
            raise ValueError("Invalid Markdown frame memory/null marker")
        length, prefix = data["payload_length"], data["prefix_length"]
        if type(length) is not int or type(prefix) is not int or length < prefix or prefix < 0:
            raise ValueError("Invalid record length")
        start = match.end()
        if start + length > len(text):
            raise ValueError("Truncated Markdown record")
        payload = text[start : start + length]
        if not re.fullmatch(r"## [^\r\n]*\n\n", payload[:prefix]):
            raise ValueError("Invalid record heading")
        if data["body_is_null"] and length != prefix:
            raise ValueError("Null body frame contains unaccounted text")
        values = data["memory"]
        values["body"] = None if data["body_is_null"] else payload[prefix:]
        memory = memory_from_dict(values)
        memory.name = payload[3 : prefix - 2] if values.get("name") is not None else None
        memory.source = Source("openclaw", relative, f"openclaw://{relative}#{memory.id}")
        records.append(memory)
        pos = start + length
    return records
