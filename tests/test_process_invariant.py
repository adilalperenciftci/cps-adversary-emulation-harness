from detect.process_invariant import ProcessSample, detect


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
