# Claude Export

Anthropic's official data export (available via Claude.ai → Settings → Privacy → Export data) includes a `conversations.json` file containing your full conversation history.

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | — |
| Emotion | — |
| Importance | — |

## Export Format

The export is a ZIP file. Extract it and point memlink at the directory containing `conversations.json`.

Unlike ChatGPT's tree-based format, Claude's export uses a flat `chat_messages` array in chronological order — no tree traversal needed.

## Field Mapping

| Claude Export | Canonical |
|---------------|-----------|
| `uuid` | `id` |
| `name` | `name` (truncated to 60 chars) |
| `created_at` (ISO 8601) | `created_at` |
| `updated_at` (ISO 8601) | `updated_at` |
| `chat_messages` (human + assistant) | `body` — formatted as `role: text` pairs |
| — | `kind = "dynamic"` |

## Usage

```bash
# Unzip your Claude export first, then:
memlink convert --from claude_export --to generic \
  -s ./claude-export/ \
  -T ./conversations/

# Convert Claude conversations to Mem0 format
memlink convert --from claude_export --to mem0 \
  -s ./claude-export/ \
  -T ./mem0-out/
```

## Body Format

Each memory's body contains the full conversation as:

```
human: What's the difference between asyncio and threading?

assistant: asyncio and threading solve similar problems but in different ways...
```

## Known Limitations

- Attachments and file uploads in conversations are not included in the text export — only the text content of messages is captured.
- Conversations with no human/assistant messages are skipped with a warning.
