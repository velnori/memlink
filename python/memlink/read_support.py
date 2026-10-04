"""Deterministic input discovery, accounting, bounded parsing and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

from .plugin import ReadResult, Severity, ValidationIssue
from .safety import MAX_FILE_BYTES, MAX_RECORDS, checked_root, files_in


def markdown_files(path: Path) -> list[Path]:
    return [f for f in files_in(path) if f.suffix.lower() == ".md"]


def relative(file: Path, root: Path) -> str:
    return file.name if root.is_file() else file.relative_to(root).as_posix()


def pick_json(path: Path, preferred: tuple[str, ...]) -> tuple[Path, list[Path]]:
    candidates = [f for f in files_in(path) if f.suffix.lower() == ".json" and (path.is_file() or f.parent == path)]
    if not candidates:
        raise ValueError("No JSON file found in approved input")
    for name in preferred:
        selected = [f for f in candidates if f.name == name]
        if selected:
            return selected[0], [f for f in candidates if f != selected[0]]
    if len(candidates) != 1:
        raise ValueError("Ambiguous JSON input; specify one file explicitly")
    return candidates[0], []


def load_json(file: Path):
    file = checked_root(file)
    if file.stat().st_size > MAX_FILE_BYTES or file.stat().st_nlink > 1:
        raise ValueError("Oversized or hardlinked JSON input")
    return loads_json(file.read_bytes().decode("utf-8"))


def loads_json(text: str):
    """Decode file/frame JSON with identical finite, unique-key and resource rules."""
    if len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("JSON byte resource limit exceeded")

    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    from .serialization import sanitize

    return sanitize(json.loads(text, parse_constant=invalid_constant, object_pairs_hook=unique_keys))


def stats_init() -> dict[str, int]:
    return {"parsed": 0, "skipped": 0, "invalid": 0, "unsupported": 0, "records_total": 0}


def check_records(records) -> list:
    if not isinstance(records, list):
        raise ValueError("Expected a record array")
    if len(records) > MAX_RECORDS:
        raise ValueError("Record resource limit exceeded")
    return records


def read_issues(result: ReadResult) -> list[ValidationIssue]:
    issues = [ValidationIssue(code="ML202", severity=Severity.ERROR, message=e) for e in result.errors]
    issues.extend(ValidationIssue(code="ML103", severity=Severity.WARNING, message=w) for w in result.warnings)
    if not result.memories and not result.valid_empty:
        issues.append(ValidationIssue(code="ML303", severity=Severity.ERROR, message="No valid records parsed"))
    if result.stats.get("invalid", 0) or result.stats.get("unsupported", 0):
        issues.append(
            ValidationIssue(code="ML004", severity=Severity.ERROR, message="Invalid/unsupported input records")
        )
    return issues
