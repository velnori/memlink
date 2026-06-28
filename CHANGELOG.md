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

[0.1.0]: https://github.com/velnori/memlink/releases/tag/v0.1.0
