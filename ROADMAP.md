# Roadmap

## v0.1.0 — MVP ✅ (current)

- [x] Canonical Memory Schema v1
- [x] Ombre Brain Reader + Writer
- [x] OpenClaw Reader + Writer (daily-notes + structured modes)
- [x] Bidirectional conversion with 100% roundtrip
- [x] CLI: convert, validate, inspect, diff, stats, formats
- [x] Plugin registry with entry_points discovery
- [x] Structured Compatibility Report
- [x] 111 tests, 3 OS × 3 Python CI

## v0.2.0 — New Format + Stability

- [ ] **Mem0 Reader** — prove O(n) with a mainstream format
- [ ] MEMORY.md file lock (`filelock` dependency)
- [ ] `--fail-on-loss` for CI pipelines
- [ ] Daily-notes roundtrip test coverage
- [ ] Performance benchmarks (100/1K/10K memories)

## v0.3.0 — Ecosystem

- [ ] **Zep Reader**
- [ ] `memlink merge` — merge multiple sources into one target
- [ ] `memlink broadcast` — write to multiple targets at once
- [ ] Plugin Contract Tests published as public API
- [ ] Spec Compliance checklist per plugin
- [ ] MkDocs documentation site

## v1.0.0 — Stable

- [ ] Canonical Schema v1 stable (no breaking changes)
- [ ] Plugin API stable
- [ ] Community format plugins (Mem0, Zep, etc.)
- [ ] `spec/` published as standalone language-neutral specification

## Future

- [ ] `--output-mode` extensible per format
- [ ] Converter pipeline hooks (before_read / after_write)
- [ ] Bidirectional sync (watchdog + diff-based)
- [ ] Web UI for visual memory browsing
