# Zep

[Zep](https://github.com/getzep/zep) is a long-term memory store for AI assistants (CE and Cloud).

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | ✅ |
| Emotion | — |
| Importance | — |

## Supported JSON Formats

memlink auto-detects the Zep export format:

- `{"facts": [...]}` — Zep CE facts export (primary)
- `{"uuid": ..., "facts": [...]}` — session summary format
- `[...]` — direct array of fact objects

## Field Mapping

### Read (Zep → Canonical)

| Zep | Canonical |
|-----|-----------|
| `uuid` | `id` |
| `fact` / `content` | `body` (+ `name` truncated to 60 chars) |
| `created_at` | `created_at` |
| `updated_at` | `updated_at` |
| `metadata` | `extensions.zep_metadata` |
| `session_id` | `extensions.zep_session_id` |

### Write (Canonical → Zep)

| Canonical | Zep |
|-----------|-----|
| `id` | `uuid` |
| `body` \| `name` | `fact` |
| `created_at` | `created_at` |
| `updated_at` | `updated_at` |
| `extensions.zep_metadata` | `metadata` |
| `extensions.zep_session_id` | `session_id` |

Output file: `facts.json`

## Usage

```bash
# Export Zep memories to Ombre Brain format
memlink convert --from zep --to ombre \
  -s ./zep-export/ \
  -T ./ombre-memories/

# Import from Ombre back to Zep
memlink convert --from ombre --to zep \
  -s ./ombre-memories/ \
  -T ./zep-export/
```

## Known Limitations

- Emotion fields (`valence`/`arousal`) are not supported by Zep — stored in `extensions` on roundtrip
- `kind` is always written as `dynamic`; Zep has no native kind field
