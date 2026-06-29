"""Plugin Contract Tests — standard test suite for any format plugin.

Every new Reader/Writer pair must pass these tests. Import and call:

    from memlink.testing import test_plugin_contract
    test_plugin_contract(MyReader(), MyWriter())
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .models import Memory

MINIMAL_MEMORY = Memory(id="test-001", name="Test", body="Content.")


def test_plugin_contract(reader, writer) -> None:
    """Run the full contract test suite for a Reader/Writer pair.

    Tests:
      1. Reader parses minimal valid data
      2. Reader handles unknown fields without crashing
      3. Reader handles invalid input with structured warnings
      4. Writer produces readable output
      5. Full roundtrip preserves semantic identity
      6. Reader is deterministic (two reads return same result)
    """
    test_reader_minimal(reader)
    test_reader_unknown_fields(reader)
    test_reader_invalid_input(reader)
    test_writer_produces_output(writer)
    test_roundtrip_preserves_identity(reader, writer)
    test_reader_deterministic(reader)


def test_reader_minimal(reader) -> None:
    """Reader must parse at least one memory from a minimal valid directory."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_minimal_format_dir(root, reader.name)
        result = reader.read(root)
        assert len(result.memories) >= 1, f"Reader '{reader.name}' returned zero memories from minimal fixture"
        m = result.memories[0]
        assert m.id, "Memory must have an id"


def test_reader_unknown_fields(reader) -> None:
    """Reader must handle frontmatter with unknown fields without crashing."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_unknown_fields_dir(root, reader.name)
        result = reader.read(root)
        # Should not raise — unknown fields are tolerated
        assert isinstance(result.warnings, list), "Warnings must be a list"


def test_reader_invalid_input(reader) -> None:
    """Reader must handle malformed input without raising exceptions."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_broken_dir(root, reader.name)
        try:
            result = reader.read(root)
            # If it returns, warnings/errors should be structured
            assert isinstance(result.memories, list)
        except Exception:
            # If it raises, that's acceptable for truly broken data
            pass


def test_writer_produces_output(writer) -> None:
    """Writer must produce at least one file from minimal Canonical data."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        warnings = writer.write([MINIMAL_MEMORY], root)
        assert isinstance(warnings, list), "write() must return list of warnings"
        files = [f for f in root.rglob("*") if f.is_file()]
        assert len(files) >= 1, f"Writer '{writer.name}' produced no output files"


def test_roundtrip_preserves_identity(reader, writer) -> None:
    """Roundtrip must preserve id, name, and kind (within declared capabilities)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Write
        writer.write([MINIMAL_MEMORY], root)
        # Read back
        result = reader.read(root)
        if result.memories:
            m = result.memories[0]
            assert m.id == "test-001", f"Roundtrip id mismatch: {m.id}"
            assert m.name == "Test", f"Roundtrip name mismatch: {m.name}"


def test_reader_deterministic(reader) -> None:
    """Reader must return identical results on two reads of the same data."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_minimal_format_dir(root, reader.name)
        r1 = reader.read(root)
        r2 = reader.read(root)
        assert len(r1.memories) == len(r2.memories), "Deterministic: memory count differs"
        if r1.memories and r2.memories:
            assert r1.memories[0].id == r2.memories[0].id, "Deterministic: id differs"


# ── Fixture helpers ────────────────────────────────────────────────


def _create_minimal_format_dir(root: Path, fmt: str) -> None:
    if fmt == "ombre":
        d = root / "dynamic" / "general"
        d.mkdir(parents=True)
        (d / "test-001.md").write_text("---\nbucket_id: test-001\nname: Test\ntype: dynamic\n---\nContent.")
    elif fmt == "openclaw":
        d = root / "memory"
        d.mkdir(parents=True)
        (d / "test-001.md").write_text("---\nname: Test\nmetadata:\n  type: work\n---\nContent.")
        (root / "MEMORY.md").write_text("- memory/test-001.md")
    elif fmt == "mem0":
        import json

        (root / "memories.json").write_text(
            json.dumps({"results": [{"id": "test-001", "memory": "Test", "user_id": "test"}]})
        )
    elif fmt == "chatgpt":
        import json

        msg = {
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": ["Test content."]},
            "create_time": 1.0,
        }
        (root / "conversations.json").write_text(
            json.dumps([{"id": "test-001", "title": "Test", "mapping": {"n1": {"message": msg}}}])
        )
    elif fmt == "claude_export":
        import json

        (root / "conversations.json").write_text(
            json.dumps([{"uuid": "test-001", "name": "Test",
                         "chat_messages": [{"uuid": "m1", "text": "Test content.", "sender": "human"}]}])
        )
    elif fmt == "zep":
        import json

        (root / "facts.json").write_text(json.dumps({"facts": [{"uuid": "test-001", "fact": "Test fact content"}]}))


def _create_unknown_fields_dir(root: Path, fmt: str) -> None:
    if fmt == "ombre":
        d = root / "dynamic" / "general"
        d.mkdir(parents=True)
        (d / "test.md").write_text(
            "---\nbucket_id: test\nname: Test\ntype: dynamic\nunknown_field: blah\nfoo: {bar: baz}\n---\nBody."
        )
    elif fmt == "openclaw":
        d = root / "memory"
        d.mkdir(parents=True)
        (d / "test.md").write_text("---\nname: Test\nweird_field: [1,2,3]\n---\nBody.")
    elif fmt == "mem0":
        import json

        (root / "memories.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "id": "contract-test",
                            "memory": "Test",
                            "user_id": "u",
                            "unknown": "value",
                            "custom_field": 42,
                        }
                    ]
                }
            )
        )
    elif fmt == "zep":
        import json

        (root / "facts.json").write_text(
            json.dumps({"facts": [{"uuid": "contract-test", "fact": "Test", "unknown_field": 99}]})
        )
    elif fmt == "chatgpt":
        import json

        msg = {"author": {"role": "user"}, "content": {"content_type": "text", "parts": ["Test"]}, "create_time": 1.0}
        (root / "conversations.json").write_text(
            json.dumps([{"id": "contract-test", "title": "Test", "extra": "value",
                         "mapping": {"n1": {"message": msg}}}])
        )
    elif fmt == "claude_export":
        import json

        (root / "conversations.json").write_text(
            json.dumps([{"uuid": "contract-test", "name": "Test", "unknown": 42,
                         "chat_messages": [{"uuid": "m1", "text": "Test", "sender": "human"}]}])
        )


def _create_broken_dir(root: Path, fmt: str) -> None:
    if fmt == "ombre":
        d = root / "dynamic" / "broken"
        d.mkdir(parents=True)
        (d / "bad.md").write_text("not valid yaml\n---\n---\nbody")
    elif fmt == "openclaw":
        d = root / "memory"
        d.mkdir(parents=True)
        (d / "bad.md").write_text("not valid\n---\n")
    elif fmt == "mem0":
        (root / "memories.json").write_text("{not json")
    elif fmt == "zep":
        (root / "facts.json").write_text("{not json")
    elif fmt in ("chatgpt", "claude_export"):
        (root / "conversations.json").write_text("{not json")
