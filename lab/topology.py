import time

try:
    from mininet.topo import Topo
except ImportError:
    class Topo:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Mininet is required on the Linux lab host")


class CpsTwinTopo(Topo):
    def build(self) -> None:
        s_it = self.addSwitch("s_it", dpid="0000000000000001")
        s_dmz = self.addSwitch("s_dmz", dpid="0000000000000002")
        s_ot = self.addSwitch("s_ot", dpid="0000000000000003")

        for idx in range(1, 4):
            host = self.addHost(
                f"corp0{idx}", ip=f"10.0.10.{10 + idx}/24",
                defaultRoute="via 10.0.10.1",
            )
            self.addLink(host, s_it)

        historian = self.addHost(
            "historian", ip="10.0.20.20/24", defaultRoute="via 10.0.20.1"
        )
        hmi = self.addHost(
            "hmi01", ip="192.168.100.10/24", defaultRoute="via 192.168.100.1"
        )
        eng = self.addHost(
            "eng01", ip="192.168.100.15/24", defaultRoute="via 192.168.100.1"
        )
        plc = self.addHost(
            "openplc01", ip="192.168.100.20/24", defaultRoute="via 192.168.100.1"
        )
        self.addLink(historian, s_dmz)
        self.addLink(hmi, s_ot)
        self.addLink(eng, s_ot)
        self.addLink(plc, s_ot)

        firewall = self.addHost("fw01", ip=None)
        self.addLink(firewall, s_it)
        self.addLink(firewall, s_dmz)
        self.addLink(firewall, s_ot)


topos = {"cpstwin": CpsTwinTopo}


def _probe(host: object, address: str, port: int) -> bool:
    output = host.cmd(
        "python3 -c \"import socket; "
        f"socket.create_connection(('{address}', {port}), 1).close()\"; "
        "printf '__CPS_RC__%s' $?"
    )
    return output.rpartition("__CPS_RC__")[2].strip() == "0"


def verify_segmentation(net: object) -> dict[str, bool]:
    historian = net.get("historian")
    plc = net.get("openplc01")
    historian.cmd(
        "python3 -m http.server 443 --bind 10.0.20.20 "
        ">/tmp/cps-historian.log 2>&1 &"
    )
    plc.cmd(
        "python3 -m http.server 502 --bind 192.168.100.20 "
        ">/tmp/cps-openplc.log 2>&1 &"
    )
    time.sleep(0.2)
    try:
        results = {
            "enterprise_to_historian_https": _probe(
                net.get("corp01"), "10.0.20.20", 443
            ),
            "historian_to_plc_modbus": _probe(historian, "192.168.100.20", 502),
            "hmi_to_plc_modbus": _probe(net.get("hmi01"), "192.168.100.20", 502),
            "enterprise_to_ot_blocked": not _probe(
                net.get("corp01"), "192.168.100.20", 502
            ),
            "ot_to_enterprise_blocked": not _probe(
                plc, "10.0.10.11", 443
            ),
        }
    finally:
        historian.cmd("pkill -f 'http.server 443' || true")
        plc.cmd("pkill -f 'http.server 502' || true")
    if not all(results.values()):
        raise RuntimeError(f"segmentation verification failed: {results}")
    return results


def main() -> int:
    from mininet.net import Mininet
    from mininet.nodelib import LinuxBridge

    from lab.firewall import apply_segmentation

    net = Mininet(topo=CpsTwinTopo(), controller=None, switch=LinuxBridge)
    try:
        net.start()
        apply_segmentation(net)
        print(net.get("fw01").cmd("iptables -S FORWARD"), end="")
        for check, passed in verify_segmentation(net).items():
            print(f"{check}={'PASS' if passed else 'FAIL'}")
    finally:
        net.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
