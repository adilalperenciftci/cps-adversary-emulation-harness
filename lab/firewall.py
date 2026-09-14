from collections.abc import Iterable


def apply_segmentation(net: object) -> None:
    rules: dict[str, Iterable[str]] = {
        "corp01": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 10.0.20.20 -p tcp --dport 443 -j ACCEPT"),
        "corp02": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 10.0.20.20 -p tcp --dport 443 -j ACCEPT"),
        "corp03": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 10.0.20.20 -p tcp --dport 443 -j ACCEPT"),
        "historian": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 192.168.100.20 -p tcp --dport 502 -j ACCEPT"),
        "hmi01": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 192.168.100.20 -p tcp --dport 502 -j ACCEPT"),
        "eng01": ("iptables -P OUTPUT DROP",),
        "openplc01": ("iptables -P OUTPUT DROP", "iptables -A OUTPUT -d 10.0.20.20 -p tcp --sport 502 -j ACCEPT"),
    }
    for host, commands in rules.items():
        node = net.get(host)
        node.cmd("iptables -F")
        for command in commands:
            node.cmd(command)
