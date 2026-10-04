# Zep offline JSON

Format `zep` reads facts/results arrays, bare record arrays, or supported session objects with messages and summary. A supplied file is exact; directories prefer `facts.json`, otherwise require an unambiguous JSON file. Fact records use `uuid`/ID and `fact`/supported text aliases; timestamps are mapped to UTC.

Session scope from records or the export root is retained as `zep_session_id` and identity scope. Unknown scope stays unknown. Original records and top-level unknown fields are transport data, not native semantic assertions.

The writer creates `facts.json` with a `facts` array. ID, text and timestamps are checked by native readback. Summary/emotion/relationship/extensions and classification values that the file shape does not express require the canonical archive. Deterministic renamed segments are explicitly routed by its manifest.

This adapter does not call a Zep API or assert current cloud import compatibility. Legal empty arrays may pass schema validation; malformed/unsupported-only sources and zero-record roundtrip fail. Accepted fixture shapes are documented file exports, not live-service end-to-end tests.
