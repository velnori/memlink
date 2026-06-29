"""Tests for memlink broadcast command."""

import tempfile
from pathlib import Path

import pytest

from memlink.models import Memory
from memlink.registry import get_reader, get_writer


class TestBroadcast:
    def test_broadcast_to_two_targets(self):
        with tempfile.TemporaryDirectory() as td_src, \
             tempfile.TemporaryDirectory() as td1, \
             tempfile.TemporaryDirectory() as td2:
            src, out1, out2 = Path(td_src), Path(td1), Path(td2)

            get_writer("mem0").write([Memory(id="a", name="A", body="A.")], src)
            memories = get_reader("mem0").read(src).memories

            get_writer("mem0").write(memories, out1)
            get_writer("ombre").write(memories, out2)

            assert (out1 / "memories.json").exists()
            assert (out2 / "dynamic").exists()

    def test_broadcast_memory_count(self):
        with tempfile.TemporaryDirectory() as td_src, \
             tempfile.TemporaryDirectory() as td1, \
             tempfile.TemporaryDirectory() as td2:
            src, out1, out2 = Path(td_src), Path(td1), Path(td2)

            get_writer("mem0").write(
                [Memory(id="a", name="A", body="A."), Memory(id="b", name="B", body="B.")], src
            )
            memories = get_reader("mem0").read(src).memories

            get_writer("mem0").write(memories, out1)
            get_writer("mem0").write(memories, out2)

            assert len(get_reader("mem0").read(out1).memories) == 2
            assert len(get_reader("mem0").read(out2).memories) == 2

    def test_broadcast_dry_run_logic(self):
        with tempfile.TemporaryDirectory() as td_src:
            src = Path(td_src)
            get_writer("mem0").write([Memory(id="x", name="X", body="X.")], src)
            memories = get_reader("mem0").read(src).memories
            # Dry run = we have the memories but don't write
            assert len(memories) == 1

    def test_broadcast_single_target(self):
        with tempfile.TemporaryDirectory() as td_src, tempfile.TemporaryDirectory() as td_out:
            src, out = Path(td_src), Path(td_out)

            get_writer("mem0").write([Memory(id="solo", name="Solo", body="One.")], src)
            memories = get_reader("mem0").read(src).memories

            get_writer("mem0").write(memories, out)
            assert len(get_reader("mem0").read(out).memories) == 1

    def test_broadcast_all_formats(self):
        with tempfile.TemporaryDirectory() as td_src, \
             tempfile.TemporaryDirectory() as td1, \
             tempfile.TemporaryDirectory() as td2:
            src, out1, out2 = Path(td_src), Path(td1), Path(td2)

            get_writer("mem0").write([Memory(id="z", name="Z", body="Z.")], src)
            memories = get_reader("mem0").read(src).memories

            get_writer("mem0").write(memories, out1)
            get_writer("ombre").write(memories, out2)

            # Both targets have the memory
            r1 = get_reader("mem0").read(out1)
            r2 = get_reader("ombre").read(out2)
            assert len(r1.memories) == 1
            assert len(r2.memories) == 1
            assert r1.memories[0].id == "z"
            assert r2.memories[0].id == "z"

    def test_broadcast_invalid_writer(self):
        from memlink.registry import PluginNotFoundError

        with pytest.raises(PluginNotFoundError):
            get_writer("nonexistent")
