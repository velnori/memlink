# Privacy and threat model

Core workflows operate on explicitly supplied local paths. They do not discover home directories, upload inputs, call AI APIs, require keys/tokens, collect feedback or add telemetry. See [no-network/no-API evidence](no-network.md).

Full Migration copies the approved selected records, including sensitive content within that scope. Receipts and archives contain original canonical values and provenance, so treat the complete migration result as private. `--all` includes archived records within the approved set; it does not mean “search every account or file.”

Handoff pack is private and retains full approved source files, unknown metadata and canonical values. A selection file also exposes private inventory identifiers. The shareable handoff contains only controlled text plus manifest/receipt. Default scope is OpenClaw MEMORY.md + recursive memory notes; USER/DREAMS require explicit flags. See the detailed [Handoff threat model](context-privacy.md).

| Threat | Boundary / mitigation | Remaining limit |
|---|---|---|
| Malicious paths / links | Approved roots, overlap checks, percent-escaped IDs, link/reparse/hardlink rejection, collision checks | OS permissions and hostile same-user code are not sandboxed |
| Malformed YAML/JSON / exhaustion | Unique keys, safe YAML loader, finite typed canonical values, bounded bytes/files/records/depth/nodes | Large valid exports can exceed archive/bundle limits; see benchmark |
| Concurrent writers / partial commit | Source/target snapshots, cooperative lock, staging/readback, backup, output hashes, owned rollback | Per-file commits; no global atomicity, perfect TOCTOU elimination or power-loss recovery |
| Bundle changes | Exact file set, hashes, schema, source readback and text regeneration; optional external trusted digest/original pack | A wholly self-consistent rewrite is possible without a trusted external anchor; hashes are not signatures |
| Secret disclosure | Deterministic warn/redact/fail and user-provided local rules; selective projection | Default warn shares detected values; redaction is advisory and can miss encoded secrets or sensitive facts |
| Source prompt injection | Controlled reference rendering and explicit file sharing | Consumer LLM/tool policies remain independent; no model-resistance guarantee |
| Malicious adapters | Registration/canonical/output checks constrain cooperative plugins | Third-party Python plugins can execute arbitrary code and must be trusted |

Deleting a local output does not revoke a copy already shared with another tool/person. MemLink does not send those copies for you. Running a consumer model may have its own networking, costs, telemetry and memory behavior.

Report security problems privately using [SECURITY.md](https://github.com/velnori/memlink/blob/main/SECURITY.md). Static/advisory checks have a stated scope; a security policy is not proof of an independent audit.
