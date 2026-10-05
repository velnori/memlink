# Security policy

Report vulnerabilities privately through [GitHub private security advisories](https://github.com/velnori/memlink/security/advisories/new). Do not post personal memories, tokens, private packs or full receipts in a public issue. Include affected package/Python/OS versions, a synthetic reproducer, impact and the relevant exact file variant. Response and fix timing depend on maintainer availability; no response SLA is promised.

| Version | Scope |
|---|---|
| 2.0.0 local candidate | Current local engineering verification; not yet a published or independently finalized release |
| 1.0.11 | Legacy behavior; migration guidance supplied; findings should identify the affected version |
| Earlier releases | Not actively verified by this candidate |

MemLink processes explicitly approved local Markdown/JSON. Core migration/handoff/verify requires no network, AI API or key/token, and adds no telemetry. See [privacy/threat model](docs/guide/privacy.md) and [no-network evidence](docs/guide/no-network.md).

Known implemented boundaries include unique/bounded YAML/JSON parsing with a SafeLoader-derived YAML loader; finite typed canonical data; file/record/byte/depth/node limits; approved roots and overlap/link/reparse/hardlink rejection; escaped deterministic IDs/collision allocation; staging and actual native readback; content snapshots/competition checks; backups; verified per-file commit; and rollback of owned unchanged writes. These are behavioral contracts with synthetic regressions, not guarantees from using pathlib or safe_load alone.

Remaining limits: cooperative locks do not isolate hostile same-user code; per-file commits are not globally atomic or power-loss recovery; a wholly self-consistent bundle rewrite needs a trusted external digest/original pack to detect; hashes are not signatures; third-party plugins execute trusted Python; redaction is advisory and can miss encoded secrets/private facts; consumer models have independent prompt-injection/network/memory behavior.

The sole runtime dependency is **PyYAML ≥6.0.3**. Exact local build/check tools are pinned in requirements/release.txt; workflow actions are pinned to official commit hashes. Dependency advisory checks query the installed runtime version against public PyPI advisory metadata and record date/source/PASS/FAIL/NOT_RUN. Bounded static AST/workflow checks state their scope. Build/dev tools are outside the runtime advisory scope. Unknown vulnerabilities, a comprehensive third-party audit and remote publishing protection settings are **NOT_RUN**, never implied by this file.

Release build/test jobs use read-only permissions without publishing credentials. The separate pypi environment job uses trusted publishing only after candidate validation/artifact hashes; it does not run contributed build/test code. Protected tag/environment reviewers and trusted-publisher identity must be verified separately before an authorized release. PR workflows do not receive release credentials.

Dependabot opens reviewed dependency updates. Reports, scans and a security policy do not themselves constitute independent security certification.
