"""mem0 offline file writer; no online service/API import."""

from __future__ import annotations

import json
from pathlib import Path

from .codec import parse_time
from .plugin import Capabilities, FormatPlugin
from .serialization import sanitize


class Mem0Writer(FormatPlugin):
    name = "mem0"
    version_supported = ">=1,<3"
    capabilities = Capabilities(supported_kinds={"dynamic"})

    def read(self, path):
        raise NotImplementedError("Use the matching reader")

    def write(self, memories, path: Path) -> list[str]:
        records = []
        warnings: list[str] = []
        for mem in memories:
            text = mem.body if mem.body is not None else mem.name or ""
            original = (mem.metadata.get("memlink") or {}).get("original") or {}
            raw = mem.extensions.get("mem0_metadata") or {}
            metadata = dict(raw) if isinstance(raw, dict) else {}
            if mem.name is not None:
                metadata["_memlink_name"] = mem.name
            record = {
                "id" if self.name == "mem0" else "uuid": mem.id,
                "memory" if self.name == "mem0" else "fact": text,
                "metadata": metadata,
            }
            if self.name == "mem0":
                record["categories"] = sorted(mem.tags)
                for key in ("user_id", "agent_id", "run_id"):
                    if original.get(key) is not None:
                        record[key] = original[key]
            else:
                sid = mem.extensions.get("zep_session_id", original.get("session_id"))
                if sid is not None:
                    record["session_id"] = sid
            for field in ("created_at", "updated_at"):
                value = getattr(mem, field)
                if value is not None:
                    normalized = parse_time(value)
                    assert normalized is not None
                    record[field] = normalized.isoformat()
            records.append(record)
        path.mkdir(parents=True, exist_ok=True)
        data = {"results" if self.name == "mem0" else "facts": records}
        (path / ("memories.json" if self.name == "mem0" else "facts.json")).write_text(
            json.dumps(sanitize(data), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline=""
        )
        return warnings

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)


def _format_dt(value):
    normalized = parse_time(value)
    return normalized.isoformat() if normalized is not None else None
