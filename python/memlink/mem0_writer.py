"""Canonical → Mem0 JSON writer.

Outputs Mem0 get_all() compatible JSON (memories.json).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .plugin import Capabilities, FormatPlugin

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import Memory


class Mem0Writer(FormatPlugin):
    name = "mem0"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=False,
        importance_label=False,
        supported_kinds={"dynamic"},
    )

    def read(self, path):
        raise NotImplementedError("Use Mem0Reader for reading")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        warnings: list[str] = []
        records: list[dict] = []

        for mem in memories:
            memory_text = mem.body or mem.name
            if not memory_text:
                warnings.append(f"Skipping {mem.id}: no body or name")
                continue

            user_id = "default"
            if mem.metadata:
                original = mem.metadata.get("memlink", {}).get("original", {})
                if isinstance(original, dict):
                    uid = original.get("user_id")
                    if uid:
                        user_id = str(uid)

            # Preserve name for roundtrip (Mem0 has no native name field)
            record_metadata: dict = {}
            if mem.name:
                record_metadata["_memlink_name"] = mem.name

            # Roundtrip: restore original Mem0 metadata from extensions
            if mem.extensions:
                raw = mem.extensions.get("mem0_metadata")
                if isinstance(raw, dict):
                    record_metadata.update(raw)

            record: dict = {
                "id": mem.id,
                "memory": str(memory_text),
                "user_id": user_id,
                "categories": sorted(mem.tags),
                "metadata": record_metadata,
            }

            if mem.created_at:
                record["created_at"] = _format_dt(mem.created_at)
            if mem.updated_at:
                record["updated_at"] = _format_dt(mem.updated_at)

            records.append(record)

        path.mkdir(parents=True, exist_ok=True)
        out = path / "memories.json"
        out.write_text(
            json.dumps({"results": records}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        return warnings

    def validate(self, path):
        return []


def _format_dt(dt: datetime) -> str:
    return dt.isoformat()
