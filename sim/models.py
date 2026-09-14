from dataclasses import dataclass
from enum import StrEnum


class NodeState(StrEnum):
    SUSCEPTIBLE = "S"
    INFECTED = "I"
    RECOVERED = "R"
    QUARANTINED = "Q"


@dataclass(frozen=True)
class SimConfig:
    base_rate: float = 0.3
    recovery_rate: float = 0.04
    quarantine_rate: float = 0.03

    def __post_init__(self) -> None:
        for value in (self.base_rate, self.recovery_rate, self.quarantine_rate):
            if not 0.0 <= value <= 1.0:
                raise ValueError("probabilities must be in [0, 1]")


def clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))
