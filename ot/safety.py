from ipaddress import IPv4Address, IPv4Network

LAB_NET = IPv4Network("192.168.100.0/24")
PLC_IP = IPv4Address("192.168.100.20")
HMI_IP = IPv4Address("192.168.100.10")
EMU_IP = IPv4Address("192.168.100.15")


def assert_lab_target(value: str, expected: IPv4Address | None = None) -> IPv4Address:
    try:
        address = IPv4Address(value)
    except ValueError as exc:
        raise ValueError("literal IPv4 address required") from exc
    if address not in LAB_NET or address in (LAB_NET.network_address, LAB_NET.broadcast_address):
        raise ValueError("address is outside the OT lab")
    if expected is not None and address != expected:
        raise ValueError(f"endpoint must be {expected}")
    return address
