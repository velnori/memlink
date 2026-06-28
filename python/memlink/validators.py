"""Three-level validation: schema, semantic, roundtrip.

Error codes use the MLxxx namespace for stable CI/IDE references.
"""

from pathlib import Path

from .plugin import Severity, ValidationIssue


# ── Schema validation ────────────────────────────────────────────


def validate_schema(path: Path) -> list[ValidationIssue]:
    """Validate YAML syntax and required fields (id, schema_version)."""
    issues: list[ValidationIssue] = []
    # TODO: Phase 0.5 — iterate markdown files, parse YAML frontmatter
    return issues


# ── Semantic validation ──────────────────────────────────────────


def validate_semantic(path: Path) -> list[ValidationIssue]:
    """Validate field types, value ranges, domain integrity."""
    issues: list[ValidationIssue] = []
    # TODO: Phase 0.5
    return issues


# ── Roundtrip validation ─────────────────────────────────────────


def validate_roundtrip(path: Path) -> list[ValidationIssue]:
    """Validate A→B→A canonical consistency (semantic, not byte-level)."""
    issues: list[ValidationIssue] = []
    # TODO: Phase 2
    return issues
