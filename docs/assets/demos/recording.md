# Captured synthetic CLI output

Real CLI child processes via memlink.verification; stdout/stderr verbatim. Media pauses are edited for reading, not execution timing.

Run these in a new recording directory after exporting the bundled fixtures. The strict and tamper checks intentionally return nonzero. The original project-a bundle stays valid.

## version

```text
$ memlink --version
memlink 2.0.0
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## fixtures

```text
$ memlink conformance --export-fixtures fixtures
Exported independent synthetic fixtures: fixtures
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## full-migration

```text
$ memlink convert --from generic --to openclaw --source fixtures/generic --target migration --all
Status:   partial
Records:  2
  create: memory/2026-10-02.md
  create: memory/undated.md
Warning:  18 field values require archive or transformation
Receipt:  .memlink/receipt.json
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## validate-output

```text
$ memlink validate --from openclaw --source migration --level schema
ML103: MEMORY.md not found; scanning memory/ directory recursively
Validated schema using the source adapter
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## validate-roundtrip

```text
$ memlink validate --from generic --source fixtures/generic --level roundtrip --intermediate openclaw
Validated roundtrip using the source adapter
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## strict-blocked

```text
$ memlink convert --from generic --to mem0 --source fixtures/generic --target strict-blocked --all --strict

[stderr]
Error: Strict conversion blocked: generic-a.schema_version: archive-only; generic-a.name: archive-only; generic-a.source: archive-only; generic-a.summary: archive-only; generic-a.kind: archive-only; generic-a.status: archive-only; generic-a.checksum: archive-only; generic-a.metadata: archive-only
Warning: 16 field values require archive or transformation
```

Exit 5 (expected 5); tested network canary; zero intercepted attempts.

## pack

```text
$ memlink pack --from openclaw --input fixtures/openclaw --include-user --include-dreams --out private-pack
Status: success
Records: 6
Human reviewed: false
Warning: Private archive: contains complete approved sources; do not share/upload by default
Warning: Deterministic secret checks are advisory, not complete DLP; hashes are not signatures
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## select

```text
$ memlink select private-pack --project A --out selection-a.json
Status: selected
Records: 1
Human reviewed: false
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## handoff

```text
$ memlink handoff private-pack --selection selection-a.json --secrets redact --out project-a
Status: success
Records: 1
Human reviewed: false
Warning: Deterministic secret checks are advisory, not complete DLP; hashes are not signatures
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## verify

```text
$ memlink verify project-a --pack private-pack
Status: verified
Records: 1
Human reviewed: false
Warning: Deterministic secret checks are advisory, not complete DLP; hashes are not signatures
Manifest SHA256: 91df61f713ffa4098d62e33e284b8e5668dd46b48bb068e994a1a4b686ce5764
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## handoff-all

```text
$ memlink handoff --from openclaw --input fixtures/openclaw --all --secrets redact --out context-all
Status: success
Records: 4
Human reviewed: false
Warning: Deterministic secret checks are advisory, not complete DLP; hashes are not signatures
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## verify-all

```text
$ memlink verify context-all
Status: verified
Records: 4
Human reviewed: false
Warning: Deterministic secret checks are advisory, not complete DLP; hashes are not signatures
Manifest SHA256: 6db8766a0de5e04cc29c50334133eeb785bb03750e3b1a10175e7aba5666bdb9
```

Exit 0 (expected 0); tested network canary; zero intercepted attempts.

## tamper-rejected

```text
$ memlink verify tampered

[stderr]
Artifact digest/size mismatch
```

Exit 2 (expected 2); tested network canary; zero intercepted attempts.
