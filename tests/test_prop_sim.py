import random

from sim.models import SimConfig, clamp_probability
from sim.prop_sim import infection_probability, run_sim, sim_usb_drop


def test_seed_is_deterministic() -> None:
    assert run_sim(50, 1337) == run_sim(50, 1337)


def test_probability_bounds() -> None:
    assert clamp_probability(-2.0) == 0.0
    assert clamp_probability(2.0) == 1.0


def test_usb_probability_extremes() -> None:
    assert sim_usb_drop(random.Random(1), 0.0)[0] is False
    assert sim_usb_drop(random.Random(1), 1.0)[0] is True


def test_edr_reduces_network_infection_probability() -> None:
    edge = {
        "bandwidth": 100, "trust": 0.8, "transfer_frequency": 0.7,
    }
    node = {
        "os_type": "windows", "patch_level": 0.5, "exposure": 0.5,
        "edr_present": False,
    }
    without_edr = infection_probability(SimConfig(), node, edge)
    node["edr_present"] = True
    assert infection_probability(SimConfig(), node, edge) < without_edr


def test_cross_zone_air_gap_never_uses_network_infection() -> None:
    events = run_sim(
        2_000, 9,
        SimConfig(base_rate=1.0, recovery_rate=0.0, quarantine_rate=0.0),
    )
    crossings = [
        event for event in events
        if event.get("src") == "historian" and event.get("dst") == "eng01"
    ]
    assert crossings
    assert all(event["event_type"] in {"usb_sample", "usb_transfer"} for event in crossings)
