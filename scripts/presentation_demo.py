"""Capture real synthetic CLI output and render optional README demo media.

The CLI runs in the selected installed interpreter with the existing network
sentinel. Pillow is an optional authoring tool, never a MemLink dependency.
Destinations must be new; this script never publishes or overwrites a recording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p) for p in root.rglob("*") if p.is_file()}


def capture(root: Path, python: str) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONUTF8"] = "1"
    rows = []

    def run(name: str, args: list[str], expected: int = 0) -> None:
        probe = root / (name + "-network.json")
        process = subprocess.run(
            [python, "-m", "memlink.verification", str(probe), *args],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        network = json.loads(probe.read_text(encoding="utf-8"))
        assert process.returncode == expected, name + ": " + process.stdout + process.stderr
        assert network["canary"] and network["attempts"] == 0, name
        rows.append(
            {
                "name": name,
                "argv": args,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "exit_code": process.returncode,
                "expected_exit": expected,
                "network": network,
            }
        )
        print(f"{name}: exit {process.returncode}; network attempts {network['attempts']}", flush=True)

    run("version", ["--version"])
    assert rows[-1]["stdout"].strip() == "memlink 2.0.0"
    run("fixtures", ["conformance", "--export-fixtures", "fixtures"])
    before = snapshot(root / "fixtures")
    run(
        "full-migration",
        [
            "convert",
            "--from",
            "generic",
            "--to",
            "openclaw",
            "--source",
            "fixtures/generic",
            "--target",
            "migration",
            "--all",
        ],
    )
    receipt = json.loads((root / "migration/.memlink/receipt.json").read_text(encoding="utf-8"))
    assert receipt["accounting"]["output"] == 2
    assert receipt["status"] == "partial"
    assert receipt["readback"]["post_commit"] == "verified"
    run("validate-output", ["validate", "--from", "openclaw", "--source", "migration", "--level", "schema"])
    run(
        "validate-roundtrip",
        [
            "validate",
            "--from",
            "generic",
            "--source",
            "fixtures/generic",
            "--level",
            "roundtrip",
            "--intermediate",
            "openclaw",
        ],
    )
    run(
        "strict-blocked",
        [
            "convert",
            "--from",
            "generic",
            "--to",
            "mem0",
            "--source",
            "fixtures/generic",
            "--target",
            "strict-blocked",
            "--all",
            "--strict",
        ],
        expected=5,
    )
    assert not (root / "strict-blocked").exists()
    run(
        "pack",
        [
            "pack",
            "--from",
            "openclaw",
            "--input",
            "fixtures/openclaw",
            "--include-user",
            "--include-dreams",
            "--out",
            "private-pack",
        ],
    )
    run("select", ["select", "private-pack", "--project", "A", "--out", "selection-a.json"])
    run(
        "handoff",
        ["handoff", "private-pack", "--selection", "selection-a.json", "--secrets", "redact", "--out", "project-a"],
    )
    run("verify", ["verify", "project-a", "--pack", "private-pack"])
    run(
        "handoff-all",
        [
            "handoff",
            "--from",
            "openclaw",
            "--input",
            "fixtures/openclaw",
            "--all",
            "--secrets",
            "redact",
            "--out",
            "context-all",
        ],
    )
    run("verify-all", ["verify", "context-all"])
    public = root / "project-a"
    texts = "\n".join(p.read_text(encoding="utf-8") for p in public.rglob("*") if p.is_file())
    markers = ["PROJECT_B_EXCLUDED", "PROFILE_EXCLUDED", "DREAMS_EXCLUDED", "CONFIG_EXCLUDED", "SKILL_EXCLUDED"]
    assert "PROJECT_A_SYNTHETIC" in texts
    assert all(value not in texts for value in markers)
    assert str(root) not in texts and root.as_posix() not in texts
    assert {p.name for p in public.iterdir()} == {"context.md", "manifest.json", "report.json"}
    report = json.loads((public / "report.json").read_text(encoding="utf-8"))
    private_report = json.loads((root / "private-pack/report.json").read_text(encoding="utf-8"))
    all_report = json.loads((root / "context-all/report.json").read_text(encoding="utf-8"))
    assert not report["human_reviewed"]
    shutil.copytree(public, root / "tampered")
    (root / "tampered/context.md").write_text("Synthetic deliberate tampering.\n", encoding="utf-8")
    run("tamper-rejected", ["verify", "tampered"], expected=2)
    assert snapshot(root / "fixtures") == before
    result = {
        "schema": "memlink-presentation-recording-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "data": "bundled MIT synthetic fixtures only",
        "runtime": {"python": platform.python_version(), "os": platform.system()},
        "method": (
            "Real CLI child processes via memlink.verification; stdout/stderr verbatim. "
            "Media pauses are edited for reading, not execution timing."
        ),
        "status": "PASS",
        "checks": {
            "input_unchanged": True,
            "strict_target_absent": True,
            "project_b_profile_config_skills_absent": True,
            "public_paths_scrubbed": True,
            "tamper_rejected": True,
        },
        "summary": {
            "migration": {
                "accounting": receipt["accounting"],
                "status": receipt["status"],
                "readback": receipt["readback"],
            },
            "private_pack": {"records": len(private_report["records"])},
            "project_a": {"records": len(report["records"]), "human_reviewed": report["human_reviewed"]},
            "all_context": {"records": len(all_report["records"])},
        },
        "commands": rows,
    }
    (root / "recording.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def write_assets(root: Path, assets: Path, result: dict, media: bool, font: Path | None) -> None:
    assets.mkdir(parents=True, exist_ok=False)
    result = result.copy()
    result["files"] = {
        name: (root / name).read_text(encoding="utf-8")
        for name in (
            "fixtures/generic/note.md",
            "fixtures/generic/plain.md",
            "fixtures/openclaw/memory/project-a.md",
            "project-a/context.md",
        )
    }
    receipt = json.loads((root / "migration/.memlink/receipt.json").read_text(encoding="utf-8"))
    result["migration_files"] = sorted(snapshot(root / "migration"))
    result["migration_body_excerpts"] = {
        name: "\n".join(
            line
            for line in (root / "migration" / name).read_text(encoding="utf-8").splitlines()
            if line.startswith("Synthetic")
        )
        for name in result["migration_files"]
        if name.startswith("memory/")
    }
    result["receipt_excerpt"] = {
        "status": receipt["status"],
        "accounting.output": receipt["accounting"]["output"],
        "readback.post_commit": receipt["readback"]["post_commit"],
        "generic-a.metadata": next(row for row in receipt["records"] if row["id"] == "generic-a")["fields"]["metadata"][
            "status"
        ],
    }
    rows = {row["name"]: row for row in result["commands"]}
    scenes = {
        "full-migration": ["full-migration", "validate-output", "validate-roundtrip", "strict-blocked"],
        "context-handoff": ["pack", "select", "handoff", "verify", "tamper-rejected"],
    }
    # Public recordings contain relative CLI arguments and synthetic content only.
    serialized = json.dumps(result, ensure_ascii=False)
    assert str(root) not in serialized and root.as_posix() not in serialized
    shutil.copytree(root / "project-a", assets / "project-a")
    (assets / "recording.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Captured synthetic CLI output",
        "",
        result["method"],
        "",
        "Run these in a new recording directory after exporting the bundled fixtures. "
        "The strict and tamper checks intentionally return nonzero. The original project-a bundle stays valid.",
        "",
    ]
    for row in result["commands"]:
        lines += ["## " + row["name"], "", "```text", "$ memlink " + " ".join(row["argv"]), row["stdout"].rstrip()]
        if row["stderr"]:
            lines += ["[stderr]", row["stderr"].rstrip()]
        lines += [
            "```",
            "",
            f"Exit {row['exit_code']} (expected {row['expected_exit']}); "
            "tested network canary; zero intercepted attempts.",
            "",
        ]
    (assets / "recording.md").write_text("\n".join(lines), encoding="utf-8")
    for name, steps in scenes.items():
        events = [
            json.dumps(
                {"version": 2, "width": 112, "height": 28, "title": name + " / captured stdout / edited reading pauses"}
            )
        ]
        for index, step in enumerate(steps):
            row = rows[step]
            text = "\x1b[2J\x1b[H$ memlink " + " ".join(row["argv"]) + "\r\n"
            text += (row["stdout"] + row["stderr"]).replace("\n", "\r\n")
            text += f"\r\n[exit {row['exit_code']}; expected {row['expected_exit']}]\r\n"
            events.append(json.dumps([index * 7.0, "o", text]))
        events.append(json.dumps([len(steps) * 7.0, "o", "\r\n"]))
        (assets / (name + ".cast")).write_text("\n".join(events) + "\n", encoding="utf-8")
    if media:
        render_media(assets, rows, scenes, font, result)


def render_media(assets: Path, rows: dict, scenes: dict, font_path: Path | None, result: dict) -> None:
    from PIL import Image, ImageDraw, ImageFont

    if font_path is None:
        candidates = [Path("C:/Windows/Fonts/consola.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")]
        font_path = next((p for p in candidates if p.is_file()), None)
    if font_path is None:
        raise ValueError("Supply --font with a local monospace TTF for media rendering")
    body = ImageFont.truetype(str(font_path), 20)
    label = ImageFont.truetype(str(font_path), 16)
    title = ImageFont.truetype(str(font_path), 25)
    descriptions = {
        "full-migration": ("FULL MIGRATION", "Every approved record. Native notes + canonical archive + loss receipt."),
        "context-handoff": ("CONTEXT HANDOFF", "One project's context. Originals stay in the private pack."),
    }
    files = result["files"]
    migration_input = "fixtures/generic/note.md (exact excerpt)\n" + "\n".join(
        files["fixtures/generic/note.md"].splitlines()[:8]
    )
    migration_input += "\n\nfixtures/generic/plain.md\n" + files["fixtures/generic/plain.md"].rstrip()
    migration_output = ""
    for name, excerpt in result["migration_body_excerpts"].items():
        migration_output += f"migration/{name} (exact body excerpt)\n{excerpt}\n\n"
    migration_output += "migration/.memlink/receipt.json (field values)\n"
    migration_output += "\n".join(f"{key}: {value}" for key, value in result["receipt_excerpt"].items())
    handoff_input = "fixtures/openclaw/memory/project-a.md\n" + files["fixtures/openclaw/memory/project-a.md"].rstrip()
    handoff_input += (
        f"\n\nApproved private pack: {result['summary']['private_pack']['records']} synthetic records.\n"
        "Includes B, USER.md and DREAMS.md; only project A will be selected."
    )
    context_lines = files["project-a/context.md"].splitlines()
    handoff_output = "project-a/context.md (exact body excerpt)\n"
    handoff_output += "\n".join(line for line in context_lines if "PROJECT_A_SYNTHETIC" in line)
    handoff_output += (
        "\n\nproject-a/\n  context.md\n  manifest.json\n  report.json\n\n"
        "Verified against private pack. B/profile/config/skill markers absent."
    )
    excerpts = {
        "full-migration": (migration_input, migration_output),
        "context-handoff": (handoff_input, handoff_output),
    }
    for name, steps in scenes.items():
        frames = []
        captures = [("INPUT FILES", None, excerpts[name][0])]
        captures += [(step.upper(), rows[step], "") for step in steps]
        captures += [("OUTPUT FILES", None, excerpts[name][1])]
        for index, (step, row, excerpt) in enumerate(captures):
            frame = Image.new("RGB", (1280, 640), "#10121e")
            draw = ImageDraw.Draw(frame)
            draw.rounded_rectangle((22, 22, 1258, 618), radius=18, fill="#171b2b", outline="#36324e", width=2)
            draw.text((48, 43), descriptions[name][0], font=title, fill="#d2bdff")
            draw.text((48, 84), descriptions[name][1], font=label, fill="#c2c8dc")
            draw.text((1145, 48), f"{index + 1}/{len(captures)}", font=label, fill="#acb5cc")
            draw.line((48, 118, 1232, 118), fill="#39344e", width=1)
            terminal = []
            if row is not None:
                command = "$ memlink " + " ".join(row["argv"])
                output = row["stdout"] + row["stderr"]
                terminal = [(line, "#a8e4d5") for line in textwrap.wrap(command, width=96, subsequent_indent="  ")]
                terminal += [("", "#ffffff")]
            else:
                output = excerpt
                terminal = [(step + " / captured file excerpts", "#a8e4d5"), ("", "#ffffff")]
            for line in output.rstrip().splitlines():
                terminal.extend(
                    (part, "#eef0f9")
                    for part in (textwrap.wrap(line, width=96, replace_whitespace=False, drop_whitespace=False) or [""])
                )
            assert len(terminal) <= 16, f"{step}: output needs a taller frame; do not silently truncate it"
            y = 142
            for line, color in terminal:
                draw.text((48, y), line, font=body, fill=color)
                y += 25
            color = "#ffd693" if row is not None and row["exit_code"] else "#a8e4d5"
            footer = (
                f"exit {row['exit_code']} / expected {row['expected_exit']} / zero intercepted network attempts"
                if row is not None
                else "Invented MIT fixture data / generated files / verified local checks"
            )
            draw.text((48, 548), footer, font=label, fill=color)
            draw.text(
                (48, 588),
                "SYNTHETIC DATA  |  actual file/CLI captures  |  paced replay; no timing claim",
                font=label,
                fill="#c2c8dc",
            )
            frames.append(frame)
        poster_index = len(frames) - 1
        frames[poster_index].save(assets / (name + ".png"), optimize=True)
        frames[0].save(
            assets / (name + ".gif"),
            save_all=True,
            append_images=frames[1:],
            duration=7000,
            loop=0,
            optimize=True,
            disposal=2,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New private recording directory")
    parser.add_argument("--assets", type=Path, required=True, help="New reviewed synthetic public asset directory")
    parser.add_argument("--python", default=sys.executable, help="Installed candidate interpreter with PyYAML >=6.0.3")
    parser.add_argument("--media", action="store_true", help="Also render GIF/PNG with existing Pillow")
    parser.add_argument("--font", type=Path, help="Local monospace TTF; needed if no platform font is available")
    args = parser.parse_args()
    if args.out.exists() or args.assets.exists():
        parser.error("Use new destinations; recordings and assets are never overwritten")
    result = capture(
        args.out.resolve(), str(Path(args.python).resolve()) if Path(args.python).is_file() else args.python
    )
    write_assets(args.out.resolve(), args.assets.resolve(), result, args.media, args.font)


if __name__ == "__main__":
    main()
