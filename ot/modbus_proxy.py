import argparse
import asyncio
import json
import random
import signal
import struct
import time
from dataclasses import dataclass
from enum import StrEnum
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any
from uuid import uuid4

from lab.register_map import ProcessConfig, Register, assert_register
from ot.replay_buf import ReplayBuffer, Sample
from ot.safety import EMU_IP, HMI_IP, PLC_IP, assert_lab_target


class Phase(StrEnum):
    BASELINE = "BASELINE"
    MANIPULATE = "MANIPULATE"
    REPLAY = "REPLAY"
    RESTORE = "RESTORE"


@dataclass
class ProcessTwin:
    cfg: ProcessConfig
    rng: random.Random
    target_rpm: float
    actual_rpm: float

    def step(self) -> int:
        noise = self.rng.gauss(0.0, self.cfg.noise_std)
        self.actual_rpm += self.cfg.alpha * (self.target_rpm - self.actual_rpm) + noise
        self.actual_rpm = max(0.0, min(float(self.cfg.max_safe_rpm), self.actual_rpm))
        return round(self.actual_rpm)


class Emulator:
    def __init__(self, cfg: ProcessConfig, attack_rpm: int, seed: int, output: Path) -> None:
        if not cfg.nominal_rpm <= attack_rpm <= cfg.max_safe_rpm:
            raise ValueError("attack RPM is outside safe bounds")
        self.cfg = cfg
        self.attack_rpm = attack_rpm
        self.rng = random.Random(seed)
        self.twin = ProcessTwin(cfg, self.rng, cfg.nominal_rpm, cfg.nominal_rpm)
        self.buf = ReplayBuffer()
        self.output = output
        self.stop = asyncio.Event()
        self.tx_id = 0
        self.exp_id = f"ot-{uuid4()}"
        self.events: list[dict[str, Any]] = []

    async def run(
        self, experiment: str, baseline_sec: float, attack_sec: float,
        max_runtime: float, dry_run: bool,
    ) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text("", encoding="utf-8")
        started = time.monotonic()
        try:
            await self._phase(Phase.BASELINE, baseline_sec, replay=False, dry_run=dry_run)
            if experiment in {"EXP-02", "EXP-03"}:
                self.twin.target_rpm = self.attack_rpm
                await self._record_write(Phase.MANIPULATE, self.attack_rpm, dry_run)
                manipulate_sec = attack_sec if experiment == "EXP-02" else attack_sec / 2
                await self._phase(Phase.MANIPULATE, manipulate_sec, replay=False, dry_run=dry_run)
            if experiment == "EXP-03":
                await self._phase(Phase.REPLAY, attack_sec / 2, replay=True, dry_run=dry_run)
            if time.monotonic() - started > max_runtime:
                raise TimeoutError("maximum runtime exceeded")
        finally:
            if self.twin.target_rpm != self.cfg.nominal_rpm:
                self.twin.target_rpm = self.cfg.nominal_rpm
                await self._record_write(Phase.RESTORE, self.cfg.nominal_rpm, dry_run)

    async def _phase(self, phase: Phase, duration: float, replay: bool, dry_run: bool) -> None:
        deadline = time.monotonic() + max(0.0, duration)
        while not self.stop.is_set() and time.monotonic() < deadline:
            start = time.perf_counter()
            plc_value = self.twin.step()
            now = time.monotonic()
            self.tx_id = (self.tx_id + 1) % 65536
            if phase == Phase.BASELINE:
                self.buf.add(Sample(now, self.tx_id, 1, Register.ACTUAL_RPM, plc_value))
            hmi_value = self.buf.select(self.rng, now).value if replay else plc_value
            latency_ms = (time.perf_counter() - start) * 1000.0 + (2.5 if replay else 0.2)
            await self._record(phase, plc_value, hmi_value, latency_ms, dry_run)
            await asyncio.sleep(0.1)

    async def _record(self, phase: Phase, plc_value: int, hmi_value: int, latency_ms: float, dry_run: bool) -> None:
        assert_register(Register.ACTUAL_RPM)
        event: dict[str, Any] = {
            "timestamp": time.time(), "component": "ot_emulator",
            "event_type": "replay_event" if phase == Phase.REPLAY else "modbus_read",
            "experiment_id": self.exp_id, "phase": phase, "src": str(HMI_IP), "dst": str(PLC_IP),
            "tx_id": self.tx_id, "unit_id": 1, "function_code": 3, "register": Register.ACTUAL_RPM,
            "requested_value": round(self.twin.target_rpm), "real_value": plc_value,
            "presented_value": hmi_value, "latency_ms": round(latency_ms, 4), "dry_run": dry_run,
        }
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.events.append(event)

    async def _record_write(self, phase: Phase, value: int, dry_run: bool) -> None:
        assert_register(Register.TARGET_RPM)
        self.tx_id = (self.tx_id + 1) % 65536
        event = {
            "timestamp": time.time(), "component": "ot_emulator", "event_type": "modbus_write",
            "experiment_id": self.exp_id, "phase": phase, "src": str(EMU_IP), "dst": str(PLC_IP),
            "tx_id": self.tx_id, "unit_id": 1, "function_code": 6, "register": Register.TARGET_RPM,
            "requested_value": value, "real_value": round(self.twin.actual_rpm),
            "presented_value": round(self.twin.actual_rpm), "latency_ms": 0.0, "dry_run": dry_run,
        }
        with self.output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
        self.events.append(event)


