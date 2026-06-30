"""memlink-stream daily summary → Canonical Memory reader.

Reads memlink-stream's Markdown output with frontmatter schema
"memlink-stream-summary-v1" and maps structured fields to Memory.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import yaml

from .models import Memory, Source
from .plugin import Capabilities, FormatPlugin, ReadResult


class StreamSummaryReader(FormatPlugin):
    name = "stream-summary"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        preserve_unknown_fields=True,
        supported_kinds=["dynamic"],
    )

    def read(self, path: Path) -> ReadResult:
        memories: list[Memory] = []
        warnings: list[str] = []
        stats: dict[str, int] = {"parsed": 0, "skipped": 0}

        for md_file in sorted(path.rglob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            parts = text.split("---", 2)
            if len(parts) < 3:
                stats["skipped"] += 1
                continue

            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                stats["skipped"] += 1
                continue

            if not isinstance(fm, dict):
                stats["skipped"] += 1
                continue

            # Only process memlink-stream summaries
            if fm.get("schema") != "memlink-stream-summary-v1":
                stats["skipped"] += 1
                continue

            body = parts[2]
            title = fm.get("title") or md_file.stem
            date_str = fm.get("date", "")

            # Tags
            raw_tags = fm.get("tags", [])
            if isinstance(raw_tags, str):
                tags = sorted(t.strip() for t in raw_tags.split(",") if t.strip())
            elif isinstance(raw_tags, list):
                tags = sorted(str(t) for t in raw_tags)
            else:
                tags = []

            # Domains from collection sources
            domains = ["daily-summary"]

            # Stats as summary
            total_events = fm.get("total_events")
            peak_hour = fm.get("peak_hour")
            status_str = fm.get("status", "active")
            summary_parts = []
            if total_events is not None:
                summary_parts.append(f"{total_events} events")
            if peak_hour is not None and peak_hour != "":
                summary_parts.append(f"peak at {peak_hour}:00")
            summary = ", ".join(summary_parts) if summary_parts else None

            # Build memory
            mem_id = hashlib.sha256(f"stream-summary:{title}:{date_str}".encode()).hexdigest()[:12]
            memories.append(Memory(
                id=mem_id,
                name=title,
                summary=summary,
                body=body.strip() or None,
                kind="dynamic",
                status="active",
                tags=tags,
                domains=domains,
                source=Source(format="stream-summary", path=str(md_file.relative_to(path))),
            ))
            stats["parsed"] += 1

        return ReadResult(memories=memories, warnings=warnings, stats=stats)

    def write(self, memories, path):
        raise NotImplementedError("stream-summary is read-only from memlink-stream")

    def validate(self, path: Path) -> list:
        return []
