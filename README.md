# memlink

> A canonical interchange format for AI memories — like Pandoc, but for AI memory systems.

Built for developers building AI assistants, memory platforms, and agent frameworks.

[![CI](https://github.com/velnori/memlink/actions/workflows/test.yml/badge.svg)](https://github.com/velnori/memlink/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![PyPI version](https://img.shields.io/pypi/v/memlink-bridge)](https://pypi.org/project/memlink-bridge/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)

---

## Why memlink?

Different AI tools store memories differently. memlink lets them exchange memories without every project writing custom converters.

**Without memlink** — 10 memory formats need 45 converters. Every new format makes it worse:

```
Ombre → OpenClaw    Ombre → Mem0    Ombre → Zep
Mem0 → Zep          OpenClaw → Zep  ...
```

**With memlink** — each format writes one Reader + one Writer. Everything else is automatic:

```
         ┌── Reader → Canonical ──┬── Writer → OpenClaw
  Ombre ─┤                        ├── Writer → Mem0
         └── ...                   └── Writer → Any Format
```

**n systems = 2n plugins.** Not n² converters.

---

## Quick Start

```bash
pip install memlink-bridge

# Convert Ombre → OpenClaw
memlink convert --from ombre --to openclaw \
  -s ~/.claude/ombre-buckets -T ./my-memories/

# Inspect any memory file
memlink inspect tests/fixtures/ombre_samples/dynamic/user/sample.md

# Validate data integrity
memlink validate -s tests/fixtures/ombre_samples --level schema

# Show installed formats
memlink formats
```

---

## Supported Formats

| Format | Read | Write | Status |
|--------|------|-------|--------|
| Ombre Brain | ✅ | ✅ | Stable |
| OpenClaw | ✅ | ✅ | Stable |
| Generic Markdown | ✅ | — | Stable |
| *Mem0* | 🚧 | — | *v0.2* |
| *Zep* | 🚧 | — | *v0.3* |

**3 plugins, 7+ apps interoperable.** Generic alone covers Obsidian, Logseq, Bear, iA Writer, and plain Markdown — every app that uses YAML frontmatter.

---

## Architecture

```
  Ombre ──┐
Generic ──┼──→ Reader → Canonical Memory → Writer ──┬──→ OpenClaw
OpenClaw ─┘                                          └──→ Ombre
```

Each format implements three methods:

```python
class FormatPlugin:
    def read(path) → ReadResult       # Format → Canonical
    def write(memories, path) → []    # Canonical → Format
    def validate(path) → [Issue]      # Integrity checks
```

Add a new format = write one plugin. Zero changes to core code.

---

## Feature Compatibility

memlink is honest about what gets lost. Every conversion shows a Compatibility Report:

```
$ memlink convert --from ombre --to openclaw -s ombre/ -T openclaw/

  Read:     117 memories from ombre

  Compatibility Report:
    [ok] Preserved via metadata:
      Emotion fields (valence/arousal): 117 field values

  Warnings: 0
  Time:     0.23s
```

No silent data loss. No surprises.

---

## Canonical Memory Schema

```yaml
id: "project-alpha"
name: "Project Alpha Kickoff"
body: "..."
kind: dynamic
tags: [meeting, planning]
metadata: { ... }
```

See [spec/canonical-v1.md](spec/canonical-v1.md) for the full specification. [JSON Schema](spec/canonical-v1.schema.json) also available.

---

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.2** | Mem0 Reader, daily-notes roundtrip, `--fail-on-loss` |
| **v0.3** | Zep Reader, chat export readers (ChatGPT, Claude) |
| **v0.4** | `memlink merge`, `memlink broadcast` |
| **v1.0** | Stable Canonical Schema v1, stable Plugin API |

---

## What memlink is NOT

- ❌ **Sync engine** — v0 is export/import only
- ❌ **Memory database** — Works with files, not APIs
- ❌ **Embedding store** — No vector search
- ❌ **Knowledge graph** — No traversal or inference

---

## Development

```bash
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e ".[dev]"

pytest tests/ -v          # 115 tests
ruff check memlink/       # Lint
mypy memlink/             # Type check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a new format.

---

## License

MIT — see [LICENSE](LICENSE).
