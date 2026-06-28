"""FormatPlugin — unified interface for format readers and writers.

Each AI memory format implements one plugin with three methods:
  read()     → Format → Canonical
  write()    → Canonical → Format
  validate() → Format-specific integrity checks
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

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
    capabilities: Capabilities = field(default_factory=Capabilities)

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
