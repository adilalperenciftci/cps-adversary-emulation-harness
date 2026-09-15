import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 100_000


@dataclass(frozen=True)
class ProcessSample:
    target_rpm: float
    actual_rpm: float
    hmi_rpm: float


@dataclass(frozen=True)
class Alert:
    reason: str
    start_index: int
    count: int


def detect(samples: list[ProcessSample], threshold: float = 80.0, consecutive: int = 3) -> list[Alert]:
    alerts: list[Alert] = []
    divergence = 0
    for idx, sample in enumerate(samples):
        divergence = divergence + 1 if abs(sample.actual_rpm - sample.hmi_rpm) > threshold else 0
        if divergence == consecutive:
            alerts.append(Alert("REAL_PRESENTED_DIVERGENCE", idx - consecutive + 1, divergence))
        if idx >= consecutive:
            window = samples[idx - consecutive:idx + 1]
            target_span = max(item.target_rpm for item in window) - min(item.target_rpm for item in window)
            hmi_span = max(item.hmi_rpm for item in window) - min(item.hmi_rpm for item in window)
            if target_span > threshold and hmi_span < threshold * 0.05:
                alerts.append(Alert("FLAT_REPLAY_DURING_TARGET_CHANGE", idx - consecutive, consecutive))
                break
    return alerts


def load_samples(path: Path) -> list[ProcessSample]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("telemetry exceeds byte budget")
    samples: list[ProcessSample] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number > MAX_RECORDS:
                raise ValueError("telemetry exceeds record budget")
            try:
                event = json.loads(
                    line, parse_constant=lambda value: _reject_constant(value)
                )
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"invalid telemetry at line {line_number}") from exc
            if event.get("event_type") not in {"modbus_read", "replay_event"}:
                continue
            try:
                values = tuple(
                    float(event[field])
                    for field in ("requested_value", "real_value", "presented_value")
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid telemetry at line {line_number}") from exc
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"non-finite telemetry at line {line_number}")
            samples.append(ProcessSample(*values))
    return samples


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect digital-twin process invariant violations")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    for alert in detect(load_samples(args.input)):
        print(json.dumps(alert.__dict__, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
