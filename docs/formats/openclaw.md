# OpenClaw

[OpenClaw](https://github.com/openclaw/openclaw) is an AI agent platform with a file-based memory system.

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | ✅ |

## Output Modes

- **daily-notes** (default): `memory/YYYY-MM-DD.md` grouped by date, with `MEMORY.md` as curated long-term memory and `DREAMS.md` for emotion memories.
- **structured**: One file per memory (`memory/<id>.md`) with a `MEMORY.md` index. Use for lossless roundtrip.

Select mode with `--output-mode`:

```bash
memlink convert --from ombre --to openclaw \
  --output-mode structured \
  -s ombre/ -T openclaw/
```

## Field Mapping

| OpenClaw | Canonical |
|----------|-----------|
| `name` | `name` |
| `description` | `summary` |
| body (after frontmatter) | `body` |
| `metadata.type` | `domains[0]` |
| `metadata.tags` | `tags` |
| `metadata.importance` | `importance_score` or `importance_label` |

## Storage

YAML frontmatter Markdown files in `memory/*.md` with index in `MEMORY.md`.
