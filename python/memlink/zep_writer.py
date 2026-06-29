"""Canonical → Zep facts JSON writer.

Outputs Zep-compatible facts.json.
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


class ZepWriter(FormatPlugin):
    name = "zep"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=False,
        importance_label=False,
        supported_kinds={"dynamic"},
    )

    def read(self, path):
        raise NotImplementedError("Use ZepReader for reading")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        warnings: list[str] = []
        records: list[dict] = []

        for mem in memories:
            fact_text = mem.body or mem.name
            if not fact_text:
                warnings.append(f"Skipping {mem.id}: no body or name")
                continue

            record: dict = {
                "uuid": mem.id,
                "fact": str(fact_text),
            }

            if mem.created_at:
                record["created_at"] = _format_dt(mem.created_at)
            if mem.updated_at:
                record["updated_at"] = _format_dt(mem.updated_at)

            # Preserve name for roundtrip (Zep has no native name field)
            record_metadata: dict = {}
            if mem.name:
                record_metadata["_memlink_name"] = mem.name

            # Roundtrip: restore original Zep metadata from extensions
            if mem.extensions:
                raw = mem.extensions.get("zep_metadata")
                if isinstance(raw, dict):
                    record_metadata.update(raw)

            if record_metadata:
                record["metadata"] = record_metadata

            # Restore session_id if present
            if mem.extensions:
                sid = mem.extensions.get("zep_session_id")
                if sid:
                    record["session_id"] = str(sid)

            records.append(record)

        path.mkdir(parents=True, exist_ok=True)
        out = path / "facts.json"
        out.write_text(
            json.dumps({"facts": records}, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        return warnings

    def validate(self, path):
        return []


def _format_dt(dt: datetime) -> str:
    return dt.isoformat()
