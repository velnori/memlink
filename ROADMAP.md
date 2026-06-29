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

## Future

- [ ] **Reverse merge dedup** — `openclaw→ombre` 反向导入时跳过已有记忆。核心问题：Ombre bucket_id 和 OpenClaw memory ID 格式不同，merge 去重依赖 id 字段，需要先确认 ID 在双向转换中是否保持一致，再做 dedup 逻辑
- [ ] MEMORY.md file lock (`filelock` dependency)
- [ ] Daily-notes roundtrip test coverage
- [ ] Performance benchmarks (100/1K/10K memories)
- [ ] `--output-mode` extensible per format
- [ ] Converter pipeline hooks (before_read / after_write)
- [ ] Bidirectional sync (watchdog + diff-based)
- [ ] Web UI for visual memory browsing
