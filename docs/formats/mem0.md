# Mem0

[Mem0](https://github.com/mem0ai/mem0) is a memory layer for AI agents (24k+ GitHub stars).

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | ✅ |
| Emotion | — |
| Importance | — |

## Supported JSON Formats

- `{"results": [...], "relations": [...]}` — `get_all()` export
- `[...]` — direct array

## Field Mapping

| Mem0 | Canonical |
|------|-----------|
| `id` | `id` |
| `memory` | `body` + `name` (truncated) |
| `categories` | `tags` |
| `hash` | `checksum` |
| `created_at` | `created_at` |
| `updated_at` | `updated_at` |
| `metadata` | `extensions.mem0_metadata` |
| `user_id` | `metadata.memlink.original` |

## Usage

```bash
memlink convert --from mem0 --to openclaw \
  -s ./mem0-export/ \
  -T ./memories/
```
