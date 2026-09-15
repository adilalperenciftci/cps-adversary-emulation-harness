import asyncio

from detect.jitter_detect import analyze
from lab.register_map import ProcessConfig
from ot.modbus_proxy import Emulator, write_synthetic_pcap


def _run(tmp_path, experiment: str, seed: int):
    output = tmp_path / f"{experiment}-{seed}.jsonl"
    emulator = Emulator(ProcessConfig(), 3200, seed, output, sleep_interval=0.0)
    asyncio.run(emulator.run(experiment, 0.7, 1.4, 4.0))
    return emulator.events, analyze(output)


def test_fixed_seed_produces_identical_events(tmp_path) -> None:
    first, _ = _run(tmp_path, "EXP-03", 1337)
    second, _ = _run(tmp_path, "EXP-03", 1337)
    assert first == second


def test_baseline_is_quiet_across_multiple_seeds(tmp_path) -> None:
    for seed in (1, 7, 42, 99, 1337, 2024, 4096, 65535):
        _, result = _run(tmp_path, "EXP-01", seed)
        assert not result["anomaly"].any(), seed


def test_replay_latency_shift_is_detected(tmp_path) -> None:
    _, result = _run(tmp_path, "EXP-03", 1337)
    assert result["anomaly"].any()


def test_synthetic_pcap_is_deterministic(tmp_path) -> None:
    events, _ = _run(tmp_path, "EXP-03", 1337)
    first = tmp_path / "first.pcap"
    second = tmp_path / "second.pcap"
    write_synthetic_pcap(events, first)
    write_synthetic_pcap(events, second)
    assert first.read_bytes() == second.read_bytes()
