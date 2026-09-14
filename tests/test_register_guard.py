import pytest

from lab.register_map import Register, assert_register
from ot.safety import PLC_IP, assert_lab_target


def test_allowed_registers() -> None:
    assert assert_register(40001) == Register.TARGET_RPM
    assert assert_register(40002) == Register.ACTUAL_RPM


def test_unrelated_register_rejected() -> None:
    with pytest.raises(ValueError):
        assert_register(40003)


@pytest.mark.parametrize("value", ["8.8.8.8", "1.1.1.1", "plc.local", "192.168.101.20"])
def test_external_or_dns_target_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        assert_lab_target(value, PLC_IP)
