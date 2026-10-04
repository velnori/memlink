"""Closure regressions using locale-mode CLI processes and managed source reads."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from memlink.converter import read_source
from memlink.models import Memory, Source
from memlink.registry import get_reader, get_writer
from memlink.safety import snapshot
from memlink.transaction import OutputTransaction, TransactionError, execute_output

ROOT = Path(__file__).parents[1]
UNICODE_BODY = "happy day 💛 𐐷 中文记忆"


def locale_env():
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    env["PYTHONPATH"] = str(ROOT / "python")
    return env


def cli_args(*args):
    # Disable interpreter UTF-8 mode too, including on machines whose defaults enable it.
    return [sys.executable, "-X", "utf8=0", "-m", "memlink.cli", *map(str, args)]


def run_cli(*args, stdout=subprocess.PIPE):
    return subprocess.run(cli_args(*args), env=locale_env(), stdout=stdout, stderr=subprocess.PIPE, timeout=30)


def make_source(tmp_path, body=UNICODE_BODY, mid="e1"):
    source = tmp_path / "source"
    source.mkdir()
    (source / "e1.md").write_text(f"---\nid: {mid}\nname: Unicode note\n---\n\n{body}", encoding="utf-8")
    return source


def conversion(source, target, *options):
    return ("convert", "--from", "generic", "--to", "openclaw", "-s", source, "-T", target, "--all", *options)


def test_subprocess_starts_without_utf8_environment_or_mode():
    code = (
        "import json, locale, os, sys; "
        "print(json.dumps({'locale': locale.getpreferredencoding(False), 'stdout': sys.stdout.encoding, "
        "'utf8_mode': sys.flags.utf8_mode, 'env': {k: os.environ.get(k) "
        "for k in ['PYTHONUTF8', 'PYTHONIOENCODING']}}))"
    )
    result = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", code], env=locale_env(), capture_output=True, timeout=30, check=True
    )
    startup = json.loads(result.stdout.decode("ascii"))
    assert startup["utf8_mode"] == 0
    assert startup["env"] == {"PYTHONUTF8": None, "PYTHONIOENCODING": None}
    if sys.platform == "win32":
        # Real Windows locale-mode pipes must use the locale before main() configures them.
        assert startup["stdout"].replace("gbk", "cp936") == startup["locale"].replace("gbk", "cp936")


@pytest.mark.parametrize("body", [UNICODE_BODY, "中文记忆"])
@pytest.mark.parametrize("output", ["pipe", "file"])
def test_json_conversion_is_utf8_without_environment_overrides(tmp_path, body, output):
    source = make_source(tmp_path, body)
    before = snapshot(source)
    target = tmp_path / "target"
    args = conversion(source, target, "--format", "json")
    if output == "file":
        path = tmp_path / "receipt.json"
        with path.open("wb") as stream:
            result = run_cli(*args, stdout=stream)
        raw = path.read_bytes()
    else:
        result = run_cli(*args)
        raw = result.stdout
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert result.stderr == b""
    assert not raw.startswith(b"\xef\xbb\xbf")
    receipt = json.loads(raw.decode("utf-8"))
    assert receipt["records"][0]["fields"]["body"]["original"] == body
    assert receipt["accounting"]["output"] == 1
    assert json.loads((target / ".memlink/receipt.json").read_text(encoding="utf-8")) == receipt
    assert get_reader("openclaw").read(target).memories[0].body == body
    assert snapshot(source) == before


def test_json_output_pipes_to_real_utf8_consumer(tmp_path):
    source = make_source(tmp_path)
    consumer_code = (
        "import json, sys; receipt = json.loads(sys.stdin.buffer.read().decode('utf-8')); "
        "assert receipt['records'][0]['fields']['body']['original'] == " + ascii(UNICODE_BODY) + "; print('ok')"
    )
    with subprocess.Popen(
        cli_args(*conversion(source, tmp_path / "target", "--format", "json")),
        env=locale_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as producer:
        result = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-c", consumer_code],
            env=locale_env(),
            stdin=producer.stdout,
            capture_output=True,
            timeout=30,
        )
        producer.stdout.close()
        producer.stdout = None
        _, stderr = producer.communicate(timeout=30)
        assert producer.returncode == 0, stderr.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert result.stdout.strip() == b"ok"


def test_pretty_output_and_inspect_preserve_unicode(tmp_path):
    source = make_source(tmp_path, mid="e1💛")
    result = run_cli(*conversion(source, tmp_path / "target", "-vv"))
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert "e1💛" in result.stdout.decode("utf-8")
    inspected = run_cli("inspect", source / "e1.md", "--format", "generic", "--id", "e1💛")
    assert inspected.returncode == 0, inspected.stderr.decode("utf-8")
    assert json.loads(inspected.stdout.decode("utf-8"))["memories"][0]["body"] == UNICODE_BODY


@pytest.mark.parametrize("output", ["pretty", "json"])
def test_strict_failure_unicode_receipt_and_diagnostics(tmp_path, output):
    source = make_source(tmp_path, mid="e1💛")
    target = tmp_path / "target"
    result = run_cli(*conversion(source, target, "--strict", "--format", output))
    assert result.returncode == 5
    assert not target.exists()
    if output == "json":
        receipt = json.loads(result.stdout.decode("utf-8"))
        assert receipt["status"] == "failed"
        assert receipt["records"][0]["fields"]["body"]["original"] == UNICODE_BODY
        assert "e1💛" in receipt["errors"][0]
    else:
        assert "e1💛" in result.stderr.decode("utf-8")


@pytest.mark.parametrize("kind", ["argparse", "lookup"])
def test_unicode_errors_use_utf8_stderr(tmp_path, kind):
    if kind == "argparse":
        result = run_cli(*conversion(tmp_path / "source", tmp_path / "target", "--status", "invalid💛"))
        expected = 2
    else:
        source = make_source(tmp_path)
        result = run_cli("inspect", source / "e1.md", "--format", "missing💛")
        expected = 5
    assert result.returncode == expected
    assert "💛" in result.stderr.decode("utf-8")
    assert result.stdout == b""


def test_cli_reconfigures_preexisting_legacy_text_streams(tmp_path):
    # Also exercise a non-UTF-8 sink on platforms with a UTF-8 locale by default.
    source = make_source(tmp_path)
    code = (
        "import sys; sys.stdout.reconfigure(encoding='cp936', errors='strict'); "
        "sys.stderr.reconfigure(encoding='cp936', errors='strict'); from memlink.cli import main; main()"
    )
    result = subprocess.run(
        [sys.executable, "-X", "utf8=0", "-c", code, "inspect", str(source / "e1.md"), "--format", "generic"],
        env=locale_env(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert json.loads(result.stdout.decode("utf-8"))["memories"][0]["body"] == UNICODE_BODY


@pytest.mark.parametrize("context_count", [0, 1, 3])
def test_managed_library_sources_require_complete_read_contexts(tmp_path, monkeypatch, context_count):
    source = make_source(tmp_path)
    memories, context, _, _ = read_source(get_reader("generic"), source, all=True)
    target = tmp_path / "target"
    get_writer("generic").write([Memory(id="old", body="keep")], target)
    before = snapshot(target)
    entered_commit = []
    monkeypatch.setattr(OutputTransaction, "before_commit", lambda self: entered_commit.append(True))
    kwargs = {"source_contexts": [context] * context_count} if context_count else {}
    with pytest.raises(TransactionError, match="one source_context per source") as failure:
        execute_output(memories, get_writer("generic"), target, sources=[source, source], mode="migrate", **kwargs)
    assert failure.value.exit_code == 2
    assert failure.value.receipt["status"] == "failed"
    assert snapshot(target) == before
    assert not entered_commit
    assert not list(tmp_path.glob(".memlink-stage-*"))
    assert not list(tmp_path.glob(".memlink-lock-*"))


@pytest.mark.parametrize("change", ["modify", "add", "delete"])
def test_managed_library_read_context_detects_source_mutation(tmp_path, monkeypatch, change):
    source = make_source(tmp_path)
    memories, context, _, _ = read_source(get_reader("generic"), source, all=True)
    target = tmp_path / "target"

    def mutate(self):
        if change == "modify":
            (source / "e1.md").write_text("external change", encoding="utf-8")
        elif change == "add":
            (source / "new.md").write_text("external new note", encoding="utf-8")
        else:
            (source / "e1.md").unlink()

    monkeypatch.setattr(OutputTransaction, "before_commit", mutate)
    with pytest.raises(TransactionError, match="Source changed") as failure:
        execute_output(memories, get_writer("generic"), target, sources=[source], source_contexts=[context])
    assert failure.value.exit_code == 4
    assert not target.exists()
    assert not list(tmp_path.glob(".memlink-stage-*"))
    assert not list(tmp_path.glob(".memlink-lock-*"))


def test_materialized_library_export_does_not_open_provenance_path(tmp_path):
    memory = Memory(id="a", body=UNICODE_BODY, source=Source("generic", "not-a-managed-root/missing.md"))
    writer = get_writer("generic")
    target = tmp_path / "target"
    writer.write([memory], target)
    assert writer.last_receipt["sources"] == []
    assert get_reader("generic").read(target).memories[0].body == UNICODE_BODY


def test_managed_library_export_with_matching_read_context_succeeds(tmp_path):
    source = make_source(tmp_path)
    memories, context, _, _ = read_source(get_reader("generic"), source, all=True)
    before = snapshot(source)
    target = tmp_path / "target"
    receipt = execute_output(memories, get_writer("generic"), target, sources=[source], source_contexts=[context])
    assert receipt["accounting"]["parsed"] == receipt["accounting"]["output"] == 1
    assert get_reader("generic").read(target).memories[0].body == UNICODE_BODY
    assert snapshot(source) == before


def test_library_context_without_managed_path_is_rejected(tmp_path):
    source = make_source(tmp_path)
    memories, context, _, _ = read_source(get_reader("generic"), source, all=True)
    target = tmp_path / "target"
    with pytest.raises(TransactionError, match="one source_context per source") as failure:
        execute_output(memories, get_writer("generic"), target, source_contexts=[context])
    assert failure.value.exit_code == 2
    assert not target.exists()
