from dataclasses import dataclass
from enum import IntEnum


class Register(IntEnum):
    RUN_CMD = 0
    TARGET_RPM = 40001
    ACTUAL_RPM = 40002


@dataclass(frozen=True)
class ProcessConfig:
    alpha: float = 0.18
    noise_std: float = 4.0
    nominal_rpm: int = 1800
    max_safe_rpm: int = 3500

    def __post_init__(self) -> None:
        if not 0.0 < self.alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        if self.noise_std < 0:
            raise ValueError("noise_std must be non-negative")
        if not 0 < self.nominal_rpm <= self.max_safe_rpm:
            raise ValueError("invalid RPM bounds")


ALLOWED_REGISTERS = frozenset(Register)


def assert_register(reg: int) -> Register:
    try:
        item = Register(reg)
    except ValueError as exc:
        raise ValueError(f"register {reg} is outside the lab map") from exc
    if item not in ALLOWED_REGISTERS:
        raise ValueError(f"register {reg} is not allowed")
    return item
