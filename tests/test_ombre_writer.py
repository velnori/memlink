"""Tests for Canonical → Ombre writer."""

import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from memlink.models import Memory
from memlink.ombre_writer import OmbreWriter


class TestOmbreWriter:
    def test_write_basic(self, tmp_path):
        mem = Memory(id="test-123", name="Test Memory", body="Content.", kind="dynamic",
                     domains=["user"], tags=["test"], importance_score=8,
                     created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        file_path = tmp_path / "dynamic" / "user" / "test-123.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "bucket_id: test-123" in content
        assert "type: dynamic" in content
        assert "importance: 8" in content

    def test_write_emotion_to_feel(self, tmp_path):
        mem = Memory(id="excited-001", name="Excited", body="Feeling great!", kind="emotion",
                     domains=["personal"], valence=0.8, arousal=0.7)
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        file_path = tmp_path / "feel" / "personal" / "excited-001.md"
        assert file_path.exists()
        content = file_path.read_text()
        assert "type: feel" in content

    def test_write_permanent_kind(self, tmp_path):
        mem = Memory(id="fact-001", name="Important Fact", body="Never forget.", kind="permanent",
                     domains=["knowledge"])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        assert (tmp_path / "permanent" / "knowledge" / "fact-001.md").exists()

    def test_restore_original_id(self, tmp_path):
        mem = Memory(id="renamed-id", name="Test", body="Content", kind="dynamic", domains=["user"],
                     metadata={"memlink": {"original": {"id": "original-bucket-id"}}})
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        file_path = tmp_path / "dynamic" / "user" / "original-bucket-id.md"
        assert file_path.exists()
        assert "bucket_id: original-bucket-id" in file_path.read_text()

    def test_restore_original_importance(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     importance_score=0.8,
                     metadata={"memlink": {"original": {"importance": 8}}})
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "importance: 8" in content

    def test_importance_label_to_score(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     importance_label="high")
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "importance: 8" in content

    def test_empty_domains_fallback(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=[])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        assert (tmp_path / "dynamic" / "general" / "test.md").exists()

    def test_only_unknown_domain_fallback(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["_unknown"])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        assert (tmp_path / "dynamic" / "general" / "test.md").exists()

    def test_unknown_kind_fallback(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="unknown_kind", domains=["user"])
        writer = OmbreWriter()
        warnings = writer.write([mem], tmp_path)
        assert any("Unknown kind" in w for w in warnings)
        assert (tmp_path / "dynamic" / "user" / "test.md").exists()

    def test_archived_status_warning(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", status="archived",
                     domains=["user"])
        writer = OmbreWriter()
        warnings = writer.write([mem], tmp_path)
        assert any("archived" in w.lower() for w in warnings)

    def test_restore_original_timezone(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     created_at=datetime(2024, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
                     metadata={"memlink": {"original": {"created_tz": "2024-01-01T10:00:00+08:00"}}})
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "2024-01-01T10:00:00+08:00" in content

    def test_multi_domain_list(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic",
                     domains=["user", "work", "project"])
        writer = OmbreWriter()
        warnings = writer.write([mem], tmp_path)
        assert (tmp_path / "dynamic" / "user" / "test.md").exists()
        assert any("domains" in w.lower() for w in warnings)

    def test_tags_comma_separated(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     tags=["tag1", "tag2", "tag3"])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "tags: tag1, tag2, tag3" in content

    def test_importance_nan_fallback(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     importance_score=float("nan"))
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "importance: 5" in content

    def test_importance_negative_clamp(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     importance_score=-3.5)
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert "importance: 1" in content

    def test_chinese_domain_and_id(self, tmp_path):
        mem = Memory(id="项目-启动", name="Project Kickoff", body="内容", kind="dynamic",
                     domains=["工作"], tags=["重要"])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        file_path = tmp_path / "dynamic" / "工作" / "项目-启动.md"
        assert file_path.exists()

    def test_yaml_special_chars_quoted(self, tmp_path):
        mem = Memory(id="test", name="Project: Alpha", body="Content", kind="dynamic", domains=["user"])
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        assert 'name: "Project: Alpha"' in content

    def test_batch_write(self, tmp_path):
        memories = [Memory(id=f"test-{i}", name=f"Test {i}", body=f"Content {i}", kind="dynamic",
                           domains=["user"]) for i in range(10)]
        writer = OmbreWriter()
        writer.write(memories, tmp_path)
        assert len(list((tmp_path / "dynamic" / "user").glob("*.md"))) == 10

    def test_frontmatter_field_order(self, tmp_path):
        mem = Memory(id="test", name="Test", body="Content", kind="dynamic", domains=["user"],
                     importance_score=8, valence=0.5, pinned=True)
        writer = OmbreWriter()
        writer.write([mem], tmp_path)
        content = (tmp_path / "dynamic" / "user" / "test.md").read_text()
        # Check expected field order
        lines = content.split("\n")
        assert lines[1].startswith("bucket_id")
        assert lines[2].startswith("name")
        assert lines[3].startswith("type")
        assert lines[4].startswith("domain")
        assert lines[5].startswith("tags")
        assert lines[6].startswith("importance")
