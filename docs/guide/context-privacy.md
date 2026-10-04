# Context Handoff privacy and threat model

MemLink operates on local files provided by the caller. It makes no AI API calls, does
not upload files or fetch links, and requires no API keys. Core acceptance uses a network
sentinel with a working DNS canary, then exercises pack/select/handoff/verify and direct
`handoff --all` with key variables removed. This is a Python network-call boundary test,
not a claim about an OS firewall or unrelated running applications.

## Private and shareable assets

| Asset | Intended boundary |
|---|---|
| Private pack | Full approved raw sources, Canonical values, unknown fields, inventory, namespace and local approved root; keep private |
| Selection and custom rules | Local approval digests and private disclosure policy; keep private |
| Handoff | Only approved record text and necessary source-relative/scope metadata, aggregate policy/budget information and opaque digests |
| Verification output | Integrity result, manifest digest and count-only warnings; does not sign or authenticate a bundle |

Selecting A never copies B's raw files or unknown extension payloads into output.
No archival sidecar or alternate hidden copy of a redacted value is emitted. Reports have
strict known fields and no raw original values. A selected record's prose may itself mention
other people/projects or contain sensitive facts: selectors do not perform semantic DLP.
Structured user/agent/session/run scope values remain shareable metadata unless redacted.
Complex scope objects stay private and appear as explicitly unknown scope values in the handoff.

Default `warn` intentionally retains detected credentials. Use `redact`/`fail` or remove
affected records. Deterministic patterns miss unknown/encoded keys, personal facts and
unusual paths and can have false positives. User redaction regexes are trusted local policy;
source notes cannot define them. Path scrubbing also changes matching slash-style text.
No exact native/semantic preservation claim is made for this context projection.

## Untrusted notes

Body, summary and metadata are literal reference text inside dynamically sized fences.
HTML and links stay quoted; control and bidi characters become visible escapes. No text
is executed, no URL is fetched, and original prompts are not relabelled as system messages.
Overlong files/serialization graphs are bounded; budgets preserve whole records.

Fencing is a file-rendering defense, not an LLM sandbox. A target model may still follow
malicious instructions or misunderstand contradictions. Check its permissions and results.
`unknown` values remain unknown; unresolved and archived states are retained as such.

## Trust and concurrent files

Selections are bound to both the private manifest and record versions. The source root
namespace follows the existing identity/scope contract; moving a source root changes it.
Symlinks, junction/reparse paths, hardlinks, unsafe path components, overlaps and collisions
are rejected for approved memory and bundle artifacts. Files outside memory scope are
neither archived nor hashed. Snapshot checks detect observed modifications/additions/deletions.

The filesystem is not frozen. No protection is claimed against privileged attackers changing
path objects between checks, exact change-and-revert races, OS compromise, power loss or
uncooperative writers defeating final per-file checks. Failed operations remove only their
owned unchanged files; external modifications are preserved and rollback problems reported.
Third-party plugin Python code remains trusted under the existing plugin contract.

SHA256 is not a signature. Without a trusted external manifest digest/private pack, a
self-consistent rewrite is indistinguishable from a new internally valid bundle. Review
evidence is a local explicit-confirmation receipt, not identity authentication or independent
proof that a particular person read every word. `--all`/selectors without TTY confirmation
always report `human_reviewed=false`; positive TTY regression tests simulate confirmation
and are not evidence of a live user review.

MemLink does not modify `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, client settings, hooks,
saved memory, accounts or retrieval databases. Client consumption can involve a network
service under that client's own rules; the MemLink offline boundary ends at its files.
