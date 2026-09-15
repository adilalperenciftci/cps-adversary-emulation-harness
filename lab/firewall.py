EXPECTED_FORWARD_RULES = (
    "-P FORWARD DROP",
    "-A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT",
    "-A FORWARD -s 10.0.10.0/24 -d 10.0.20.20/32 -p tcp -m tcp --dport 443 -j ACCEPT",
    "-A FORWARD -s 10.0.20.20/32 -d 192.168.100.20/32 -p tcp -m tcp --dport 502 -j ACCEPT",
)


def _checked(node: object, command: str) -> str:
    marker = "__CPS_RC__"
    output = node.cmd(f"{command}; printf '\\n{marker}%s' $?")
    body, separator, status = output.rpartition(marker)
    if not separator or status.strip() != "0":
        raise RuntimeError(f"segmentation command failed: {command}")
    return body.strip()


def apply_segmentation(net: object) -> None:
    firewall = net.get("fw01")
    _checked(firewall, "sysctl -w net.ipv4.ip_forward=0")
    try:
        _checked(firewall, "iptables -P FORWARD DROP")
        _checked(firewall, "iptables -F FORWARD")
        for interface, address in (
            ("fw01-eth0", "10.0.10.1/24"),
            ("fw01-eth1", "10.0.20.1/24"),
            ("fw01-eth2", "192.168.100.1/24"),
        ):
            _checked(firewall, f"ip addr flush dev {interface}")
            _checked(firewall, f"ip addr add {address} dev {interface}")
        for command in (
            "iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            "iptables -A FORWARD -s 10.0.10.0/24 -d 10.0.20.20 -p tcp --dport 443 -j ACCEPT",
            "iptables -A FORWARD -s 10.0.20.20 -d 192.168.100.20 -p tcp --dport 502 -j ACCEPT",
        ):
            _checked(firewall, command)
        rules = tuple(_checked(firewall, "iptables -S FORWARD").splitlines())
        if rules != EXPECTED_FORWARD_RULES:
            raise RuntimeError("installed segmentation policy differs from expected rules")
        _checked(firewall, "sysctl -w net.ipv4.ip_forward=1")
    except Exception:
        firewall.cmd("sysctl -w net.ipv4.ip_forward=0")
        firewall.cmd("iptables -P FORWARD DROP")
        raise
