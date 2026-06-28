"""Three-level validation: schema, semantic, roundtrip.

Error codes use the MLxxx namespace for stable CI/IDE references.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import yaml

from .plugin import Severity, ValidationIssue


# ── Error codes ───────────────────────────────────────────────────


class ErrorCode(str, Enum):
    # Schema errors (ML001–ML099)
    INVALID_DATETIME = "ML001"
    MISSING_ID = "ML002"
    DUPLICATE_ID = "ML003"
    INVALID_SCHEMA = "ML004"
    MISSING_REQUIRED_FIELD = "ML005"
    INVALID_SOURCE_URI = "ML010"

    # Semantic warnings/errors (ML100–ML199)
    BODY_EMPTY = "ML100"
    VALUE_OUT_OF_RANGE = "ML101"
    UNSUPPORTED_KIND = "ML102"
    UNKNOWN_DOMAIN = "ML103"

    # I/O errors (ML200–ML299)
    FILE_NOT_FOUND = "ML200"
    PERMISSION_DENIED = "ML201"
    CORRUPT_FILE = "ML202"

    # Conversion errors (ML300–ML399)
    CONCURRENT_MODIFICATION = "ML300"
    FORMAT_INCOMPATIBLE = "ML301"
    ID_CONFLICT = "ML302"

    # Roundtrip errors (ML400–ML499)
    ROUNDTRIP_ID_MISMATCH = "ML400"
    ROUNDTRIP_KIND = "ML401"
    ROUNDTRIP_BODY = "ML402"
    ROUNDTRIP_IMPORTANCE = "ML403"
    ROUNDTRIP_TIME = "ML404"
    # Legacy alias
    ROUNDTRIP_CONTENT_MISMATCH = "ML401"  # deprecated — use ROUNDTRIP_KIND


# ── Schema validation ──────────────────────────────────────────────


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown file.

    Returns (frontmatter_dict, body_text). If no frontmatter, returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, text

    return fm, parts[2]


def validate_schema(path: Path) -> list[ValidationIssue]:
    """Validate YAML syntax and required fields."""
    issues: list[ValidationIssue] = []

    for md_file in sorted(path.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            issues.append(ValidationIssue(
                code=ErrorCode.FILE_NOT_FOUND,
                severity=Severity.ERROR,
                path=str(md_file),
                message=f"Cannot read file: {md_file}",
            ))
            continue

        fm, body = _parse_frontmatter(text)

        # Check frontmatter is valid dict
        if not isinstance(fm, dict):
            issues.append(ValidationIssue(
                code=ErrorCode.INVALID_SCHEMA,
                severity=Severity.ERROR,
                path=str(md_file),
                message="YAML frontmatter did not parse to a dictionary",
                suggestion="Ensure the file starts with '---' followed by valid YAML key:value pairs",
            ))
            continue

        # Required: id (bucket_id for Ombre)
        mem_id = fm.get("id") or fm.get("bucket_id")
        if not mem_id:
            issues.append(ValidationIssue(
                code=ErrorCode.MISSING_ID,
                severity=Severity.ERROR,
                path=str(md_file),
                message="Missing required field: id or bucket_id",
                suggestion="Add 'id:' or 'bucket_id:' to the frontmatter",
            ))
        elif not isinstance(mem_id, (str, int, float)):
            issues.append(ValidationIssue(
                code=ErrorCode.MISSING_ID,
                severity=Severity.ERROR,
                path=str(md_file),
                field="id",
                message=f"id must be a string, got {type(mem_id).__name__}",
            ))

    return issues


# ── Semantic validation ────────────────────────────────────────────


def validate_semantic(path: Path) -> list[ValidationIssue]:
    """Validate field types, value ranges, domain integrity."""
    issues: list[ValidationIssue] = []
    seen_ids: dict[str, Path] = {}

    for md_file in sorted(path.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)

        mem_id = str(fm.get("id") or fm.get("bucket_id") or "")
        file_path = str(md_file)

        # Duplicate ID (casefold for cross-platform)
        if mem_id:
            key = mem_id.casefold()
            if key in seen_ids:
                issues.append(ValidationIssue(
                    code=ErrorCode.DUPLICATE_ID,
                    severity=Severity.ERROR,
                    path=file_path,
                    memory_id=mem_id,
                    message=f"Duplicate ID '{mem_id}' (case-insensitive match with '{seen_ids[key].name}')",
                    suggestion="Memory IDs must be unique within a dataset.",
                ))
            else:
                seen_ids[key] = md_file

        # Valence range
        valence = fm.get("valence")
        if valence is not None:
            try:
                v = float(valence)
                if not (0.0 <= v <= 1.0):
                    issues.append(ValidationIssue(
                        code=ErrorCode.VALUE_OUT_OF_RANGE,
                        severity=Severity.WARNING,
                        path=file_path,
                        memory_id=mem_id,
                        field="valence",
                        message=f"valence={v} is outside [0.0, 1.0]",
                    ))
            except (ValueError, TypeError):
                pass

        # Arousal range
        arousal = fm.get("arousal")
        if arousal is not None:
            try:
                a = float(arousal)
                if not (0.0 <= a <= 1.0):
                    issues.append(ValidationIssue(
                        code=ErrorCode.VALUE_OUT_OF_RANGE,
                        severity=Severity.WARNING,
                        path=file_path,
                        memory_id=mem_id,
                        field="arousal",
                        message=f"arousal={a} is outside [0.0, 1.0]",
                    ))
            except (ValueError, TypeError):
                pass

        # Body empty warning (info level, not an error)
        if not body.strip():
            issues.append(ValidationIssue(
                code=ErrorCode.BODY_EMPTY,
                severity=Severity.INFO,
                path=file_path,
                memory_id=mem_id,
                message="Body is empty",
                suggestion="Consider adding content or a summary.",
            ))

        # Datetime format
        created = fm.get("created") or fm.get("created_at")
        if isinstance(created, str):
            if not _is_iso_datetime(created):
                issues.append(ValidationIssue(
                    code=ErrorCode.INVALID_DATETIME,
                    severity=Severity.WARNING,
                    path=file_path,
                    memory_id=mem_id,
                    field="created",
                    message=f"Datetime '{created}' is not valid ISO 8601",
                    suggestion="Use format: 2024-01-01T10:00:00Z",
                ))

    return issues


# ── Roundtrip validation ───────────────────────────────────────────


def validate_roundtrip(path: Path, source_format: str = "ombre",
                       intermediate_format: str = "openclaw") -> list[ValidationIssue]:
    """Validate A→B→A canonical consistency (semantic, not byte-level)."""
    from .converter import run_roundtrip
    try:
        report = run_roundtrip(path, source_format, intermediate_format)
        return report.issues
    except Exception as e:
        return [ValidationIssue(
            code=ErrorCode.VALIDATION_ERROR, severity=Severity.ERROR,
            message=f"Roundtrip validation failed: {e}",
        )]


# ── Helpers ────────────────────────────────────────────────────────


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2}|Z)?$"
)


def _is_iso_datetime(s: str) -> bool:
    return bool(_ISO_RE.match(s))
