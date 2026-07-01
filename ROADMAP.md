# Roadmap

## v0.1.0 — MVP ✅

- [x] Canonical Memory Schema v1
- [x] Ombre Brain Reader + Writer
- [x] OpenClaw Reader + Writer (daily-notes + structured modes)
- [x] Bidirectional conversion with 100% roundtrip
- [x] CLI: convert, validate, inspect, diff, stats, formats
- [x] Plugin registry with entry_points discovery
- [x] Structured Compatibility Report
- [x] 111 tests, 3 OS × 3 Python CI

## v0.2.0 — New Format + Stability ✅

- [x] **Mem0 Reader** — prove O(n) with a mainstream format ✅
- [x] `--fail-on-loss` for CI pipelines

## v0.3.0 — Ecosystem ✅

- [x] **Zep Reader** ✅
- [x] MkDocs documentation site
- [x] `memlink merge` — merge multiple sources into one target
- [x] `memlink broadcast` — write to multiple targets at once
- [x] Plugin Contract Tests published as public API
- [x] Spec Compliance checklist per plugin

## v0.4.0 — Writers ✅

- [x] **Mem0 Writer** — full roundtrip: read + write
- [x] `memlink merge` CLI command

## v0.5.0 — Broadcast ✅

- [x] **Zep Writer** — full roundtrip: read + write
- [x] `memlink broadcast` CLI command

## v0.6.0 — Chat Archives ✅

- [x] **ChatGPT Export Reader** — each conversation → one Canonical Memory
- [x] **Claude Export Reader** — each conversation → one Canonical Memory
- [x] Verified on 122 real Ombre memories, 0 warnings

## v1.0.0 — Stable ✅

- [x] Canonical Schema v1 Frozen (no breaking changes in 1.x)
- [x] Plugin API stable
- [x] Community format plugins (Mem0, Zep, etc.)
- [x] `spec/` published as standalone language-neutral specification

## v1.0.9 — Generic Write ✅

- [x] **GenericWriter** — Canonical → `notes/*.md` with YAML frontmatter; Generic format fully bidirectional (Obsidian, Logseq, Bear, iA Writer, plain Markdown)
- [x] **StreamSummaryReader registered** — `stream-summary` reader now in entry-points; discoverable via `memlink formats`
- [x] 257 tests

## v1.0.10 — Registry Safety ✅

- [x] **Registry discovery tests** — `pyproject.toml` entry-points cross-checked against `list_formats()` in CI; leaks fail immediately
- [x] `tomli>=2` dev dependency for Python 3.10 compatibility
- [x] 260 tests

## Future

- [x] **Reverse merge dedup** — verified: ID preserved in bidirectional roundtrip, `merge --on-conflict newest` sufficient
- [x] **Daily-notes roundtrip** — name/domains/tags/body all recovered from roundtrip block; verified on real workspace with 140 memories
- [x] **DREAMS.md reverse import** — OpenClaw Reader reads feel entries (hex IDs + native freetext headings); roundtrip-less entries parsed via valence fallback
- [x] **Non-hex bucket id guard** — OmbreWriter auto-generates valid hex id for non-standard IDs from external formats; `original_id` preserved in frontmatter
- [ ] **Source file roundtrip update** — when OmbreWriter remaps a non-hex id, update `"id"` in the source DREAMS.md roundtrip block for full reverse-flow consistency (CLI-layer work)
- [ ] MEMORY.md file lock (`filelock` dependency)
- [ ] Performance benchmarks (100/1K/10K memories)
- [ ] `--output-mode` extensible per format
- [ ] Converter pipeline hooks (before_read / after_write)
- [ ] Bidirectional sync (watchdog + diff-based)
- [ ] Web UI for visual memory browsing
