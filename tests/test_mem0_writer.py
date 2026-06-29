"""Tests for Canonical → Mem0 writer."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from memlink.mem0_reader import Mem0Reader
from memlink.mem0_writer import Mem0Writer
from memlink.models import Memory


class TestMem0Writer:
    def test_write_creates_memories_json(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Test", body="Content.")], root)
            assert (root / "memories.json").exists()

    def test_write_results_format(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Test", body="Content.")], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            assert "results" in data
            assert isinstance(data["results"], list)
            assert len(data["results"]) == 1

    def test_field_mapping_memory(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Test", body="I prefer dark mode.")], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert data["results"][0]["memory"] == "I prefer dark mode."

    def test_field_mapping_categories(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Test", body="X.", tags=["b", "a"])], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert data["results"][0]["categories"] == ["a", "b"]

    def test_field_mapping_user_id(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mem = Memory(
                id="t1",
                name="Test",
                body="X.",
                metadata={"memlink": {"original": {"user_id": "alice"}}},
            )
            writer.write([mem], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert data["results"][0]["user_id"] == "alice"

    def test_field_mapping_user_id_default(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Test", body="X.")], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert data["results"][0]["user_id"] == "default"

    def test_roundtrip_mem0(self):
        reader = Mem0Reader()
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write(
                [Memory(id="abc-123", name="Test", body="User prefers dark mode", tags=["ui"])],
                root,
            )
            result = reader.read(root)
            assert len(result.memories) == 1
            m = result.memories[0]
            assert m.id == "abc-123"
            assert m.body == "User prefers dark mode"
            assert m.tags == ["ui"]

    def test_metadata_roundtrip(self):
        reader = Mem0Reader()
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_meta = {"key": "value", "nested": {"a": 1}}
            mem = Memory(
                id="meta-001",
                name="Test",
                body="With metadata.",
                extensions={"mem0_metadata": original_meta},
            )
            writer.write([mem], root)
            result = reader.read(root)
            m = result.memories[0]
            assert m.extensions.get("mem0_metadata") == original_meta

    def test_empty_body_uses_name(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="t1", name="Name only", body=None)], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert data["results"][0]["memory"] == "Name only"

    def test_no_body_no_name_skipped(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            warnings = writer.write([Memory(id="empty-1", name=None, body=None)], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert len(data["results"]) == 0
            assert len(warnings) >= 1
            assert any("empty-1" in w for w in warnings)

    def test_datetime_iso_format(self):
        writer = Mem0Writer()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            writer.write([Memory(id="dt-1", name="Test", body="X.", created_at=dt)], root)
            data = json.loads((root / "memories.json").read_text(encoding="utf-8"))
            assert "2024-01-15T10:00:00" in data["results"][0]["created_at"]

    def test_plugin_contract(self):
        from memlink.testing import test_plugin_contract

        test_plugin_contract(Mem0Reader(), Mem0Writer())
