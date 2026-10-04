"""Use canonical paths for test-created temporary directories."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def canonical_test_tempdir():
    previous = tempfile.tempdir
    # macOS exposes its system temp directory through the /var symlink.
    tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve(strict=True))
    try:
        yield
    finally:
        tempfile.tempdir = previous
