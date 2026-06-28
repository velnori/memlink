"""Safe serialization for metadata and extensions.

Converts non-JSON types (datetime, set, custom objects) into
JSON-compatible equivalents. Detects circular references and
excessive nesting depth.
"""

from __future__ import annotations

import warnings
from datetime import date, datetime


def sanitize(obj, _depth: int = 0, _max_depth: int = 100, _seen: set[int] | None = None):
    """Recursively convert object to a serialization-safe type.

    Args:
        obj: Value to sanitize.
        _depth: Current recursion depth (internal).
        _max_depth: Maximum allowed depth.
        _seen: Set of object ids already visited (circular reference detection).

    Returns:
        A JSON/YAML/TOML-compatible value.

    Raises:
        ValueError: If nesting exceeds _max_depth or a circular reference is detected.
    """
    if _seen is None:
        _seen = set()

    if _depth > _max_depth:
        raise ValueError(f"Metadata nesting exceeds {_max_depth} levels")

    # Primitives pass through
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # datetime / date → ISO 8601 string
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()

    # Circular reference detection (mutable containers only)
    obj_id = id(obj)
    if isinstance(obj, (dict, list)):
        if obj_id in _seen:
            raise ValueError("Circular reference detected in metadata")
        _seen = _seen | {obj_id}

    if isinstance(obj, dict):
        return {
            str(k): sanitize(v, _depth + 1, _max_depth, _seen)
            for k, v in obj.items()
        }

    if isinstance(obj, (list, tuple)):
        return [
            sanitize(item, _depth + 1, _max_depth, _seen)
            for item in obj
        ]

    if isinstance(obj, (set, frozenset)):
        return sorted(
            sanitize(item, _depth + 1, _max_depth, _seen)
            for item in obj
        )

    # Unknown type → string with warning
    warnings.warn(
        f"Non-serializable type {type(obj).__name__} converted to string",
        UserWarning,
        stacklevel=2,
    )
    return str(obj)
