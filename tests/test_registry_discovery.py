"""Registry discovery tests — catch unregistered plugins.

Every reader/writer declared in pyproject.toml entry-points must be
discoverable via list_formats(). This prevents regressions like the
StreamSummaryReader that was implemented but not registered.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore[assignment]

import pytest
from memlink.registry import list_formats


def _declared_formats() -> dict[str, set[str]]:
    """Parse pyproject.toml entry-points and return {format: {reader, writer}}."""
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    declared: dict[str, set[str]] = {}
    eps = data.get("project", {}).get("entry-points", {})

    for key in ("memlink.readers", "memlink.writers"):
        role = "reader" if "reader" in key else "writer"
        entries = eps.get(key, {})
        if isinstance(entries, dict):
            for fmt in entries:
                declared.setdefault(fmt, set()).add(role)

    return declared


pytestmark = pytest.mark.skipif(tomllib is None, reason="tomllib/tomli not available (Python <3.11 without tomli)")


def test_all_declared_readers_discoverable() -> None:
    """Every reader declared in pyproject.toml must appear in list_formats()."""
    declared = _declared_formats()
    actual = list_formats()

    missing = []
    for fmt, roles in declared.items():
        if "reader" in roles:
            if fmt not in actual or not actual[fmt]["reader"]:
                missing.append(f"{fmt} (reader)")

    assert not missing, (
        f"Readers declared in pyproject.toml but not discoverable: {missing}. "
        "Check registry.py _discover_builtins() or pyproject.toml entry-points."
    )


def test_all_declared_writers_discoverable() -> None:
    """Every writer declared in pyproject.toml must appear in list_formats()."""
    declared = _declared_formats()
    actual = list_formats()

    missing = []
    for fmt, roles in declared.items():
        if "writer" in roles:
            if fmt not in actual or not actual[fmt]["writer"]:
                missing.append(f"{fmt} (writer)")

    assert not missing, (
        f"Writers declared in pyproject.toml but not discoverable: {missing}. "
        "Check registry.py _discover_builtins() or pyproject.toml entry-points."
    )


def test_formats_count_consistent() -> None:
    """Total formats = sum of declared entry-points."""
    declared = _declared_formats()
    actual = list_formats()

    # Every declared format must be in actual
    for fmt in declared:
        assert fmt in actual, f"Format '{fmt}' declared in pyproject.toml but not in list_formats()"

    # Check counts
    readers_actual = sum(1 for v in actual.values() if v["reader"])
    writers_actual = sum(1 for v in actual.values() if v["writer"])

    readers_declared = sum(1 for roles in declared.values() if "reader" in roles)
    writers_declared = sum(1 for roles in declared.values() if "writer" in roles)

    assert readers_actual == readers_declared, (
        f"{readers_actual} readers discoverable, {readers_declared} declared in pyproject.toml"
    )
    assert writers_actual == writers_declared, (
        f"{writers_actual} writers discoverable, {writers_declared} declared in pyproject.toml"
    )
