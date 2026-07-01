"""Tests for Canonical → Generic Markdown writer."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from memlink.generic_reader import GenericReader
from memlink.generic_writer import GenericWriter
from memlink.models import Memory


class TestGenericWriter:
    def test_write_creates_notes_dir(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="Content.")], root)
            assert (root / "notes").is_dir()

    def test_write_creates_md_files(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="Content.")], root)
            files = list((root / "notes").glob("*.md"))
            assert len(files) == 1

    def test_yaml_frontmatter_has_title(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="Content.")], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "title: Test" in text

    def test_body_in_output(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="Some body text.")], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "Some body text." in text

    def test_tags_in_frontmatter(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="X.", tags=["python", "oss"])], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "python" in text
            assert "oss" in text

    def test_category_from_domains(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="X.", domains=["dev", "docs"])], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "category: dev" in text

    def test_kind_as_type(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="X.", kind="emotion")], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "type: emotion" in text

    def test_archived_status(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="X.", status="archived")], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "status: archived" in text

    def test_active_status_omitted(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="Test", body="X.", status="active")], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "status:" not in text

    def test_datetime_in_frontmatter(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            writer.write([Memory(id="g1", name="Test", body="X.", created_at=dt)], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "2024-01-15T10:00:00" in text

    def test_roundtrip_generic(self):
        reader = GenericReader()
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write(
                [
                    Memory(
                        id="rt-1",
                        name="Roundtrip Test",
                        body="Body text.",
                        tags=["test", "roundtrip"],
                        kind="emotion",
                        domains=["testing"],
                    )
                ],
                root,
            )
            result = reader.read(root / "notes")
            assert result.stats["parsed"] == 1
            m = result.memories[0]
            assert m.name == "Roundtrip Test"
            assert m.body == "Body text."
            assert "test" in m.tags
            assert "roundtrip" in m.tags
            assert m.kind == "emotion"

    def test_empty_body_outputs_empty(self):
        writer = GenericWriter()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            writer.write([Memory(id="g1", name="No body", body=None)], root)
            text = (root / "notes" / "g1.md").read_text(encoding="utf-8")
            assert "---" in text  # frontmatter still valid

    def test_plugin_contract(self):
        from memlink.testing import test_plugin_contract

        test_plugin_contract(GenericReader(), GenericWriter())
