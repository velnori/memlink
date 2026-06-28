"""Ombre Brain → Canonical Memory reader.

Reads ombre-buckets/**/*.md files with YAML frontmatter.
Maps Ombre fields: type→kind, feel→emotion, domain→domains, importance→importance_score.
"""

from pathlib import Path

from .models import Memory
from .plugin import Capabilities, FormatPlugin, ReadResult


class OmbreReader(FormatPlugin):
    name = "ombre"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        emotion=True,
        importance_label=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path) -> ReadResult:
        # TODO: Phase 1
        raise NotImplementedError

    def write(self, memories, path: Path) -> list[str]:
        # OmbreReader only reads; writing is OmbreWriter
        raise NotImplementedError("OmbreReader is read-only")

    def validate(self, path: Path) -> list:
        # TODO: Phase 0.5
        return []
