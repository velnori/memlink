# memlink

**Pandoc for AI memories.**

One canonical schema to bridge AI memory systems.

Stop writing n² converters between memory formats.  
Write one Reader + one Writer per format. Everything else is automatic.

*Explicit compatibility reports. No silent data loss.*

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
Mem0 → Zep          ...
```

**With memlink** — each format writes one Reader + one Writer:

```
         ┌── Reader → Canonical ──┬── Writer → OpenClaw
  Ombre ─┤                        ├── Writer → Any Format
         └── ...                   └── Writer → Any Format
```

**n systems = 2n plugins.** Not n² converters.

---

## Quick Start

```bash
pip install memlink-bridge

# Create a demo memory file
mkdir -p /tmp/memlink-demo
cat > /tmp/memlink-demo/hello.md << 'EOF'
---
title: Hello MemLink
tags: [demo]
---
This is a memory. memlink can bridge it across AI memory formats.
EOF

# Convert Generic Markdown → OpenClaw
memlink convert --from generic --to openclaw \
  -s /tmp/memlink-demo \
  -T /tmp/memlink-output

# Show installed formats
memlink formats
```

**What just happened:** A plain Markdown file was read into Canonical Memory format, then written as an OpenClaw memory.

Sample output:

```
Read:     1 memories from generic
Warnings: 0
Time:     0.00s
```

You should now see an OpenClaw-style memory file in `/tmp/memlink-output/`. The Compatibility Report tells you exactly what was preserved or dropped — no silent data loss.

---

## Supported Formats

| Format | Read | Write | Status |
|--------|------|-------|--------|
| Ombre Brain | ✅ | ✅ | v0.1.1 |
| OpenClaw | ✅ | ✅ | v0.1.1 |
| Generic Markdown | ✅ | — | v0.1.1 |
| Mem0 | ✅ | — | v0.2.0 |
| Zep | ✅ | — | v0.3.0 |

**Generic Markdown** works with YAML-frontmatter Markdown used by tools like Obsidian, Logseq, Bear, and plain Markdown. Tool-specific extensions are preserved as metadata or reported as compatibility notes.

### Planned Formats

Planned formats are roadmap items, **not implemented in v0.1.1**:

| Format | Target |
|--------|--------|
| Zep Reader | v0.3 |
| Chat export readers (ChatGPT, Claude) | later |

---

## Feature Compatibility

MemLink is honest about what transfers and what doesn't.

**Without a compatibility layer:**
- Format-specific fields can disappear silently.

**With MemLink:**
- Preserved fields stay in Canonical Memory.
- Format-specific fields are preserved in metadata when possible.
- Compatibility reports explain what changed.

*Example compatibility report:*

```
$ memlink convert --from ombre --to openclaw -s ~/.claude/ombre-buckets -T ./memories/

  Read:     117 memories from ombre

  Compatibility Report:
    [ok] Preserved via metadata:
      Emotion fields (valence/arousal): 117 field values

  Warnings: 0
  Time:     0.23s
```

---

## Architecture

```
  Ombre ──┐
  Mem0  ──┼──→ Reader → Canonical Memory → Writer ──┬──→ OpenClaw
Generic ──┘                                          └──→ Ombre
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

## What memlink is NOT

- ❌ **Sync engine** — v0 is export/import only
- ❌ **Memory database** — Works with files, not APIs
- ❌ **Embedding store** — No vector search
- ❌ **Knowledge graph** — No traversal or inference
- ❌ **Production ready** — v0.1.1 is an alpha. Use in production at your own discretion.

---

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.2** | Mem0 Reader ✅, file lock, `--fail-on-loss`, daily-notes roundtrip |
| **v0.3** | Zep Reader, `memlink merge`, `memlink broadcast` |
| **v0.4** | Chat export readers (ChatGPT, Claude) |
| **v1.0** | Stable Canonical Schema v1, stable Plugin API |

---

## Development

```bash
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e ".[dev]"

pytest tests/ -v          # 132 tests
ruff check python/memlink/       # Lint
mypy python/memlink/             # Type check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a new format.

---

## License

MIT — see [LICENSE](LICENSE).
