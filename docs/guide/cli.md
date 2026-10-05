# CLI contract · local 2.0.0

This document describes the current checkout, not a published release. Run `python -m memlink.cli` with the repository's `python/` on `PYTHONPATH`, or use `memlink` after installing the local wheel. See [Quick Start](quickstart.md) for fixture-backed commands and [2.0 migration](migration-2.0.md) for compatibility changes.

## Commands

| Command | Inputs and behavior |
|---|---|
| `convert` | `--from/-f FORMAT` (default `auto`), `--to/-t FORMAT`, `--source/-s PATH`, `--target/-T PATH`; export into a new/empty target |
| `migrate` | Same source/target arguments; existing file workspace; `--on-conflict skip\|replace\|rename` (default `skip`) |
| `ombre2claw`, `claw2ombre` | Conversion aliases; source/target arguments; use new/empty targets |
| `merge` | `--sources/-s FORMAT:PATH ...`, `--to/-T FORMAT:PATH`; sources may also be supplied by repeated `--sources` |
| `broadcast` | `--from/-f FORMAT:PATH`, `--to/-T FORMAT:PATH ...`; repeated `--to` is also supported |
| `validate` | `--source/-s PATH`, `--from FORMAT` (default `auto`), `--level schema\|semantic\|roundtrip`, `--intermediate FORMAT`, `--output-mode daily-notes\|structured`, `--format pretty\|json` |
| `diff` | `--source/-s PATH1 PATH2`, `--from-1 FORMAT`, `--from-2 FORMAT`, `--ignore FIELDS`, `--format pretty\|json` |
| `stats` | `--source/-s PATH`, `--from FORMAT`; counts and UTC date range |
| `inspect` | One file/path, `--format/-f FORMAT`, optional exact `--id ID`; missing IDs/files fail |
| `formats` | Actual registered reader/writer roles; eight built-in readers, five writers |
| `pack` | `--from openclaw --input WORKSPACE --out NEW_DIRECTORY`; complete private approved memory archive; optional `--include-user` / `--include-dreams` |
| `select` | `PRIVATE_PACK --out NEW_JSON`; explicit `--all`, repeatable source/ID/tag/project/scope/state selectors, or optional TTY `--interactive` |
| `handoff` | `PRIVATE_PACK --selection JSON` / explicit selectors / `--all`, or `--from openclaw --input WORKSPACE --all`; `--out NEW_DIRECTORY`, optional exact-text TTY `--review` |
| `verify` | `BUNDLE`, optional `--expected-sha256 DIGEST`, `--pack PRIVATE_PACK`, `--redact-file PRIVATE_RULES`, `--format pretty\|json`; offline bundle consistency/provenance checks |

`--version`, command `--help/-h` are available. Format auto-detection must be unambiguous. Multiple unrelated JSON candidates fail; explicit format does not mean “pick the first arbitrary JSON”. `inspect --format` selects the input adapter, unlike the output-format switch on conversion commands.

The CLI configures stdout and stderr as UTF-8 before parsing arguments. Redirected and piped output uses UTF-8 without a BOM, including machine JSON, pretty output and diagnostics; `PYTHONUTF8` / `PYTHONIOENCODING` are not required. Consumers must decode these bytes as UTF-8. Unicode characters, including emoji, retain their values in JSON. Unpaired surrogate code points are escaped rather than causing an encoding failure. An enclosing shell or text consumer can re-encode captured output; byte-preserving redirection retains this CLI contract.

A JSON directory represents one preferred/unique top-level export, not a recursive collection of independent exports. Its other files are listed as excluded/unsupported in the file ledger. `--all` selects every record in that declared input variant. To combine independent exports, pass their exact files as separate merge sources. Markdown workspace adapters discover their documented notes recursively.

## Conversion options

Context commands have a separate additive contract in the [Handoff guide](context-handoff.md).
They do not change migration defaults. Handoff `--secrets warn|redact|fail` defaults to warn,
which retains detected values without an interactive prompt. UTF-8 context budgets default
to 1 MiB/1,000 complete records; overflow fails unless `--truncate-at-record-boundary` is
explicit. Source/include flags cannot expand an existing pack's approved scope. Context
`--all` cannot be combined with selectors, and missing explicit approval never silently
selects everything. Bundle exports require new directories; selective and all-record outputs
are independently verified. Review decline exits 130; no-review stays `human_reviewed=false`.

The remaining options in this section apply to Full Migration only.

These apply to convert, migrate, aliases, merge and broadcast:

