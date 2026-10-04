# Claude conversation transcript export

Format `claude_export` reads exported conversation arrays or supported conversation containers. It is a transcript adapter, not a Saved Memory importer. Message `text` and textual content blocks enter the selected body; supported message timestamps enter canonical UTC times.

Mixed content, unknown blocks, tool records, attachments and alternate text are retained in `claude_transcript` and/or reported. The adapter does not retrieve attachment binaries or claim their contents are understood. A conversation without supported human text is explicitly unsupported; mixed usable input can convert with warnings, while unsupported-only input fails.

This is reader-only. Targets require a supported writer and real conversion receipt. There is no online Claude connection, binary upload, OCR or automatic Saved Memory behavior.
