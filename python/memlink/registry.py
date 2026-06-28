"""Unified plugin registry — stores classes, not instances.

Separates Reader and Writer per format. get_reader/get_writer create
fresh instances on each call, supporting **kwargs for construction params.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin import FormatPlugin

_readers: dict[str, type[FormatPlugin]] = {}
_writers: dict[str, type[FormatPlugin]] = {}
_loaded: bool = False


class PluginNotFoundError(KeyError):
    """Raised when a requested format plugin is not registered."""

    def __init__(self, name: str, kind: str = "format", available: list[str] | None = None):
        self.name = name
        self.kind = kind
        self.available = sorted(available or [])
        msg = f"No {kind} for '{name}'"
        if self.available:
            msg += f". Available: {', '.join(self.available)}"
        super().__init__(msg)


def register_reader(cls: type[FormatPlugin]) -> None:
    """Register a Reader class (not an instance)."""
    _readers[cls.name] = cls


def register_writer(cls: type[FormatPlugin]) -> None:
    """Register a Writer class (not an instance)."""
    _writers[cls.name] = cls


def get_reader(name: str, **kwargs) -> FormatPlugin:
    """Get a fresh Reader instance. Supports constructor kwargs."""
    _ensure_loaded()
    if name not in _readers:
        raise PluginNotFoundError(name, kind="reader", available=list(_readers))
    return _readers[name](**kwargs)


def get_writer(name: str, **kwargs) -> FormatPlugin:
    """Get a fresh Writer instance. Supports constructor kwargs.

    Example: get_writer("openclaw", output_mode="structured")
    """
    _ensure_loaded()
    if name not in _writers:
        raise PluginNotFoundError(name, kind="writer", available=list(_writers))
    return _writers[name](**kwargs)


def list_formats() -> dict[str, dict[str, bool]]:
    """Return {format_name: {reader: bool, writer: bool}}."""
    _ensure_loaded()
    names = sorted(set(_readers) | set(_writers))
    return {n: {"reader": n in _readers, "writer": n in _writers} for n in names}


# ── Lazy loading ───────────────────────────────────────────────────


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    _discover_builtins()
    _discover_entry_points()


def _discover_builtins() -> None:
    from .generic_reader import GenericReader
    from .ombre_reader import OmbreReader
    from .ombre_writer import OmbreWriter
    from .openclaw_reader import OpenClawReader
    from .openclaw_writer import OpenClawWriter

    register_reader(OmbreReader)
    register_writer(OmbreWriter)
    register_reader(OpenClawReader)
    register_writer(OpenClawWriter)
    register_reader(GenericReader)


def _discover_entry_points() -> None:
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return
    for group in ("memlink.readers", "memlink.writers"):
        try:
            for ep in entry_points(group=group):
                try:
                    cls = ep.load()
                    if not isinstance(cls, type):
                        warnings.warn(f"Entry point '{ep.name}' in {group} is not a class — skipping", stacklevel=2)
                        continue
                    if group == "memlink.readers":
                        register_reader(cls)
                    else:
                        register_writer(cls)
                except Exception as e:
                    warnings.warn(f"Failed to load plugin '{ep.name}' from {group}: {e}", stacklevel=2)
        except Exception:
            pass
