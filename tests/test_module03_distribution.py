"""Release/conformance regressions with independent synthetic expectations."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from memlink.conformance import _golden, fixture_root, run_conformance
from memlink.converter import convert
from memlink.registry import get_reader, get_writer


@pytest.mark.parametrize("target_format", ["generic", "mem0", "zep", "ombre", "openclaw"])
def test_repeated_scoped_id_rename_allocates_fresh_native_ids(tmp_path, target_format):
    source = fixture_root() / "mem0-results"
    target = tmp_path / "workspace"
    convert(get_reader("mem0"), get_writer(target_format), source, target, all=True)
    for _ in range(2):
        receipt = convert(
            get_reader("mem0"),
            get_writer(target_format),
            source,
            target,
            all=True,
            mode="migrate",
            conflict="rename",
        )["receipt"]
        assert receipt["accounting"]["output"] == 2
        assert receipt["readback"]["post_commit"] == "verified"
    native = get_reader(target_format)
    native.native_only = True
    readback = native.read(target)
    assert not readback.errors
    assert len(readback.memories) == 6
    assert len({m.id for m in readback.memories}) == 6
    assert sorted(m.body.strip() for m in readback.memories) == sorted(["Synthetic user A.", "Synthetic user B."] * 3)


def test_conformance_rejects_wrong_independent_golden_without_updating_it(tmp_path):
    source = tmp_path / "fixtures"
    shutil.copytree(fixture_root(), source)
    suite = source / "suite.json"
    data = json.loads(suite.read_text(encoding="utf-8"))
    data["cases"][0]["expected"][0]["body"] = "Wrong independent expectation."
    suite.write_text(json.dumps(data), encoding="utf-8")
    before = suite.read_bytes()
    report = run_conformance("generic", source)
    assert report["status"] == "FAIL"
    assert any(c["status"] == "FAIL" and "golden" in c["name"] for c in report["checks"])
    assert suite.read_bytes() == before


@pytest.mark.parametrize(
    "adapter,relative,frontmatter",
    [
        (
            "ombre",
            "dynamic/general/newline-note.md",
            "bucket_id: newline-note\nname: Synthetic newline note\ntype: dynamic\n"
            "domain: general\ntags: [synthetic]\ncreated: 2026-10-02T00:00:00Z\n",
        ),
        (
            "openclaw",
            "memory/newline-note.md",
            "name: Synthetic newline note\nmetadata:\n  tags: [synthetic]\n  created_at: 2026-10-02T00:00:00Z\n",
        ),
    ],
)
@pytest.mark.parametrize(
    "header_newline,body",
    [
        ("\n", "Synthetic first line.\nSynthetic second line.\n"),
        ("\r\n", "Synthetic first line.\r\nSynthetic second line.\r\n"),
        ("\r\n", "Synthetic first line.\r\nSynthetic second line.\n"),
    ],
    ids=["lf", "crlf", "mixed"],
)
def test_frontmatter_readers_preserve_body_line_endings(tmp_path, adapter, relative, frontmatter, header_newline, body):
    source = tmp_path / relative
    source.parent.mkdir(parents=True)
    raw = (("---\n" + frontmatter + "---\n").replace("\n", header_newline) + body).encode("utf-8")
    source.write_bytes(raw)
    result = get_reader(adapter).read(tmp_path)
    assert not result.errors
    assert result.stats["invalid"] == 0
    assert len(result.memories) == 1
    memory = result.memories[0]
    # The closing delimiter consumes its optional CR; its LF starts the canonical body.
    expected_body = "\n" + body
    assert memory.id == "newline-note"
    assert memory.name == "Synthetic newline note"
    assert memory.tags == ["synthetic"]
    assert memory.created_at.isoformat() == "2026-10-02T00:00:00+00:00"
    assert memory.body == expected_body
    assert memory.checksum == hashlib.sha256(expected_body.encode("utf-8")).hexdigest()
    assert source.read_bytes() == raw


@pytest.mark.parametrize("autocrlf", ["false", "true", "input"])
def test_git_checkout_preserves_conformance_fixture_bytes_and_strict_goldens(tmp_path, autocrlf):
    root = Path(__file__).resolve().parents[1]
    repository = tmp_path / "repository"
    repository.mkdir()
    prefix = Path("python/memlink/resources/conformance")
    source = repository / prefix
    shutil.copytree(fixture_root(), source)
    attributes = root / ".gitattributes"
    if attributes.is_file():
        shutil.copyfile(attributes, repository / ".gitattributes")

    def git(*args):
        return subprocess.run(["git", *args], cwd=repository, check=True, capture_output=True)

    git("init", "--quiet")
    git("-c", "core.autocrlf=false", "add", "--all")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    git(
        "-c",
        f"core.autocrlf={autocrlf}",
        "checkout-index",
        "--all",
        "--force",
        f"--prefix={checkout.as_posix()}/",
    )
    restored = checkout / prefix
    suite_before = (source / "suite.json").read_bytes()
    suite = json.loads(suite_before)
    for case in suite["cases"]:
        _golden(case, restored / case["path"])
    for file in source.rglob("*"):
        if file.is_file():
            raw = file.read_bytes()
            assert b"\r\n" not in raw
            assert (restored / file.relative_to(source)).read_bytes() == raw
    assert (restored / "suite.json").read_bytes() == suite_before
    assert (source / "suite.json").read_bytes() == suite_before
