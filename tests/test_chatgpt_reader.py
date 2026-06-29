"""Tests for ChatGPT export → Canonical reader."""

import tempfile
from datetime import datetime
from pathlib import Path

from memlink.chatgpt_reader import ChatGPTReader

FIXTURES = Path(__file__).parent / "fixtures"


class TestChatGPTReader:
    def test_read_conversations(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        assert result.stats["parsed"] == 2
        assert result.stats["skipped"] == 1  # conv-003: system-only
        assert len(result.warnings) == 1

    def test_field_mapping_id(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        assert result.memories[0].id == "conv-001"

    def test_field_mapping_name(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        assert result.memories[0].name == "Python async patterns"

    def test_name_truncation(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        mem = result.memories[1]
        assert mem.name is not None
        assert len(mem.name or "") <= 60

    def test_field_mapping_body(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        body = result.memories[0].body or ""
        assert "user:" in body
        assert "assistant:" in body
        assert "asyncio" in body

    def test_datetime_parsed(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        assert isinstance(result.memories[0].created_at, datetime)

    def test_empty_messages_skip(self):
        reader = ChatGPTReader()
        result = reader.read(FIXTURES / "chatgpt_samples")
        assert result.stats["skipped"] >= 1
        assert any("conv-003" in w for w in result.warnings)

    def test_broken_json_no_crash(self):
        reader = ChatGPTReader()
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "conversations.json").write_text("{not valid", encoding="utf-8")
            result = reader.read(d)
            assert result.stats["parsed"] == 0
            assert len(result.warnings) >= 1

    def test_empty_json_no_crash(self):
        reader = ChatGPTReader()
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

        reader = ChatGPTReader()
        test_reader_minimal(reader)
        test_reader_unknown_fields(reader)
        test_reader_invalid_input(reader)
        test_reader_deterministic(reader)
