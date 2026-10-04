"""Subprocess-only CLI acceptance; actual output, exit codes and offline sentinel."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from memlink.codec import memory_dict
from memlink.registry import get_reader
from memlink.safety import snapshot

ROOT = Path(__file__).parents[1]
FULL = ROOT / "tests/fixtures/module01/full-workspace"


def cli(*args, env=None, cwd=ROOT):
    process_env = os.environ.copy()
    process_env["PYTHONPATH"] = str(ROOT / "python")
    process_env["PYTHONUTF8"] = "1"
    if env:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "memlink.cli", *map(str, args)],
        cwd=cwd,
        env=process_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def payload(result, expected=0):
    assert result.returncode == expected, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_full_migration_one_command_no_per_record_review(tmp_path):
    before = snapshot(FULL)
    target = tmp_path / "openclaw"
    receipt = payload(
        cli(
            "convert",
            "--from",
            "generic",
            "--to",
            "openclaw",
            "--source",
            FULL,
            "--target",
            target,
            "--all",
            "--format",
            "json",
        )
    )
    assert receipt["status"] == "partial"
    assert receipt["accounting"] == {
        "input_records": 5,
        "parsed": 5,
        "invalid": 0,
        "unsupported": 0,
        "selected": 5,
        "excluded": 0,
        "output": 5,
        "conflict_skipped": 0,
    }
    assert receipt["sources"][0]["stats"]["files_total"] == 5
    assert not receipt["excluded"]
    assert (target / "memory/2026-10-02.md").exists()
    assert (target / "MEMORY.md").exists()
    back = get_reader("openclaw").read(target)
    original = get_reader("generic").read(FULL)
    assert sorted(json.dumps(memory_dict(m), sort_keys=True) for m in back.memories) == sorted(
        json.dumps(memory_dict(m), sort_keys=True) for m in original.memories
    )
    assert any(m.status == "archived" for m in back.memories)
    assert snapshot(FULL) == before
    assert json.loads((target / ".memlink/receipt.json").read_text(encoding="utf-8")) == receipt


@pytest.mark.parametrize("strict_flag", ["--strict", "--fail-on-loss"])
def test_actual_strict_alias_exits_five_before_any_target_write(tmp_path, strict_flag):
    target = tmp_path / "not-created"
    receipt = payload(
        cli(
            "convert", "-f", "generic", "-t", "mem0", "-s", FULL, "-T", target, "--all", strict_flag, "--format", "json"
        ),
        5,
    )
    assert receipt["status"] == "failed"
    assert receipt["tool_version"] == "2.0.0"
    assert receipt["readback"]["status"] == "verified"
    assert not target.exists()
    assert not list(tmp_path.glob(".memlink-*"))


@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], {"daily-a", "daily-b", "daily-c", "long-term"}),
        (["--include-archived"], {"daily-a", "daily-b", "daily-c", "long-term", "archived-note"}),
        (["--kind", "emotion"], {"daily-b"}),
        (["-k", "permanent"], {"long-term"}),
        (["--domain", "project"], {"daily-a"}),
        (["-d", "personal"], {"daily-b", "long-term"}),
        (["--status", "archived"], {"archived-note"}),
    ],
)
def test_filters_apply_to_actual_outputs_and_archive(tmp_path, flags, expected):
    target = tmp_path / "target"
    receipt = payload(
        cli("convert", "--from", "generic", "--to", "generic", "-s", FULL, "-T", target, *flags, "--format", "json")
    )
    archived = json.loads((target / ".memlink/archive.json").read_text(encoding="utf-8"))
    assert {e["memory"]["id"] for e in archived["records"]} == expected
    assert {m.id for m in get_reader("generic").read(target).memories} == expected
    assert len(receipt["excluded"]) == 5 - len(expected)


def test_migrate_dry_run_no_mutation_and_real_replace(tmp_path):
    target = tmp_path / "existing"
    payload(cli("convert", "-f", "generic", "-t", "openclaw", "-s", FULL, "-T", target, "--all", "--format", "json"))
    (target / "memory/2026-10-02.md").write_text("existing daily record", encoding="utf-8")
    (target / "TOOLS.md").write_bytes(b"original configuration")
    before = snapshot(target)
    dry = payload(
        cli(
            "migrate",
            "--from",
            "generic",
            "--to",
            "openclaw",
            "--source",
            FULL,
            "--target",
            target,
            "--all",
            "--on-conflict",
            "replace",
            "--dry-run",
            "--format",
            "json",
            "--verbose",
        )
    )
    assert dry["status"] == "planned"
    assert any(p["action"] == "update" for p in dry["plan"])
    assert snapshot(target) == before
    receipt = payload(
        cli(
            "migrate",
            "-f",
            "generic",
            "-t",
            "openclaw",
            "-s",
            FULL,
            "-T",
            target,
            "--all",
            "--on-conflict",
            "replace",
            "--format",
            "json",
            "-vv",
        )
    )
    assert receipt["readback"]["post_commit"] == "verified"
    backup = target / receipt["backup"]["path"]
    assert (backup / "memory/2026-10-02.md").read_text(encoding="utf-8") == "existing daily record"
    assert (target / "TOOLS.md").read_bytes() == b"original configuration"


def test_explicit_user_and_dreams_options(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "MEMORY.md").write_text("A fact", encoding="utf-8")
    (source / "USER.md").write_text("User details", encoding="utf-8")
    dreams = "## Dream 2026-10-02\n\nLegacy dream text\nvalence: 0.0\n"
    (source / "DREAMS.md").write_text(dreams, encoding="utf-8")
    default = payload(
        cli(
            "convert",
            "-f",
            "openclaw",
            "-t",
            "generic",
            "-s",
            source,
            "-T",
            tmp_path / "default",
            "--all",
            "--format",
            "json",
        )
    )
    assert len(default["records"]) == 1
    explicit = payload(
        cli(
            "convert",
            "-f",
            "openclaw",
            "-t",
            "generic",
            "-s",
            source,
            "-T",
            tmp_path / "explicit",
            "--all",
            "--include-user",
            "--include-dreams",
            "--format",
            "json",
        )
    )
    assert len(explicit["records"]) == 3


@pytest.mark.parametrize("strategy", ["newest", "oldest", "first", "last"])
def test_merge_multi_source_syntax_and_explicit_override(tmp_path, strategy):
    sources = []
    for index in (1, 2):
        source = tmp_path / f"source-{index}"
        source.mkdir()
        (source / "memories.json").write_text(
            json.dumps({"results": [{"id": "same", "memory": f"value-{index}", "created_at": index}]}), encoding="utf-8"
        )
        sources.append(f"mem0:{source}")
    receipt = payload(
        cli(
            "merge",
            "--sources",
            *sources,
            "--to",
            f"generic:{tmp_path / 'merged'}",
            "--on-conflict",
            strategy,
            "--all",
            "--format",
            "json",
        )
    )
    assert len(receipt["records"]) == 2
    linked = payload(
        cli(
            "merge",
            "-s",
            sources[0],
            "-s",
            sources[1],
            "-T",
            f"generic:{tmp_path / 'linked'}",
            "--link-by-id",
            "--on-conflict",
            strategy,
            "--format",
            "json",
        )
    )
    assert len(linked["records"]) == 1
    assert linked["workflow"]["merge"]["conflicts"][0]["explicit_link_by_id"] is True


@pytest.mark.parametrize(
    "targets", [["generic:success", "missing:failure"], ["missing:failure", "missing:also-failure"]]
)
def test_broadcast_partial_and_all_target_failure_are_nonzero(tmp_path, targets):
    specs = [f"{f}:{tmp_path / p}" for f, p in (s.split(":") for s in targets)]
    args = ["broadcast", "--from", f"generic:{FULL}", "--all", "--format", "json"]
    for spec in specs:
        args += ["-T", spec]
    receipt = payload(cli(*args), 3)
    assert receipt["status"] == "failed"
    assert len(receipt["targets"]) == 2
    assert any(t["exit_code"] != 0 for t in receipt["targets"])
    if targets[0].startswith("generic"):
        assert (tmp_path / "success/.memlink/receipt.json").exists()
        assert receipt["targets"][0]["exit_code"] == 0


def test_broadcast_space_group_and_dry_run(tmp_path):
    result = cli(
        "broadcast",
        "-f",
        f"generic:{FULL}",
        "--to",
        f"generic:{tmp_path / 'one'}",
        f"mem0:{tmp_path / 'two'}",
        "--dry-run",
        "--all",
        "--format",
        "json",
    )
    receipt = payload(result)
    assert receipt["status"] == "planned" and len(receipt["targets"]) == 2
    assert not (tmp_path / "one").exists() and not (tmp_path / "two").exists()


@pytest.mark.parametrize(
    "fmt,fixture",
    [
        ("generic", "module01/full-workspace"),
        ("mem0", "mem0_samples"),
        ("zep", "zep_samples"),
        ("ombre", "ombre_samples/dynamic"),
        ("openclaw", "openclaw_samples"),
    ],
)
def test_validate_all_levels_and_default_actual_format(tmp_path, fmt, fixture):
    source = ROOT / "tests/fixtures" / fixture
    for level in ("schema", "semantic", "roundtrip"):
        receipt = payload(cli("validate", "--source", source, "--from", fmt, "--level", level, "--format", "json"))
        assert receipt["errors"] == []
    assert cli("validate", "-s", source, "--level", "roundtrip").returncode == 0
    assert (
        payload(
            cli(
                "validate",
                "-s",
                source,
                "--from",
                fmt,
                "--level",
                "roundtrip",
                "--output-mode",
                "structured",
                "--intermediate",
                "openclaw",
                "--format",
                "json",
            )
        )["errors"]
        == []
    )


def test_roundtrip_zero_and_bad_json_not_green(tmp_path):
    assert cli("validate", "-s", tmp_path, "--from", "generic", "--level", "roundtrip").returncode == 2
    (tmp_path / "memories.json").write_text("{}", encoding="utf-8")
    assert cli("validate", "-s", tmp_path, "--from", "mem0", "--level", "schema").returncode == 2
    (tmp_path / "memories.json").write_text('{"results":[]}', encoding="utf-8")
    assert cli("validate", "-s", tmp_path, "--from", "mem0").returncode == 0
    assert cli("validate", "-s", tmp_path, "--from", "mem0", "--level", "roundtrip").returncode == 2


def test_inspect_exact_file_and_id_and_ambiguous_recognition(tmp_path):
    receipt = payload(cli("inspect", FULL / "daily-a.md", "--format", "generic", "--id", "daily-a"))
    assert receipt["memories"][0]["id"] == "daily-a"
    assert cli("inspect", FULL / "daily-a.md", "-f", "generic", "--id", "missing").returncode == 2
    broken = tmp_path / "broken.md"
    broken.write_text("---\nx: [invalid\n---\nbody", encoding="utf-8")
    assert cli("inspect", broken, "--format", "generic").returncode == 2
    (tmp_path / "a.json").write_text('{"results":[{"id":"a","memory":"one"}]}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"results":[{"id":"b","memory":"two"}]}', encoding="utf-8")
    assert (
        cli(
            "convert", "--from", "mem0", "--to", "generic", "-s", tmp_path, "-T", tmp_path.parent / "ambiguous"
        ).returncode
        == 2
    )


def test_stats_diff_aliases_version_formats_and_strict_exception(tmp_path):
    stats = cli("stats", "--source", FULL, "--from", "generic")
    assert stats.returncode == 0 and "2026-10-02" in stats.stdout
    assert "Total: 5" in stats.stdout
    assert (
        payload(
            cli(
                "diff",
                "--source",
                FULL,
                FULL,
                "--from-1",
                "generic",
                "--from-2",
                "generic",
                "--ignore",
                "timestamps,importance",
                "--format",
                "json",
            )
        )["issues"]
        == []
    )
    second = tmp_path / "second"
    second.mkdir()
    (second / "note.md").write_text("different", encoding="utf-8")
    assert cli("diff", "-s", FULL, second, "--from-1", "generic", "--from-2", "generic").returncode == 1
    assert cli("--version").stdout.strip() == "memlink 2.0.0"
    formats = cli("formats")
    assert formats.returncode == 0 and len(formats.stdout.splitlines()) == 8
    assert "stream-summary" in formats.stdout
    for alias, source, _sourcefmt in [
        ("ombre2claw", ROOT / "tests/fixtures/ombre_samples/dynamic", "ombre"),
        ("claw2ombre", ROOT / "tests/fixtures/openclaw_samples", "openclaw"),
    ]:
        assert cli(alias, "--source", source, "--target", tmp_path / alias, "--all").returncode == 0
    # Exception whitelist is per field, explicit and persisted; it does not hide the measured change.
    target = tmp_path / "strict-exception"
    args = [
        "convert",
        "--from",
        "generic",
        "--to",
        "generic",
        "-s",
        FULL,
        "-T",
        target,
        "--all",
        "--strict",
        "--allow-change",
        "source",
        "--format",
        "json",
    ]
    receipt = payload(cli(*args))
    assert receipt["policy"]["allow_changes"] == ["source"]


@pytest.mark.parametrize(
    "command",
    [
        "convert",
        "migrate",
        "merge",
        "broadcast",
        "validate",
        "diff",
        "stats",
        "inspect",
        "formats",
        "ombre2claw",
        "claw2ombre",
    ],
)
def test_help_is_real_subprocess(command):
    assert cli(command, "--help").returncode == 0
    assert cli(command, "-h").returncode == 0


def test_cli_warnings_are_visible_in_pretty_output(tmp_path):
    result = cli(
        "convert", "--from", "generic", "--to", "mem0", "-s", FULL, "-T", tmp_path / "out", "--all", "--verbose"
    )
    assert result.returncode == 0
    assert "Warning:" in result.stdout and "partial" in result.stdout


def test_core_commands_offline_socket_http_sentinel(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    marker = sentinel / "network-called.txt"
    (sentinel / "sitecustomize.py").write_text(
        """import socket, urllib.request, http.client, os