| Option | Contract |
|---|---|
| `--all` | Include all parseable records inside the supplied approved root, including archived records. Never scan home or the whole computer. |
| `--include-archived` | Include archived without selecting the `--all` intent. Default selection excludes archived. |
| `--kind/-k KIND ...`, `--domain/-d DOMAIN ...`, `--status active\|archived` | Actual selection filters; excluded records do not enter the output archive. `--all` does not disable explicit filters. |
| `--include-user`, `--include-dreams` | Explicitly include the OpenClaw user model or dreaming review surface; neither is implied by `--all`. |
| `--output-mode daily-notes\|structured` | OpenClaw writer only; default daily notes and legacy structured are independently tested. |
| `--dry-run` | No staging, locks, output directories, receipts on disk, or mtime changes; plan-only JSON marks fields `unknown`. It cannot prove serialization/readback. |
| `--strict`, `--fail-on-loss` | Same policy: fail with 5 before committing any meaningful unallowed archive-only, transformed, dropped or unknown field/input impact. Null/empty defaults alone do not imply loss. |
| `--allow-change FIELD` | Repeatable exception for a published canonical field; narrow and recorded in the receipt. Invalid field names fail. |
| `--format pretty\|json` | Pretty output always shows warnings; JSON carries the versioned receipt. |
| `--verbose/-v`, `-vv` | Add source accounting and record mapping; second level adds per-field impacts in pretty output. |

Default best effort finishes successfully at process level when the transaction succeeds. Its receipt is `partial` if warnings/field impacts exist. Invalid or unsupported source entries are accounted for; a mixed usable source can proceed with warnings. An entirely unreadable/unsupported source fails. A defined empty JSON array can pass schema validation, but cannot pass roundtrip as “zero records preserved”.

## Merge, comparison and broadcast

Merge groups by source namespace + scope + native ID. Same bare IDs in different roots/users remain separate. `--link-by-id` is an explicit audited override. `--on-conflict newest|oldest|first|last` chooses only within the resulting identity group. Datetimes compare in UTC; naive values assume UTC, epoch 0 is dated, and dated records precede undated choices. Ties retain the earlier record; `first`/`last` follow input order.

Diff compares all canonical fields, identities and duplicate occurrences. External checksum claims do not bypass body comparison. `--ignore` accepts comma-separated canonical field names and the groups `importance` and `timestamps`; it is not a blanket loss waiver for migration.

Broadcast reads one source snapshot and executes an independent transaction per target. Any target failure makes the overall exit code nonzero. Successful destinations remain committed; there is no cross-target rollback guarantee.

## Receipt and restore

Native output, `.memlink/archive.json` and `.memlink/receipt.json` form one transport result. The archive stores only selected canonical records and original identity. Native-preserved means equality established through the actual native adapter without archive recovery; comments/sidecars cannot prove native semantics. Transformed/archive-only fields carry archive locations. Stale archive hashes produce a warning and use current native data; malformed/unknown-version archives fail validation.

Migrate handles conflicts at **file** granularity. A daily note can hold multiple records; Mem0/Zep exports are grouped JSON files. `skip` leaves the whole conflicting file unchanged and reports selected incoming records as dropped. `replace` backs up then replaces that file. `rename` retains both using deterministic imported/segment paths. An unchanged native file whose canonical archive would change is also a conflict.

Replacement backups remain at `.memlink/backups/<transaction-id>/`. `restore.json` lists replaced files, saved originals and newly created paths. Backups are not automatically deleted. To restore manually: stop concurrent writers; inspect the matching receipt/manifest; confirm current files still match that transaction's output hashes; copy saved originals back to their listed paths; remove only listed created paths that still match the transaction's outputs. Restore the old receipt/archive when listed. If a file has changed externally, preserve it and reconcile manually. There is no automatic restore CLI or power-loss recovery claim.

The transaction rejects overlapping roots, links/reparse points/hardlinks, collisions and bounded-resource violations. It stages/readbacks, checks source and target snapshots before commit, verifies committed outputs, and rolls back only its own unchanged writes on failure. An external change is retained and incomplete rollback is reported. Cooperative locks do not prevent arbitrary outside programs writing in the final per-file check/write window. No global multi-file atomicity is promised.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Command completed; inspect receipt for `success`, `partial` or dry-run `planned` |
| 1 | Diff found differences |
| 2 | Invalid input/format/schema/arguments or failed validation |
| 3 | I/O/commit failure; broadcast returns 3 if any target fails |
| 4 | Source/target changed during reading/planning/commit checks |
| 5 | Strict-mode incompatibility or unsupported safe migration target |
| 130 | User interrupted |

Reader-only transcript/stream formats have no writer and cannot perform a return trip to themselves. All core commands are local and require no AI API keys or network access.
