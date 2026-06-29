# memlink Specification

This directory contains the language-neutral specification for the Canonical Memory Schema.
Any implementation — in any language — can use these documents to build a compatible Reader or Writer.

## Documents

| File | Description |
|------|-------------|
| [canonical-v1.md](canonical-v1.md) | Canonical Memory Schema v1 — field definitions, types, semantics |
| [canonical-v1.schema.json](canonical-v1.schema.json) | JSON Schema for machine validation |
| [source-uri.md](source-uri.md) | Source URI format (RFC 3986 based) |

## Stability

`canonical-v1.md` is **frozen** as of memlink v1.0.

- **1.x**: additive only — new optional fields, no removals, no type changes
- **2.0**: breaking changes allowed

Implementations declaring `version_supported: ">=1,<3"` are compatible with all 1.x releases.

## Implementing a Compatible Plugin

A conforming implementation must:

1. Accept a directory path and return a list of Canonical Memory objects (`read`)
2. Accept a list of Canonical Memory objects and write them to a directory (`write`)
3. Never raise on malformed input — return warnings instead
4. Set `schema_version: "1"` on every emitted Memory
5. Preserve unknown fields in `extensions` rather than discarding them

See [canonical-v1.md](canonical-v1.md) for the full field reference.

## Python Reference Implementation

The reference implementation is [`memlink-bridge`](https://pypi.org/project/memlink-bridge/) on PyPI.

```python
from memlink import FormatPlugin, ReadResult, Memory

class MyReader(FormatPlugin):
    name = "myformat"

    def read(self, path) -> ReadResult: ...
    def write(self, memories, path) -> list[str]: ...
    def validate(self, path) -> list: ...
```
