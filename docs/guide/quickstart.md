# Quick Start

This is an unpublished local 2.0.0 checkout. Use its local wheel, or run from the repository in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path python).Path
python -m memlink.cli --version
python -m memlink.cli formats
python -m memlink.cli convert --from generic --to openclaw --source tests/fixtures/module01/full-workspace --target demo-output/openclaw --all --format json
python -m memlink.cli validate --from openclaw --source demo-output/openclaw --level schema
```

The demonstration target must be new/empty. If you already ran it, use a different new path or the explicit migrate options in the [CLI contract](cli.md). `demo-output/` is generated locally and excluded from Git. The output is readable Markdown plus a canonical archive and actual receipt. Default `partial` reports archive-only/transformed fields while completing the transfer; `--strict` blocks those unallowed impacts before committing.

Existing approved memory workspaces use `migrate`, with default `skip` and explicit `replace`/`rename` policies. They do not require manual per-record classification or copying. Backups and per-file rollback limits are explained in the [CLI contract](cli.md).

Supported source variants and roles appear in [Formats](../index.md). Mem0/Zep output is offline JSON; chat exports are transcripts. The [CLI contract](cli.md) documents options, exit codes and restore limits; [2.0 migration](migration-2.0.md) explains behavior changes.
