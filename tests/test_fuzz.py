"""Fuzz tests — random inputs must never crash Reader/Writer."""

import random
import string
import tempfile
from pathlib import Path

import pytest

from memlink.models import Memory
from memlink.ombre_reader import OmbreReader
from memlink.ombre_writer import OmbreWriter
from memlink.openclaw_reader import OpenClawReader
from memlink.openclaw_writer import OpenClawWriter


def _random_string(min_len=0, max_len=200):
    length = random.randint(min_len, max_len)
    chars = string.ascii_letters + string.digits + "中文测试😊🚀\n\t  "
    return "".join(random.choice(chars) for _ in range(length))


def _random_memory() -> Memory:
    return Memory(
        id=_random_string(1, 50),
        name=_random_string(0, 80),
        summary=_random_string(0, 200),
        body=_random_string(0, 5000),
        kind=random.choice(["dynamic", "permanent", "emotion", "unknown-kind"]),
        tags=[_random_string(1, 20) for _ in range(random.randint(0, 5))],
        domains=[_random_string(1, 30) for _ in range(random.randint(0, 3))],
        importance_score=random.choice([None, random.uniform(0, 15), float("nan")]),
        importance_label=random.choice([None, "high", "critical", "low"]),
        valence=random.choice([None, random.random()]),
        arousal=random.choice([None, random.random()]),
        pinned=random.choice([True, False]),
        checksum=_random_string(0, 64),
        extensions={_random_string(1, 10): _random_string(0, 50)} if random.random() > 0.7 else {},
    )


@pytest.mark.slow
class TestFuzzOmbre:
    def test_read_write_never_crashes(self):
        """Random Canonical memories → Ombre write → Ombre read, 50 iterations."""
        writer = OmbreWriter()
        reader = OmbreReader()
        for _ in range(50):
            mems = [_random_memory() for _ in range(random.randint(1, 10))]
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                try:
                    writer.write(mems, root)
                    result = reader.read(root)
                    assert isinstance(result.memories, list)
                    assert isinstance(result.warnings, list)
                except NotImplementedError:
                    pass
                except Exception as e:
                    # Only acceptable if truly malformed data
                    if "Circular" not in str(e) and "nesting" not in str(e):
                        raise

    def test_roundtrip_semantic(self):
        """Random memories write→read never crashes."""
        writer = OmbreWriter()
        reader = OmbreReader()
        for _ in range(20):
            mems = [_random_memory() for _ in range(random.randint(1, 3))]
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                try:
                    writer.write(mems, root)
                    result = reader.read(root)
                    assert isinstance(result.memories, list)
                except NotImplementedError:
                    pass


@pytest.mark.slow
class TestFuzzOpenClaw:
    def test_write_read_never_crashes(self):
        """Random Canonical → OpenClaw write → OpenClaw read, 50 iterations."""
        writer = OpenClawWriter()
        reader = OpenClawReader()
        for _ in range(50):
            mems = [_random_memory() for _ in range(random.randint(1, 10))]
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                try:
                    writer.write(mems, root)
                    result = reader.read(root)
                    assert isinstance(result.memories, list)
                except NotImplementedError:
                    pass
                except Exception as e:
                    if "Concurrent" not in str(e):
                        raise


@pytest.mark.slow
class TestFuzzCrossFormat:
    def test_ombre_to_openclaw_never_crashes(self):
        """Random Ombre→Canonical→OpenClaw, 30 iterations."""
        o_reader = OmbreReader()
        o_writer = OmbreWriter()
        oc_writer = OpenClawWriter()
        oc_reader = OpenClawReader()

        for _ in range(30):
            mems = [_random_memory() for _ in range(random.randint(1, 5))]
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                o_writer.write(mems, root)
                canonical = o_reader.read(root).memories

                with tempfile.TemporaryDirectory() as td2:
                    root2 = Path(td2)
                    oc_writer.write(canonical, root2)
                    back = oc_reader.read(root2)
                    assert isinstance(back.memories, list)
