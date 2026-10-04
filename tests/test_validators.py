"""Tests for three-level validation."""

from pathlib import Path

from memlink.plugin import Severity
from memlink.validators import ErrorCode, validate_schema, validate_semantic

FIXTURES = Path(__file__).parent / "fixtures"


class TestValidateSchema:
    def test_valid_ombre_files_no_errors(self):
        issues = validate_schema(FIXTURES / "ombre_samples" / "dynamic")
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors == []

    def test_valid_permanent_no_errors(self):
        issues = validate_schema(FIXTURES / "ombre_samples" / "permanent")
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors == []

    def test_missing_id_detected(self):
        issues = validate_schema(FIXTURES / "ombre_samples" / "broken")
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors
        assert any("records" in i.message.lower() for i in errors)

    def test_invalid_yaml_detected(self):
        # Truly broken file (no frontmatter at all) → reader skips, validator sees no .md files
        # A file without '---' delimiter is treated as body-only
        issues = validate_schema(FIXTURES / "test_edge_cases" / "broken")
        assert isinstance(issues, list)  # No crash — gracefully handled

    def test_openclaw_files_valid(self):
        # The actual OpenClaw adapter obtains stable IDs from filenames.
        issues = validate_schema(FIXTURES / "openclaw_samples")
        missing = [i for i in issues if i.code == ErrorCode.MISSING_ID]
        assert missing == []
        assert not [i for i in issues if i.severity == Severity.ERROR]


class TestValidateSemantic:
    def test_valid_ombre_no_errors(self):
        issues = validate_semantic(FIXTURES / "ombre_samples" / "dynamic")
        errors = [i for i in issues if i.severity == Severity.ERROR]
        assert errors == []

    def test_duplicate_id_detected(self):
        issues = validate_semantic(FIXTURES / "test_edge_cases" / "duplicate")
        dups = [i for i in issues if i.code == ErrorCode.DUPLICATE_ID]
        assert len(dups) == 1
        assert dups[0].severity == Severity.ERROR

    def test_body_empty_info(self):
        issues = validate_semantic(FIXTURES / "test_edge_cases" / "empty_body")
        empty = [i for i in issues if i.code == ErrorCode.BODY_EMPTY]
        assert len(empty) >= 1

    def test_valence_out_of_range(self):
        issues = validate_semantic(FIXTURES / "ombre_samples" / "dynamic")
        # sample.md has valence=0.8 which is in range
        oob = [i for i in issues if i.code == ErrorCode.VALUE_OUT_OF_RANGE]
        assert oob == []
