# Migrating to the local 2.0.0 implementation

The 1.x plugin API stability promise was real. This local major-version change keeps `FormatPlugin.read(path)`, `write(memories, path)` and `validate(path)` signatures, but intentionally changes unsafe or misleading behavior. Canonical-v1 remains unchanged; package 2.0.0, receipt-v1 and archive-v1 are distinct versions. Nothing in this checkout implies that 2.0.0 has been published.

| 1.x behavior | 2.0 behavior and required adjustment |
|---|---|
| Writers could write directly into nonempty targets | Public writes are transaction-wrapped exports; choose a new/empty path. Use `convert(..., mode="migrate", conflict="replace")` or CLI `migrate --on-conflict ...` for existing supported file targets. |
| Reader errors or zero parsed records could appear successful | ReadResult adds file/record ledgers, errors, variant and explicit valid-empty marker; fully unreadable inputs fail. |
| Writer returned warnings without shared safety/readback | Return type remains `list[str]`; `writer.last_receipt` exposes the real transaction result. A failing write raises `TransactionError` with receipt and exit code. |
| Naked ID merged independent sources/users | Default identity includes namespace and scope. Use the explicit audited `--link-by-id` only when appropriate. |
| Capabilities could be missing or duplicate registrations silently replaced | Concrete plugins must declare a valid `Capabilities`; separate reader/writer registration checks roles, name, version range and duplicate names. |
| Native filename sanitizer erased information or collided | Percent escaping, edge/device-name encoding and stable hash suffixes change filenames/target IDs. Follow receipt mapping; do not reconstruct paths by the old sanitizer. |
| Ombre foreign IDs were random; created time was absent | Stable identity-based IDs; canonical UTC time plus original raw/timezone transport data. |
| OpenClaw emotion output used DREAMS, default daily roundtrip was not tested | Emotion uses deterministic daily placement. DREAMS/USER require explicit input selection; legacy structured remains separate. |
| External checksum could suppress comparison; selected fields compared | Checksums are recomputed from actual bodies; full canonical/identity/duplicate comparison. Use narrow explicit comparison ignores. |
| Direct NaN/Inf/opaque object serialization could appear preserved | Canonical validation fails nonfinite/opaque values; bounded serialization rejects cycles and excessive resources. |
| CLI/version/package and support tables drifted | Single `_version.py` source; eight readers/five writers; Python classifiers match the existing 3.10–3.12 CI matrix. |

Default writer filtering is removed: callers select approved records; writers honor that selection. CLI defaults still exclude archived, while `--all` or `--include-archived` includes them. Unknown source scope remains explicitly unknown; Mem0 does not invent a default user.

For a legacy plugin, keep the three public methods, declare capabilities and return validated canonical Memory records. The wrapper calls the existing writer on staging, never the live target, and validates using the registered reader. Do not call your own public `write()` recursively from inside the raw serializer. Do not write outside the supplied staging path. See the runnable minimal shape in [Plugin API](../api/plugin.md). Unknown third-party formats can export with honest archive/unknown semantics; safe apply is enabled only for the declared built-in file targets.

`convert`, `merge`, `broadcast`, library conversion and direct public writers use the same transaction boundary. Strict-mode archive exceptions must be named fields; capabilities are not final truth. Keep `.memlink/archive.json` with outputs if canonical restoration is required. Copying only native notes loses transport-only values, even when those values were preserved in the archive.

The wheel now contains canonical schema, receipt/archive schemas, compatibility contract and `py.typed`. Fresh install uses the checkout's wheel and PyYAML ≥6.0.3. No AI service or new runtime dependency was introduced. The [CLI contract](cli.md) documents output encoding, exit codes, receipt semantics and transaction limits; [Quick Start](quickstart.md) provides reproducible fixture commands.
