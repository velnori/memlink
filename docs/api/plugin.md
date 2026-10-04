# Plugin API · 2.0 behavior

The historical 1.x stability promise is preserved in the source. The three public `FormatPlugin` signatures remain `read(path) → ReadResult`, `write(memories, path) → list[str]`, and `validate(path) → list[ValidationIssue]`. Safety and stricter behavior require the local major version 2.0.0; see [migration notes](../guide/migration-2.0.md).

Concrete classes must declare a unique `name` matching `[a-z][a-z0-9_-]*`, a `Capabilities` instance with version `1`, and a numeric canonical version range compatible with `1` (default `>=1,<3`). Register reader/writer roles separately with `register_reader` / `register_writer`, or their `memlink.readers` / `memlink.writers` entry points. A duplicate different class, malformed capability/version/name or abstract class fails registration. Identical-class re-registration is idempotent. Reader-only/writer-only lookup follows those separate registrations; a role implementation that cannot return valid data fails guarded validation rather than producing success.

Capabilities are preflight hints. They never prove final preservation. The writer wrapper stages the existing raw writer, uses the registered reader for actual native readback, checks paths/hashes, records canonical archive transport and commits/rolls back. Direct `writer.write()` is an export into a new/empty target, not an overwrite method. Success keeps warnings return type and sets `writer.last_receipt`; failure raises `TransactionError`. Legacy plugins also pass through this wrapper. Safe migrate is restricted to the built-in declared file targets.

`writer.write(memories, target_path)` accepts already materialized canonical memories and only manages the target path. `Memory.source.path` is provenance, often a relative path or record location; it is not an approved filesystem root and is never implicitly opened for source checks. The caller owns materialization and any source reads outside this entrypoint. For a managed path conversion, use `memlink.converter.convert(reader, writer, source_path, target_path, ...)`, which captures the read ledger and checks source changes before commit.

At the lower transaction level, `memlink.transaction.execute_output(..., sources=[...], source_contexts=[...])` and `OutputTransaction.execute()` require exactly one context per managed source, in the same order, obtained from `memlink.converter.read_source(reader, path, ...)`. Missing or mismatched contexts fail with `TransactionError` / exit code 2 before staging or target writes. Contexts without matching source paths also fail. File-set and content changes since the read fail with code 4 before commit. With no managed sources and no contexts, materialized-memory export remains valid. A fresh snapshot taken only after materialization would miss changes since the read; therefore the transaction requires the actual read context instead of silently constructing one later.

ReadResult retains memories/warnings/stats and adds files, records, errors, variant and valid_empty. Returned Memory objects are schema-checked. Use `source` to locate native output records; invalid/unsupported entries require explicit accounting. A legitimate empty set is not a successful roundtrip. JSON-compatible metadata/extensions, finite numbers and bounded serialization are required. Canonical-v1 requires `schema_version` and ID; body/time are optional. Emotion valence/arousal ranges are 0–1, not -1–1.

## Minimal legacy-style plugin shape

This example keeps the original signatures. The serializer receives staging; it never manages the live target or calls its own public `write()` recursively.

```python
import json
from pathlib import Path
from memlink.codec import memory_dict, memory_from_dict
from memlink.models import Source
from memlink.plugin import Capabilities, FormatPlugin, ReadResult
from memlink.registry import register_reader, register_writer
from memlink.validators import validate_memory

class ExampleJSON(FormatPlugin):
    name = "example-json"
    capabilities = Capabilities()

    def read(self, path: Path) -> ReadResult:
        file = path if path.is_file() else path / "records.json"
        rows = json.loads(file.read_text(encoding="utf-8"))
        memories = [memory_from_dict(row) for row in rows]
        for memory in memories:
            memory.source = Source(self.name, file.name)
        return ReadResult(memories, valid_empty=not rows, variant="records-array-v1")

    def write(self, memories, path: Path) -> list[str]:
        (path / "records.json").write_text(
            json.dumps([memory_dict(m) for m in memories], ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        return []

    def validate(self, path: Path):
        return [issue for m in self.read(path).memories for issue in validate_memory(m)]

register_reader(ExampleJSON)
register_writer(ExampleJSON)
```

Native semantics of an unlisted third-party format are unknown; its complete canonical values can be archive-only rather than “native-preserved” despite successful raw readback. To customize a built-in format, retain its declared mapping and demonstrate actual native equivalence; do not inflate capabilities. For custom production JSON input, add duplicate-key, shape, scope and invalid-record handling instead of relying on this minimal serializer example.

Plugin code is trusted Python code, not an executable sandbox. A malicious plugin can run arbitrary Python; the transaction contract constrains cooperative plugin output, not hostile Python execution. No adapter/entry-point should make network access a core prerequisite.
