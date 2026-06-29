"""Tests for memlink merge command."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from memlink.cli import _parse_source, _resolve_conflict
from memlink.models import Memory
from memlink.registry import get_reader, get_writer


class TestParseSource:
    def test_posix_path(self):
        fmt, path = _parse_source("ombre:/data/memories")
        assert fmt == "ombre"
        assert path == Path("/data/memories")

    def test_windows_path(self):
        fmt, path = _parse_source("ombre:C:\\Users\\PC\\memories")
        assert fmt == "ombre"
        assert path == Path("C:\\Users\\PC\\memories")

    def test_relative_path(self):
        fmt, path = _parse_source("mem0:./data")
        assert fmt == "mem0"
        assert path == Path("./data")


class TestResolveConflict:
    def _mem(self, id_str, updated_at=None, created_at=None):
        return Memory(id=id_str, name="Test", body="X.",
                      updated_at=updated_at, created_at=created_at)

    def test_newest_keeps_later(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        # existing older, incoming newer → keep existing = False
        assert _resolve_conflict(self._mem("a", updated_at=dt1), self._mem("a", updated_at=dt2), "newest") is False

    def test_newest_keeps_existing_when_older(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        # existing newer, incoming older → keep existing = True
        assert _resolve_conflict(self._mem("a", updated_at=dt2), self._mem("a", updated_at=dt1), "newest") is True

    def test_first_always_keeps_existing(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert _resolve_conflict(self._mem("a", updated_at=dt1), self._mem("a", updated_at=dt2), "first") is True

    def test_last_always_replaces(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        assert _resolve_conflict(self._mem("a", updated_at=dt1), self._mem("a", updated_at=dt2), "last") is False

    def test_falls_back_to_created_at(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        existing = self._mem("a", updated_at=None, created_at=dt1)
        incoming = self._mem("a", updated_at=None, created_at=dt2)
        assert _resolve_conflict(existing, incoming, "newest") is False

    def test_oldest_keeps_earlier(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        # existing newer, incoming older → oldest keeps incoming
        assert _resolve_conflict(self._mem("a", updated_at=dt2), self._mem("a", updated_at=dt1), "oldest") is False

    def test_oldest_keeps_existing_when_earlier(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        # existing older, incoming newer → oldest keeps existing
        assert _resolve_conflict(self._mem("a", updated_at=dt1), self._mem("a", updated_at=dt2), "oldest") is True

    def test_oldest_undated_incoming_never_replaces(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        # existing has a date, incoming has no date → undated incoming never wins
        assert _resolve_conflict(self._mem("a", updated_at=dt1), self._mem("a"), "oldest") is True

    def test_newest_undated_existing_replaced_by_dated(self):
        dt2 = datetime(2024, 6, 1, tzinfo=timezone.utc)
        # existing has no date, incoming has a date → newest replaces undated existing
        assert _resolve_conflict(self._mem("a"), self._mem("a", updated_at=dt2), "newest") is False


class TestMergeFlow:
    def test_merge_two_sources(self):
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            root1, root2 = Path(td1), Path(td2)

            # Source 1: Ombre with 2 memories
            writer1 = get_writer("ombre")
            writer1.write([
                Memory(id="m1", name="First", body="A.", kind="dynamic"),
                Memory(id="m2", name="Second", body="B.", kind="dynamic"),
            ], root1)

            # Source 2: Mem0 with 1 memory (non-overlapping)
            writer2 = get_writer("mem0")
            writer2.write([Memory(id="m3", name="Third", body="C.")], root2)

            # Read both and merge manually
            r1 = get_reader("ombre")
            r2 = get_reader("mem0")
            mems = r1.read(root1).memories + r2.read(root2).memories

            merged: dict[str, Memory] = {}
            for m in mems:
                if m.id not in merged:
                    merged[m.id] = m
            assert len(merged) == 3
            assert set(merged) == {"m1", "m2", "m3"}

    def test_merge_conflict_newest(self):
        dt_old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt_new = datetime(2024, 6, 1, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            root1, root2 = Path(td1), Path(td2)

            # Source 1: older version of m1
            writer1 = get_writer("mem0")
            writer1.write([Memory(id="m1", name="Old", body="Old body.", updated_at=dt_old)], root1)

            # Source 2: newer version of m1
            writer2 = get_writer("mem0")
            writer2.write([Memory(id="m1", name="New", body="New body.", updated_at=dt_new)], root2)

            r1 = get_reader("mem0")
            r2 = get_reader("mem0")
            mems = r1.read(root1).memories + r2.read(root2).memories

            merged: dict[str, Memory] = {}
            for m in mems:
                if m.id in merged:
                    if not _resolve_conflict(merged[m.id], m, "newest"):
                        merged[m.id] = m
                else:
                    merged[m.id] = m

            assert len(merged) == 1
            assert merged["m1"].body == "New body."

    def test_merge_output_count(self):
        with tempfile.TemporaryDirectory() as td1, \
             tempfile.TemporaryDirectory() as td2, \
             tempfile.TemporaryDirectory() as td_out:
            root1, root2, out = Path(td1), Path(td2), Path(td_out)

            w1 = get_writer("mem0")
            w1.write([Memory(id="a", name="A", body="A.")], root1)
            w2 = get_writer("mem0")
            w2.write([Memory(id="b", name="B", body="B.")], root2)

            mems = get_reader("mem0").read(root1).memories + get_reader("mem0").read(root2).memories
            merged = {}
            for m in mems:
                merged.setdefault(m.id, m)

            get_writer("mem0").write(list(merged.values()), out)
            result = get_reader("mem0").read(out)
            assert len(result.memories) == 2

    def test_merge_dry_run_logic(self):
        # dry-run should produce same merge result without side effects
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            root1, root2 = Path(td1), Path(td2)

            get_writer("mem0").write([Memory(id="x", name="X", body="X.")], root1)
            get_writer("mem0").write([Memory(id="y", name="Y", body="Y.")], root2)

            mems = get_reader("mem0").read(root1).memories + get_reader("mem0").read(root2).memories
            merged = {}
            for m in mems:
                merged.setdefault(m.id, m)

            # Assert merge produces correct unique set without writing
            assert len(merged) == 2
            assert set(merged) == {"x", "y"}
