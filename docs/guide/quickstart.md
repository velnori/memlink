# Quick Start — Full Migration and Context Handoff

This is an unpublished **2.0.0** local candidate. Start from the checkout in a clean Python **3.10–3.12** environment:

```sh
git clone https://github.com/velnori/memlink.git
cd memlink
python -m venv .venv
```

Activate it with `source .venv/bin/activate` on macOS/Linux, or `.\.venv\Scripts\Activate.ps1` in PowerShell. Then install from the checkout:

```sh
python -m pip install .
memlink --version
```

Expected: `memlink 2.0.0`. The package name is `memlink-bridge`; the examples need this checkout or a locally built candidate wheel. If a wheel is already available, install it instead:

```sh
python -m pip install /path/to/dist/memlink_bridge-2.0.0-py3-none-any.whl
memlink --version
memlink formats --manifest
```

Only PyYAML ≥6.0.3 is required at runtime. Installation may access the package index. For installation without an index, provide the candidate and PyYAML wheels with `--no-index --find-links /path/to/wheelhouse`. Core workflows do not need an AI API/key/token. Run A and B in the same new working directory, outside the checkout; existing exports/recordings are not overwritten.

## Create a trial directory

Keep the environment activated. From the checkout, create a **new sibling directory** and run A, then B there. Choose a different name if `memlink-trial` already exists.

macOS / Linux (POSIX shell):

```sh
mkdir ../memlink-trial
cd ../memlink-trial
```

PowerShell:

```powershell
New-Item -ItemType Directory -Path ../memlink-trial -ErrorAction Stop | Out-Null
Set-Location ../memlink-trial
```

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
