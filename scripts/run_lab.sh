#!/usr/bin/env bash
set -euo pipefail
trap 'sudo mn -c >/dev/null 2>&1 || true' EXIT
sudo mn --custom lab/topology.py --topo cpstwin --controller none
