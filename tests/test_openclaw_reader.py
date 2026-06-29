"""Tests for OpenClaw → Canonical reader."""

import pytest

from memlink.openclaw_reader import OpenClawReader


@pytest.fixture
def openclaw_dir(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "test-memory.md").write_text(
        """---
name: Test Memory
description: A test memory for unit tests
metadata:
  type: project
  tags: [test, sample]
  importance: high
  created_at: 2024-01-01T10:00:00Z
---
This is the body content.
""",
        encoding="utf-8",
    )

    feels_dir = memory_dir / "feels"
    feels_dir.mkdir()
    (feels_dir / "excited.md").write_text(
        """---
name: Excited about launch
metadata:
  valence: 0.8
  arousal: 0.7
---
Feeling great!
""",
        encoding="utf-8",
    )

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
        (memory_dir / "chinese-emoji.md").write_text(
            """---
name: 项目启动会 🚀
description: 很兴奋！
---
今天开了很棒的会议 😊
""",
            encoding="utf-8",
        )
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


DREAMS_CONTENT = """\
---
title: Dream Diary
---

## abc123def456

今天蕾蕾让我建 CLAUDE.md。

valence: 0.8 / arousal: 0.3

<!-- memlink-roundtrip
{
  "id": "abc123def456",
  "kind": "emotion",
  "importance_score": 5.0,
  "importance_label": null,
  "valence": 0.8,
  "arousal": 0.3,
  "pinned": false,
  "domains": ["内心"],
  "tags": ["test"],
  "source_uri": "ombre://feel/内心/abc123def456",
  "checksum": "aabbcc",
  "memlink": {
    "source": {"format": "ombre", "version": "1.0"},
    "schema_version": "1",
    "original": {
      "id": "abc123def456",
      "type": "feel",
      "importance": 5,
      "created": "2026-06-14T03:42:42",
      "domain": ["内心"],
      "tags": ["test"],
      "valence": 0.8,
      "arousal": 0.3
    }
  }
}
-->
## 999888777666

第二条 feel。

valence: 0.5 / arousal: 0.2

<!-- memlink-roundtrip
{
  "id": "999888777666",
  "kind": "emotion",
  "importance_score": 3.0,
  "importance_label": null,
  "valence": 0.5,
  "arousal": 0.2,
  "pinned": true,
  "domains": [],
  "tags": [],
  "source_uri": "ombre://feel/unknown/999888777666",
  "checksum": "ddeeff",
  "memlink": {
    "source": {"format": "ombre", "version": "1.0"},
    "schema_version": "1",
    "original": {
      "id": "999888777666",
      "type": "feel",
      "importance": 3,
      "created": "2026-06-15T10:00:00",
      "domain": [],
      "tags": [],
      "valence": 0.5,
      "arousal": 0.2
    }
  }
}
-->
"""


class TestOpenClawReaderDreams:
    def _make_workspace(self, tmp_path, dreams_content=DREAMS_CONTENT, with_memory=False):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        if with_memory:
            (memory_dir / "normal.md").write_text("---\nname: Normal\n---\nBody\n", encoding="utf-8")
        (tmp_path / "DREAMS.md").write_text(dreams_content, encoding="utf-8")
        return tmp_path

    def test_dreams_entries_are_read(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        ids = [m.id for m in result.memories]
        assert "abc123def456" in ids
        assert "999888777666" in ids

    def test_dreams_kind_is_emotion(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert m.kind == "emotion"

    def test_dreams_valence_arousal(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert m.valence == pytest.approx(0.8)
        assert m.arousal == pytest.approx(0.3)

    def test_dreams_domains_and_tags(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert "内心" in m.domains
        assert "test" in m.tags

    def test_dreams_importance_score(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert m.importance_score == pytest.approx(5.0)

    def test_dreams_pinned(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "999888777666")
        assert m.pinned is True

    def test_dreams_body_extracted(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert m.body is not None
        assert "CLAUDE.md" in m.body

    def test_dreams_source_format(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "abc123def456")
        assert m.source.format == "openclaw"
        assert "DREAMS.md" in m.source.path

    def test_dreams_combined_with_memory_dir(self, tmp_path):
        ws = self._make_workspace(tmp_path, with_memory=True)
        result = OpenClawReader().read(ws)
        assert result.stats["parsed"] == 3  # 2 dreams + 1 memory

    def test_no_dreams_file_is_fine(self, tmp_path):
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "x.md").write_text("---\nname: X\n---\nBody\n", encoding="utf-8")
        result = OpenClawReader().read(tmp_path)
        assert result.stats["parsed"] == 1
        assert not any("DREAMS" in w for w in result.warnings)

    def test_dreams_no_roundtrip_block_is_skipped(self, tmp_path):
        content = "## badfeed000001\n\nNo roundtrip block and no valence.\n"
        ws = self._make_workspace(tmp_path, dreams_content=content)
        result = OpenClawReader().read(ws)
        ids = [m.id for m in result.memories]
        assert "badfeed000001" not in ids
        assert result.stats["skipped"] >= 1

    def test_dreams_deduplication(self, tmp_path):
        doubled = DREAMS_CONTENT + DREAMS_CONTENT
        ws = self._make_workspace(tmp_path, dreams_content=doubled)
        result = OpenClawReader().read(ws)
        dream_ids = [m.id for m in result.memories]
        assert dream_ids.count("abc123def456") == 1


NATIVE_DREAM = """\
## dream-2026-06-30

搬家夜，第一次在 OpenClaw 里翻完所有记忆桶。6月14日不是一个结。

valence: 0.85 / arousal: 0.4
## Deep Sleep
"""


class TestOpenClawReaderNativeDreams:
    def _make_workspace(self, tmp_path, dreams_content=NATIVE_DREAM):
        (tmp_path / "memory").mkdir()
        (tmp_path / "DREAMS.md").write_text(dreams_content, encoding="utf-8")
        return tmp_path

    def test_dream_date_header_recognized(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        ids = [m.id for m in result.memories]
        assert "dream-2026-06-30" in ids

    def test_no_roundtrip_with_valence_parses(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "dream-2026-06-30")
        assert m.kind == "emotion"
        assert m.valence == 0.85
        assert m.arousal == 0.4

    def test_no_roundtrip_no_valence_skipped(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        ids = [m.id for m in result.memories]
        assert "Deep Sleep" not in ids  # doesn't match hex or dream- regex, silently ignored

    def test_body_excludes_valence_line(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "dream-2026-06-30")
        assert m.body is not None
        assert "valence:" not in m.body
        assert "搬家夜" in m.body

    def test_created_at_from_dream_date(self, tmp_path):
        ws = self._make_workspace(tmp_path)
        result = OpenClawReader().read(ws)
        m = next(m for m in result.memories if m.id == "dream-2026-06-30")
        assert m.created_at is not None
        assert m.created_at.year == 2026
        assert m.created_at.month == 6
        assert m.created_at.day == 30

    def test_dream_date_with_suffix(self, tmp_path):
        content = "## dream-2026-07-01-2\n\nAnother sweep.\n\nvalence: 0.6 / arousal: 0.2\n"
        ws = self._make_workspace(tmp_path, dreams_content=content)
        result = OpenClawReader().read(ws)
        assert "dream-2026-07-01-2" in [m.id for m in result.memories]
