"""memlink-stream-summary-v1 adapter; raw frontmatter remains recoverable."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ._frontmatter import parse_frontmatter
from .codec import parse_time
from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult
from .read_support import markdown_files, relative, stats_init


class StreamSummaryReader(FormatPlugin):
    name = "stream-summary"
    version_supported = ">=1,<3"
    capabilities = Capabilities(summary=True, preserve_unknown_fields=True, supported_kinds={"dynamic"})

    def read(self, path: Path) -> ReadResult:
        result = ReadResult([], stats=stats_init(), variant="memlink-stream-summary-v1")
        for file in markdown_files(path):
            rel = relative(file, path)
            try:
                fm, body = parse_frontmatter(file.read_bytes().decode("utf-8"))
                if fm.get("schema") != "memlink-stream-summary-v1":
                    result.stats["skipped"] += 1
                    result.stats["unsupported"] += 1
                    result.files.append({"path": rel, "outcome": "unsupported"})
                    result.records.append(
                        {"path": rel, "outcome": "unsupported", "reason": "Different/missing stream schema"}
                    )
                    result.warnings.append(f"{rel}: not a stream summary")
                    continue
                title = str(fm.get("title") or file.stem)
                raw_date = fm.get("date")
                created = parse_time(raw_date)
                if raw_date is not None and fm.get("timezone"):
                    raw_dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
                    if raw_dt.tzinfo is None:
                        try:
                            created = parse_time(raw_dt.replace(tzinfo=ZoneInfo(str(fm["timezone"]))))
                        except ZoneInfoNotFoundError:
                            result.warnings.append(
                                f"{rel}: timezone database unavailable; assumed UTC, original retained"
                            )
                raw_tags = fm.get("tags", [])
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else raw_tags
                if not isinstance(tags, list):
                    raise ValueError("tags must be a list or comma-separated string")
                status = fm.get("status", "active")
                if status not in {"active", "archived"}:
                    raise ValueError("Unsupported status")
                parts = []
                if fm.get("total_events") is not None:
                    parts.append(f"{fm['total_events']} events")
                if fm.get("peak_hour") is not None and fm.get("peak_hour") != "":
                    parts.append(f"peak at {fm['peak_hour']}:00")
                # Relative source path prevents equal title/date records being collapsed.
                mid = str(fm.get("id") or hashlib.sha256(f"stream-summary:{rel}".encode()).hexdigest()[:12])
                result.memories.append(
                    Memory(
                        id=mid,
                        name=title,
                        summary=", ".join(parts) or None,
                        body=body.strip() or None,
                        kind="dynamic",
                        status=status,
                        tags=sorted(str(t) for t in tags),
                        domains=["daily-summary"],
                        created_at=created,
                        extensions={"stream_frontmatter": fm},
                        metadata={"memlink": {"original": fm}},
                        source=Source("stream-summary", rel),
                    )
                )
                result.files.append({"path": rel, "outcome": "parsed"})
                result.records.append({"id": mid, "path": rel, "outcome": "parsed"})
            except (ValueError, TypeError, OSError, OverflowError) as exc:
                result.stats["invalid"] += 1
                result.files.append({"path": rel, "outcome": "invalid"})
                result.records.append({"path": rel, "outcome": "invalid", "reason": str(exc)})
                result.warnings.append(f"{rel}: {exc}")
        result.stats["parsed"] = len(result.memories)
        return result

    def write(self, memories, path):
        raise NotImplementedError("stream-summary is read-only")

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)
