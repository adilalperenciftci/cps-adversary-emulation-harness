try:
    from mininet.topo import Topo
except ImportError:
    class Topo:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Mininet is required on the Linux lab host")


class CpsTwinTopo(Topo):
    def build(self) -> None:
        s_it = self.addSwitch("s_it")
        s_dmz = self.addSwitch("s_dmz")
        s_ot = self.addSwitch("s_ot")

        for idx in range(1, 4):
            host = self.addHost(f"corp0{idx}", ip=f"10.0.10.{10 + idx}/24")
            self.addLink(host, s_it)

        historian = self.addHost("historian", ip="10.0.20.20/24")
        hmi = self.addHost("hmi01", ip="192.168.100.10/24")
        eng = self.addHost("eng01", ip="192.168.100.15/24")
        plc = self.addHost("openplc01", ip="192.168.100.20/24")
        self.addLink(historian, s_dmz)
        self.addLink(hmi, s_ot)
        self.addLink(eng, s_ot)
        self.addLink(plc, s_ot)

        fw_it = self.addHost("fw_it", ip="10.0.10.1/24")
        fw_dmz = self.addHost("fw_dmz", ip="10.0.20.1/24")
        self.addLink(fw_it, s_it)
        self.addLink(fw_it, s_dmz)
        self.addLink(fw_dmz, s_dmz)
        self.addLink(fw_dmz, s_ot)


topos = {"cpstwin": CpsTwinTopo}
