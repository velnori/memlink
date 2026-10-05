# Context bundle / selection / report v1

This additive contract leaves Canonical-v1, Reader/Writer plugin APIs and Full Migration
receipts unchanged. First input is the documented OpenClaw file workspace. Conversion
remains Reader → Canonical → Writer; a handoff writer produces a controlled text projection.

## Schema assets

Maintained JSON Schema draft 2020-12 files are mirrored verbatim into
`python/memlink/resources/` and packaged in the wheel:

- `memlink-context-bundle-v1.schema.json`: private-pack/handoff manifests.
- `memlink-context-selection-v1.schema.json`: explicit digest-bound approval.
- `memlink-context-record-v1.schema.json`: closed shareable projection fields.
- `memlink-context-report-v1.schema.json`: additional context receipt fields.

Runtime uses the existing offline instance validator plus closed-field, conditional-kind
and cross-artifact checks. It resolves no network schema references. Reports also satisfy
the existing `memlink-receipt` v1 schema, use `operation="export"`, and add `bundle_kind`,
`human_reviewed`, `review`, `policy`, `accounting`, and handoff `safety`/`budget`.
Content fields in context receipts contain fixed classification labels, not original values.

## Scope and identity

`scope.format="openclaw"`; rules are ordered `MEMORY.md`, `memory/**/*.md`, then optional
`USER.md` and `DREAMS.md` in that order. They approve only one supplied workspace, including
archived records. Optional files require explicit flags. Other roots/config/credentials,
session stores, skills/plugins and `.memlink/` recovery sidecars are not imported.

`namespace` uses the existing `openclaw:<SHA256(canonical absolute root)[:20]>` identity.
Canonical identity is namespace + existing structured scope + native ID. Duplicate
occurrences are preserved: `record_id = "r-" + SHA256(stable_json([identity, occurrence]))`.
`source_ref = "s-" + SHA256(source_relative_path)[:24]`. Missing scope stays `{scope: unknown}`.
No LLM or text-based inference supplies scope, tags, project or state.

Private identity retains the existing codec's JSON-compatible scope values. A complex
scope value is not copied into a public identity: its slot explicitly says
`unknown: structured scope retained privately`; the original identity still binds the
opaque record ID/digest. Simple structured scope values are retained and can be redacted.

Source discovery/copy/read and final commit compare approved file bytes, sizes and mtimes.
Copies provide a bounded view for the existing Reader. Native content is reparsed during
private verification. These checks do not freeze an active workspace or claim global atomicity.

## Private pack

Exact files are manifest, receipt, `records.jsonl`, `inventory.md` and the approved original
files under `sources/`. `scope.approved_root` exists only here. Manifest `sources` commit to
raw bytes/path/reference; `snapshot_sha256` hashes that ordered descriptor array. Reader
variant, accounting, warnings and raw-source suspected credential count are retained privately.

Each JSONL envelope stores `record_id`, `identity`, zero-based `occurrence`, `source_ref`,
structured `labels`, complete serialized Canonical `memory`, and `sha256`. The envelope
SHA256 is over stable JSON excluding its own `sha256`. Unknown fields remain in Canonical
extension layers and/or exact raw source bytes. Manifest record descriptors match envelopes.
Verification compares both envelopes and inventory to an actual Reader readback of sources.

Stable JSON follows the existing codec: UTF-8, sorted keys, compact separators, finite
values, normalized UTC timestamps and existing serialization resource limits.

## Selection

Required fields: `schema="memlink-context-selection"`, `version="1"`, private
`pack_sha256` (SHA256 of exact manifest bytes), `mode=all|selection`, UTC `created_at`,
and an ordered nonempty `records` array of `{record_id, sha256}` proofs.

Selection must be a unique ordered subset of the verified inventory. `all` requires the
complete array. Regenerated/edited packs invalidate old approval. Selection has no review
flag, selectors cannot imply hidden full approval, and missing selection/intent fails.

## Handoff

Exact files are `context.md`, manifest and receipt. No sources/JSONL/inventory/unknown
metadata/selection/rule file is permitted. Projection fields are closed: record ID and
original digest, sanitized identity/source-relative path, title, summary/body, kind,
canonical status, explicit state, structured tags/project and timestamps.

`approval` records the private manifest digest, total pack record count and an opaque digest
of its complete proof array, the requested proofs, mode and budget exclusions. `all` must
match that complete inventory commitment. Selective mode discloses no unselected titles,
scope values or source filenames. Excluded budget items use only opaque ID/digest/reason.
Only used source references appear in public `sources`.

`context.md` has a fixed reference-material header followed by complete record sections.
All caller text/metadata is fenced; fence length exceeds every backtick run in its payload.
Control/bidi chars are escaped, common local paths scrubbed, and URL/HTML/instruction text
is never executed/fetched/promoted in authority. Unknown fields remain private. Explicit
unknown/unresolved/archived states are shown without semantic conflict resolution.

## Policy, budget and review

`policy.secrets=warn|redact|fail`; literal/pattern rule counts are recorded without values.
Warn retains suspected values with warnings. Redact replaces values using `[REDACTED]`;
no alternate original copy is emitted. Fail stops on suspected credentials before output.
Private pack policy is `private` and deliberately preserves complete source data.

Handoff `safety` records detected credential occurrences, introduced output redaction
markers, scrubbed paths, and strings with escaped controls. Standalone verification
rescans known credential/path/control patterns, checks policy and marker consistency;
original custom rules plus `verify --pack` recompute the complete projection.

Budget applies to all UTF-8 bytes of `context.md`, including header/metadata/fences, and
complete record count. Defaults: 1 MiB and 1,000 records. Positive caller budgets are
bounded by artifact/record resource limits. Default overflow fails; explicit truncation
keeps a complete ordered prefix and records every excluded approved proof. Zero fitting
records fails. Exact model tokens are not estimated or promised.

No-review sets `human_reviewed=false`, `review=null`. Optional TTY review shows exactly
the sanitized budgeted bytes, then requires `APPROVE`. True review evidence contains
`method=tty-confirmation`, that `context_sha256`, and `decision=approved`. Decline exits 130.
Machine checks and selection files cannot elevate this state.

## File integrity and trust

Manifest `files` hashes/sizes every artifact except the manifest itself. Receipt `outputs`
hashes data artifacts, excluding receipt and manifest to avoid self-reference. Receipt
and manifest metadata must match recomputed results exactly; missing/extra files and
directories fail. A retained external manifest SHA256 can be required during verification.

Standalone verification establishes internal consistency. `verify --pack` additionally
checks original admission, full inventory commitment, scope, projected text/policy/budget
against an actual verified private pack. Hashes are not signatures and do not authenticate
author identity, factual truth or a human. Rewriting all artifacts consistently can pass
without a trusted external anchor. See the user-facing privacy/threat model.

New-directory exports reuse existing exclusive-write, competition-check and owned-rollback
primitives. The manifest is committed last, followed by real final readback and source checks.
Handled failures roll back owned unchanged outputs and do not leave a completed bundle;
external concurrent modifications are preserved and reported. Power-loss recovery is not claimed.
