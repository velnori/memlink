# Synthetic demonstrations and recordings

## Two visible, reproducible walkthroughs

The README media comes from **real installed 2.0.0 CLI processes**, with the existing
Python network sentinel. The GIFs add captured input/output file excerpts and seven-second
reading pauses. They are **paced replays**, not real-time videos or performance measurements.
Commands use default human-readable output; the marked README Quickstarts use JSON.

| Demo | Actual input → output | Verification |
|---|---|---|
| Full Migration | Two generic Markdown records, one archived → two OpenClaw notes, canonical archive and receipt | `partial` / exit 0; native readback verified; schema + canonical roundtrip pass; strict Mem0 conversion exits 5 and creates no target |
| Context Handoff | Six approved synthetic private records, including optional USER/DREAMS → one Project A record | `human_reviewed=false`; `verify --pack` passes; B/profile/config/skill marker values absent; tampered copy exits 2 |

![Full Migration: captured files, real conversion and verification, strict rejection.](../assets/demos/full-migration.gif)

[Static output view](../assets/demos/full-migration.png) · [CLI stdout replay (.cast)](../assets/demos/full-migration.cast)

![Context Handoff: captured input, private pack, Project A selection, verification and tamper rejection.](../assets/demos/context-handoff.gif)

[Static output view](../assets/demos/context-handoff.png) · [CLI stdout replay (.cast)](../assets/demos/context-handoff.cast)

Read the [actual synthetic context](../assets/demos/project-a/context.md), its
[manifest](../assets/demos/project-a/manifest.json) and [receipt](../assets/demos/project-a/report.json).
These three files form a valid synthetic public handoff bundle. The private pack is not supplied.
[Verbatim captured output](../assets/demos/recording.md) and [machine recording](../assets/demos/recording.json)
include all 13 command arguments, actual stdout/stderr, expected/actual exits and tested canaries.
Every command recorded zero intercepted network attempts. Hashes prove consistency, not authorship.

The smaller packaged conformance fixture used here has **one** Project A record.
The earlier `tests/fixtures/module02` tutorial uses a different, larger A scenario.
Counts and promises should always be read with their named fixture set.

### Recreate the presentation media

From the checkout, use an interpreter with the **installed local candidate and PyYAML ≥6.0.3**:

```sh
python scripts/presentation_demo.py --python /path/to/installed/python --out demo-output/presentation-run --assets demo-output/presentation-assets
```

The `--python` interpreter executes the CLI with `memlink.verification`; it does not import
from `PYTHONPATH`. The script reuses `conformance --export-fixtures` and requires new output
and asset directories. The default recording needs only Python's standard library in the authoring
environment. Add `--media` when **Pillow is already available there** to produce GIF/PNG assets;
Pillow is an optional authoring tool, not a MemLink runtime dependency. `--font /path/to/mono.ttf`
selects an existing local monospace font when the platform font is unavailable.

The actual commands, file excerpts and field values are saved alongside the media. The script
checks that sources are unchanged, the strict target is absent, only the three public bundle files
are present, excluded markers and absolute source roots are absent, and the original public bundle
remains valid after a **separate copy** is tampered with. Do not replace these fixtures with personal
memory when creating public media.

## Full engineering demonstration

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
