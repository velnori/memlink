"""FormatPlugin — unified interface for format readers and writers.

Each AI memory format implements one plugin with three methods:
  read()     → Format → Canonical
  write()    → Canonical → Format
  validate() → Format-specific integrity checks

**API Stability (v1.0):** The following are stable and will not have breaking changes in 1.x:
  - FormatPlugin ABC (read/write/validate signatures)
  - ReadResult, Capabilities, ValidationIssue, Severity dataclasses
  - All field names and types on the above classes

Breaking changes require a 2.0 version bump.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Literal

from .models import Memory


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Structured validation result with stable error codes."""

    code: str  # "ML001" — see spec for full list
    severity: Severity
    path: str | None = None  # file path
    memory_id: str | None = None  # memory ID within the file
    field: str | None = None  # affected field name
    message: str = ""
    suggestion: str | None = None  # actionable fix hint


@dataclass
class ReadResult:
    """Result of reading a format's memory store into Canonical."""

    memories: list[Memory]
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)  # {"parsed": N, "skipped": N, "invalid": N}
    files: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    variant: str = "unknown"
    valid_empty: bool = False


@dataclass
class Capabilities:
    """What a format plugin supports — used for compatibility checking."""

    version: Literal["1"] = "1"

    # Feature support
    relationships: bool = False
    attachments: bool = False
    summary: bool = True
    emotion: bool = False  # valence / arousal
    importance_label: bool = False
    ttl: bool = False
    embedding: bool = False

    # Constraints
    max_body_size: int | None = None  # bytes, None = unlimited
    supported_kinds: set[str] | None = None  # None = all kinds

    # Extension handling
    preserve_unknown_fields: bool = True  # Can this format store extensions it doesn't understand?


class FormatPlugin(ABC):
    """Abstract base for all format plugins."""

    name: str  # "ombre" | "openclaw" | "mem0" | ...
    version_supported: str = ">=1,<3"  # semver range
    capabilities: Capabilities  # Required on concrete plugins; no dataclass Field class default.
    _serialize: Callable[..., list[str]]
    _parse: Callable[..., ReadResult]
    native_only: bool = False
    selection: str = "explicit"
    last_receipt: dict[str, Any]

    def __init_subclass__(cls, **kwargs):
        """Keep v1 signatures while putting public writes behind one transaction."""
        super().__init_subclass__(**kwargs)
        raw_write = cls.__dict__.get("write")
        if raw_write is not None:
            cls._serialize = raw_write

            @wraps(raw_write)
            def write(self, memories, path):
                from .transaction import execute_output

                result = execute_output(list(memories), self, Path(path))
                self.last_receipt = result
                return result["warnings"]

            cls.write = write
        raw_read = cls.__dict__.get("read")
        if raw_read is not None:
            cls._parse = raw_read

            @wraps(raw_read)
            def read(self, path):
                from .reading import guarded_read

                return guarded_read(self, raw_read, Path(path), native_only=getattr(self, "native_only", False))

            cls.read = read

    @abstractmethod
    def read(self, path: Path) -> ReadResult:
        """Read memories from this format into Canonical."""
        ...

    @abstractmethod
    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        """Write Canonical memories into this format. Returns warnings."""
        ...

    @abstractmethod
    def validate(self, path: Path) -> list[ValidationIssue]:
        """Validate this format's storage integrity."""
        ...
