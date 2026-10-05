"""Offline, hostile input, and transaction boundary regressions for module 2."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from memlink import context_bundle as cb
from memlink import context_scope as cs
from memlink.codec import content_checksum, stable_json
from memlink.read_support import load_json
from memlink.safety import snapshot
from memlink.transaction import TransactionError
from tests.test_module02_context import FIXTURE, SECRET, cli, ok


@pytest.fixture
def source(tmp_path):
    out = tmp_path / "synthetic workspace 中文 💛"
    shutil.copytree(FIXTURE, out)
    return out


@pytest.fixture
def private(source, tmp_path):
    out = tmp_path / "private-pack"
    cb.pack(source, out, include_user=True, include_dreams=True)
    return cb.load_bundle(out)


def test_network_sentinel_full_flow_no_keys(source, tmp_path):
    sentinel = tmp_path / "network-sentinel"
    sentinel.mkdir()
    marker = sentinel / "network-attempt.txt"
    (sentinel / "sitecustomize.py").write_text(
        """import socket, urllib.request, http.client, os
from pathlib import Path
def forbidden(*args, **kwargs):
    Path(os.environ['MEMLINK_NETWORK_MARKER']).write_text('network attempted', encoding='utf-8')
    raise RuntimeError('Network forbidden by acceptance sentinel')
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.gethostbyname = forbidden
urllib.request.urlopen = forbidden
http.client.HTTPConnection.connect = forbidden
http.client.HTTPSConnection.connect = forbidden
""",
        encoding="utf-8",
    )
    root = Path(__file__).parents[1]
    env = {"PYTHONPATH": os.pathsep.join([str(sentinel), str(root / "python")]), "MEMLINK_NETWORK_MARKER": str(marker)}
    for key in os.environ:
        if any(word in key.upper() for word in ("API_KEY", "API_TOKEN")) or key.startswith(
            ("OPENAI_", "ANTHROPIC_", "MEM0_", "ZEP_")
        ):
            env[key] = ""
    canary_env = os.environ.copy()
    canary_env.update(env)
    canary = subprocess.run(
        [sys.executable, "-c", "import socket; socket.getaddrinfo('example.invalid',443)"],
        env=canary_env,
        capture_output=True,
        timeout=10,
    )
    assert canary.returncode != 0 and marker.exists()
    marker.unlink()  # Owned canary marker only; subsequent attempts are retained.
    before = snapshot(source)
    pack = tmp_path / "pack"
    selection = tmp_path / "selection.json"
    public = tmp_path / "public"
    all_output = tmp_path / "all"
    commands = [
        ("pack", "--from", "openclaw", "--input", source, "--out", pack),
        ("verify", pack),
        ("select", pack, "--project", "A", "--out", selection),
        ("handoff", pack, "--selection", selection, "--out", public),
        ("verify", public, "--pack", pack),
        ("handoff", "--from", "openclaw", "--input", source, "--all", "--secrets", "redact", "--out", all_output),
        ("verify", all_output),
    ]
    for command in commands:
        ok(*command, env=env)
    assert not marker.exists() and snapshot(source) == before


def test_direct_source_mutates_during_target_commit(source, tmp_path, monkeypatch):
    target = tmp_path / "direct"

    def changing(self, relative):
        if self.target == target and relative == "context.md":
            (source / "memory/project-a.md").write_text("concurrent source change", encoding="utf-8")

    monkeypatch.setattr(cb.BundleTransaction, "after_file_commit", changing)
    with pytest.raises(TransactionError) as failed:
        cb.handoff_from(source, target, secrets="redact")
    assert failed.value.exit_code == 4 and not target.exists()
    assert not list(tmp_path.glob(".memlink-stage-*")) and not list(tmp_path.glob(".memlink-lock-*"))


def test_target_competition_preserves_other_task_files(private, tmp_path, monkeypatch):
    target = tmp_path / "public"

    def competing(self):
        target.mkdir()
        (target / "other-task.txt").write_text("external owner", encoding="utf-8")

    monkeypatch.setattr(cb.BundleTransaction, "before_commit", competing)
    with pytest.raises(TransactionError) as failed:
        cb.handoff(private, cb.choose(private, projects=["A"]), target)
    assert failed.value.exit_code == 4
    assert {p.name for p in target.iterdir()} == {"other-task.txt"}
    assert (target / "other-task.txt").read_text(encoding="utf-8") == "external owner"


def test_private_record_rehash_cannot_replace_source_readback(private):
    m = load_json(private.root / "manifest.json")
    records = private.records
    records[0]["memory"]["body"] = "edited canonical body"
    records[0]["memory"]["checksum"] = content_checksum("edited canonical body")
    records[0]["sha256"] = cs.object_sha({k: v for k, v in records[0].items() if k != "sha256"})
    m["records"][0]["sha256"] = records[0]["sha256"]
    content = {
        p.relative_to(private.root).as_posix(): p.read_bytes()
        for p in private.root.rglob("*")
        if p.is_file() and p.name not in {"manifest.json", "report.json"}
    }
    content["records.jsonl"] = "".join(stable_json(r) + "\n" for r in records).encode("utf-8")
    for path, raw in cb._seal(m, content).items():
        (private.root / path).write_bytes(raw)
    result = cli("verify", private.root)
    assert result.returncode == 2 and "source readback" in result.stderr


@pytest.mark.parametrize("change", ["kind", "version", "records-type", "unknown-field", "scope", "duplicate-key"])
def test_malformed_bundle_schema_rejected_without_traceback(private, change):
    path = private.root / "manifest.json"
    manifest = load_json(path)
    if change == "duplicate-key":
        raw = path.read_text(encoding="utf-8").replace('"version": "1"', '"version": "1", "version": "2"')
        path.write_text(raw, encoding="utf-8")
    else:
        if change == "kind":
            manifest["kind"] = "alien"
        elif change == "version":
            manifest["version"] = "future"
        elif change == "records-type":
            manifest["records"] = "not-array"
        elif change == "unknown-field":
            manifest["extra-private-data"] = "invalid"
        else:
            manifest["scope"]["rules"].append("credentials/**")
        path.write_text(json.dumps(manifest), encoding="utf-8")
    result = cli("verify", private.root)
    assert result.returncode == 2 and "Traceback" not in result.stderr


@pytest.mark.parametrize("link_type", ["hardlink", "symlink"])
def test_approved_memory_links_rejected(source, tmp_path, link_type):
    outside = tmp_path / "outside.md"
    outside.write_text("OUTSIDE_ONLY_SYNTHETIC", encoding="utf-8")
    linked = source / "memory/linked.md"
    if link_type == "hardlink":
        os.link(outside, linked)
    else:
        try:
            linked.symlink_to(outside)
        except OSError:
            pytest.skip("Symlink creation unavailable in this environment")
    target = tmp_path / "failed"
    result = cli("pack", "--from", "openclaw", "--input", source, "--out", target)
    assert result.returncode == 2 and not target.exists()


def test_explicit_credential_field_and_pem_redaction(source, tmp_path):
    password = "synthetic-password-value-42"
    pem = "-----BEGIN PRIVATE KEY-----\nSYNTHETIC_NOT_A_REAL_KEY\n-----END PRIVATE KEY-----"
    json_password = "synthetic-json-password-99"
    (source / "memory/credentials.md").write_text(
        f'password: {password}\n{{"password": "{json_password}"}}\n{pem}', encoding="utf-8"
    )
    output = tmp_path / "redacted"
    result = ok(
        "handoff",
        "--from",
        "openclaw",
        "--input",
        source,
        "--all",
        "--secrets",
        "redact",
        "--out",
        output,
        "--format",
        "json",
    )
    report = json.loads(result.stdout)
    assert report["safety"]["detected"] >= 3 and report["safety"]["redacted"] >= 3
    for file in output.iterdir():
        text = file.read_text(encoding="utf-8")
        assert password not in text and json_password not in text
        assert SECRET not in text and "SYNTHETIC_NOT_A_REAL_KEY" not in text
    ok("verify", output)


def test_invalid_selections_and_no_accidental_all(private, tmp_path):
    for command in (
        ("select", private.root, "--out", tmp_path / "selection.json"),
        ("handoff", private.root, "--out", tmp_path / "public"),
    ):
        assert cli(*command).returncode == 2
    selection = cb.choose(private, all_records=True)
    selection["records"].pop()
    with pytest.raises(ValueError, match="omits"):
        cb.validate_selection(private, selection)
    selection = cb.choose(private, projects=["A"])
    selection["human_reviewed"] = True
    with pytest.raises(ValueError, match="schema"):
        cb.validate_selection(private, selection)
    assert not (tmp_path / "public").exists()


def test_bad_yaml_in_long_term_memory_is_not_silently_omitted(source, tmp_path):
    (source / "MEMORY.md").write_text("---\nname: [invalid\n---\nbody", encoding="utf-8")
    target = tmp_path / "failed"
    result = cli("pack", "--from", "openclaw", "--input", source, "--out", target)
    assert result.returncode == 2 and not target.exists()


def test_source_snapshot_read_change_rejected(source, tmp_path, monkeypatch):
    original = Path.read_bytes
    note = source / "memory/project-a.md"

    def changing(path):
        raw = original(path)
        if path == note:
            note.write_text("new content after read", encoding="utf-8")
        return raw

    monkeypatch.setattr(Path, "read_bytes", changing)
    with pytest.raises(TransactionError) as failed:
        cb.pack(source, tmp_path / "failed")
    assert failed.value.exit_code == 4 and not (tmp_path / "failed").exists()


def test_complex_scope_preserved_private_and_not_disclosed(source, tmp_path):
    marker = "PRIVATE_COMPLEX_SCOPE_SYNTHETIC"
    (source / "memory/complex.md").write_text(
        "---\nname: Complex scope\nmetadata:\n  memlink:\n    original:\n      user_id:\n"
        f"        private: {marker}\n---\npublic body",
        encoding="utf-8",
    )
    cb.pack(source, tmp_path / "private")
    pack = cb.load_bundle(tmp_path / "private")
    selection = cb.choose(pack, sources=["memory/complex.md"])
    cb.handoff(pack, selection, tmp_path / "public")
    assert marker in (pack.root / "records.jsonl").read_text(encoding="utf-8")
    for file in (tmp_path / "public").iterdir():
        assert marker not in file.read_text(encoding="utf-8")
    assert cb.verify(tmp_path / "public", private_pack=pack.root)["status"] == "verified"


def test_owned_temp_directory_alias_works_but_input_alias_is_rejected(source, tmp_path, monkeypatch):
    import tempfile

    owned = tmp_path / "owned-temp"
    owned.mkdir()
    alias = tmp_path / "temp-alias"
    if sys.platform == "win32":
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(owned)], capture_output=True, timeout=10)
        if created.returncode:
            pytest.skip("Junction creation unavailable")
    else:
        alias.symlink_to(owned, target_is_directory=True)
    assert alias.resolve(strict=True) == owned
    monkeypatch.setattr(tempfile, "tempdir", str(alias))
    target = tmp_path / "public"
    cb.handoff_from(source, target, secrets="redact")
    assert cb.verify(target)["status"] == "verified" and not list(owned.iterdir())
    with pytest.raises(ValueError, match="Symlink/junction"):
        cb.handoff_from(alias, tmp_path / "rejected-input", secrets="redact")
