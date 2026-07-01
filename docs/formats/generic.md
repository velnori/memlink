# Generic Markdown

Reads and writes any directory of `.md` files with optional YAML frontmatter. One plugin covers many note-taking apps — fully bidirectional since v1.0.9.

## Supported Apps

- [Obsidian](https://obsidian.md)
- [Logseq](https://logseq.com)
- [Bear](https://bear.app)
- [iA Writer](https://ia.net/writer)
- Plain Markdown notes

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | ✅ |

## How it Works

### Reading

Files with YAML frontmatter are parsed into Canonical Memory. Files without frontmatter use the filename as the title and the full text as the body.

Frontmatter fields are mapped automatically:
- `title` / `name` → `name`
- `tags` (list or comma-separated) → `tags`
- `category` / `folder` → `domains`
- `created` / `date` → `created_at`
- Unknown fields → `extensions` (preserved)

```bash
memlink convert --from generic --to openclaw \
  -s ./my-notes/ \
  -T ./memories/
```

### Writing

Each Canonical Memory is written as a single `.md` file under `notes/` inside the target directory. Frontmatter is generated from Canonical fields; the body becomes the file content. Unknown fields stored in `extensions` are written back as frontmatter keys, making the output compatible with Obsidian, Logseq, Bear, and iA Writer.

Frontmatter mapping:
- `id` → `id`
- `name` → `title`
- `tags` → `tags` (sorted list)
- first domain → `category`
- `kind` → `type`
- non-`active` status → `status`
- `summary` → `description`
- `created_at` → `created` (ISO 8601)
- `updated_at` → `updated` (ISO 8601)
- `pinned=True` → `pinned: true`
- `extensions` keys → written as-is

```bash
memlink convert --from ombre --to generic \
  -s ./ombre-data/ \
  -T ./notes-export/
```
