# memlink

> A language-neutral interchange layer for AI memory systems — similar in spirit to how Pandoc enables document interoperability.

[![CI](https://github.com/velnori/memlink/actions/workflows/test.yml/badge.svg)](https://github.com/velnori/memlink/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/pypi-memlink-blue)](https://pypi.org/project/memlink/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)
[![codecov](https://codecov.io/gh/velnori/memlink/branch/main/graph/badge.svg)](https://codecov.io/gh/velnori/memlink)

## Why memlink?

**Problem**: 10+ AI memory formats (Ombre, OpenClaw, Mem0, Zep, Letta...), each with its own schema. Converting between them naively requires O(n²) converters.

**Solution**: A single Canonical Memory intermediate format. Add a new system = write one Reader + one Writer. O(n) complexity.

```
Ombre ──┐
Mem0  ──┼──→ Canonical ──┬──→ OpenClaw
Zep   ──┘                └──→ Your Format
```

## Quick Start

```bash
# Install (PyPI coming soon — use git for now)
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e .

# Inspect a memory
memlink inspect tests/fixtures/ombre_samples/dynamic/user/sample.md

# Convert Ombre → OpenClaw
memlink convert --from ombre --to openclaw \
  -s tests/fixtures/ombre_samples \
  -T ./my-memories/

# Validate roundtrip
memlink validate -s tests/fixtures/ombre_samples --level schema

# Show installed formats
memlink formats

# Validate roundtrip integrity
memlink validate --level roundtrip -s ~/.claude/ombre-buckets/

# List installed formats
memlink formats
```

## Supported Formats

| Format | Read | Write | Roundtrip | Lossless |
|--------|------|-------|-----------|----------|
| [Ombre Brain](https://github.com/P0luz/Ombre-Brain) | ✅ | ✅ | ✅ | ✅ |
| [OpenClaw](https://github.com/basicmachines-co/openclaw-basic-memory) | ✅ | ✅ | ✅ | ⚠️ summary |
| Mem0 | 🚧 | 🚧 | — | — |
| Zep | 🚧 | 🚧 | — | — |

## Architecture

memlink uses a **Canonical Memory** intermediate format. Each AI memory format gets a plugin with three methods:

```python
class FormatPlugin:
    def read(path) -> ReadResult      # Format → Canonical
    def write(memories, path) -> []   # Canonical → Format
    def validate(path) -> [Issue]     # Format-specific checks
```

### Canonical Memory Schema

```yaml
schema_version: "1"
id: "project-alpha-kickoff"
name: "Project Alpha Kickoff"
summary: "Initial planning session"
body: |
  ## Decisions
  - Use TypeScript for frontend
  - Deploy on AWS

kind: dynamic           # dynamic | permanent | emotion (open string)
status: active          # active | archived
tags: [meeting, planning]
domains: [work, project]

created_at: "2024-06-28T10:00:00Z"
updated_at: "2024-06-28T15:30:00Z"

importance_score: 0.8
importance_label: null
valence: 0.7
arousal: 0.6
pinned: false
checksum: "sha256:abc123..."

source:
  format: ombre
  path: dynamic/work/meeting.md
  uri: ombre://dynamic/work/project-alpha-kickoff

metadata:
  memlink:              # Roundtrip preservation
    source:
      format: ombre
      version: "1.0"
    original:
      importance: 8
      created_tz: "2024-06-28T18:00:00+08:00"

extensions: {}          # Third-party pass-through
relationships: []       # v0 reserved
```

Full schema spec: [spec/canonical-v1.md](spec/canonical-v1.md) | JSON Schema: [spec/canonical-v1.schema.json](spec/canonical-v1.schema.json)

### Feature Loss Report

Conversion warns about capabilities mismatch:

```
memlink convert --from ombre --to openclaw -s ... -t ...

  Converted: 128

  ── Feature Loss ──
  relationships      8 dropped
  emotion           14 dropped
  extensions          5 dropped
  ─────────────────
  Total loss         27 fields across 19 memories
```

## What memlink is NOT

- ❌ **Synchronization Engine** — v0 is export/import only
- ❌ **Memory Database** — Works with files, not live memory APIs
- ❌ **Embedding Store** — No vector search or similarity
- ❌ **Knowledge Graph** — No graph traversal or inference
- ❌ **Not opinionated** — Preserves original data structures, no normalization

## Spec Compliance

| Canonical v1 feature | Ombre | OpenClaw |
|---------------------|-------|----------|
| Core Fields (id, name, body) | ✅ | ✅ |
| Summary | — | ✅ |
| Tags & Domains | ✅ | ✅ |
| Emotion (valence/arousal) | ✅ | — |
| Importance | ✅ 1-10 | ✅ label/score |
| Pinned | ✅ | ✅ |
| Timestamps | ✅ | ✅ |
| Relationships | ⚠ v0 metadata | ⚠ v0 metadata |
| Extensions | ⚠ pass-through | ⚠ not preserved |

Full spec: [spec/canonical-v1.md](spec/canonical-v1.md)

## Non-Goals

- ❌ **Not a sync tool** — v0 is export/import only. Bidirectional sync is future work.
- ❌ **Not a database** — Works with files, not live memory APIs.
- ❌ **Not opinionated** — Preserves original data structures. No normalization.

## Limitations

### Lossy Conversions

| Direction | What may be lost | Mitigation |
|-----------|-----------------|------------|
| OpenClaw → Ombre | Domain if no `metadata.domain` | `--unknown-domain-action default:general` |
| Ombre → OpenClaw | Local timezone | Stored in `metadata.memlink.original.created_tz` |

### Concurrency

⚠️ v0 does not support concurrent writes to the same target directory. See [#1](https://github.com/velnori/memlink/issues/1).

## Development

```bash
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Lint & type check
ruff check memlink/
mypy memlink/
```

### Adding a New Format

1. Create `memlink/<format>_reader.py` — implement `FormatPlugin.read()`
2. Create `memlink/<format>_writer.py` — implement `FormatPlugin.write()`
3. Register in `pyproject.toml` under `[project.entry-points."memlink.readers"]` and `writers`

## License

MIT — see [LICENSE](LICENSE).
