# Ombre Brain

[Ombre Brain](https://github.com/P0luz/Ombre-Brain) is an open-source AI memory system with emotional tagging and natural forgetting.

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | ✅ |
| Emotion (valence/arousal) | ✅ Preserved |
| Importance (1–10) | ✅ Preserved |

## Field Mapping

| Ombre | Canonical |
|-------|-----------|
| `bucket_id` | `id` |
| `name` | `name` |
| `content` | `body` |
| `type` | `kind` |
| `domain` | `domains` |
| `tags` | `tags` |
| `importance` (1–10) | `importance_score` |
| `valence` | `valence` |
| `arousal` | `arousal` |
| `created` | `created_at` |
| `pinned` | `pinned` |

## Storage

Markdown files with YAML frontmatter in `ombre-buckets/{type}/{domain}/{id}.md`.
