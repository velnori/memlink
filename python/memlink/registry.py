"""Unified plugin registry — stores classes, not instances.

Separates Reader and Writer per format. get_reader/get_writer create
fresh instances on each call, supporting **kwargs for construction params.
"""

from __future__ import annotations

import re
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
    _register(cls, _readers, "read")


def register_writer(cls: type[FormatPlugin]) -> None:
    """Register a Writer class (not an instance)."""
    _register(cls, _writers, "write")


def _register(cls, store, method):
    from .plugin import Capabilities, FormatPlugin

    if not isinstance(cls, type) or not issubclass(cls, FormatPlugin):
        raise ValueError("Plugin must be a FormatPlugin subclass")
    if not isinstance(getattr(cls, "name", None), str) or not re.fullmatch(r"[a-z][a-z0-9_-]*", cls.name):
        raise ValueError("Invalid plugin name")
    caps = getattr(cls, "capabilities", None)
    if not isinstance(caps, Capabilities) or caps.version != "1":
        raise ValueError("Missing capabilities or unknown capability version")
    for flag in (
        "relationships",
        "attachments",
        "summary",
        "emotion",
        "importance_label",
        "ttl",
        "embedding",
        "preserve_unknown_fields",
    ):
        if not isinstance(getattr(caps, flag), bool):
            raise ValueError(f"Invalid capability: {flag}")
    if caps.supported_kinds is not None and (
        not isinstance(caps.supported_kinds, set) or any(not isinstance(k, str) for k in caps.supported_kinds)
    ):
        raise ValueError("Invalid supported_kinds capability")
    if caps.max_body_size is not None and (type(caps.max_body_size) is not int or caps.max_body_size <= 0):
        raise ValueError("Invalid max_body_size capability")
    version = getattr(cls, "version_supported", "")
    if not _supports_v1(version):
        raise ValueError(f"Unverified plugin version range: {version}")
    if not callable(getattr(cls, method, None)) or getattr(cls, "__abstractmethods__", None):
        raise ValueError(f"Plugin cannot implement {method}")
    if cls.name in store and store[cls.name] is not cls:
        raise ValueError(f"Duplicate plugin name: {cls.name}")
    store[cls.name] = cls


def _supports_v1(version) -> bool:
    """Small documented numeric comparator grammar; unsupported syntax fails closed."""
    if not isinstance(version, str) or not version:
        return False
    if version == "*":
        return True
    for part in version.split(","):
        match = re.fullmatch(r"\s*(>=|<=|==|>|<)?\s*(\d+(?:\.\d+){0,2})\s*", part)
        if not match:
            return False
        op = match.group(1) or "=="
        numbers = tuple(int(x) for x in match.group(2).split("."))
        other = numbers + (0,) * (3 - len(numbers))
        current = (1, 0, 0)
        if not {
            ">=": current >= other,
            "<=": current <= other,
            "==": current == other,
            ">": current > other,
            "<": current < other,
        }[op]:
            return False
    return True


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
    from .chatgpt_reader import ChatGPTReader
    from .claude_export_reader import ClaudeExportReader
    from .generic_reader import GenericReader
    from .generic_writer import GenericWriter
    from .mem0_reader import Mem0Reader
    from .mem0_writer import Mem0Writer
    from .ombre_reader import OmbreReader
    from .ombre_writer import OmbreWriter
    from .openclaw_reader import OpenClawReader
    from .openclaw_writer import OpenClawWriter
    from .stream_summary_reader import StreamSummaryReader
    from .zep_reader import ZepReader
    from .zep_writer import ZepWriter

    register_reader(OmbreReader)
    register_writer(OmbreWriter)
    register_reader(OpenClawReader)
    register_writer(OpenClawWriter)
    register_reader(GenericReader)
    register_writer(GenericWriter)
    register_reader(ChatGPTReader)
    register_reader(ClaudeExportReader)
    register_reader(Mem0Reader)
    register_writer(Mem0Writer)
    register_reader(ZepReader)
    register_writer(ZepWriter)
    register_reader(StreamSummaryReader)


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
