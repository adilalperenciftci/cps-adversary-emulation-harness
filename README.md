# CPS adversary-emulation harness

Deterministic synthetic lab tooling for testing propagation models, process-variable integrity checks, Modbus timing analytics, and endpoint/network detections. The OT emulator is deliberately socketless: it models PLC and HMI views in memory and emits sanitized JSONL. It cannot connect to OpenPLC or physical controllers.

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
| Zeek Modbus | 0 alerts | 2 alerts | 9 alerts |
| Timing | 0 alerts | 0 alerts | 6 alerts |
| Process/write integrity | 0 alerts | 2 alerts | 3 alerts |
| Endpoint Sigma | quiet | optional | evaluates only external endpoint telemetry |

EXP-01 leaves the target at nominal RPM and records process noise. EXP-02 changes the in-memory target while presenting the real value; both the write and restoration originate from the modeled engineering station and are reported because only the HMI is an approved setpoint writer. EXP-03 presents sampled baseline values while separately recording the real process value. Manipulation runs restore the target to nominal during shutdown.

Counts above were reproduced with seed `1337`, a 0.7-second baseline, and a 1.4-second manipulation interval. Eight baseline seeds, including `2024`, produced no timing alerts. The process and latency streams are deterministic under a fixed seed.

The latency distributions are synthetic by design: normal samples use a seeded 0.8 ms model and replay samples use a seeded 1.7 ms model. Detecting that injected distribution validates parser and rule behavior only; it does not measure sensitivity or false-positive rates on a deployed network. `jitter_detect.py` accepts separately collected JSONL to support validation with measured telemetry.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m sim.prop_sim --epochs 500 --seed 1337 --jsonl artifacts/propagation.jsonl
python -m ot.modbus_proxy --plc 192.168.100.20 --listen 192.168.100.15 --baseline-sec 5 --attack-rpm 3200 --max-safe-rpm 3500 --attack-sec 5 --max-runtime 20 --seed 1337 --pcap artifacts/exp-03.pcap
python -m detect.jitter_detect artifacts/modbus_proxy.jsonl
python -m detect.process_invariant artifacts/modbus_proxy.jsonl
sudo python3 -m lab.topology
sudo ./scripts/run_lab.sh
```

Mininet requires Linux and root privileges. `python3 -m lab.topology` starts the Linux-bridge topology, installs the fail-closed forwarding policy, verifies both permitted paths and both denied cross-zone paths, then stops the lab. `run_lab.sh` applies the same policy before opening the Mininet CLI. The topology does not launch the OT emulator or any exploit.

## Sanitized event

```json
{"timestamp":1.4,"component":"ot_emulator","event_type":"replay_event","experiment_id":"ot-exp-03-1337","phase":"REPLAY","src":"192.168.100.10","dst":"192.168.100.20","tx_id":16,"unit_id":1,"function_code":3,"register":40002,"requested_value":3200,"real_value":2913,"presented_value":1797,"latency_ms":1.858}
```

No component implements ARP poisoning, packet interception, socket forwarding, endpoint exploitation, persistence, removable-media behavior, physical PLC support, or telemetry deletion.

## Limits

- Generated PCAP and latency evidence comes from the same synthetic event stream. It is useful for deterministic regression, not independent evidence of real-world detection quality.
- The Sigma rule requires external endpoint telemetry; this repository does not generate Windows endpoint events.
- The propagation model is a bounded risk simulation, not an implementation of lateral movement.
- Mininet validates routing policy and namespace isolation. The socketless OT emulator does not exchange traffic with those namespaces.
