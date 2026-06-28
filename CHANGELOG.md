# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
