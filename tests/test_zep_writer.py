"""Tests for Canonical → Zep writer."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from memlink.models import Memory
from memlink.zep_reader import ZepReader
from memlink.zep_writer import ZepWriter


class TestZepWriter:
    def test_write_creates_facts_json(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="z1", name="Test", body="Content.")], root)
            assert (root / "facts.json").exists()

    def test_write_facts_format(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="z1", name="Test", body="Content.")], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            assert "facts" in data
            assert isinstance(data["facts"], list)
            assert len(data["facts"]) == 1

    def test_field_mapping_fact(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="z1", name="Test", body="Prefers Python.")], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert data["facts"][0]["fact"] == "Prefers Python."

    def test_field_mapping_uuid(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="uuid-001", name="Test", body="X.")], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert data["facts"][0]["uuid"] == "uuid-001"

    def test_roundtrip_zep(self):
        reader = ZepReader()
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="r1", name="Round", body="Trip test.")], root)
            result = reader.read(root)
            assert len(result.memories) == 1
            m = result.memories[0]
            assert m.id == "r1"
            assert m.body == "Trip test."

    def test_metadata_roundtrip(self):
        reader = ZepReader()
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_meta = {"source": "zep_cloud", "version": 2}
            mem = Memory(
                id="meta-1",
                name="Test",
                body="With metadata.",
                extensions={"zep_metadata": original_meta},
            )
            writer.write([mem], root)
            result = reader.read(root)
            m = result.memories[0]
            assert m.extensions.get("zep_metadata") == original_meta

    def test_session_id_roundtrip(self):
        reader = ZepReader()
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mem = Memory(
                id="sid-1",
                name="Test",
                body="Session test.",
                extensions={"zep_session_id": "sess-abc"},
            )
            writer.write([mem], root)
            result = reader.read(root)
            m = result.memories[0]
            assert m.extensions.get("zep_session_id") == "sess-abc"

    def test_empty_body_uses_name(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="n1", name="Name is fact", body=None)], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert data["facts"][0]["fact"] == "Name is fact"

    def test_no_body_no_name_skipped(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            warnings = writer.write([Memory(id="empty-1", name=None, body=None)], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert len(data["facts"]) == 0
            assert len(warnings) >= 1
            assert any("empty-1" in w for w in warnings)

    def test_datetime_iso_format(self):
        writer = ZepWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            writer.write([Memory(id="dt-1", name="Test", body="X.", created_at=dt)], root)
            data = json.loads((root / "facts.json").read_text(encoding="utf-8"))
            assert "2024-01-15T10:00:00" in data["facts"][0]["created_at"]

    def test_plugin_contract(self):
        from memlink.testing import test_plugin_contract

        test_plugin_contract(ZepReader(), ZepWriter())
