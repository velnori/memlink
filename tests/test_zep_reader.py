"""Tests for Zep → Canonical reader."""

from datetime import datetime
from pathlib import Path

from memlink.zep_reader import ZepReader

FIXTURES = Path(__file__).parent / "fixtures"


class TestZepReader:
    def test_read_facts_format(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        assert result.stats["parsed"] == 5
        assert len(result.warnings) == 0

    def test_read_array_format(self):
        reader = ZepReader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "data.json").write_text(
            '[{"uuid":"a1","fact":"One","created_at":"2024-01-01T00:00:00Z"},'
            '{"uuid":"a2","fact":"Two","created_at":"2024-01-01T00:00:00Z"}]',
            encoding="utf-8",
        )
        result = reader.read(d)
        assert result.stats["parsed"] == 2

    def test_read_session_format(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        # session_format.json picked up by reader (alphabetically after facts.json)
        # Test session format separately
        import tempfile

        d = Path(tempfile.mkdtemp())
        text = (
            '{"messages":[{"uuid":"m1","content":"Hello"}],'
            '"summary":{"uuid":"sum-1","content":"Greeting exchange",'
            '"created_at":"2024-01-01T00:00:00Z"}}'
        )
        (d / "facts.json").write_text(text, encoding="utf-8")
        result = reader.read(d)
        assert result.stats["parsed"] == 1
        assert "Greeting" in (result.memories[0].body or "")

    def test_field_mapping_id(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        assert result.memories[0].id == "zep-001"

    def test_field_mapping_body(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        assert "Python" in (result.memories[0].body or "")

    def test_name_truncation(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        mem = result.memories[2]
        assert mem.name is not None
        assert len(mem.name or "") <= 60

    def test_datetime_parsed(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        assert isinstance(result.memories[0].created_at, datetime)

    def test_metadata_preserved(self):
        reader = ZepReader()
        result = reader.read(FIXTURES / "zep_samples")
        mem = result.memories[1]
        assert "zep_metadata" in mem.extensions

    def test_missing_uuid_skip(self):
        reader = ZepReader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "facts.json").write_text('{"facts": [{"fact": "No uuid here"}]}', encoding="utf-8")
        result = reader.read(d)
        assert result.stats["skipped"] >= 1
        assert any("uuid" in w.lower() for w in result.warnings)

    def test_missing_fact_skip(self):
        reader = ZepReader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "facts.json").write_text('{"facts": [{"uuid": "no-fact-001"}]}', encoding="utf-8")
        result = reader.read(d)
        assert result.stats["skipped"] >= 1
        assert any("fact" in w.lower() for w in result.warnings)

    def test_broken_json_no_crash(self):
        reader = ZepReader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "facts.json").write_text("{not valid json", encoding="utf-8")
        result = reader.read(d)
        assert result.stats["parsed"] == 0
        assert len(result.warnings) >= 1

    def test_empty_json_no_crash(self):
        reader = ZepReader()
        import tempfile

        d = Path(tempfile.mkdtemp())
        (d / "facts.json").write_text("{}", encoding="utf-8")
        result = reader.read(d)
        assert result.stats["parsed"] == 0
        assert len(result.warnings) >= 1

    def test_plugin_contract(self):
        from memlink.testing import (
            test_reader_deterministic,
            test_reader_invalid_input,
            test_reader_minimal,
            test_reader_unknown_fields,
        )

        reader = ZepReader()
        test_reader_minimal(reader)
        test_reader_unknown_fields(reader)
        test_reader_invalid_input(reader)
        test_reader_deterministic(reader)
