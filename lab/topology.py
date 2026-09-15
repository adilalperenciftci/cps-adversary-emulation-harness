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


def main() -> int:
    from mininet.net import Mininet

    from lab.firewall import apply_segmentation

    net = Mininet(topo=CpsTwinTopo(), controller=None)
    try:
        net.start()
        apply_segmentation(net)
        print(net.get("fw01").cmd("iptables -S FORWARD"), end="")
    finally:
        net.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
