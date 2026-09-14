import random

import pytest

from ot.replay_buf import ReplayBuffer, Sample


def sample(ts: float, value: int) -> Sample:
    return Sample(ts, value, 1, 40002, value)


def test_wraparound_and_deterministic_selection() -> None:
    buf = ReplayBuffer(capacity=2)
    for value in range(3):
        buf.add(sample(float(value), value))
    assert len(buf) == 2
    assert buf.select(random.Random(7), 2.0) == buf.select(random.Random(7), 2.0)


def test_empty_and_stale_buffers_fail() -> None:
    buf = ReplayBuffer(max_age=1.0)
    with pytest.raises(LookupError):
        buf.select(random.Random(1), 0.0)
    buf.add(sample(0.0, 10))
    with pytest.raises(LookupError):
        buf.select(random.Random(1), 5.0)
