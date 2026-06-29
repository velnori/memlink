# memlink

**Pandoc for AI memories.**

Bridge AI memory formats through one canonical schema.

Stop writing n² converters. Write one Reader + one Writer per format.

```
  Ombre ──┐
  Mem0  ──┼──→ Canonical Memory ──┬──→ OpenClaw
Generic ──┘                        └──→ Ombre
```

**n formats = 2n plugins.** Not n² converters.

---

## Quick Links

- [Quick Start](guide/quickstart.md) — convert your first memory in 60 seconds
- [Formats](formats/ombre.md) — supported memory systems
- [Plugin API](api/plugin.md) — add your own Reader/Writer

## Install

```bash
pip install memlink-bridge
```

## Supported Formats

| Format | Read | Write |
|--------|------|-------|
| Ombre Brain | ✅ | ✅ |
| OpenClaw | ✅ | ✅ |
| Generic Markdown | ✅ | — |
| Mem0 | ✅ | — |

[GitHub](https://github.com/velnori/memlink) · [PyPI](https://pypi.org/project/memlink-bridge/) · MIT License
