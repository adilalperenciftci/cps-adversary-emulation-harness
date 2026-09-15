import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from lab.register_map import Register
from ot.safety import HMI_IP

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
    flat_reported = False
    for idx, sample in enumerate(samples):
        divergence = divergence + 1 if abs(sample.actual_rpm - sample.hmi_rpm) > threshold else 0
        if divergence == consecutive:
            alerts.append(Alert("REAL_PRESENTED_DIVERGENCE", idx - consecutive + 1, divergence))
        if idx + 1 >= consecutive and not flat_reported:
            window = samples[idx - consecutive + 1:idx + 1]
            target_span = max(item.target_rpm for item in window) - min(item.target_rpm for item in window)
            hmi_span = max(item.hmi_rpm for item in window) - min(item.hmi_rpm for item in window)
            if target_span > threshold and hmi_span < threshold * 0.05:
                alerts.append(Alert(
                    "FLAT_REPLAY_DURING_TARGET_CHANGE",
                    idx - consecutive + 1,
                    consecutive,
                ))
                flat_reported = True
    return alerts


def load_events(path: Path) -> list[dict[str, object]]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("telemetry exceeds byte budget")
    events: list[dict[str, object]] = []
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
            if not isinstance(event, dict):
                raise ValueError(f"invalid telemetry at line {line_number}")
            events.append(event)
    return events


def samples_from_events(events: list[dict[str, object]]) -> list[ProcessSample]:
    samples: list[ProcessSample] = []
    for index, event in enumerate(events):
        if event.get("event_type") not in {"modbus_read", "replay_event"}:
            continue
        try:
            values = tuple(
                float(event[field])
                for field in ("requested_value", "real_value", "presented_value")
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid telemetry event {index}") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"non-finite telemetry event {index}")
        samples.append(ProcessSample(*values))
    return samples


def load_samples(path: Path) -> list[ProcessSample]:
    return samples_from_events(load_events(path))


def detect_unauthorized_writes(
    events: list[dict[str, object]], allowed_sources: frozenset[str] | None = None,
) -> list[Alert]:
    allowed_sources = allowed_sources or frozenset({str(HMI_IP)})
    alerts: list[Alert] = []
    for index, event in enumerate(events):
        if (
            event.get("event_type") == "modbus_write"
            and event.get("function_code") == 6
            and event.get("register") == Register.TARGET_RPM
            and event.get("src") not in allowed_sources
        ):
            alerts.append(Alert("UNAUTHORIZED_SETPOINT_WRITE", index, 1))
    return alerts


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect digital-twin process invariant violations")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    events = load_events(args.input)
    alerts = detect(samples_from_events(events)) + detect_unauthorized_writes(events)
    for alert in alerts:
        print(json.dumps(alert.__dict__, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
