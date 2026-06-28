"""Unified plugin registry — entry_points + built-in plugin registration.

Separates Reader and Writer per format. A format like "ombre" has both
an OmbreReader and an OmbreWriter, registered under the same name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plugin import FormatPlugin

_readers: dict[str, FormatPlugin] = {}
_writers: dict[str, FormatPlugin] = {}
_loaded: bool = False


def register_reader(plugin: FormatPlugin) -> None:
    _readers[plugin.name] = plugin


def register_writer(plugin: FormatPlugin) -> None:
    _writers[plugin.name] = plugin


def get_reader(name: str) -> FormatPlugin:
    _ensure_loaded()
    if name not in _readers:
        raise KeyError(f"No reader for '{name}'. Available: {sorted(_readers)}")
    return _readers[name]


def get_writer(name: str) -> FormatPlugin:
    _ensure_loaded()
    if name not in _writers:
        raise KeyError(f"No writer for '{name}'. Available: {sorted(_writers)}")
    return _writers[name]


def list_formats() -> dict[str, dict[str, bool]]:
    """Return {format_name: {reader: bool, writer: bool}}."""
    _ensure_loaded()
    names = sorted(set(_readers) | set(_writers))
    return {n: {"reader": n in _readers, "writer": n in _writers} for n in names}


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    _discover_builtins()
    _discover_entry_points()


def _discover_builtins() -> None:
    from .ombre_reader import OmbreReader
    from .ombre_writer import OmbreWriter
    from .openclaw_reader import OpenClawReader
    from .openclaw_writer import OpenClawWriter

    register_reader(OmbreReader())
    register_writer(OmbreWriter())
    register_reader(OpenClawReader())
    register_writer(OpenClawWriter())


def _discover_entry_points() -> None:
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return
    for group in ("memlink.readers", "memlink.writers"):
        try:
            for ep in entry_points(group=group):
                try:
                    instance = ep.load()()
                    if group == "memlink.readers":
                        register_reader(instance)
                    else:
                        register_writer(instance)
                except Exception:
                    pass
        except Exception:
            pass
