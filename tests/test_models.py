"""Tests for Canonical Memory data model and sanitize_id."""

from memlink.models import (
    Memory,
    Relationship,
    Source,
    sanitize_id,
)


class TestMemory:
    def test_default_construction(self):
        m = Memory(id="test")
        assert m.schema_version == "1"
        assert m.kind == "dynamic"
        assert m.status == "active"
        assert m.tags == []
        assert m.domains == []
        assert m.pinned is False
        assert m.relationships == []

    def test_full_construction(self):
        m = Memory(
            id="abc",
            name="Test",
            source=Source(format="ombre", path="x/y.md"),
            summary="short",
            body="long content",
            kind="permanent",
            status="active",
            tags=["a", "b"],
            domains=["work"],
            importance_score=8.0,
            importance_label="high",
            valence=0.7,
            arousal=0.3,
            pinned=True,
            checksum="sha256:abc",
            metadata={"memlink": {"source": "ombre"}},
            extensions={"extra": True},
        )
        assert m.name == "Test"
        assert m.kind == "permanent"
        assert m.importance_score == 8.0
        assert m.importance_label == "high"
        assert m.source.format == "ombre"
        assert m.extensions["extra"] is True

    def test_source_uri_default(self):
        s = Source(format="ombre", path="dyn/user/abc.md")
        assert s.uri is None
        assert s.format == "ombre"

    def test_relationship_defaults(self):
        r = Relationship(target_id="abc", type="relates_to")
        assert r.weight is None


class TestSanitizeId:
    def test_normal_id_unchanged(self):
        assert sanitize_id("normal-id") == "normal-id"

    def test_replaces_slash(self):
        assert sanitize_id("project/feature") == "project%2Ffeature"

    def test_replaces_colon_star_question(self):
        assert sanitize_id("a:b*c?d") == "a%3Ab%2Ac%3Fd"

    def test_preserves_unicode_chinese(self):
        assert sanitize_id("中文ID") == "中文ID"

    def test_preserves_emoji(self):
        assert sanitize_id("memory-😊") == "memory-😊"

    def test_windows_reserved_con(self):
        assert sanitize_id("CON") == "_CON"

    def test_windows_reserved_prn(self):
        assert sanitize_id("PRN") == "_PRN"

    def test_windows_reserved_case_insensitive(self):
        assert sanitize_id("com1") == "_com1"

    def test_strips_leading_dot_space(self):
        assert sanitize_id("..test.") == "test"

    def test_empty_fallback(self):
        assert sanitize_id("") == "unnamed"

    def test_only_special_chars(self):
        # All chars are percent-encoded, result is not empty string
        assert sanitize_id("///") == "%2F%2F%2F"

    def test_long_id_truncated(self):
        long_id = "a" * 300
        assert len(sanitize_id(long_id).encode("utf-8")) <= 255

    def test_percent_encodes_null_byte(self):
        assert sanitize_id("a\x00b") == "a%00b"

    def test_slash_reversible(self):
        # a%2Fb decodes back to a/b, whereas a-b is ambiguous
        out = sanitize_id("a/b")
        assert out == "a%2Fb"
