"""Tests for Canonical → OpenClaw writer — both output modes."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from memlink.models import Memory, Source
from memlink.openclaw_writer import OpenClawWriter, ConcurrentModificationError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_memories():
    return [
        Memory(
            id="proj-alpha",
            name="Project Alpha Kickoff",
            summary="Initial planning session",
            body="## Decisions\n- Use TypeScript",
            kind="dynamic",
            status="active",
            tags=["meeting", "planning"],
            domains=["work", "project"],
            importance_score=0.8,
            valence=0.7,
            created_at=datetime(2024, 6, 28, 10, 0, 0, tzinfo=timezone.utc),
            source=Source(format="ombre", path="dyn/work/test.md"),
            checksum="sha256:abc",
            metadata={"memlink": {"source": "ombre"}},
        ),
        Memory(
            id="feel-sunset",
            name="夏夜日落",
            body="很美的傍晚",
            kind="emotion",
            status="active",
            valence=0.9,
            created_at=datetime(2024, 7, 15, 19, 30, 0, tzinfo=timezone.utc),
            source=Source(format="ombre", path="feel/test.md"),
        ),
        Memory(
            id="archived-mem",
            name="Archived Memory",
            body="should be skipped",
            kind="dynamic",
            status="archived",
        ),
    ]


# ── Structured mode (default for backward compat) ───────────────────

class TestStructuredMode:
    def test_writes_dynamic_to_memory_dir(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="structured")
        writer.write(sample_memories, tmp_path)
        assert (tmp_path / "memory" / "proj-alpha.md").exists()

    def test_routes_emotion_to_feels_dir(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="structured")
        writer.write(sample_memories, tmp_path)
        assert (tmp_path / "memory" / "feels" / "feel-sunset.md").exists()

    def test_skips_archived(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="structured")
        writer.write(sample_memories, tmp_path)
        assert not (tmp_path / "memory" / "archived-mem.md").exists()

    def test_creates_memory_index(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="structured")
        writer.write(sample_memories, tmp_path)
        index = tmp_path / "MEMORY.md"
        assert index.exists()
        lines = index.read_text(encoding="utf-8")
        assert "memory/proj-alpha.md" in lines

    def test_incremental_update(self, tmp_path):
        writer = OpenClawWriter(output_mode="structured")
        mem1 = [Memory(id="a", name="First", kind="dynamic")]
        writer.write(mem1, tmp_path)
        assert "memory/a.md" in (tmp_path / "MEMORY.md").read_text()
        # second write — no duplicate
        mem2 = [Memory(id="a", name="Updated", kind="dynamic", body="new")]
        writer.write(mem2, tmp_path)
        assert (tmp_path / "MEMORY.md").read_text().count("memory/a.md") == 1

    def test_preserves_memlink_metadata(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="structured")
        writer.write(sample_memories, tmp_path)
        content = (tmp_path / "memory" / "proj-alpha.md").read_text(encoding="utf-8")
        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert "memlink" in fm.get("metadata", {})


# ── Daily Notes mode (native OpenClaw) ──────────────────────────────

class TestDailyNotesMode:
    def test_writes_date_based_files(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)
        # Dynamic memory dated 2024-06-28
        assert (tmp_path / "memory" / "2024-06-28.md").exists()
        # Emotion memory dated 2024-07-15
        assert (tmp_path / "memory" / "2024-07-15.md").exists()

    def test_writes_curated_memory_md(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)
        curated = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
        assert "Curated Memory" in curated
        assert "Durable facts" in curated

    def test_writes_dreams_md_for_emotion(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)
        dreams = (tmp_path / "DREAMS.md").read_text(encoding="utf-8")
        assert "Dream Diary" in dreams
        assert "夏夜日落" in dreams

    def test_skips_archived_in_daily(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)
        # archived memory shouldn't appear anywhere
        for f in tmp_path.rglob("*.md"):
            content = f.read_text(encoding="utf-8")
            assert "Archived Memory" not in content

    def test_embeds_roundtrip_comment(self, tmp_path, sample_memories):
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)
        day_file = tmp_path / "memory" / "2024-06-28.md"
        content = day_file.read_text(encoding="utf-8")
        # Roundtrip data embedded as HTML comment
        assert "<!-- memlink-roundtrip" in content

    def test_no_dreams_md_without_emotion(self, tmp_path):
        writer = OpenClawWriter(output_mode="daily-notes")
        mem = [Memory(id="a", name="Just a note", kind="dynamic", body="hi")]
        writer.write(mem, tmp_path)
        assert not (tmp_path / "DREAMS.md").exists()

    def test_roundtrip_through_daily_notes(self, tmp_path, sample_memories):
        """Convert to daily-notes, read back as OpenClaw, verify roundtrip metadata intact."""
        writer = OpenClawWriter(output_mode="daily-notes")
        writer.write(sample_memories, tmp_path)

        # Read back via OpenClaw reader
        from memlink.openclaw_reader import OpenClawReader
        # (Phase 2 — will verify roundtrip then)
