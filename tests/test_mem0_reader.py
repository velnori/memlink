"""Tests for Mem0 → Canonical reader."""

from datetime import datetime
from pathlib import Path

from memlink.mem0_reader import Mem0Reader

FIXTURES = Path(__file__).parent / "fixtures"


class TestMem0Reader:
    def test_read_results_format(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        assert result.stats["parsed"] == 5
        assert len(result.warnings) == 0

    def test_read_array_format(self):
        reader = Mem0Reader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "data.json").write_text(
            '[{"id": "a1", "memory": "First", "user_id": "u1"}, {"id": "a2", "memory": "Second", "user_id": "u2"}]',
            encoding="utf-8",
        )
        result = reader.read(d)
        assert result.stats["parsed"] == 2

    def test_field_mapping_id(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        mem = result.memories[0]
        assert mem.id == "550e8400-e29b-41d4-a716-446655440001"

    def test_field_mapping_body(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        mem = result.memories[0]
        assert "dark mode" in (mem.body or "")

    def test_field_mapping_tags(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        mem = result.memories[0]
        assert "preferences" in mem.tags
        assert "ui" in mem.tags

    def test_name_truncation(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        # The 3rd record has a long Chinese text
        mem = result.memories[2]  # id=003 has long memory
        assert mem.name is not None
        assert len(mem.name or "") <= 60

    def test_datetime_parsed(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        mem = result.memories[0]
        assert isinstance(mem.created_at, datetime)

    def test_metadata_preserved(self):
        reader = Mem0Reader()
        result = reader.read(FIXTURES / "mem0_samples")
        mem = result.memories[0]
        assert "mem0_metadata" in mem.extensions
        assert mem.extensions["mem0_metadata"]["source"] == "chat"

    def test_missing_id_skip(self):
        reader = Mem0Reader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "memories.json").write_text(
            '{"results": [{"memory": "no id here", "categories": ["test"]}]}',
            encoding="utf-8",
        )
        result = reader.read(d)
        # No id → skipped
        assert result.stats["skipped"] >= 1
        assert any("id" in w.lower() for w in result.warnings)

    def test_missing_memory_skip(self):
        reader = Mem0Reader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "memories.json").write_text(
            '{"results": [{"id": "no-mem-001", "categories": ["incomplete"]}]}',
            encoding="utf-8",
        )
        result = reader.read(d)
        assert result.stats["skipped"] >= 1
        assert any("memory" in w.lower() for w in result.warnings)

    def test_broken_json_no_crash(self):
        reader = Mem0Reader()
        # broken/invalid.json is not parseable
        # But partial_invalid.json is parseable, so it gets picked first
        # (it's alphabetically first with "partial" < "invalid"... wait, "empty" < "invalid" < "partial")
        # Create a dir with only invalid.json
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "memories.json").write_text("{not valid json", encoding="utf-8")
        result = reader.read(d)
        assert result.stats["parsed"] == 0
        assert len(result.warnings) >= 1

    def test_empty_json_no_crash(self):
        reader = Mem0Reader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "memories.json").write_text("{}", encoding="utf-8")
        result = reader.read(d)
        assert result.stats["parsed"] == 0
        assert len(result.warnings) == 0

    def test_plugin_contract(self):

        reader = Mem0Reader()
        # Minimal test: create a single valid record
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "memories.json").write_text(
            '{"results": [{"id": "test-001", "memory": "Test content", "user_id": "test"}]}',
            encoding="utf-8",
        )
        result = reader.read(d)
        assert len(result.memories) == 1
        assert result.memories[0].id == "test-001"
