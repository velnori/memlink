"""Safe serialization for metadata and extensions.

Converts non-JSON types (datetime, set, custom objects) into
JSON-compatible equivalents. Detects circular references and
excessive nesting depth.
"""

from __future__ import annotations

import json
import math
import warnings
from datetime import date, datetime


def sanitize(
    obj, _depth: int = 0, _max_depth: int = 100, _seen: set[int] | None = None, _budget: list[int] | None = None
):
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
    if _budget is None:
        _budget = [0]
    _budget[0] += 1
    if _budget[0] > 100000:
        raise ValueError("Serialization node resource limit exceeded")

    if _depth > _max_depth:
        raise ValueError(f"Metadata nesting exceeds {_max_depth} levels")

    # Primitives pass through
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("Non-finite number is not JSON-compatible")
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # datetime / date → ISO 8601 string
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()

    # Circular reference detection (mutable containers only)
    obj_id = id(obj)
    if isinstance(obj, (dict, list, tuple, set, frozenset)):
        if obj_id in _seen:
            raise ValueError("Circular reference detected in metadata")
        _seen = _seen | {obj_id}

    if isinstance(obj, dict):
        if len({str(k) for k in obj}) != len(obj):
            raise ValueError("Dictionary key collision after JSON encoding")
        return {str(k): sanitize(v, _depth + 1, _max_depth, _seen, _budget) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [sanitize(item, _depth + 1, _max_depth, _seen, _budget) for item in obj]

    if isinstance(obj, (set, frozenset)):
        values = [sanitize(item, _depth + 1, _max_depth, _seen, _budget) for item in obj]
        return sorted(values, key=lambda x: (type(x).__name__, json.dumps(x, sort_keys=True, ensure_ascii=False)))

    # Unknown type → string with warning
    warnings.warn(
        f"Non-serializable type {type(obj).__name__} converted to string",
        UserWarning,
        stacklevel=2,
    )
    return str(obj)
