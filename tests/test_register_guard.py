import pytest

from lab.register_map import Register, assert_register
from lab.firewall import EXPECTED_FORWARD_RULES, apply_segmentation
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


def test_wrong_in_subnet_endpoint_rejected() -> None:
    with pytest.raises(ValueError):
        assert_lab_target("192.168.100.21", PLC_IP)


class FakeNode:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.commands: list[str] = []

    def cmd(self, command: str) -> str:
        self.commands.append(command)
        if "iptables -S FORWARD" in command:
            body = "\n".join(EXPECTED_FORWARD_RULES)
        else:
            body = ""
        status = "1" if self.fail_on and self.fail_on in command else "0"
        return f"{body}\n__CPS_RC__{status}"


class FakeNet:
    def __init__(self, node: FakeNode) -> None:
        self.node = node

    def get(self, name: str) -> FakeNode:
        assert name == "fw01"
        return self.node


def test_firewall_enables_forwarding_only_after_verified_policy() -> None:
    node = FakeNode()
    apply_segmentation(FakeNet(node))
    disable = next(i for i, command in enumerate(node.commands) if "ip_forward=0" in command)
    policy = next(i for i, command in enumerate(node.commands) if "-P FORWARD DROP" in command)
    enable = next(i for i, command in enumerate(node.commands) if "ip_forward=1" in command)
    assert disable < policy < enable


def test_firewall_failure_keeps_forwarding_disabled() -> None:
    node = FakeNode("ip addr add 10.0.20.1/24")
    with pytest.raises(RuntimeError):
        apply_segmentation(FakeNet(node))
    assert "sysctl -w net.ipv4.ip_forward=0" in node.commands[-2]
