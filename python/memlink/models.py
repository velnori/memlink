"""Canonical Memory data model — language-neutral intermediate representation.

See spec/canonical-v1.md for the full schema specification.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Union

# JSON-compatible value type (recursive)
JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]

# Characters forbidden in filenames on Windows + Linux
_FILENAME_RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names
_RESERVED_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})


def sanitize_id(raw: str) -> str:
    """Convert an arbitrary string into a safe filename.

    Rules:
      1. Reserved characters → percent-encode (reversible).
      2. Unicode (中文/emoji) is preserved.
      3. Length ≤ 255 bytes (UTF-8).
      4. Windows device names get a leading underscore.
      5. Empty string falls back to ``"unnamed"``.
    """

    def _encode(m: re.Match) -> str:
        return f"%{ord(m.group(0)):02X}"

    out = _FILENAME_RESERVED.sub(_encode, raw)
    out = out.strip(". ")

    if out.upper() in _RESERVED_NAMES:
        out = f"_{out}"

    # Truncate to 255 UTF-8 bytes without splitting a multi-byte character.
    encoded = out.encode("utf-8")
    if len(encoded) > 255:
        out = encoded[:255].decode("utf-8", errors="ignore")

    return out or "unnamed"


@dataclass
class Source:
    """Origin of a memory within its native format."""

    format: str  # "ombre" | "openclaw" | "mem0" | ...
    path: str  # relative path within the format's storage
    uri: str | None = None  # "ombre://dynamic/user/abc"


@dataclass
class Relationship:
    """Directed link between two memories."""

    target_id: str
    type: str  # recommended: relates_to | parent | child | derived_from
    weight: float | None = None


@dataclass
class Memory:
    """Canonical Memory — the universal intermediate representation.

    Design philosophy: lossless transport, not a standardization judge.
    Preserve original values rather than normalizing them.
    """

    schema_version: Literal["1"] = "1"

    # Identity
    id: str = ""
    name: str | None = None
    source: Source | None = None

    # Content
    summary: str | None = None
    body: str | None = None

    # Classification (kind is open string, not closed enum)
    kind: str = "dynamic"  # recommended: dynamic | permanent | emotion
    status: Literal["active", "archived"] = "active"

    # Tags & domains
    tags: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    # Time (UTC RFC 3339)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Emotion (Russell's circumplex model, 0.0–1.0)
    valence: float | None = None
    arousal: float | None = None

    # Importance (not normalized — preserve native values)
    importance_score: float | None = None
    importance_label: str | None = None

    pinned: bool = False

    # Content integrity
    checksum: str | None = None  # SHA256(body)

    # Extension layers
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    extensions: dict[str, JSONValue] = field(default_factory=dict)

    # Relationships (v0 reserved — stored in metadata.memlink.relationships)
    relationships: list[Relationship] = field(default_factory=list)
