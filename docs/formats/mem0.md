# Mem0 offline JSON

Format `mem0` reads a record array or `{ "results": [...] }` from a supplied file, preferred `memories.json`, or one unambiguous JSON candidate. Records use `id`, `memory`, metadata and optional created/updated timestamps. Empty arrays are defined valid empty sets for schema validation; an empty roundtrip is an error.

`user_id`, `agent_id`, `run_id` and optional session scope are retained. Unknown scope stays unknown; the writer never invents a default user. Same IDs from different users/sources remain separate under scoped identity. Unknown record and top-level export fields remain in transport extensions/metadata.

The writer creates `memories.json` with a `results` array. ID/body/tags/time can be native when actual readback agrees; emotion, summary, relationship, multiple-domain/classification and unsupported values are honestly archive-only or transformed. Generated renamed JSON segments are located by the versioned archive manifest.

This is a local file adapter. No live Mem0 API or service ingestion has been tested or promised. Unsupported records and malformed/top-level-wrong JSON have explicit ledgers and cannot make an entirely unreadable source green.
