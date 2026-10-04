"""Canonical Memory data model — language-neutral intermediate representation.

See spec/canonical-v1.md for the full schema specification.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Union

# JSON-compatible value type (recursive)
JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]

# Characters forbidden in filenames on Windows + Linux
_FILENAME_RESERVED = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names
_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def sanitize_id(raw: str) -> str:
    """Convert an arbitrary string into a safe filename.

    Rules:
      1. Reserved characters → percent-encode (reversible).
      2. Unicode (中文/emoji) is preserved.
      3. Long UTF-8 names use a stable hash suffix, leaving room for extensions.
      4. Edge dots/spaces and Windows device names are percent-encoded.
      5. Empty string falls back to ``"%EMPTY"``.
    """

    def _encode(m: re.Match) -> str:
        return f"%{ord(m.group(0)):02X}"

    out = _FILENAME_RESERVED.sub(_encode, raw.replace("%", "%25"))
    # Encode edge dots/spaces; never erase information.
    leading = len(out) - len(out.lstrip(". "))
    trailing = len(out.rstrip(". "))
    out = "".join(f"%{ord(c):02X}" if i < leading or i >= trailing else c for i, c in enumerate(out))

    if out.split(".")[0].upper() in _RESERVED_NAMES:
        out = f"%{ord(out[0]):02X}" + out[1:]

    # Truncate to 255 UTF-8 bytes without splitting a multi-byte character.
    encoded = out.encode("utf-8")
    if len(encoded) > 180:
        out = (
            encoded[:140].decode("utf-8", errors="ignore") + "~" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        )

    return out or "%EMPTY"


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
