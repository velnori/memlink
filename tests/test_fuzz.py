"""Seeded fuzz cases verify valid roundtrips and reject non-finite inputs explicitly."""

import copy
import math
import random
import string
from pathlib import Path

import pytest

from memlink.codec import content_checksum, memory_dict, stable_json
from memlink.models import Memory
from memlink.registry import get_reader, get_writer
from memlink.transaction import TransactionError


def _random_memory(rng):
    chars = string.ascii_letters + string.digits + "中文😊🚀\n\t "

    def text(n):
        return "".join(rng.choice(chars) for _ in range(rng.randint(1, n)))

    return Memory(
        id=text(50),
        name=text(80),
        summary=text(200),
        body=text(2000),
        kind=rng.choice(["dynamic", "permanent", "emotion", "unknown-kind"]),
        tags=[text(20) for _ in range(rng.randint(0, 5))],
        domains=[text(30) for _ in range(rng.randint(0, 3))],
        importance_score=rng.choice([None, rng.uniform(0, 15), float("nan")]),
        valence=rng.choice([None, 0.0, rng.random()]),
        arousal=rng.choice([None, 0.0, rng.random()]),
        pinned=rng.choice([True, False]),
        extensions={"unknown": text(50)},
    )


def _check_batch(memories, fmt, root: Path):
    writer = get_writer(fmt)
    if any(m.importance_score is not None and not math.isfinite(m.importance_score) for m in memories):
        with pytest.raises(TransactionError) as error:
            writer.write(memories, root)
        assert error.value.exit_code == 2
        assert not root.exists()
        return None
    writer.write(memories, root)
    result = get_reader(fmt).read(root)
    assert not result.errors
    expected = copy.deepcopy(memories)
    for m in expected:
        m.checksum = content_checksum(m.body)
    assert sorted(stable_json(memory_dict(m)) for m in result.memories) == sorted(
        stable_json(memory_dict(m)) for m in expected
    )
    return result.memories


@pytest.mark.slow
class TestFuzzOmbre:
    def test_read_write_never_crashes(self, tmp_path):
        rng = random.Random(101)
        for i in range(50):
            _check_batch([_random_memory(rng) for _ in range(rng.randint(1, 10))], "ombre", tmp_path / str(i))

    def test_roundtrip_semantic(self, tmp_path):
        rng = random.Random(102)
        for i in range(20):
            _check_batch([_random_memory(rng) for _ in range(rng.randint(1, 3))], "ombre", tmp_path / str(i))


@pytest.mark.slow
class TestFuzzOpenClaw:
    def test_write_read_never_crashes(self, tmp_path):
        rng = random.Random(103)
        for i in range(50):
            _check_batch([_random_memory(rng) for _ in range(rng.randint(1, 10))], "openclaw", tmp_path / str(i))


@pytest.mark.slow
class TestFuzzCrossFormat:
    def test_ombre_to_openclaw_never_crashes(self, tmp_path):
        rng = random.Random(104)
        for i in range(30):
            memories = [_random_memory(rng) for _ in range(rng.randint(1, 5))]
            canonical = _check_batch(memories, "ombre", tmp_path / f"source-{i}")
            if canonical is not None:
                _check_batch(canonical, "openclaw", tmp_path / f"target-{i}")
