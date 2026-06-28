"""Tests for Ombre Brain → Canonical reader."""

from pathlib import Path

from memlink.ombre_reader import OmbreReader

FIXTURES = Path(__file__).parent / "fixtures"


class TestOmbreReader:
    def test_reads_dynamic_memory(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "dynamic" / "user")

        assert result.stats["parsed"] == 2  # sample.md + minimal.md
        mem = next(m for m in result.memories if m.name == "用户偏好设置")
        assert mem.kind == "dynamic"
        assert mem.status == "active"
        assert mem.importance_score == 7.0
        assert mem.valence == 0.8
        assert mem.arousal == 0.3
        assert mem.pinned is False
        assert "暗色模式" in (mem.body or "")
        assert "dark-mode" in mem.tags
        assert "中文标签" in mem.tags
        assert mem.source is not None
        assert mem.source.format == "ombre"
        assert "ombre://dynamic/user" in (mem.source.uri or "")
        # Checksum present
        assert mem.checksum is not None and len(mem.checksum) == 64

    def test_reads_permanent_memory(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "permanent")

        assert result.stats["parsed"] == 1
        mem = result.memories[0]
        assert mem.kind == "permanent"
        assert mem.pinned is True
        assert mem.importance_score == 9.0
        assert "setup" in mem.tags
        # timezone preserved in metadata
        orig = mem.metadata.get("memlink", {}).get("original", {})
        assert orig.get("created") == "2024-01-15T08:00:00+08:00"

    def test_reads_feel_as_emotion(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "feel")

        assert result.stats["parsed"] == 1
        mem = result.memories[0]
        assert mem.kind == "emotion"

    def test_skips_broken_files(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "broken")

        # no-id.md and invalid-yaml both have frontmatter but no valid id
        warnings_text = "\n".join(result.warnings)
        assert result.stats["skipped"] >= 1
        assert "Missing bucket_id" in warnings_text

    def test_empty_directory(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "feel")
        assert result.stats["parsed"] == 1

    def test_source_path_is_relative(self):
        reader = OmbreReader()
        result = reader.read(FIXTURES / "ombre_samples" / "dynamic" / "user")
        for mem in result.memories:
            assert mem.source is not None
            assert "\\" not in mem.source.path  # uses forward slashes or OS native
