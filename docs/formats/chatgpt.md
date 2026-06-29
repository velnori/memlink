# ChatGPT Export

ChatGPT's official data export (available via Settings → Data controls → Export data) includes a `conversations.json` file containing your full conversation history.

## Capabilities

| Feature | Status |
|---------|--------|
| Read | ✅ |
| Write | — |
| Emotion | — |
| Importance | — |

## Export Format

The export is a ZIP file. Extract it and point memlink at the directory containing `conversations.json`.

Each conversation in the JSON uses a tree-based `mapping` structure where nodes represent individual messages. memlink traverses this tree, extracts `user` and `assistant` messages in chronological order, and concatenates them into the memory body.

## Field Mapping

| ChatGPT | Canonical |
|---------|-----------|
| `id` | `id` |
| `title` | `name` (truncated to 60 chars) |
| `create_time` (unix timestamp) | `created_at` |
| `update_time` (unix timestamp) | `updated_at` |
| messages (user + assistant) | `body` — formatted as `role: text` pairs |
| — | `kind = "dynamic"` |

## Usage

```bash
# Unzip your ChatGPT export first, then:
memlink convert --from chatgpt --to generic \
  -s ./chatgpt-export/ \
  -T ./conversations/

# Or inspect what will be preserved before converting:
memlink convert --from chatgpt --to ombre --dry-run \
  -s ./chatgpt-export/ \
  -T ./output/
```

## Body Format

Each memory's body contains the full conversation as:

```
user: How do I use asyncio in Python?

assistant: asyncio is Python's standard library for writing concurrent code...

user: Can you show me an example?

assistant: Sure, here's a basic example...
```

## Known Limitations

- If you edited a message in ChatGPT, the conversation tree has branches. memlink collects all nodes by timestamp — edited and original versions may both appear in the body.
- System and tool messages are skipped; only `user` and `assistant` turns are included.
- Conversations with no user/assistant messages (e.g. empty or tool-only) are skipped with a warning.
