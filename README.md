# CPS adversary-emulation harness

Deterministic lab tooling for testing propagation models, process-variable integrity checks, Modbus timing analytics, and endpoint/network detections. The OT emulator is deliberately socketless: it models PLC and HMI views in memory and emits sanitized JSONL. It cannot connect to OpenPLC or physical controllers.

## Topology

| Zone | CIDR | Nodes |
|---|---|---|
| Enterprise | `10.0.10.0/24` | `corp01`, `corp02`, `corp03` |
| DMZ | `10.0.20.0/24` | `historian` |
| OT | `192.168.100.0/24` | `hmi01`, `eng01`, `openplc01` |

Enterprise hosts can reach only the historian's modeled HTTPS service. The historian can reach only the modeled OT telemetry service. Enterprise-to-OT and OT-to-enterprise traffic is denied by default.

## Register model

| Address | Type | Name | Meaning |
|---|---|---|---|
| `00001` | Coil | `RUN_CMD` | Run/stop |
| `40001` | Holding register | `TARGET_RPM` | Requested rotor speed |
| `40002` | Holding register | `ACTUAL_RPM` | Simulated rotor speed |

`ACTUAL_RPM` follows a first-order lag with bounded Gaussian noise. Configuration exposes `alpha`, `noise_std`, `nominal_rpm`, and `max_safe_rpm`.

## Experiments

| Detector | EXP-01 baseline | EXP-02 manipulation | EXP-03 manipulation + replay |
|---|---:|---:|---:|
| Zeek Modbus | 0 alerts | 0 alerts | 7 alerts |
| Timing | 0 alerts | 0 alerts | 7 alerts |
| Process invariant | 0 alerts | 0 alerts | 1 alert |
| Endpoint Sigma | quiet | optional | evaluates only external endpoint telemetry |

EXP-01 leaves the target at nominal RPM and records process noise. EXP-02 changes the in-memory target while presenting the real value. EXP-03 presents sampled baseline values while separately recording the real process value. Manipulation runs restore the target to nominal during shutdown. Counts above are from fixed-seed, short-duration validation; they are regression evidence, not performance benchmarks.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m sim.prop_sim --epochs 500 --seed 1337 --jsonl artifacts/propagation.jsonl
python -m ot.modbus_proxy --plc 192.168.100.20 --listen 192.168.100.15 --baseline-sec 5 --attack-rpm 3200 --max-safe-rpm 3500 --attack-sec 5 --max-runtime 20 --seed 1337 --dry-run --pcap artifacts/exp-03.pcap
python -m detect.jitter_detect artifacts/modbus_proxy.jsonl
python -m detect.process_invariant artifacts/modbus_proxy.jsonl
sudo python3 -m lab.topology
sudo ./scripts/run_lab.sh
```

Mininet requires Linux and root privileges. `python3 -m lab.topology` starts the Linux-bridge topology, installs the fail-closed forwarding policy, verifies both permitted paths and both denied cross-zone paths, then stops the lab. `run_lab.sh` applies the same policy before opening the Mininet CLI. The topology does not launch the OT emulator or any exploit.

## Sanitized event

```json
{"timestamp":0.3,"component":"ot_emulator","event_type":"modbus_read","experiment_id":"ot-1337-sample","phase":"REPLAY","src":"192.168.100.10","dst":"192.168.100.20","tx_id":73,"unit_id":1,"function_code":3,"register":40002,"requested_value":3200,"real_value":2714,"presented_value":1802,"latency_ms":2.63,"dry_run":true}
```

No component implements ARP poisoning, packet interception, socket forwarding, endpoint exploitation, persistence, removable-media behavior, physical PLC support, or telemetry deletion.
