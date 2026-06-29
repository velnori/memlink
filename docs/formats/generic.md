# Generic Markdown

Reads any directory of `.md` files with optional YAML frontmatter. One Reader covers many note-taking apps.

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
| Write | — |

## How it Works

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
