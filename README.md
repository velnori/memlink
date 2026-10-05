# MemLink

**Move AI memory between tools — locally, with verifiable loss reports.**

Migrate everything automatically, or hand off only the context you choose. No AI API required.

[![CI](https://github.com/velnori/memlink/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/velnori/memlink/actions/workflows/test.yml?query=branch%3Amain)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![Published version](https://img.shields.io/pypi/v/memlink-bridge?label=PyPI%20published)](https://pypi.org/project/memlink-bridge/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

This checkout is the **local 2.0.0 release candidate**, not a published release. Install its wheel in a clean Python environment: `python -m pip install /path/to/dist/memlink_bridge-2.0.0-py3-none-any.whl`. The only runtime dependency is PyYAML ≥6.0.3. For installation without an index, supply both wheels with `--no-index --find-links /path/to/wheelhouse`. Installation may access the package index; core workflows run offline.

Run these examples in a new working directory. The fixtures are invented, MIT-licensed data. Release readiness executes these command blocks in shell and PowerShell.

## Quickstart A — Full Migration

Convert the entire approved source, including archived records, in one command. No per-record selection or manual classification is required.

<!-- release-example -->
```sh
memlink conformance --export-fixtures fixtures
memlink convert --from generic --to openclaw --source fixtures/generic --target migration --all --format json
memlink validate --from openclaw --source migration --level schema --format json
memlink validate --from generic --source fixtures/generic --level roundtrip --intermediate openclaw --format json
```

The target contains native notes, `.memlink/archive.json` and `.memlink/receipt.json`. The receipt reports actual native readback and field differences. Default **best effort** completes supported conversion; `partial` with exit 0 honestly reports archive-only or transformed values. Keep the archive to restore those canonical values. `--strict` / `--fail-on-loss` stops unallowed changes before committing and exits 5.

For an existing approved workspace, use `migrate --on-conflict skip|replace|rename`; default is `skip`. A dry run shows conflicts without writes. Apply stages output, verifies readback, checks source/target competition, backs up replacements and commits per file. See the [Full Migration tutorial](docs/guide/full-migration.md) for conflicts, backups, verification and restore limits.

## Quickstart B — Context Handoff

`--all` creates reference context from the entire approved OpenClaw memory scope, without a selection or review prompt. Machine verification remains active.

<!-- release-example -->
```sh
memlink handoff --from openclaw --input fixtures/openclaw --all --secrets redact --out context-all --format json
memlink verify context-all --format json
memlink pack --from openclaw --input fixtures/openclaw --out private-pack --format json
memlink select private-pack --project A --out selection-a.json --format json
memlink handoff private-pack --selection selection-a.json --secrets redact --out project-a --format json
memlink verify project-a --pack private-pack --format json
```

The selective example excludes project B, profile, configuration and skills. Share `project-a/context.md` or its verified bundle; keep the full pack and selection private. Default `--secrets warn` retains detected values; these examples explicitly choose `redact`. Review is optional with `--review` and exact-text TTY confirmation. No-review receipts record `human_reviewed=false`. See [Handoff](docs/guide/context-handoff.md) and [privacy/threat model](docs/guide/privacy.md).

## Exact file compatibility

| Adapter | Reader | Writer / safe migrate | Scope |
|---|---|---|---|
| `generic` | yes | yes | Plain Markdown / YAML frontmatter; generated canonical notes |
| `openclaw` | yes | yes | Plain MEMORY + recursive memory notes; framed daily output; separate legacy structured variant |
| `ombre` | yes | yes | Bucket Markdown under dynamic/permanent/feel |
| `mem0` | yes | yes, offline files | Results/array JSON; scoped user/agent/run records |
| `zep` | yes | yes, offline files | Facts/results/array/session-summary JSON |
| `chatgpt` | yes | no | Conversation transcript export; active text branch |
| `claude_export` | yes | no | Conversation transcript export; supported text blocks |
| `stream-summary` | yes | no | `memlink-stream-summary-v1` Markdown |

The [machine-readable manifest](python/memlink/resources/compatibility-manifest-v1.json), also available as `memlink formats --manifest`, records exact structures, source review dates, synthetic fixture authorization, field rules, verification layers and limitations. **Verified refers to those fixture/file layers**, not every brand version or model memory semantics. [Compatibility and loss classification](docs/guide/compatibility.md) explains the scope.

Handoff pack currently accepts **OpenClaw only**. OpenClaw `USER.md` and `DREAMS.md` need explicit flags even with `--all`; configuration, credentials, sessions, skills and plugins are excluded. Mem0/Zep writers create offline JSON, with no online import or connector claim. ChatGPT/Claude exports are transcripts, not Saved Memory. Markdown support does not promise complete Obsidian/Logseq/Bear semantics.

## Verify an adapter or bundle

```sh
memlink conformance --adapter openclaw --report openclaw-conformance.json
memlink conformance --adapter openclaw --fixtures fixtures --report contributed-conformance.json
memlink verify project-a --pack private-pack --format json
```

Conformance is installed with the wheel and needs no test framework. It checks independent goldens, accounting, identity/scope, native readback, canonical archive roundtrip, deterministic output, paths/collisions/links, existing-target transactions, policy/exit codes, rollback, schemas, bundle integrity, network canaries and package version. Results distinguish `PASS`, `FAIL`, and `NOT_RUN`; unavailable OS layers stay unverified. Golden updates need a reviewed diff and reason. See [Contributing](CONTRIBUTING.md).

## Architecture / Developer

```text
                 Reader → Canonical → Writer
                          /         \
                Full Migration   Context Handoff
```

MemLink remains an **AI Memory Interchange Layer**. Canonical is the language-neutral intermediate representation, independent of adapters. Canonical-v1 is frozen; package 2.0.0, canonical-v1, receipt-v1 and bundle-v1 are separate version dimensions. Capabilities are advisory; final preservation comes from actual output and target readback. Default identity is source namespace + scope + native ID. [Architecture](docs/guide/architecture.md), [Plugin API](docs/api/plugin.md), [DESIGN](docs/DESIGN.md), and [1.0.11 → 2.0 upgrade](docs/guide/migration-2.0.md) retain the original interchange and plugin direction.

## Privacy, limits and release evidence

Full Migration, Handoff, receipts and verification use no AI API, key/token, upload or telemetry. They are deterministic local file operations. Future Online Connectors must be optional with separate cost/privacy/authorization contracts. See [no-network/no-API](docs/guide/no-network.md) and [security reporting](SECURITY.md).

Limits are enforced: 16 MiB/file, 256 MiB/scanned root, 10,000 files, 100,000 records, depth 100 and 100,000 serialization nodes. Archives must also fit these limits, so record count alone does not predict success. Handoff defaults to 1,000 records / 1 MiB of UTF-8 context. See [synthetic benchmark and failure modes](docs/guide/benchmark.md); no unlimited claim is made.

Transactions provide per-file commits and owned rollback, not global multi-file atomicity or power-loss recovery. Symlinks, junctions, hardlinks and overlapping storage roots are rejected. Third-party plugins are trusted Python code. Hashes prove consistency, not authorship. Redaction is advisory, not complete DLP; reference text cannot guarantee a consumer model's prompt-injection resistance or future recall.

The [release guide](docs/guide/releasing.md) provides one-command readiness, wheel/sdist hashes, fresh installation outside the checkout, executable examples, demonstrations and security-check scope. Remote CI, untested OS/Python and real consumers are recorded as `NOT_RUN` until actually run. [Synthetic recordings](docs/guide/demos.md), the [feedback template](docs/community/feedback.md) and the [empty real-case template](docs/community/real-case.md) distinguish engineering evidence from real adoption. No feedback or telemetry is collected automatically.

## Development

```sh
python -m pytest tests/ -q
python -m ruff check python/memlink/ tests/ scripts/
python -m ruff format --check python/memlink/ tests/ scripts/
python -m mypy python/memlink/ scripts/
```

MIT — [LICENSE](LICENSE).
