"""Installed adapter and core conformance against independent synthetic goldens."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import tempfile
from datetime import datetime, timezone
from importlib import metadata, resources
from pathlib import Path
from unittest.mock import patch

from ._version import __version__
from .codec import identity, identity_key, memory_dict, stable_json
from .converter import convert
from .detection import detect_format
from .models import Memory
from .read_support import load_json
from .registry import get_reader, get_writer, list_formats
from .safety import digest, file_key, safe_child, snapshot
from .transaction import OutputTransaction, TransactionError
from .validators import validate_instance, validate_memory
from .verification import invoke_cli, offline_guard


class NotRunError(RuntimeError):
    """An unavailable verification layer, never a passing check."""


def fixture_root() -> Path:
    return Path(str(resources.files("memlink").joinpath("resources/conformance")))


def compatibility_manifest() -> dict:
    return json.loads(
        resources.files("memlink").joinpath("resources/compatibility-manifest-v1.json").read_text(encoding="utf-8")
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _expect_error(action, codes=(2, 3, 4, 5)) -> None:
    try:
        action()
    except TransactionError as exc:
        _require(exc.exit_code in codes, f"Unexpected transaction exit {exc.exit_code}")
    except ValueError:
        _require(2 in codes, "Unexpected validation rejection")
    else:
        raise AssertionError("Invalid operation was accepted")


def _accounting(result) -> None:
    _require(not result.errors, str(result.errors))
    stats = result.stats
    _require(stats["parsed"] == len(result.memories), "Parsed count differs from actual records")
    _require(stats["records_total"] == len(result.records), "Record ledger total differs")
    _require(
        stats["records_total"] == sum(stats.get(k, 0) for k in ("parsed", "invalid", "unsupported")),
        "Record accounting is not conserved",
    )
    _require(
        stats["files_total"]
        == sum(stats.get("files_" + k, 0) for k in ("parsed", "invalid", "unsupported", "excluded")),
        "File accounting is not conserved",
    )


def _golden(case: dict, root: Path) -> None:
    reader = get_reader(case["adapter"], **case.get("reader_options", {}))
    result = reader.read(root)
    _accounting(result)
    _require(result.variant == case["variant"], f"Variant differs: {result.variant}")
    _require(result.stats["invalid"] == case.get("invalid", 0), "Invalid count differs from golden")
    expected = case["expected"]
    _require(len(result.memories) == len(expected) > 0, "Expected record count differs or golden is empty")
    actual = [{**memory_dict(m), "scope": identity(m)["scope"]} for m in result.memories]
    unmatched = list(actual)
    for golden in expected:
        match = next((a for a in unmatched if all(a.get(k) == v for k, v in golden.items())), None)
        _require(match is not None, f"Independent golden mismatch for {golden['id']}; fields: {list(golden)}")
        assert match is not None
        unmatched.remove(match)
    repeated = reader.read(root)
    _require(
        [memory_dict(m) for m in repeated.memories] == [memory_dict(m) for m in result.memories],
        "Reader output is not deterministic",
    )
    keys = [identity_key(m) for m in result.memories]
    _require(len(set(keys)) == len(keys), "Native IDs and scope collapse identities")
    _require(all(not validate_memory(m) for m in result.memories), "Canonical schema failed")


def _writer_case(case: dict, root: Path, work: Path) -> None:
    fmt = case["adapter"]
    target_fmt = fmt if list_formats()[fmt]["writer"] else "generic"
    before = snapshot(root)
    options = case.get("writer_options", {})
    first, second = work / "first", work / "second"
    receipt = convert(get_reader(fmt), get_writer(target_fmt, **options), root, first, all=True)["receipt"]
    convert(get_reader(fmt), get_writer(target_fmt, **options), root, second, all=True)
    _require(receipt["readback"]["post_commit"] == "verified", "Committed native output was not read back")
    _require(receipt["accounting"]["output"] == len(case["expected"]), "Output count differs")
    original = sorted(stable_json(memory_dict(m)) for m in get_reader(fmt).read(root).memories)
    restored = sorted(stable_json(memory_dict(m)) for m in get_reader(target_fmt).read(first).memories)
    _require(original == restored, "Archive-assisted full canonical roundtrip differs")
    native = get_reader(target_fmt)
    native.native_only = True
    native_result = native.read(first)
    _accounting(native_result)
    _require(len(native_result.memories) == len(original), "Native readback count differs")
    for record in receipt["records"]:
        actual = next(m for m in native_result.memories if m.id == record["target_id"])
        impact = record["fields"]["body"]
        _require(impact["target"] == actual.body, "Receipt body differs from real native readback")
        expected_status = "native-preserved" if impact["original"] == actual.body else "transformed"
        _require(impact["status"] == expected_status, "Native body change was misclassified")
    schemas = resources.files("memlink").joinpath("resources")
    for name, instance in (
        ("memlink-receipt-v1.schema.json", receipt),
        ("memlink-archive-v1.schema.json", load_json(first / ".memlink/archive.json")),
    ):
        _require(not validate_instance(instance, json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))), name)

    def hashes(p):
        return {k: v["sha256"] for k, v in snapshot(p).items() if k != ".memlink/receipt.json"}

    _require(hashes(first) == hashes(second), "Native/archive output differs across identical runs")
    _require(snapshot(root) == before, "Conversion changed its input")


def _migrate(fmt: str, root: Path, work: Path, options: dict) -> None:
    if fmt not in compatibility_manifest()["formats"] or not compatibility_manifest()["formats"][fmt]["writer"]:
        raise NotRunError("Safe apply is not declared for this third-party/reader-only target")
    for policy in ("skip", "replace", "rename"):
        target = work / policy
        convert(get_reader(fmt), get_writer(fmt, **options), root, target, all=True)
        (target / "unrelated.txt").write_text("synthetic config", encoding="utf-8")
        before = snapshot(target)
        planned = convert(
            get_reader(fmt),
            get_writer(fmt, **options),
            root,
            target,
            all=True,
            mode="migrate",
            conflict=policy,
            dry_run=True,
        )["receipt"]
        _require(planned["status"] == "planned" and snapshot(target) == before, "Dry-run changed target")
        receipt = convert(
            get_reader(fmt),
            get_writer(fmt, **options),
            root,
            target,
            all=True,
            mode="migrate",
            conflict=policy,
        )["receipt"]
        _require(receipt["readback"]["post_commit"] == "verified", "Migrate readback failed")
        _require((target / "unrelated.txt").read_text(encoding="utf-8") == "synthetic config", "Config changed")
        backup = target / receipt["backup"]["path"]
        _require((backup / "restore.json").is_file(), "Restore point missing")
        for name in receipt["backup"]["files"]:
            _require(digest(backup / name) == before[name]["sha256"], "Backup differs from pre-migration bytes")
        _require(bool(receipt["plan"]), "Conflict plan missing")


def _paths(fmt: str, work: Path, options: dict) -> None:
    for bad in ("../escape", "/escape", "C:/escape", "notes/../../escape"):
        _expect_error(lambda b=bad: safe_child(work, b), (2,))
    records = [Memory(id=k, body="Synthetic collision note.") for k in ("../a", "A", "a", "CON", "中文")]
    writer = get_writer(fmt, **options)
    writer.write(records, work / "collision")
    paths = [p["path"] for p in writer.last_receipt["plan"]]
    _require(len(set(map(file_key, paths))) == len(paths), "Case/path collision in output plan")
    _require(len(get_reader(fmt).read(work / "collision").memories) == len(records), "Collision lost records")


def _links(work: Path, kind: str) -> None:
    root = work / kind
    root.mkdir()
    original = work / (kind + "-original.md")
    original.write_text("Synthetic external file.", encoding="utf-8")
    link = root / "link.md"
    try:
        if kind == "symlink":
            link.symlink_to(original)
        else:
            os.link(original, link)
    except OSError as exc:
        raise NotRunError(f"OS cannot create {kind}: {exc.__class__.__name__}") from exc
    _expect_error(lambda: snapshot(root), (2,))


def _cli_policy(work: Path) -> None:
    source = fixture_root() / "generic"
    for strict in (False, True):
        target = work / ("strict" if strict else "default")
        args = [
            "convert",
            "--from",
            "generic",
            "--to",
            "mem0",
            "-s",
            str(source),
            "-T",
            str(target),
            "--all",
            "--format",
            "json",
        ]
        code, stdout, stderr = invoke_cli(args + (["--strict"] if strict else []))
        _require(code == (5 if strict else 0), f"Wrong policy exit: {code}; {stderr}")
        receipt = json.loads(stdout)
        _require(receipt["status"] == ("failed" if strict else "partial"), "Wrong loss status")
        _require(target.exists() != strict, "Strict/default disk side effect differs")
        _require(
            any(r["fields"]["summary"]["status"] == "archive-only" for r in receipt["records"]), "Loss not reported"
        )
    code, stdout, _ = invoke_cli(
        [
            "broadcast",
            "--from",
            f"generic:{source}",
            "--to",
            f"generic:{work / 'broadcast-good'}",
            f"missing-synthetic:{work / 'broadcast-bad'}",
            "--all",
            "--format",
            "json",
        ]
    )
    result = json.loads(stdout)
    _require(code == 3 and result["targets"][0]["exit_code"] == 0, "Partial broadcast exit differs")
    _require(result["targets"][1]["exit_code"] == 5, "Unsupported target was not rejected")
    _require(not (work / "broadcast-bad").exists(), "Failed target created")
    partial = fixture_root() / "mem0-partial"
    code, stdout, _ = invoke_cli(
        [
            "convert",
            "-f",
            "mem0",
            "-t",
            "generic",
            "-s",
            str(partial),
            "-T",
            str(work / "partial"),
            "--all",
            "--format",
            "json",
        ]
    )
    _require(code == 0 and json.loads(stdout)["accounting"]["invalid"] == 1, "Partial input accounting differs")


def _rollback(work: Path) -> None:
    source, target = fixture_root() / "generic", work / "rollback"
    convert(get_reader("generic"), get_writer("generic"), source, target, all=True)
    before = snapshot(target)
    put = OutputTransaction._put
    calls = 0

    def fail_after_one(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic partial commit failure")
        return put(self, *args, **kwargs)

    with patch.object(OutputTransaction, "_put", fail_after_one):
        _expect_error(
            lambda: convert(
                get_reader("generic"),
                get_writer("generic"),
                source,
                target,
                all=True,
                mode="migrate",
                conflict="replace",
            ),
            (3,),
        )
    _require(calls == 2, "Partial failure injection did not run")
    after = snapshot(target)
    _require(
        all(k in after and v["sha256"] == after[k]["sha256"] for k, v in before.items())
        and all(k in before or k.startswith(".memlink/backups/") for k in after),
        "Owned rollback differs",
    )


def _bundle(work: Path) -> None:
    from .context_bundle import choose, handoff, handoff_from, load_bundle, pack, verify

    source = fixture_root() / "openclaw"
    private, public, full = work / "private", work / "selected", work / "all"
    pack(source, private)
    verify(private)
    bundle = load_bundle(private)
    selection = choose(bundle, projects=["A"])
    handoff(bundle, selection, public, secrets="redact")
    verify(public, private_pack=private)
    text = "\n".join(p.read_text(encoding="utf-8") for p in public.rglob("*") if p.is_file())
    _require("PROJECT_A_SYNTHETIC" in text, "Selected context is absent")
    _require(
        all(
            s not in text
            for s in ("PROJECT_B_EXCLUDED", "PROFILE_EXCLUDED", "DREAMS_EXCLUDED", "CONFIG_EXCLUDED", "SKILL_EXCLUDED")
        ),
        "Unselected data leaked",
    )
    handoff_from(source, full, secrets="redact")
    verify(full)
    (public / "context.md").write_text("Synthetic tampering.", encoding="utf-8")
    _expect_error(lambda: verify(public), (2,))


def _ambiguity(work: Path) -> None:
    root = work / "ambiguous"
    root.mkdir()
    (root / "a.json").write_text('[{"id":"a","memory":"synthetic"}]', encoding="utf-8")
    (root / "b.json").write_text('[{"uuid":"b","fact":"synthetic"}]', encoding="utf-8")
    _expect_error(lambda: detect_format(root), (2,))
    _require(bool(get_reader("mem0").read(root).errors), "Ambiguous explicit input was accepted")


def _resources() -> None:
    names = [p.name for p in resources.files("memlink").joinpath("resources").iterdir() if p.name.endswith(".json")]
    _require(
        "canonical-v1.schema.json" in names and "compatibility-manifest-v1.json" in names, "Package assets missing"
    )
    for name in names:
        json.loads(resources.files("memlink").joinpath("resources").joinpath(name).read_text(encoding="utf-8"))
    _require(not validate_instance({"schema_version": "1", "id": "synthetic", "valence": 0.0}), "Schema rejected valid")
    _require(
        bool(validate_instance({"schema_version": "future", "id": "synthetic"})), "Schema accepted unknown version"
    )
    try:
        installed = metadata.version("memlink-bridge")
    except metadata.PackageNotFoundError as exc:
        raise NotRunError("Package metadata unavailable; run from an installed wheel") from exc
    code, out, _ = invoke_cli(["--version"])
    _require(
        code == 0 and out.strip() == f"memlink {installed}" and installed == __version__, "Version metadata differs"
    )


def _installed_integrity() -> None:
    try:
        distribution = metadata.distribution("memlink-bridge")
    except metadata.PackageNotFoundError as exc:
        raise NotRunError("Install a wheel to verify its RECORD hashes") from exc
    if Path(str(distribution.locate_file("memlink"))).resolve() != Path(__file__).resolve().parent:
        raise NotRunError("Source/editable import is outside the installed wheel; RECORD layer NOT_RUN")
    entries = [p for p in distribution.files or [] if p.parts[0] == "memlink" and p.hash is not None]
    _require(bool(entries), "Installed package has no RECORD-covered content")
    for entry in entries:
        assert entry.hash is not None
        _require(entry.hash.mode == "sha256", "Unsupported RECORD hash algorithm")
        path = Path(str(distribution.locate_file(entry)))
        actual = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).decode().rstrip("=")
        _require(actual == entry.hash.value, "Installed RECORD mismatch: " + str(entry))


def run_conformance(adapter: str = "all", fixtures: Path | None = None) -> dict:
    root = fixtures or fixture_root()
    before = snapshot(root)
    suite = load_json(root / "suite.json")
    _require(
        suite.get("schema") == "memlink-conformance-fixtures" and suite.get("version") == "1",
        "Unknown fixture contract",
    )
    formats = list_formats()
    if adapter != "all" and adapter not in formats:
        raise ValueError("Unknown adapter: " + adapter)
    selected = [c for c in suite["cases"] if adapter == "all" or c["adapter"] == adapter]
    _require(bool(selected), "No independent golden fixtures for this adapter")
    checks = []

    def check(name, action):
        try:
            action()
            checks.append({"name": name, "status": "PASS"})
        except NotRunError as exc:
            checks.append({"name": name, "status": "NOT_RUN", "reason": str(exc)})
        except Exception as exc:
            checks.append({"name": name, "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"})

    with tempfile.TemporaryDirectory(prefix="memlink-conformance-") as temp, offline_guard() as network:
        work = Path(temp).resolve(strict=True)
        for case in selected:
            path = safe_child(root, case["path"])
            case_work = work / case["id"]
            case_work.mkdir()
            check(case["id"] + ":golden-accounting-identity-schema", lambda c=case, p=path: _golden(c, p))
            if not case.get("invalid"):
                check(
                    case["id"] + ":discovery",
                    lambda c=case, p=path: _require(detect_format(p) == c["adapter"], "Discovery differs"),
                )
            if formats[case["adapter"]]["writer"]:
                check(
                    case["id"] + ":native-roundtrip-determinism-receipt",
                    lambda c=case, p=path, w=case_work: _writer_case(c, p, w),
                )
                check(
                    case["id"] + ":existing-target-transaction",
                    lambda c=case, p=path, w=case_work: _migrate(c["adapter"], p, w, c.get("writer_options", {})),
                )
                check(
                    case["id"] + ":path-collision",
                    lambda c=case, w=case_work: _paths(c["adapter"], w, c.get("writer_options", {})),
                )
            else:
                check(
                    case["id"] + ":export-canonical-archive-roundtrip",
                    lambda c=case, p=path, w=case_work: _writer_case(c, p, w),
                )
        check("core:ambiguous-input", lambda: _ambiguity(work))
        check("core:best-effort-strict-partial-exit", lambda: _cli_policy(work))
        check("core:partial-commit-rollback", lambda: _rollback(work))
        check("core:bundle-integrity-minimum-disclosure", lambda: _bundle(work))
        check("core:symlink", lambda: _links(work, "symlink"))
        check("core:hardlink", lambda: _links(work, "hardlink"))
        check("core:package-schema-version", _resources)
        check("core:installed-package-integrity", _installed_integrity)
        check(
            "core:no-network-no-api",
            lambda: _require(
                network["canary"] and network["attempts"] == 0, "Network sentinel failed or observed attempts"
            ),
        )
    check("fixtures:immutable", lambda: _require(snapshot(root) == before, "Conformance modified fixtures/goldens"))
    counts = {s: sum(c["status"] == s for c in checks) for s in ("PASS", "FAIL", "NOT_RUN")}
    return {
        "schema": "memlink-conformance-report",
        "version": "1",
        "tool_version": __version__,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "adapter": adapter,
        "fixture_suite_sha256": digest(root / "suite.json"),
        "status": "FAIL" if counts["FAIL"] else "PASS",
        "counts": counts,
        "checks": checks,
        "limits": (
            "Synthetic file/transaction/bundle layers only. NOT_RUN layers remain unverified; "
            "no live service, model memory or hostile-plugin sandbox claim."
        ),
    }


def export_fixtures(target: Path) -> None:
    if target.exists():
        raise ValueError("Fixture export requires a new directory")
    safe_child(target.absolute().parent, target.name)
    shutil.copytree(fixture_root(), target)


def cli_command(args) -> None:
    if args.export_fixtures:
        export_fixtures(args.export_fixtures)
        print("Exported independent synthetic fixtures: " + str(args.export_fixtures))
        return
    report = run_conformance(args.adapter, args.fixtures)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)
    print(text, end="")
    if report["status"] == "FAIL":
        raise SystemExit(2)
