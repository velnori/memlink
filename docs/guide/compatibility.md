# Compatibility and loss classification

Run `memlink formats --manifest` to inspect the packaged machine-readable manifest. Its source is `python/memlink/resources/compatibility-manifest-v1.json` in the repository. The earlier `compatibility-v1.json` remains the preflight candidate mapping; it is not the final verification evidence.

The manifest records reader/writer roles, exact file shapes, upstream review date and source, synthetic fixture path and MIT authorization, field/conversion/archive rules, export/safe-apply/roundtrip support, Handoff pack support, conformance commands and variant status. Upstream product documentation was checked on **2026-10-04**. Exact fixtures freeze MemLink's file contract; no live upstream application or online connector was tested.

| Adapter | Exact fixture-backed variants | Destination | Handoff pack |
|---|---|---|---|
| generic | plain Markdown; YAML frontmatter; generated canonical notes | notes/*.md, safe migrate | unsupported |
| ombre | dynamic/permanent/feel bucket YAML | bucket Markdown, safe migrate | unsupported |
| openclaw | MEMORY.md; recursive daily/slug notes; optional USER/DREAMS; legacy name/metadata | framed daily notes by default; separate legacy structured, safe migrate | supported |
| mem0 | results envelope; array; mixed valid/invalid records | offline memories.json, safe migrate | unsupported |
| zep | facts/results envelope; array; session-summary object | offline facts.json, safe migrate | unsupported |
| chatgpt | conversation graph with selected active text path | reader only; export through another Writer | unsupported |
| claude_export | chat_messages text/content blocks | reader only; export through another Writer | unsupported |
| stream-summary | memlink-stream-summary-v1 frontmatter | reader only; export through another Writer | unsupported |

OpenClaw file semantics are grounded in [official memory documentation](https://docs.openclaw.ai/concepts/memory). Legacy structured notes are labeled **legacy**, not asserted to be the current upstream native layout. USER/DREAMS require explicit approval; `--all` does not expand to configuration, sessions or plugins.

[Mem0's API documentation](https://docs.mem0.ai/api-reference/memory/get-memories) and [Zep memory documentation](https://help.getzep.com/v2/memory) describe live products, but this implementation reads/writes the listed **offline JSON shapes** only. It neither follows API pagination nor uploads to a service. [ChatGPT data export](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data) and [Claude data export](https://support.claude.com/en/articles/9450526-how-can-i-export-my-claude-data) establish the transcript export context, not a stable public JSON schema or Saved Memory interoperability claim.

## Status and verification layers

- **verified**: the exact independent synthetic fixture and listed file/transaction layers pass conformance. It does not cover every upstream version, online import, application retrieval or model long-term memory semantics.
- **legacy**: a historical MemLink variant, separately tested; current upstream semantics are not claimed.
- **experimental**: an explicitly unverified variation; do not rely on it as verified support.
- **unsupported**: no declared implementation/verification layer. Online connectors and model Saved Memory/retrieval are unsupported here.

OS-specific unavailable layers appear as `NOT_RUN`, even when other checks pass. Inspect `counts` and every check rather than just the summary. Python 3.10–3.12 on Linux/macOS/Windows is the configured CI matrix; a local run does not prove the other eight environments or new remote CI.

Installed wheel conformance checks package files against RECORD SHA-256 hashes. A source/editable import outside that installed wheel reports this layer as `NOT_RUN`; it cannot substitute for fresh installation. Bundle hashes and RECORD checks detect inconsistency, not signed authorship or malicious code that also replaces the hashes.

## Field outcomes

| Receipt status | Meaning |
|---|---|
| native-preserved | Actual native Reader values equal the original value without archive recovery |
| transformed | Native mapping changes the value; the original remains in the archive |
| archive-only | The destination native contract cannot express it; exact canonical transport is in the archive |
| dropped | Approved incoming data was not committed, for example a skipped conflicting file |
| unsupported | Source/target shape or semantic feature has no implemented mapping |
| unknown | Not measured, such as a dry-run estimate or undeclared third-party semantics |

Ombre may add Markdown separator whitespace, coerce importance or constrain domains; these are reported as transformed rather than described as native preservation. Chat transcript tools, alternative branches and attachment metadata remain opaque/raw canonical transport; no OCR, binary retrieval or semantic conversion is claimed. Bad records are counted, not silently called converted.

The receipt's real readback is the final evidence; capabilities and manifest candidate fields cannot override measured differences. Full canonical equality with a retained verified archive is distinct from native semantic preservation. Hashes establish consistency, not signed authorship.

```sh
memlink conformance --adapter openclaw --report conformance.json
memlink conformance --export-fixtures fixtures
memlink conformance --adapter mem0 --fixtures fixtures --report mem0-conformance.json
```

Goldens in `suite.json` are authored separately from the tested writer. Update them only with the visible input/expected diff and an explained contract change. See [contribution requirements](https://github.com/velnori/memlink/blob/main/CONTRIBUTING.md).
