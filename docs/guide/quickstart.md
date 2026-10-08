# Quick Start — installed local candidate

This is a local unpublished **2.0.0** candidate. Install its wheel in a clean Python environment:

```sh
python -m pip install /path/to/dist/memlink_bridge-2.0.0-py3-none-any.whl
memlink --version
memlink formats --manifest
```

Only PyYAML ≥6.0.3 is required at runtime. For installation without an index, provide the candidate and PyYAML wheels with `--no-index --find-links /path/to/wheelhouse`. Core workflows do not need an AI API/key/token. Work in a new directory; existing exports/recordings are not overwritten.

## A — Full Migration

```sh
memlink conformance --export-fixtures fixtures
memlink convert --from generic --to openclaw --source fixtures/generic --target workspace --all --format json
memlink validate --from openclaw --source workspace --level schema --format json
memlink validate --from generic --source fixtures/generic --level roundtrip --intermediate openclaw --format json
```

This converts all two approved invented records, including archived, without per-record classification. Read the receipt's real accounting/field results and keep the archive for canonical recovery. Default best effort reports partial loss honestly and completes; explicit strict blocks unallowed changes. [Full Migration](full-migration.md) explains safe migrate into existing workspaces, backups and verification.

## B — Context Handoff

```sh
memlink handoff --from openclaw --input fixtures/openclaw --all --secrets redact --out all-context --format json
memlink verify all-context --format json
memlink pack --from openclaw --input fixtures/openclaw --out private-pack --format json
memlink select private-pack --project A --out selection-a.json --format json
memlink handoff private-pack --selection selection-a.json --secrets redact --out project-a --format json
memlink verify project-a --pack private-pack --format json
```

All needs no human selection/review; selective A excludes B/profile/config/skills. Keep pack/selection private. Default secret policy is warn; examples explicitly redact. See [Handoff](context-handoff.md), [Privacy](privacy.md) and [Compatibility](compatibility.md).

These commands work in shell and PowerShell. Release readiness executes the corresponding actual README blocks in both available shells and verifies a fresh wheel outside the checkout. See [local release checks](releasing.md).
