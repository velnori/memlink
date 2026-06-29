"""Tests for Claude export → Canonical reader."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from memlink.claude_export_reader import ClaudeExportReader

FIXTURES = Path(__file__).parent / "fixtures"


class TestClaudeExportReader:
    def test_read_conversations(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        assert result.stats["parsed"] == 2
        assert result.stats["skipped"] == 1  # claude-conv-003: empty

    def test_field_mapping_id(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        assert result.memories[0].id == "claude-conv-001"

    def test_field_mapping_name(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        assert result.memories[0].name == "Python async discussion"

    def test_name_truncation(self):
        reader = ClaudeExportReader()
        d = Path(tempfile.mkdtemp())
        long_name = "A" * 80
        (d / "conversations.json").write_text(
            json.dumps(
                [
                    {
                        "uuid": "t1",
                        "name": long_name,
                        "chat_messages": [{"uuid": "m1", "text": "Hello", "sender": "human"}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = reader.read(d)
        assert len(result.memories[0].name or "") <= 60

    def test_field_mapping_body(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        body = result.memories[0].body or ""
        assert "human:" in body
        assert "assistant:" in body
        assert "asyncio" in body

    def test_chinese_content(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        body = result.memories[1].body or ""
        assert "反转字符串" in body

    def test_datetime_parsed(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        assert isinstance(result.memories[0].created_at, datetime)

    def test_empty_messages_skip(self):
        reader = ClaudeExportReader()
        result = reader.read(FIXTURES / "claude_export_samples")
        assert result.stats["skipped"] >= 1
        assert any("claude-conv-003" in w for w in result.warnings)

    def test_broken_json_no_crash(self):
        reader = ClaudeExportReader()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "conversations.json").write_text("{not valid", encoding="utf-8")
            result = reader.read(d)
            assert result.stats["parsed"] == 0
            assert len(result.warnings) >= 1

    def test_empty_json_no_crash(self):
        reader = ClaudeExportReader()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "conversations.json").write_text("[]", encoding="utf-8")
            result = reader.read(d)
            assert result.stats["parsed"] == 0

    def test_plugin_contract(self):
        from memlink.testing import (
            test_reader_deterministic,
            test_reader_invalid_input,
            test_reader_minimal,
            test_reader_unknown_fields,
        )

        reader = ClaudeExportReader()
        test_reader_minimal(reader)
        test_reader_unknown_fields(reader)
        test_reader_invalid_input(reader)
        test_reader_deterministic(reader)
