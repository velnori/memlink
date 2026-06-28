"""Validate spec/canonical-v1.schema.json against sample data."""

import json
from pathlib import Path

SPEC_DIR = Path(__file__).parent.parent / "spec"
SCHEMA_PATH = SPEC_DIR / "canonical-v1.schema.json"


def test_schema_valid_json():
    """The JSON Schema is valid JSON."""
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    schema = json.loads(text)
    assert schema["$id"] == "https://memlink.dev/canonical-v1.schema.json"
    assert schema["title"] == "Canonical Memory v1"


def test_schema_required_fields():
    """Schema declares required fields."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert "schema_version" in schema["required"]
    assert "id" in schema["required"]


def test_schema_all_core_fields_present():
    """All core Canonical fields are defined in the schema."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    props = schema["properties"]
    expected = [
        "schema_version", "id", "name", "source", "summary", "body",
        "kind", "status", "tags", "domains", "created_at", "updated_at",
        "valence", "arousal", "importance_score", "importance_label",
        "pinned", "checksum", "metadata", "extensions", "relationships",
    ]
    for field in expected:
        assert field in props, f"Field '{field}' missing from JSON Schema"


def test_sample_validates_against_schema():
    """A minimal valid Canonical Memory validates against the schema.

    Only validates the structural check, not full JSON Schema spec conformance.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    sample = {
        "schema_version": "1",
        "id": "test-123",
        "name": "Test Memory",
        "kind": "dynamic",
        "status": "active",
        "tags": [],
        "domains": [],
        "pinned": False,
    }

    # Validate required fields present
    for req in schema.get("required", []):
        assert req in sample, f"Required field '{req}' missing from sample"

    # Validate field types match schema
    for field, value in sample.items():
        if field in schema["properties"]:
            prop = schema["properties"][field]
            _check_type(field, value, prop)


def _check_type(field: str, value, prop: dict) -> None:
    """Basic type check against JSON Schema type definition."""
    expected_type = prop.get("type")
    if expected_type is None:
        return
    # Allow null for nullable fields
    if isinstance(expected_type, list) and "null" in expected_type and value is None:
        return
    types = expected_type if isinstance(expected_type, list) else [expected_type]
    type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict, "null": type(None),
    }
    valid = any(t in types and isinstance(value, type_map.get(t, object)) for t in types)
    assert valid, f"Field '{field}': expected {expected_type}, got {type(value).__name__}"
