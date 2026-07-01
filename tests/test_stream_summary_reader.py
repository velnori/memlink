"""Tests for StreamSummaryReader."""

from __future__ import annotations

from pathlib import Path

from memlink.stream_summary_reader import StreamSummaryReader


def test_reads_memlink_stream_summary(tmp_path: Path) -> None:
    reader = StreamSummaryReader()
    md = tmp_path / "2026-06-29-1d.md"
    md.write_text(
        """---
title: \"每日摘要 2026-06-29\"
date: \"2026-06-29\"
timezone: \"UTC\"
schema: \"memlink-stream-summary-v1\"
status: \"active\"
total_events: 9
peak_hour: 6
tags: [high-commit-velocity]
coverage: 0.04
collection_bash_history: 'partial: none'
collection_git: 'ok'
---

## 统计

| 指标 | 数值 |
|------|------|
| git | 9 |

## 活动特征

- high-commit-velocity (9 次 commit)
""",
        encoding="utf-8",
    )

    result = reader.read(tmp_path)
    assert result.stats["parsed"] == 1
    assert result.stats["skipped"] == 0

    m = result.memories[0]
    assert m.name == "每日摘要 2026-06-29"
    assert "9 events" in (m.summary or "")
    assert "peak at 6:00" in (m.summary or "")
    assert "high-commit-velocity" in m.tags
    assert "daily-summary" in m.domains
    assert m.kind == "dynamic"
    assert m.status == "active"
    assert m.body is not None
    assert "git | 9" in m.body


def test_skips_non_stream_summary(tmp_path: Path) -> None:
    reader = StreamSummaryReader()
    # A regular md without the stream schema
    md = tmp_path / "note.md"
    md.write_text(
        """---
title: just a note
---

hello
""",
        encoding="utf-8",
    )
    result = reader.read(tmp_path)
    assert result.stats["parsed"] == 0
    assert result.stats["skipped"] == 1


def test_empty_directory(tmp_path: Path) -> None:
    reader = StreamSummaryReader()
    result = reader.read(tmp_path)
    assert result.stats["parsed"] == 0
    assert result.memories == []
