# Stream summary

Format `stream-summary` is reader-only and expects frontmatter `schema: memlink-stream-summary-v1`. It is not a generic audio/chat ingest adapter. It maps ID/title/body, status, tags and timestamps, and retains original collection/events/unknown fields.

Epoch 0, zero peak hour/event counts and original timezone values remain distinguishable from absence. Times normalize to UTC; if a named timezone database is unavailable the adapter reports the fallback rather than silently claiming the timezone was recognized. Missing IDs are derived deterministically from the relative source path.

Use a supported file writer for conversion. Native field semantics depend on that target's actual readback; raw stream collection data may need the canonical archive. No writer, return trip to stream format, media decoding or online connector is provided.
