"""OpenClaw → Canonical Memory reader.

Reads MEMORY.md index + memory/*.md files with YAML frontmatter.
Maps description→summary, metadata.type→domains[0], metadata.importance→importance_score/label.
"""

from pathlib import Path

from .models import Memory
from .plugin import Capabilities, FormatPlugin, ReadResult


class OpenClawReader(FormatPlugin):
    name = "openclaw"
    version_supported = ">=1,<3"
    capabilities = Capabilities(
        summary=True,
        importance_label=False,
        supported_kinds={"dynamic", "permanent", "emotion"},
    )

    def read(self, path: Path) -> ReadResult:
        # TODO: Phase 1
        raise NotImplementedError

    def write(self, memories, path: Path) -> list[str]:
        raise NotImplementedError("OpenClawReader is read-only")

    def validate(self, path: Path) -> list:
        return []
