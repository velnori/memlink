# Contributing to memlink

Thanks for your interest in contributing!

memlink is an AI Memory Interchange Layer — we bridge different AI memory formats through a common Canonical Memory schema. Whether you want to fix a bug, add support for a new memory system, or improve documentation, this guide covers what you need.

## Code of Conduct

This project follows a [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Be respectful, constructive, and kind.

## Getting Started

```bash
git clone https://github.com/velnori/memlink.git
cd memlink
pip install -e ".[dev]"
```

The declared CI matrix is Python 3.10–3.12. PyYAML ≥6.0.3 is the runtime dependency; no AI API or online service is required. Run the checks below before submitting changes; the CI workflow verifies its configured platform matrix.

## Development Workflow

```bash
# Run tests
python -m pytest tests/ -v

# Lint
python -m ruff check python/memlink/ tests/

# Format
python -m ruff format --check python/memlink/ tests/

# Type check
python -m mypy python/memlink/

# Run the CLI locally
python -m memlink.cli --help
```

Run all checks before submitting a PR.

## Adding a New Format

Want to add support for a new memory system (Mem0, Zep, Letta, etc.)? Here's the recipe:

### 1. Study the format

Understand the source format's storage layout, field semantics, and edge cases. Read its docs or source code.

### 2. Map to Canonical

Create a field mapping table — how does each source field map to the Canonical Memory schema? Which fields are 1:1, which need transformation, which have no equivalent?

### 3. Implement the plugin

```
python/memlink/
  yourformat_reader.py    # YourFormat → Canonical
  yourformat_writer.py    # Canonical → YourFormat
```

Your Reader implements `FormatPlugin.read()` and returns `ReadResult`. Your Writer implements `FormatPlugin.write()` on the supplied staging path. Public writes are transaction-wrapped; see [the plugin contract](docs/api/plugin.md) for registration, readback, archive semantics and failure behavior.

Key rules:
- Use `pathlib.Path` for all file paths — never string concatenation
- Return warnings, don't silently drop data
- Declare capabilities honestly — what features does this format actually support?
- Preserve original fields in `metadata.memlink.original` for roundtrip integrity

### 4. Register the plugin

Add to `pyproject.toml`:

```toml
[project.entry-points."memlink.readers"]
yourformat = "memlink.yourformat_reader:YourFormatReader"

[project.entry-points."memlink.writers"]
yourformat = "memlink.yourformat_writer:YourFormatWriter"
```

### 5. Add tests

- Unit tests for your Reader and Writer
- Roundtrip test: `YourFormat → Canonical → YourFormat`
- Add sample fixtures to `tests/fixtures/yourformat_samples/`

### 6. Update docs

- Add your format to the Compatibility Matrix in README.md
- Document known lossy conversions

## Project Structure

```
memlink/
├── spec/              # Language-neutral Canonical Schema (read this first!)
│   ├── canonical-v1.md
│   ├── canonical-v1.schema.json
│   └── source-uri.md
├── python/memlink/    # Python implementation
│   ├── models.py      # Memory, Source, Relationship
│   ├── plugin.py      # FormatPlugin ABC, Capabilities, ReadResult
│   ├── converter.py   # Conversion pipeline
│   ├── validators.py  # Schema/semantic/roundtrip validation
│   └── *_reader.py / *_writer.py  # Format plugins
└── docs/
    └── DESIGN.md      # Full technical design
```

Read `spec/canonical-v1.md` before writing any Reader/Writer — it defines the target schema.

## Commit Messages

Use present tense, describe the why:

```
add Mem0 reader with roundtrip preservation
fix OpenClaw writer dropping extensions on roundtrip
docs: clarify source_uri encoding rules
```

## Pull Requests

1. Fork the repo and create a feature branch
2. Make your changes
3. Run `pytest`, `ruff check`, `ruff format`, and `mypy` — all must pass
4. Push and open a PR
5. CI will run tests on Linux, macOS, and Windows across Python 3.10–3.12
6. A maintainer will review

If your PR adds a new format, include a field mapping table in the PR description showing how each source field maps to Canonical.

## Fixture and conformance contributions

Use `memlink formats --manifest` and exact variants rather than brand-wide claims. Every fixture states direction, shape/version or review date/source, license/authorization and synthetic/official/real-redacted classification. Prefer invented data. Personal memories, credentials and private provenance are not allowed; real-redacted data needs explicit permission/privacy review and is not supplied here.

`python/memlink/resources/conformance/suite.json` contains independently authored canonical subsets, scope and accounting. Never regenerate expected values from the tested Writer. Every golden change needs a visible input/expected diff, reason and affected field/native/archive/unsupported contract. A test failure alone is not a reason to change its oracle.

```sh
memlink conformance --export-fixtures fixtures
memlink conformance --adapter openclaw --fixtures fixtures --report conformance.json
```

This runs outside the checkout after wheel installation without pytest or an AI API. Inspect every PASS/FAIL/NOT_RUN. Add meaningful regressions for behavior changes: malformed/ambiguous input, scoped duplicate IDs, native/receipt mappings, links/collisions, partial failure and default/strict. Retain public plugin signatures/registration; new adapters stay export-only until safe apply's complete transaction contract is verified. Update manifest and exact docs, then run existing tests/lint/type and readiness.

Synthetic demos/benchmarks are engineering evidence. Do not fabricate users, testimonials or adoption. Feedback/case templates are opt-in, require public-use permission and contain no personal memory. Do not add runtime telemetry.

## Questions and private security reports

Open a [Discussions](https://github.com/velnori/memlink/discussions) thread. Happy to help you get started.

Use [private reporting](SECURITY.md) for security issues, with a synthetic reproducer where possible.