from pathlib import Path
def forbidden(*args, **kwargs):
    Path(os.environ["MEMLINK_NETWORK_MARKER"]).write_text("network call", encoding="utf-8")
    raise RuntimeError("Network forbidden by acceptance sentinel")
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
urllib.request.urlopen = forbidden
http.client.HTTPConnection.connect = forbidden
http.client.HTTPSConnection.connect = forbidden
""",
        encoding="utf-8",
    )
    env = {"PYTHONPATH": os.pathsep.join([str(sentinel), str(ROOT / "python")]), "MEMLINK_NETWORK_MARKER": str(marker)}
    for key in os.environ:
        if key.startswith(("OPENAI_", "ANTHROPIC_", "MEM0_", "ZEP_")):
            env[key] = ""
    target = tmp_path / "offline"
    commands = [
        ["convert", "-f", "generic", "-t", "openclaw", "-s", FULL, "-T", target, "--all"],
        ["migrate", "-f", "generic", "-t", "openclaw", "-s", FULL, "-T", target, "--all", "--on-conflict", "replace"],
        ["validate", "-s", target, "--from", "openclaw", "--level", "schema"],
        ["validate", "-s", target, "--from", "openclaw", "--level", "roundtrip"],
    ]
    for args in commands:
        result = cli(*args, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
