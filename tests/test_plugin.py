"""Tests for plugin interface types."""

from memlink.models import Memory
from memlink.plugin import (
    Capabilities,
    ReadResult,
    Severity,
    ValidationIssue,
)


class TestCapabilities:
    def test_defaults(self):
        c = Capabilities()
        assert c.version == "1"
        assert c.relationships is False
        assert c.emotion is False
        assert c.summary is True
        assert c.max_body_size is None
        assert c.supported_kinds is None
        assert c.preserve_unknown_fields is True

    def test_custom(self):
        c = Capabilities(
            emotion=True,
            max_body_size=10000,
            supported_kinds={"dynamic", "permanent"},
            preserve_unknown_fields=False,
        )
        assert c.emotion is True
        assert c.max_body_size == 10000
        assert c.supported_kinds == {"dynamic", "permanent"}
        assert c.preserve_unknown_fields is False


class TestValidationIssue:
    def test_minimal_issue(self):
        vi = ValidationIssue(
            code="ML001",
            severity=Severity.ERROR,
            message="bad datetime",
        )
        assert vi.code == "ML001"
        assert vi.path is None
        assert vi.memory_id is None
        assert vi.suggestion is None

    def test_full_issue(self):
        vi = ValidationIssue(
            code="ML002",
            severity=Severity.WARNING,
            path="dynamic/user/test.md",
            memory_id="abc123",
            field="name",
            message="Missing name",
            suggestion="Add a name field.",
        )
        assert vi.path == "dynamic/user/test.md"
        assert vi.memory_id == "abc123"
        assert vi.field == "name"
        assert vi.suggestion == "Add a name field."


class TestReadResult:
    def test_minimal_result(self):
        rr = ReadResult(memories=[])
        assert rr.memories == []
        assert rr.warnings == []
        assert rr.stats == {}

    def test_with_stats(self):
        m = Memory(id="test")
        rr = ReadResult(
            memories=[m],
            warnings=["unsupported field"],
            stats={"parsed": 1, "skipped": 0},
        )
        assert len(rr.memories) == 1
        assert rr.warnings == ["unsupported field"]
        assert rr.stats["parsed"] == 1


class TestSeverity:
    def test_enum_values(self):
        assert Severity.ERROR == "error"
        assert Severity.WARNING == "warning"
        assert Severity.INFO == "info"
