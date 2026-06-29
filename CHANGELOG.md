# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-29

### Added

- **Zep Reader** — reads Zep CE and Cloud JSON exports (facts format, session summary format, array format). Fifth format, 0 core changes needed.
- **`--fail-on-loss` flag** — `memlink convert --fail-on-loss` exits with code 5 if any fields will be lost during conversion. CI pipeline integration.
- Plugin Contract Tests extended to cover ZepReader via `testing.py`
- Test fixtures for Zep format (`tests/fixtures/zep_samples/`)

### Metrics

- 148 tests (16 new: 13 Zep + 3 --fail-on-loss)
- 5 formats: Ombre Brain, OpenClaw, Generic Markdown, Mem0, Zep

[0.3.0]: https://github.com/velnori/memlink/compare/v0.2.0...v0.3.0

## [0.4.0] — 2026-06-29

### Added

- **Mem0 Writer** — writes Canonical → Mem0 `get_all()` JSON format. Full roundtrip: read + write.
- **`memlink merge`** — merge memories from multiple sources into one target with conflict resolution (newest/oldest/first/last strategies).

### Metrics

- 172 tests (+24)
- mem0: reader ✅ writer ✅

[0.4.0]: https://github.com/velnori/memlink/compare/v0.3.0...v0.4.0

## [0.5.0] — 2026-06-29

### Added

- **Zep Writer** — writes Canonical → Zep facts JSON format. Full roundtrip: read + write.
- **`memlink broadcast`** — write memories from one source to multiple targets simultaneously.

### Metrics

- 189 tests (+17)
- zep: reader ✅ writer ✅
- 4 fully bidirectional formats: ombre, openclaw, mem0, zep

[0.5.0]: https://github.com/velnori/memlink/compare/v0.4.0...v0.5.0

## [0.6.0] — 2026-06-29

### Added

- **ChatGPT Export Reader** — reads official ChatGPT `conversations.json` exports. Each conversation → one Canonical Memory.
- **Claude Export Reader** — reads Anthropic official Claude `conversations.json` exports. Each conversation → one Canonical Memory.

### Metrics

- 210 tests (+21)
- 7 formats: ombre, openclaw, generic, mem0, zep, chatgpt, claude_export

[0.6.0]: https://github.com/velnori/memlink/compare/v0.5.0...v0.6.0

## [0.1.0] — 2026-06-28

### Added

- Canonical Memory Schema v1 (spec/canonical-v1.md + JSON Schema)
- Ombre Brain Reader + Writer (Ombre ↔ Canonical)
- OpenClaw Reader + Writer (daily-notes + structured output modes)
- Bidirectional conversion with 100% roundtrip on real data (118/118)
- Structured Compatibility Report (lost/degraded/preserved with reasons)
- FormatPlugin ABC with Capabilities discovery
- Plugin registry with entry_points auto-discovery
- CLI: convert, validate, inspect, diff, stats, formats, ombre2claw, claw2ombre
- Three-level validation: schema, semantic, roundtrip
- MLxxx error code system (ML001–ML401 across 4 layers)
- Plugin Contract Tests (testing.py — 6 standard tests per plugin)
- Fuzz testing (4 suites, 120 random iterations)
- README with quick start, spec compliance table, compatibility matrix
- DESIGN.md (570 lines, 4 rounds of external review)
- IMPLEMENTATION.md (950+ lines, file-by-file execution plan)
- ROADMAP.md (v0.1 → v1.0)
- SECURITY.md
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- GitHub Actions CI (3 OS × 3 Python, lint + type check + test + schema validation)
- GitHub Actions release workflow (tag → PyPI)
- pre-commit hooks (ruff + mypy)
- Dependabot configuration
- Issue/PR templates (bug, feature, format request)
- MkDocs documentation site configuration

### Tests

- 107 unit tests (0.27s)
- 4 fuzz test suites (2.99s)
- Real Ombre data verified: 118 memories, 100% roundtrip

## [0.2.0] — 2026-06-29

### Added

- **Mem0 Reader** — reads Mem0 `get_all()` JSON exports (both `{"results":[...]}` and `[...]` array formats). Fourth format, 0 core changes needed.
- Plugin Contract Tests extended to cover Mem0Reader via `testing.py`
- Test fixtures for Mem0 format (`tests/fixtures/mem0_samples/`)

### Metrics

- 132 tests (13 new for Mem0Reader)
- 4 formats: Ombre Brain, OpenClaw, Generic Markdown, Mem0

[0.2.0]: https://github.com/velnori/memlink/compare/v0.1.1...v0.2.0

## [0.1.1] — 2026-06-28

### Fixed

- **Registry stores classes, not instances** — `get_writer("openclaw", output_mode="structured")` now correctly passes construction params
- **`PluginNotFoundError`** replaces bare `KeyError` with friendly "Available: ombre, openclaw" message
- **`validate_roundtrip` implemented** — full `run_roundtrip()` with structured `RoundtripReport` (matched/partial/failed)
- **Compare Engine** — automatic `dataclass.fields()` iteration with `CompareOptions` (unicode/newline normalization, casefold tags, time epsilon). One place for diff, validate, and roundtrip
- **Dead code removed** — duplicate `_loss_reason` stubs, unused `_is_read_only`/`_is_write_only`
- **`ErrorCode` split** — `ROUNDTRIP_KIND/BODY/IMPORTANCE/TIME` (ML401-404)
- **`extensions` type tightened** — `dict[str, Any]` → `dict[str, JSONValue]`
- `OmbreReader` forces `name` to string (prevents int→str mismatch for numeric names)

### Metrics

- 107 unit tests + 4 fuzz tests
- Real data roundtrip: 118/118 matched (0.66s)

### Added

- **GenericReader** — reads any Markdown+YAML directory (Obsidian, Logseq, Bear, plain notes). Third format, 0 core changes needed.

[0.1.1]: https://github.com/velnori/memlink/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/velnori/memlink/releases/tag/v0.1.0
