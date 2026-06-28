"""Tests for OpenClaw → Canonical reader."""

from datetime import datetime
from pathlib import Path

import pytest

from memlink.openclaw_reader import OpenClawReader


@pytest.fixture
def openclaw_dir(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "test-memory.md").write_text("""---
name: Test Memory
description: A test memory for unit tests
metadata:
  type: project
  tags: [test, sample]
  importance: high
  created_at: 2024-01-01T10:00:00Z
---
This is the body content.
""", encoding="utf-8")

    feels_dir = memory_dir / "feels"
    feels_dir.mkdir()
    (feels_dir / "excited.md").write_text("""---
name: Excited about launch
metadata:
  valence: 0.8
  arousal: 0.7
---
Feeling great!
""", encoding="utf-8")

    (tmp_path / "MEMORY.md").write_text("""# Memory Index
- memory/test-memory.md - Test memory
- memory/feels/excited.md
""")
    return tmp_path


class TestOpenClawReader:
    def test_read_basic(self, openclaw_dir):
        reader = OpenClawReader()
        result = reader.read(openclaw_dir)
        assert result.stats["parsed"] == 2

    def test_read_with_description(self, openclaw_dir):
        reader = OpenClawReader()
        result = reader.read(openclaw_dir)
        mem = next(m for m in result.memories if m.id == "test-memory")
        assert mem.summary == "A test memory for unit tests"

    def test_read_emotion_kind(self, openclaw_dir):
        reader = OpenClawReader()
        result = reader.read(openclaw_dir)
        em = next(m for m in result.memories if "excited" in m.id)
        assert em.kind == "emotion"

    def test_read_importance_label(self, openclaw_dir):
        reader = OpenClawReader()
        result = reader.read(openclaw_dir)
        mem = next(m for m in result.memories if m.id == "test-memory")
        assert mem.importance_label == "high"

    def test_domain_from_metadata_type(self, openclaw_dir):
        reader = OpenClawReader()
        result = reader.read(openclaw_dir)
        mem = next(m for m in result.memories if m.id == "test-memory")
        assert "project" in mem.domains

    def test_missing_name_field(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "broken.md").write_text("""---
description: No name field
---
Body
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.stats["skipped"] >= 1

    def test_restore_from_memlink_metadata(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "restored.md").write_text("""---
name: Restored
metadata:
  memlink:
    source: ombre
    original:
      id: original-bucket-id
      kind: permanent
      domains: [user, work, project]
      importance: 8
      created_tz: "2024-01-01T18:00:00+08:00"
---
Body
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        mem = result.memories[0]
        assert mem.id == "original-bucket-id"
        assert mem.kind == "permanent"
        assert set(mem.domains) == {"user", "work", "project"}
        assert mem.importance_score == 8

    def test_unknown_domain_fallback(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "no-domain.md").write_text("""---
name: No Domain
---
Body
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.memories[0].domains == []

    def test_chinese_and_emoji(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "chinese-emoji.md").write_text("""---
name: 项目启动会 🚀
description: 很兴奋！
---
今天开了很棒的会议 😊
""", encoding="utf-8")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        mem = result.memories[0]
        assert "项目启动会" in str(mem.name)
        assert "😊" in str(mem.body)

    def test_empty_body(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "no-body.md").write_text("""---
name: Only Title
---

""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.memories[0].body is None

    def test_malformed_yaml(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "broken-yaml.md").write_text("""---
name: broken
  bad: indent
---
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.stats["invalid"] >= 1 or result.stats["skipped"] >= 1

    def test_memory_index_grouped_format(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "work.md").write_text("---\nname: Work\n---\nBody\n")
        (memory_dir / "personal.md").write_text("---\nname: Personal\n---\nBody\n")
        (tmp_path / "MEMORY.md").write_text("""# Memory Index

## Work Memories
- memory/work.md

## Personal
- memory/personal.md - Personal note
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.stats["parsed"] == 2

    def test_priority_high_to_permanent(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "important.md").write_text("""---
name: Important
metadata:
  priority: high
---
Body
""")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        assert result.memories[0].kind == "permanent"

    def test_percent_encoded_filename(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "project%2Ffeature.md").write_text("---\nname: Feature\n---\nBody\n")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        # On filesystem, %2F is literal — unquote turns it to /
        assert result.memories[0].id in ("project/feature", "project%2Ffeature")

    def test_fallback_when_memory_md_missing(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "orphan.md").write_text("---\nname: Orphan\n---\nBody\n")
        reader = OpenClawReader()
        result = reader.read(tmp_path)
        # Should still find orphan files via recursive scan
        assert result.stats["parsed"] == 1
