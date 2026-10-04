# Context Handoff · local 2.0.0

Context Handoff is a second offline workflow alongside [Full Migration](quickstart.md).
Give another agent all approved memory records, or select a smaller set. No AI API,
key, upload, telemetry, automatic classification, or mandatory human review is involved.
This checkout is unpublished; use the source checkout or its locally built wheel.

## One command, all approved memory

After installing the local wheel:

```powershell
memlink handoff --from openclaw --input tests/fixtures/module02/openclaw --all --secrets redact --out demo-output/context-all
memlink verify demo-output/context-all
```

This synthetic demo produces five records, including archived and unresolved notes,
with `human_reviewed=false`. It does not invoke the selection CLI or ask for confirmation.
The automatically created private working pack is temporary. The final directory contains
only `context.md`, `manifest.json`, and `report.json`.

The approved input is **one explicit OpenClaw workspace directory**. Default scope is
`MEMORY.md` plus recursive Markdown in `memory/`. `--all` includes archived records;
it never implies home discovery or optional `USER.md` / `DREAMS.md`. Add
`--include-user` / `--include-dreams` deliberately to approve those files. Configuration,
credentials, session databases, skills, plugins and transport `.memlink/` files are outside
the default archive. Notes containing credentials are still notes and need a suitable secret policy.
These file roles follow the [OpenClaw memory documentation](https://docs.openclaw.ai/concepts/memory).

For an unpublished source checkout in PowerShell, first set
`$env:PYTHONPATH = (Resolve-Path python).Path` and replace `memlink` with `python -m memlink.cli`.
All bundle destinations must be new directories. Pick a new name on subsequent runs.
Existing-workspace Full Migration continues to use `migrate` and its existing conflict policies.

## Selective workflow

```powershell
memlink pack --from openclaw --input tests/fixtures/module02/openclaw --include-user --include-dreams --out demo-output/context-private
memlink verify demo-output/context-private
memlink select demo-output/context-private --project A --out demo-output/selection-a.json
memlink handoff demo-output/context-private --selection demo-output/selection-a.json --secrets redact --out demo-output/context-a
memlink verify demo-output/context-a --pack demo-output/context-private
```

The private pack contains `records.jsonl`, original approved files in `sources/`, an
`inventory.md`, a manifest, and a receipt. It preserves Canonical fields and unknown
metadata for local inspection. **Do not share or upload the private pack by default.**
The selection file is private too. Keep both outside public repositories.

The A handoff contains three complete records: the active decision, archived proposal,
and unresolved conflicting proposal. The B note, profile, dreaming review, B secret,
private extension payload, and absolute source root are absent from every public artifact.
No original source files or complete Canonical metadata are copied into the handoff.

## Selectors and optional review

`select` accepts repeatable `--source`, `--id`, `--tag`, `--project`, `--scope KEY=VALUE`,
and `--state`. Different selector types use AND; repeated values within a type use OR,
except scope clauses use AND. Tags/project/state come only from existing structured
fields. A plain note without those fields is not classified from its prose.

```powershell
memlink select demo-output/context-private --source 'memory\project-a.md' --out demo-output/selection-file.json
memlink select demo-output/context-private --tag project-a --state archived --out demo-output/selection-archived.json
memlink select demo-output/context-private --scope user_id=synthetic-owner-a --out demo-output/selection-scope.json
memlink handoff demo-output/context-private --project A --secrets redact --out demo-output/context-direct-selector
```

Inventory `record_id` distinguishes duplicate native IDs and different scopes. Bare native
IDs must be unambiguous after filters. Select whole records; selecting a mixed-topic note
does not separate its prose into projects. `--all` cannot be combined with selectors.
Omitting both explicit selection and `--all` fails with exit 2 and creates no handoff.

Each selection binds the exact private `manifest.json` SHA256 and each record digest.
Editing or regenerating the pack expires the old selection. For manual editing, preserve
the recorded digests, use `mode="selection"`, remove whole proof entries, and preserve
inventory order. Do not change IDs, version digests, or add review claims.

TTY users can use `select --interactive` for a numbered picker. Choosing records does
not claim review. `handoff --review` separately prints the **entire final sanitized,
budgeted `context.md`** and requires typing `APPROVE`; anything else declines with 130.
Only that confirmation sets `human_reviewed=true`, bound to the exact context digest.
Neither selection files nor machine checks can set that flag. Non-TTY review/picking
fails with 2; deterministic selectors, selection files and `--all` work without a TTY.

## Secrets and budgets

The default `--secrets warn` emits count-only diagnostics and **shares detected values**.
It does not ask an interactive question. Choose `redact` to replace recognized secret
values throughout shareable text/metadata, or `fail` to stop before creating output.
Private pack source inspection reports suspected credentials without altering the archive.
The deterministic checks cover common key patterns, complete PEM private keys and
explicit credential fields; they are advisory and do not provide complete DLP.

Optional private JSON rules use literal values and Python regular expressions:

```json
{"literals": ["SYNTHETIC_PRIVATE_PHRASE"], "patterns": ["private-synthetic-[0-9]+"]}
```

```powershell
memlink handoff demo-output/context-private --all --secrets redact --redact-file /path/to/private-rules.json --out demo-output/context-custom
memlink verify demo-output/context-custom --pack demo-output/context-private --redact-file /path/to/private-rules.json
```

Custom rules require `redact`. Their values remain private; the public policy records
rule counts. They apply to shareable user text and metadata, keeping structural IDs,
hashes, namespace, source format and canonical status intact. Common Windows/Unix,
UNC, tilde and file-URL paths are scrubbed. These checks cannot identify every private
fact, encoded secret or unusual path. Inspect the result when that matters.

Default limits are **1 MiB UTF-8 `context.md`** and **1,000 records**, not exact model tokens.
Over-budget output fails with 2. Nothing is silently cut mid-record.

```powershell
memlink handoff demo-output/context-private --all --secrets redact --max-records 2 --truncate-at-record-boundary --out demo-output/context-prefix
memlink verify demo-output/context-prefix --pack demo-output/context-private
```

Explicit truncation keeps a complete prefix in inventory order and records excluded
opaque record IDs/digests in the receipt. A budget too small for one record fails.
Review, if requested, happens after redaction and truncation. Underlying bundle artifacts
must also satisfy the existing 16 MiB per-file, 256 MiB root and serialization limits.

## What verification proves

`verify` checks versioned schemas, the exact file/directory set, byte sizes and hashes,
source/record references, scopes, approval, review evidence, secret policy and budget.
Private pack verification reparses actual archived source bytes through the existing
OpenClaw Reader and compares Canonical data and inventory. Public verification renders
the approved projection again and requires byte-for-byte equality with `context.md`.
All-record approval includes a commitment to the complete pack inventory.

`verify HANDOFF --pack PRIVATE_PACK` additionally recomputes the actual projection from
the original private records. Custom redaction requires the original private rules.
Standalone verification checks internal consistency; it cannot independently reconstruct
omitted records, original secret values or the original private approval.

Retain the `manifest_sha256` from `verify --format json` separately and later supply
`--expected-sha256 DIGEST`. Hashes are not signatures. A fully self-consistent rewrite
of content, manifest and receipt can pass standalone verification; an external trusted
digest or original trusted pack detects such a change. Verification does not prove author
identity, factual truth, a human's identity, or prompt-injection immunity.

Source snapshots check approved content during scanning and again before/after commits.
They do not freeze a running agent, detect every transient change-and-revert, or provide
global atomicity/power-loss recovery. Failures roll back only owned unchanged files;
concurrent external files are preserved. See the [threat model](context-privacy.md).

For explicit consumption, use the [Codex](handoff-codex.md) and
[Claude Code](handoff-claude-code.md) tutorials. Client reading/model answering is separate
from file generation and integrity verification. Long-term saved memory is outside this feature.
