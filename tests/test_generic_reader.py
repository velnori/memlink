"""Tests for Generic Markdown Reader."""


import pytest

from memlink.generic_reader import GenericReader


@pytest.fixture
def obsidian_dir(tmp_path):
    d = tmp_path / "vault" / "notes"
    d.mkdir(parents=True)

    (d / "daily.md").write_text("""---
title: daily note
date: 2024-06-28
tags: [diary, work, archived]
---
## Tasks
- [ ] do stuff
""", encoding="utf-8")

    (d / "project.md").write_text("""---
title: memlink
tags: [oss, python]
category: dev
created: 2024-06-15T10:00:00+08:00
---
# memlink
bridge for AI memories.
""", encoding="utf-8")

    (d / "plain.md").write_text("No frontmatter here\nJust text.", encoding="utf-8")
    return tmp_path / "vault"


class TestGenericReader:
    def test_reads_obsidian_files(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        assert result.stats["parsed"] == 3

    def test_tags_parsed(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "daily note")
        assert "diary" in mem.tags
        assert "work" in mem.tags

    def test_category_to_domain(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "memlink")
        assert "dev" in mem.domains

    def test_timestamp_mapped(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "memlink")
        assert mem.created_at is not None

    def test_plain_file_no_frontmatter(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "plain")
        assert mem.kind == "dynamic"
        assert mem.body == "No frontmatter here\nJust text."

    def test_archived_from_tags(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "daily note")
        assert mem.status == "archived"

    def test_extensions_sanitized(self, obsidian_dir):
        reader = GenericReader()
        result = reader.read(obsidian_dir)
        mem = next(m for m in result.memories if m.name == "daily note")
        assert isinstance(mem.extensions, dict)

    def test_empty_directory(self, tmp_path):
        reader = GenericReader()
        result = reader.read(tmp_path)
        assert result.stats["parsed"] == 0
        assert result.warnings == []
