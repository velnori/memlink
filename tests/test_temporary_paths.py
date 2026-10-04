"""Internal temporary directories work through system aliases without accepting user links."""

import os
import subprocess
import tempfile

import pytest

from memlink.converter import run_roundtrip
from memlink.models import Memory
from memlink.registry import get_reader, get_writer
from memlink.safety import BoundaryError, snapshot
from memlink.testing import test_plugin_contract as check_plugin_contract

FORMATS = ["generic", "ombre", "openclaw", "mem0", "zep"]


@pytest.fixture
def aliased_tempdir(tmp_path, monkeypatch):
    real = tmp_path.resolve(strict=True) / "real-temp"
    real.mkdir()
    alias = real.parent / "temp-alias"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(real)], capture_output=True, check=True)
    else:
        alias.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(tempfile, "tempdir", str(alias))
    try:
        yield real, alias
    finally:
        if os.name == "nt":
            os.rmdir(alias)
        else:
            alias.unlink()


@pytest.mark.parametrize("fmt", FORMATS)
def test_roundtrip_with_aliased_system_tempdir(tmp_path, aliased_tempdir, fmt):
    real, _ = aliased_tempdir
    source = tmp_path.resolve(strict=True) / "source"
    get_writer(fmt).write([Memory(id="sample", name="Sample", body="Synthetic temporary path fixture.")], source)
    before = snapshot(source)
    report = run_roundtrip(source, fmt)
    assert report.total == report.matched == 1 and report.failed == 0, report.to_dict()
    assert snapshot(source) == before
    assert not list(real.iterdir())


@pytest.mark.parametrize("fmt", FORMATS)
def test_plugin_contract_with_aliased_system_tempdir(aliased_tempdir, fmt):
    real, _ = aliased_tempdir
    check_plugin_contract(get_reader(fmt), get_writer(fmt))
    assert not list(real.iterdir())


def test_user_paths_through_alias_are_still_rejected(aliased_tempdir):
    real, alias = aliased_tempdir
    assert get_reader("generic").read(alias).errors
    with pytest.raises(BoundaryError):
        get_writer("generic").write([Memory(id="sample")], alias / "user-target")
    assert not list(real.iterdir())
