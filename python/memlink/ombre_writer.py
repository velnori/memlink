"""Canonical Memory → Ombre Brain writer.

Writes ombre-buckets/{type}/{domain}/{id}.md with YAML frontmatter.
Maps Canonical fields back: kind→type, emotion→feel, importance_score→importance.
"""

from collections.abc import Iterable
from pathlib import Path

from .models import Memory
from .plugin import Capabilities, FormatPlugin


class OmbreWriter(FormatPlugin):
    name = "ombre"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=True,
        importance_label=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path):
        raise NotImplementedError("OmbreWriter is write-only")

    def write(self, memories: Iterable[Memory], path: Path) -> list[str]:
        # TODO: Phase 2
        raise NotImplementedError

    def validate(self, path: Path) -> list:
        return []
