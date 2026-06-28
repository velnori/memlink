# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in memlink, please report it privately to
the maintainers rather than opening a public issue.

**Contact**: Open a private security advisory on GitHub:
https://github.com/velnori/memlink/security/advisories/new

Please include:
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact

We aim to respond within 48 hours and publish a fix within 7 days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ Yes |
| < 0.1   | ❌ No |

## Scope

memlink processes local markdown files. Security concerns include:

- **Path traversal**: Malicious frontmatter could attempt to read/write outside the target directory
- **YAML bombs**: Excessively nested or large YAML could cause resource exhaustion
- **Concurrency**: Concurrent writes to the same target without file locking

### Known mitigations

- All file paths use `pathlib.Path`, preventing string-based path injection
- YAML parsing uses `yaml.safe_load()` (no arbitrary code execution)
- `serialization.py` limits nesting depth and detects circular references
- `MEMORY.md` concurrent modification is detected via mtime+size

## Dependencies

memlink has one runtime dependency: `pyyaml>=6.0`. We monitor PyYAML security advisories and upgrade promptly.

Dependabot is configured to automatically open PRs for dependency updates monthly.
