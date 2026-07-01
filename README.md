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

| Format | Read | Write | Since |
|--------|------|-------|-------|
| Ombre Brain | ✅ | ✅ | v0.1.0 |
| OpenClaw | ✅ | ✅ | v0.1.0 |
| Generic Markdown | ✅ | ✅ | v0.1.1 |
| Mem0 | ✅ | ✅ | v0.2.0 |
| Zep | ✅ | ✅ | v0.3.0 |
| ChatGPT Export | ✅ | — | v0.6.0 |
| Claude Export | ✅ | — | v0.6.0 |

**Generic Markdown** works with YAML-frontmatter Markdown used by tools like Obsidian, Logseq, Bear, and plain Markdown. Tool-specific extensions are preserved as metadata or reported as compatibility notes.

### Planned Formats

| Format | Target |
|--------|--------|
| ChatGPT/Claude Writers | later |

---

## Feature Compatibility

MemLink is honest about what transfers and what doesn't.

**Without a compatibility layer:**
- Format-specific fields can disappear silently.

**With MemLink:**
- Preserved fields stay in Canonical Memory.
- Format-specific fields are preserved in metadata when possible.
- Compatibility reports explain what changed.

*Multi-format demo — convert, merge, broadcast:*

```
$ memlink convert --from ombre --to mem0 -s ./ombre-data -T ./mem0-out --verbose

Read:     4 memories from ombre

Compatibility Report:
  [ok] Preserved via metadata:
    Emotion fields (valence/arousal): 3 field values (75%)
  [~] Degraded:
    Unsupported memory kinds: 2 field values (50%)
Warnings: 2
Time:     0.00s

$ memlink merge --sources mem0:./mem0-out ombre:./ombre-data --to openclaw:./merged --verbose

Source mem0: 4 memories from ./mem0-out
Source ombre: 4 memories from ./ombre-data
Sources:  2 (mem0(4), ombre(4))
Total:    8 memories
Unique:   4
Resolved: 4 conflicts (strategy: newest)
Warnings: 0
Time:     0.00s

$ memlink formats

Format          Reader     Writer
-----------------------------------
chatgpt         yes        no
claude_export   yes        no
generic         yes        yes
mem0            yes        yes
ombre           yes        yes
openclaw        yes        yes
zep             yes        yes
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

- ❌ **Sync engine** — v1.0 is export/import only
- ❌ **Memory database** — Works with files, not APIs
- ❌ **Embedding store** — No vector search
- ❌ **Knowledge graph** — No traversal or inference
- ⚠️ **Battle-tested** — v1.0 API is stable, but not yet tested at scale (10K+ memories) or with production workloads. Use with that in mind.

---

## Roadmap

| Version | Focus |
|---------|-------|
| **v0.2** | Mem0 Reader ✅, `--fail-on-loss` ✅ |
| **v0.3** | Zep Reader ✅, MkDocs ✅, merge ✅ |
| **v0.4** | Mem0 Writer ✅, `memlink merge` ✅ |
| **v0.5** | Zep Writer ✅, `memlink broadcast` ✅ |
| **v0.6** | ChatGPT + Claude Export Readers ✅ |
| **v1.0** | Schema Frozen, Plugin API Stable ✅ (current) |

---

## Development

```bash
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e ".[dev]"

pytest tests/ -v          # 257 tests
ruff check python/memlink/       # Lint
mypy python/memlink/             # Type check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add a new format.

---

## License

MIT — see [LICENSE](LICENSE).