async def async_main(args: argparse.Namespace) -> int:
    assert_lab_target(args.plc, PLC_IP)
    assert_lab_target(args.listen, EMU_IP)
    cfg = ProcessConfig(nominal_rpm=args.nominal_rpm, max_safe_rpm=args.max_safe_rpm)
    emulator = Emulator(cfg, args.attack_rpm, args.seed, args.output)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, emulator.stop.set)
        except NotImplementedError:
            pass
    await asyncio.wait_for(
        emulator.run(args.experiment, args.baseline_sec, args.attack_sec, args.max_runtime, args.dry_run),
        timeout=args.max_runtime + 2.0,
    )
    if args.pcap is not None:
        write_synthetic_pcap(emulator.events, args.pcap)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Socketless OT digital-twin adversary emulator")
    parser.add_argument("--plc", default=str(PLC_IP))
    parser.add_argument("--listen", default=str(EMU_IP))
    parser.add_argument("--baseline-sec", type=float, default=5.0)
    parser.add_argument("--attack-sec", type=float, default=5.0)
    parser.add_argument("--nominal-rpm", type=int, default=1800)
    parser.add_argument("--attack-rpm", type=int, default=3200)
    parser.add_argument("--max-safe-rpm", type=int, default=3500)
    parser.add_argument("--max-runtime", type=float, default=30.0)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--experiment", choices=("EXP-01", "EXP-02", "EXP-03"), default="EXP-03")
    parser.add_argument("--output", type=Path, default=Path("artifacts/modbus_proxy.jsonl"))
    parser.add_argument("--pcap", type=Path)
    return asyncio.run(async_main(parser.parse_args()))


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total & 0xFFFF) + (total >> 16)
    total += total >> 16
    return (~total) & 0xFFFF


def _frame(src: str, dst: str, sport: int, dport: int, seq: int, ack: int, flags: int, payload: bytes) -> bytes:
    src_raw = IPv4Address(src).packed
    dst_raw = IPv4Address(dst).packed
    ip_base = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 40 + len(payload), 1, 0x4000, 64, 6, 0, src_raw, dst_raw)
    ip_hdr = ip_base[:10] + struct.pack("!H", _checksum(ip_base)) + ip_base[12:]
    tcp_base = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 5 << 4, flags, 64240, 0, 0)
    pseudo = src_raw + dst_raw + struct.pack("!BBH", 0, 6, len(tcp_base) + len(payload))
    tcp_hdr = tcp_base[:16] + struct.pack("!H", _checksum(pseudo + tcp_base + payload)) + tcp_base[18:]
    ethernet = bytes.fromhex("0200000000200200000000100800")
    return ethernet + ip_hdr + tcp_hdr + payload


def _mbap(event: dict[str, Any], response: bool) -> bytes:
    tx_id = int(event["tx_id"])
    unit_id = int(event["unit_id"])
    fc = int(event["function_code"])
    reg = int(event["register"])
    offset = 0 if reg == Register.TARGET_RPM else 1
    if fc == 6:
        pdu = struct.pack("!BHH", fc, offset, int(event["requested_value"]))
    elif response:
        pdu = struct.pack("!BBH", fc, 2, int(event["presented_value"]))
    else:
        pdu = struct.pack("!BHH", fc, offset, 1)
    return struct.pack("!HHHB", tx_id, 0, len(pdu) + 1, unit_id) + pdu


def write_synthetic_pcap(events: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    packets: list[tuple[float, bytes]] = []
    sport = 12000
    cli_seq, srv_seq = 1000, 5000
    first_ts = float(events[0]["timestamp"]) if events else time.time()
    packets.extend([
        (first_ts - 0.003, _frame(str(HMI_IP), str(PLC_IP), sport, 502, cli_seq, 0, 0x02, b"")),
        (first_ts - 0.002, _frame(str(PLC_IP), str(HMI_IP), 502, sport, srv_seq, cli_seq + 1, 0x12, b"")),
        (first_ts - 0.001, _frame(str(HMI_IP), str(PLC_IP), sport, 502, cli_seq + 1, srv_seq + 1, 0x10, b"")),
    ])
    cli_seq += 1
    srv_seq += 1
    for event in events:
        req = _mbap(event, response=False)
        resp = _mbap(event, response=True)
        ts = float(event["timestamp"])
        packets.append((ts, _frame(str(HMI_IP), str(PLC_IP), sport, 502, cli_seq, srv_seq, 0x18, req)))
        cli_seq += len(req)
        if event["event_type"] == "replay_event":
            duplicate = _mbap(event, response=False)
            packets.append((ts + 0.0005, _frame(str(HMI_IP), str(PLC_IP), sport, 502, cli_seq, srv_seq, 0x18, duplicate)))
            cli_seq += len(duplicate)
        packets.append((ts + 0.001, _frame(str(PLC_IP), str(HMI_IP), 502, sport, srv_seq, cli_seq, 0x18, resp)))
        srv_seq += len(resp)
    with path.open("wb") as handle:
        handle.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for timestamp, packet in packets:
            sec = int(timestamp)
            usec = int((timestamp - sec) * 1_000_000)
            handle.write(struct.pack("<IIII", sec, usec, len(packet), len(packet)))
            handle.write(packet)


if __name__ == "__main__":
    raise SystemExit(main())
