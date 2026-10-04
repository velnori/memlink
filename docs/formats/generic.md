# Generic Markdown

Format `generic` reads plain Markdown or optional YAML frontmatter recursively inside the supplied root. Frontmatter delimiters must occupy complete lines. Name/title, ID, status, kinds, multiple domains, times and canonical fields are mapped; unknown fields are retained as transport metadata/extensions. Missing IDs are derived deterministically from relative paths.

The writer emits `notes/<safe-id>.md` with complete canonical frontmatter and an exact body-length marker. This documented variant supports actual native readback of canonical fields; reserved extension keys cannot overwrite ID/status/body framing. Body headings, horizontal lines and CRLF are not record delimiters. The archive additionally retains original canonical identity and source.

Optional Markdown/frontmatter compatibility is not complete Obsidian, Logseq or Bear application semantics. This adapter does not migrate graph databases, application configuration, attachments outside the approved input root or live application state. Invalid YAML, nonfinite values and resource violations are reported as invalid inputs.
