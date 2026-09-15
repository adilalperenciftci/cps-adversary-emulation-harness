#!/usr/bin/env bash
set -euo pipefail
trap 'sudo mn -c >/dev/null 2>&1 || true' EXIT
sudo python3 - <<'PY'
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.nodelib import LinuxBridge

from lab.firewall import apply_segmentation
from lab.topology import CpsTwinTopo

net = Mininet(topo=CpsTwinTopo(), controller=None, switch=LinuxBridge)
try:
    net.start()
    apply_segmentation(net)
    CLI(net)
finally:
    net.stop()
PY
