"""Reproducible synthetic recording with real CLI processes and offline canaries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .conformance import export_fixtures
from .read_support import load_json
from .safety import digest, snapshot


def run_demo(root: Path) -> dict:
    if root.exists():
        raise ValueError("Demo requires a new output directory")
    root = root.absolute()
    root.mkdir(parents=True)
    fixtures = root / "fixtures"
    export_fixtures(fixtures)
    before = snapshot(fixtures)
    results = []
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["TEMP"] = str(root)
    environment["TMP"] = str(root)

    def run(name, args, expected=0, json_output=True):
        evidence = root / (name + "-network.json")
        process = subprocess.run(
            [sys.executable, "-m", "memlink.verification", str(evidence), *map(str, args)],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        network = load_json(evidence) if evidence.exists() else {"canary": False, "attempts": None}
        row = {
            "name": name,
            "argv": list(map(str, args)),
            "expected_exit": expected,
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "network": network,
        }
        results.append(row)
        print(f"{name}: exit {process.returncode} (expected {expected})", flush=True)
        if process.returncode != expected or not network["canary"] or network["attempts"] != 0:
            raise AssertionError(name + ": CLI/sentinel differs; " + process.stderr + process.stdout[:500])
        return json.loads(process.stdout) if json_output else process.stdout

    run("help", ["--help"], json_output=False)
    run("version", ["--version"], json_output=False)
    run("formats", ["formats"], json_output=False)
    run("manifest", ["formats", "--manifest"])
    source, target = fixtures / "generic", root / "migration"
    run("validate-source", ["validate", "-s", source, "--from", "generic", "--format", "json"])
    migration = run(
        "full-migration",
        [
            "convert",
            "-f",
            "generic",
            "-t",
            "openclaw",
            "-s",
            source,
            "-T",
            target,
            "--all",
            "--format",
            "json",
        ],
    )
    assert migration["accounting"]["output"] == 2
    assert any(f["status"] == "archive-only" for r in migration["records"] for f in r["fields"].values())
    run("validate-output", ["validate", "-s", target, "--from", "openclaw", "--format", "json"])
    run(
        "validate-roundtrip",
        [
            "validate",
            "-s",
            source,
            "--from",
            "generic",
            "--level",
            "roundtrip",
            "--intermediate",
            "openclaw",
            "--format",
            "json",
        ],
    )
    run(
        "strict-blocked",
        [
            "convert",
            "-f",
            "generic",
            "-t",
            "mem0",
            "-s",
            source,
            "-T",
            root / "strict-blocked",
            "--all",
            "--strict",
            "--format",
            "json",
        ],
        expected=5,
    )
    assert not (root / "strict-blocked").exists()
    native_path = next(p for p in migration["plan"] if p["path"].startswith("memory/"))["path"]
    (target / native_path).write_text("Synthetic pre-migration conflict.\n", encoding="utf-8")
    (target / "TOOLS.md").write_text("Synthetic unrelated config.\n", encoding="utf-8")
    target_before = snapshot(target)
    base = [
        "migrate",
        "-f",
        "generic",
        "-t",
        "openclaw",
        "-s",
        source,
        "-T",
        target,
        "--all",
        "--on-conflict",
        "replace",
        "--format",
        "json",
    ]
    run("migrate-plan", [*base, "--dry-run"])
    assert snapshot(target) == target_before
    applied = run("migrate-apply", base)
    assert any(p["action"] == "update" for p in applied["plan"])
    backup = target / applied["backup"]["path"]
    assert (backup / "restore.json").is_file()
    for name in applied["backup"]["files"]:
        assert digest(backup / name) == target_before[name]["sha256"]
    assert (target / "TOOLS.md").read_text(encoding="utf-8") == "Synthetic unrelated config.\n"
    assert all(digest(target / p["path"]) == p["sha256"] for p in applied["outputs"])
    run("migrate-verify", ["validate", "-s", target, "--from", "openclaw", "--format", "json"])
    claw, private, selection, public, all_out = (
        fixtures / "openclaw",
        root / "private-pack",
        root / "selection-a.json",
        root / "project-a",
        root / "all",
    )
    run(
        "handoff-all",
        [
            "handoff",
            "--from",
            "openclaw",
            "--input",
            claw,
            "--all",
            "--secrets",
            "redact",
            "--out",
            all_out,
            "--format",
            "json",
        ],
    )
    run("verify-all", ["verify", all_out, "--format", "json"])
    run(
        "pack",
        [
            "pack",
            "--from",
            "openclaw",
            "--input",
            claw,
            "--include-user",
            "--include-dreams",
            "--out",
            private,
            "--format",
            "json",
        ],
    )
    run("verify-private", ["verify", private, "--format", "json"])
    run("select", ["select", private, "--project", "A", "--out", selection, "--format", "json"])
    run(
        "handoff-selective",
        ["handoff", private, "--selection", selection, "--secrets", "redact", "--out", public, "--format", "json"],
    )
    run("verify-selective", ["verify", public, "--pack", private, "--format", "json"])
    text = "\n".join(p.read_text(encoding="utf-8") for p in public.rglob("*") if p.is_file())
    assert "PROJECT_A_SYNTHETIC" in text
    assert all(
        s not in text
        for s in ("PROJECT_B_EXCLUDED", "PROFILE_EXCLUDED", "DREAMS_EXCLUDED", "CONFIG_EXCLUDED", "SKILL_EXCLUDED")
    )
    (public / "context.md").write_text("Synthetic deliberate tampering.\n", encoding="utf-8")
    run("tamper-rejected", ["verify", public, "--format", "json"], expected=2, json_output=False)
    report = run("conformance", ["conformance", "--fixtures", fixtures, "--report", root / "conformance.json"])
    assert report["status"] == "PASS"
    assert snapshot(fixtures) == before
    result = {
        "status": "PASS",
        "data": "synthetic",
        "commands": results,
        "conformance": report,
        "input_unchanged": True,
    }
    (root / "demo-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Synthetic demo recording", "", "Every command is a real CLI process with a tested network canary.", ""]
    for row in results:
        lines += [
            "## " + row["name"],
            "",
            "```text",
            "memlink " + " ".join(row["argv"]),
            row["stdout"].rstrip(),
            "```",
            "",
            f"Exit: {row['exit_code']}; expected: {row['expected_exit']}",
            "",
        ]
    (root / "recording.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run_demo(args.out)


if __name__ == "__main__":
    main()
