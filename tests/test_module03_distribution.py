"""Release/conformance regressions with independent synthetic expectations."""

from __future__ import annotations

import shutil

import pytest

from memlink.conformance import fixture_root, run_conformance
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
    import json

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
