"""Adapter-aware validation and packaged canonical-v1 instance checks."""

from __future__ import annotations

import json
import math
import re
import warnings
from enum import Enum
from importlib.resources import files
from pathlib import Path

from .codec import identity_key, memory_dict, parse_time
from .models import Memory
from .plugin import Severity, ValidationIssue


class ErrorCode(str, Enum):
    INVALID_DATETIME = "ML001"
    MISSING_ID = "ML002"
    DUPLICATE_ID = "ML003"
    INVALID_SCHEMA = "ML004"
    MISSING_REQUIRED_FIELD = "ML005"
    INVALID_SOURCE_URI = "ML010"
    BODY_EMPTY = "ML100"
    VALUE_OUT_OF_RANGE = "ML101"
    UNSUPPORTED_KIND = "ML102"
    UNKNOWN_DOMAIN = "ML103"
    FILE_NOT_FOUND = "ML200"
    PERMISSION_DENIED = "ML201"
    CORRUPT_FILE = "ML202"
    CONCURRENT_MODIFICATION = "ML300"
    FORMAT_INCOMPATIBLE = "ML301"
    ID_CONFLICT = "ML302"
    VALIDATION_ERROR = "ML303"
    ROUNDTRIP_ID_MISMATCH = "ML400"
    ROUNDTRIP_KIND = "ML401"
    ROUNDTRIP_BODY = "ML402"
    ROUNDTRIP_IMPORTANCE = "ML403"
    ROUNDTRIP_TIME = "ML404"
    ROUNDTRIP_CONTENT_MISMATCH = "ML401"


_SCHEMA_CACHE = None


def _load_canonical_schema() -> dict:
    data = json.loads(files("memlink").joinpath("resources/canonical-v1.schema.json").read_text(encoding="utf-8"))
    if data.get("$id") != "https://memlink.dev/canonical-v1.schema.json":
        raise ValueError("Canonical schema resource is missing or invalid")
    return data


def _get_schema() -> dict:
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = _load_canonical_schema()
    return _SCHEMA_CACHE


def _check_json_type(value, types: list[str]) -> bool:
    for t in types:
        if t == "string" and isinstance(value, str):
            return True
        if t == "number" and type(value) in {int, float} and math.isfinite(value):
            return True
        if t == "integer" and type(value) is int:
            return True
        if t == "boolean" and type(value) is bool:
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
        if t == "null" and value is None:
            return True
    return False


def validate_instance(data, schema: dict | None = None, prefix: str = "") -> list[str]:
    """Validate every keyword used by the frozen canonical-v1 schema (no external refs)."""
    schema = _get_schema() if schema is None else schema
    problems = []
    types = schema.get("type")
    if types and not _check_json_type(data, types if isinstance(types, list) else [types]):
        return [f"{prefix or 'record'}: invalid type for {types}"]
    if "const" in schema and data != schema["const"]:
        problems.append(f"{prefix}: unknown schema version/value")
    if "enum" in schema and data not in schema["enum"]:
        problems.append(f"{prefix}: invalid enum value")
    if data is None:
        return problems
    if type(data) in {int, float}:
        if "minimum" in schema and data < schema["minimum"]:
            problems.append(f"{prefix}: below minimum")
        if "maximum" in schema and data > schema["maximum"]:
            problems.append(f"{prefix}: above maximum")
    if isinstance(data, str):
        if "pattern" in schema and not re.search(schema["pattern"], data):
            problems.append(f"{prefix}: invalid pattern")
        if schema.get("format") == "date-time":
            try:
                dt = parse_time(data)
                if dt is None or not re.search(r"[T ]\d{2}:\d{2}", data):
                    raise ValueError("not datetime")
            except (ValueError, TypeError, OverflowError):
                problems.append(f"{prefix}: invalid datetime")
    if isinstance(data, dict):
        for key in schema.get("required", []):
            if key not in data:
                problems.append(f"{prefix}.{key}: required field missing")
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                problems.extend(validate_instance(data[key], sub, f"{prefix}.{key}".lstrip(".")))
    if isinstance(data, list) and "items" in schema:
        for i, value in enumerate(data):
            problems.extend(validate_instance(value, schema["items"], f"{prefix}[{i}]"))
    return problems


def validate_memory(memory: Memory) -> list[ValidationIssue]:
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error", message="Non-serializable type .* converted to string", category=UserWarning
            )
            data = memory_dict(memory)
        problems = validate_instance(data)
        if not isinstance(memory.id, str) or not memory.id:
            problems.append("id: missing stable ID")
        if memory.source and (not isinstance(memory.source.format, str) or not isinstance(memory.source.path, str)):
            problems.append("source: invalid")
        return [
            ValidationIssue(
                code=ErrorCode.MISSING_ID if p.startswith("id:") else ErrorCode.INVALID_SCHEMA,
                severity=Severity.ERROR,
                memory_id=memory.id,
                field=p.split(":")[0],
                message=p,
            )
            for p in problems
        ]
    except Exception as exc:
        return [
            ValidationIssue(
                code=ErrorCode.INVALID_SCHEMA,
                severity=Severity.ERROR,
                memory_id=memory.id,
                message=f"Canonical validation failed: {exc}",
            )
        ]


def _read_validation(path: Path, source_format: str | None) -> tuple[list[Memory], list[ValidationIssue]]:
    from .detection import detect_format
    from .read_support import read_issues
    from .registry import get_reader

    try:
        _get_schema()
        result = get_reader(source_format or detect_format(path)).read(path)
        issues = read_issues(result)
        for memory in result.memories:
            issues.extend(validate_memory(memory))
        return result.memories, issues
    except Exception as exc:
        return [], [
            ValidationIssue(code=ErrorCode.INVALID_SCHEMA, severity=Severity.ERROR, path=str(path), message=str(exc))
        ]


def validate_schema(path: Path, source_format: str | None = None) -> list[ValidationIssue]:
    return _read_validation(path, source_format)[1]


def validate_semantic(path: Path, source_format: str | None = None) -> list[ValidationIssue]:
    memories, issues = _read_validation(path, source_format)
    seen = set()
    for memory in memories:
        key = identity_key(memory)
        if key in seen:
            issues.append(
                ValidationIssue(
                    code=ErrorCode.DUPLICATE_ID,
                    severity=Severity.ERROR,
                    memory_id=memory.id,
                    message="Duplicate scoped identity",
                )
            )
        seen.add(key)
        if not memory.body or not memory.body.strip():
            issues.append(
                ValidationIssue(
                    code=ErrorCode.BODY_EMPTY, severity=Severity.INFO, memory_id=memory.id, message="Body is empty"
                )
            )
    return issues


def validate_roundtrip(
    path: Path,
    source_format: str | None = None,
    intermediate_format: str = "openclaw",
    output_mode: str = "daily-notes",
) -> list[ValidationIssue]:
    from .converter import run_roundtrip
    from .detection import detect_format

    try:
        return run_roundtrip(
            path, source_format or detect_format(path), intermediate_format, output_mode=output_mode
        ).issues
    except Exception as exc:
        return [
            ValidationIssue(
                code=ErrorCode.VALIDATION_ERROR, severity=Severity.ERROR, message=f"Roundtrip validation failed: {exc}"
            )
        ]


_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _is_iso_datetime(s: str) -> bool:
    try:
        return bool(_ISO_RE.match(s) and parse_time(s))
    except ValueError:
        return False
