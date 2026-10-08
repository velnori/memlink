# Full Migration

Install the local candidate wheel as described in [Quick Start](quickstart.md). Work in a new directory and export the invented fixture set. The following commands work in shell and PowerShell.

```sh
memlink conformance --export-fixtures fixtures
memlink convert --from generic --to openclaw --source fixtures/generic --target workspace --all --format json
memlink validate --from openclaw --source workspace --level schema --format json
memlink validate --from generic --source fixtures/generic --level roundtrip --intermediate openclaw --format json
```

All two approved records, including an archived record, are converted automatically. There is no review/select/classify step. Read `.memlink/receipt.json`: input/parsed/invalid/unsupported/selected/excluded/output counts, native ID mapping, actual readback, field statuses and output hashes are evidence. `.memlink/archive.json` stores transport values the target cannot express natively. Keep it beside the native files.

Default best effort completes supported work with honest `partial` / exit 0. Archive-only is recoverable canonical transport, not a native destination feature. Strict blocks unallowed changes before committing:

```sh
memlink convert --from generic --to mem0 --source fixtures/generic --target strict-blocked --all --strict --format json
```

Expected exit: **5**; `strict-blocked` is absent. `--fail-on-loss` is the same policy. Use `--allow-change FIELD` only for explicit named exceptions recorded in the receipt.

## Existing workspace

The existing target is not categorically rejected. Preview and apply the full approved set:

```sh
memlink migrate --from generic --to openclaw --source fixtures/generic --target workspace --all --on-conflict replace --dry-run --format json
memlink migrate --from generic --to openclaw --source fixtures/generic --target workspace --all --on-conflict replace --format json
memlink validate --from openclaw --source workspace --level schema --format json
```

`skip` is the default conflict policy; `replace` and `rename` are explicit. Conflicts are at **file** granularity: one daily note or offline JSON file can contain multiple records. Skip retains the old conflicting file and reports dropped incoming records. Replace backs up affected originals, stages output, checks snapshots, commits and verifies output hashes/readback. Rename keeps both through deterministic imported paths and distinct native target IDs, including repeated scoped IDs.

The synthetic recording deliberately edits a target note before applying, verifies the dry run is unchanged, shows update conflicts, compares backups with original hashes, preserves unrelated `TOOLS.md`, and verifies committed files. Run it via [Demos](demos.md).

Backups remain at `.memlink/backups/<transaction-id>/` with `restore.json`. They also remain useful after a failed apply. Stop concurrent writers before manual restore; verify current transaction output hashes, restore only listed originals, and remove only listed created files still owned by that transaction. Preserve outside modifications for reconciliation. See the exact [CLI restore contract](cli.md).

Transactions are per file, with owned rollback. They do not provide global atomicity, power-loss recovery, automatic restore/cleanup, hostile-plugin isolation or online service ingestion. Only the declared built-in file writers support safe apply. Other plugins remain export-only unless their transaction contract is verified.
