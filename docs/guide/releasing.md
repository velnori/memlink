# Local release candidates and readiness

This checkout contains **local 2.0.0 candidate tooling**. The command performs no push, PR, merge, tag, publication, deployment, community post or OSS application.

With existing development tools and a local PyYAML ≥6.0.3 wheelhouse:

```sh
python scripts/release_readiness.py --output .planning/local-release --wheelhouse /path/to/wheelhouse
```

Use a new evidence directory. On a restricted machine, use `--fresh-root /writable/path/outside-checkout` with a new directory. Preserve old candidates using `--dist dist/new-candidate`. Installation has no index by default; `--allow-index` explicitly allows runtime dependency installation. `--audit-online` separately queries public PyPI advisories by package name/version, without user memory or fixtures.

Readiness snapshots public Git-listed files and non-ignored new files, excluding internal notes. It records commit and dirty state separately from the actual public working-tree digest. It builds wheel/sdist using the installed setuptools backend in a public source copy, checks schemas/manifest/license/fixtures, rebuilds from sdist and compares all wheel members. It does not stage or commit files.

The fresh venv is **outside the checkout**, without system/user sites. Imports must come from that venv with the candidate version and supported PyYAML. Actual installed CLI processes run help/version/formats/manifest/validate/convert/migrate/pack/select/handoff/all/verify/conformance. Conformance verifies the installed package files against their wheel RECORD hashes. Readiness also alters one fixture resource in its own fresh venv, requires a failing integrity check and exit 2, then restores the original bytes. These hashes establish consistency, not signed authorship. Synthetic demos prove loss policies, conflicts/backups/readback, minimum disclosure and tamper rejection, with tested network canaries. Actual README blocks and shell/PowerShell recording wrappers run where available.

The full suite uses the fresh runtime/PyYAML; only existing test/coverage/docs tools are added for those checks. Lint/format/type, independent draft 2020-12 schema validation, strict docs, bounded static rules, current runtime dependency advisories and benchmarks have explicit results. `--benchmark-evidence` reuses measurements only after verifying identical core bytes/dependency/Python/OS/sizes.

| Local artifact | Evidence |
|---|---|
| readiness.json / readiness.md | Version, commit/dirty/source digest, build hashes, checks, manifest, workflows, OS/Python matrix |
| conformance.json | Exact variant/core layers; unavailable layers NOT_RUN |
| demo-results.json / demo-recording.md | Real argv, stdout/stderr, exit codes, canaries |
| benchmark.json / benchmark.md | Measurements, failures and limits |
| security.json | Bounded AST/workflow rules and runtime PyYAML advisory query |
| tests.xml / coverage / logs | Actual local tests and skipped cases |

`local_status=PASS` means performed local gates passed. It does not verify remote CI, other OS/Python, unavailable symlink layers, live upstream ingestion, consumer models, real adoption or independent final acceptance. Read every NOT_RUN. `release_authorized=false` is explicit: engineering evidence is not publication authorization. A comprehensive third-party security audit remains **NOT_RUN**.

Internal closeouts, manual decision notes, .planning and local evidence stay outside public packages and Pages. Package checks and MkDocs exclude the whole relaunch directory.

For a future separately authorized release, Actions are fixed to official commit hashes and build/check tools are fixed in `requirements/release.txt`. Update pins with reviewed diffs and readiness. Index resolution is not a signature or full supply-chain audit.

Tag-triggered candidate jobs check tag/version equality and main ancestry, then validate Python 3.10–3.12 on Linux/macOS/Windows with read-only permissions and no publishing credentials. A separate `pypi` environment job downloads and checks artifact hashes before trusted publishing with job-scoped `id-token: write`. It does not check out contributed code or run its build/tests. PRs never trigger release publishing; coverage credentials are limited to trusted pushes.

Maintainers must separately configure and verify trusted-publisher identity, protected tags and pypi environment reviewers. Those settings, the new remote matrix and publishing remain **NOT_RUN** locally. Human publication authorization must match the exact candidate and target.
