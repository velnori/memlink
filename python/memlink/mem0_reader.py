"""mem0 offline JSON reader."""

from __future__ import annotations

from pathlib import Path

from .json_readers import read_json_format
from .plugin import Capabilities, FormatPlugin, ReadResult


class Mem0Reader(FormatPlugin):
    name = "mem0"
    version_supported = ">=1,<3"
    capabilities = Capabilities(supported_kinds={"dynamic"})

    def read(self, path: Path) -> ReadResult:
        return read_json_format(self.name, path)

    def write(self, memories, path):
        raise NotImplementedError("mem0 Reader is read-only")

    def validate(self, path):
        from .validators import validate_schema

        return validate_schema(path, source_format=self.name)
