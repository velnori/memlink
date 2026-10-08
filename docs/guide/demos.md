# Synthetic demonstrations and recordings

Every bundled fixture is invented and MIT-licensed. No customer or real-redacted sample is supplied. Use the installed local candidate and a **new** output directory:

```sh
python -m memlink.demo --out synthetic-demo
```

The repository also provides executable recording wrappers:

```sh
bash scripts/demo.sh demo-output/shell-recording
```

```powershell
./scripts/demo.ps1 -OutputDirectory demo-output/powershell-recording
```

Set `MEMLINK_PYTHON` for the shell wrapper, or `-Python` for PowerShell, to choose a fresh installed interpreter. Release readiness executes both wrappers where available. New directories avoid overwriting prior recordings or user data.

The actual CLI processes produce `demo-results.json` (argv, stdout/stderr, expected and actual exits, network canary) and `recording.md`. The recording shows:

1. All approved records, including archived, migrate automatically without per-record categorization.
2. Real archive-only/transformed field reports and verified native output.
3. Default best effort exit 0 versus strict exit 5, with no strict target created.
4. A deliberately changed existing target, no-write dry run, conflicts, exact backup hashes, retained unrelated config and post-commit validation.
5. All-record Handoff and selective project A Handoff; every public file excludes B/profile/config/skill marker values.
6. Deliberate `context.md` tampering rejected by verify with exit 2.
7. Installed conformance, independent goldens, real readback, rollback and version/resources.

The tampered `project-a` directory is intentionally invalid at the end; `all` remains a valid demonstration. Private packs/selection files and recordings can contain full synthetic originals and local provenance. Do not substitute real personal input when recording a public demo.

These recordings prove engineering behavior. They do not demonstrate live upstream ingestion, model retrieval, customer outcomes, genuine adoption or human interactive review. Real case records remain empty until an actual consented case occurs.
