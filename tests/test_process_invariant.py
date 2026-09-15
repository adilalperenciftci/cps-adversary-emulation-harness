import asyncio
import json

import pytest

from detect.process_invariant import ProcessSample, detect, load_samples
from detect.jitter_detect import analyze
from lab.register_map import ProcessConfig
from ot.modbus_proxy import Emulator


def test_replay_divergence_detected() -> None:
    samples = [ProcessSample(3200, 2800 + idx * 20, 1800) for idx in range(5)]
    reasons = {alert.reason for alert in detect(samples)}
    assert "REAL_PRESENTED_DIVERGENCE" in reasons


def test_noisy_legitimate_signal_is_quiet() -> None:
    samples = [ProcessSample(1800, 1800 + (-1) ** idx * 8, 1800 + (-1) ** idx * 6) for idx in range(20)]
    assert detect(samples) == []


def test_short_divergence_does_not_alert() -> None:
    samples = [ProcessSample(1800, 2000, 1800), ProcessSample(1800, 2000, 1800)]
    assert detect(samples, consecutive=3) == []


def test_flat_replay_during_target_change() -> None:
    samples = [
        ProcessSample(1800, 1800, 1800),
        ProcessSample(2200, 1900, 1800),
        ProcessSample(2600, 2100, 1801),
        ProcessSample(3000, 2400, 1800),
    ]
    reasons = {alert.reason for alert in detect(samples, threshold=80, consecutive=3)}
    assert "FLAT_REPLAY_DURING_TARGET_CHANGE" in reasons


def test_latency_step_is_detected(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    rows = []
    for idx, latency in enumerate([1.0, 1.1, 0.9, 1.0, 1.05, 1.0, 8.0, 8.2]):
        rows.append(
            '{"timestamp":%d,"src":"hmi","dst":"plc","latency_ms":%.2f}'
            % (idx, latency)
        )
    path.write_text("\n".join(rows), encoding="utf-8")
    result = analyze(path, window=6, threshold=3.5)
    assert result["anomaly"].any()


def test_experiment_modes_and_restoration(tmp_path) -> None:
    async def execute(experiment: str) -> Emulator:
        emulator = Emulator(
            ProcessConfig(), 3200, 1337, tmp_path / f"{experiment}.jsonl"
        )
        await emulator.run(experiment, 0.35, 0.7, 3.0, False)
        return emulator

    baseline = asyncio.run(execute("EXP-01"))
    manipulate = asyncio.run(execute("EXP-02"))
    replay = asyncio.run(execute("EXP-03"))

    assert not any(event["event_type"] == "modbus_write" for event in baseline.events)
    assert any(event["phase"] == "MANIPULATE" for event in manipulate.events)
    assert not any(event["event_type"] == "replay_event" for event in manipulate.events)
    replay_events = [
        event for event in replay.events if event["event_type"] == "replay_event"
    ]
    assert replay_events
    assert any(
        event["real_value"] != event["presented_value"] for event in replay_events
    )
    assert replay.twin.target_rpm == replay.cfg.nominal_rpm
    parsed = [
        json.loads(line)
        for line in (tmp_path / "EXP-03.jsonl").read_text().splitlines()
    ]
    assert all(
        {"timestamp", "component", "event_type", "experiment_id"} <= event.keys()
        for event in parsed
    )


@pytest.mark.parametrize(
    "payload",
    [
        "{broken",
        '{"event_type":"modbus_read","requested_value":NaN,"real_value":1,"presented_value":1}',
        '{"event_type":"modbus_read","requested_value":1}',
    ],
)
def test_process_parser_rejects_malformed_or_nonfinite(tmp_path, payload) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        load_samples(path)


def test_jitter_parser_rejects_nonfinite(tmp_path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text(
        '{"timestamp":1,"src":"hmi","dst":"plc","latency_ms":Infinity}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        analyze(path)
