"""Canonical Memory → OpenClaw writer.

Writes memory/<id>.md files + updates MEMORY.md index.
Routes by kind+status: dynamic→MEMORY.md, permanent→priority:high, emotion→feels/.
Implements SHA256-based concurrent modification detection on MEMORY.md.
"""

from collections.abc import Iterable
from pathlib import Path

from .models import Memory
from .plugin import Capabilities, FormatPlugin


class OpenClawWriter(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        importance_label=False,
        preserve_unknown_fields=False,  # MEMORY.md has no extensions slot
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path):
        raise NotImplementedError("OpenClawWriter is write-only")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        # TODO: Phase 1
        raise NotImplementedError

    def validate(self, path: Path) -> list:
        return []
