import random
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    timestamp: float
    tx_id: int
    unit_id: int
    register: int
    value: int


class ReplayBuffer:
    def __init__(self, capacity: int = 256, max_age: float = 300.0) -> None:
        if capacity < 1 or max_age <= 0:
            raise ValueError("invalid replay buffer limits")
        self._items: deque[Sample] = deque(maxlen=capacity)
        self.max_age = max_age

    def add(self, sample: Sample) -> None:
        self._items.append(sample)

    def select(self, rng: random.Random, now: float) -> Sample:
        valid = [item for item in self._items if 0 <= now - item.timestamp <= self.max_age]
        if not valid:
            raise LookupError("no fresh baseline sample")
        return valid[rng.randrange(len(valid))]

    def __len__(self) -> int:
        return len(self._items)
