from dataclasses import dataclass


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
