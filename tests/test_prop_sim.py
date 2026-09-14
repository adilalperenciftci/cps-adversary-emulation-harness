import random

from sim.models import clamp_probability
from sim.prop_sim import run_sim, sim_usb_drop


def test_seed_is_deterministic() -> None:
    assert run_sim(50, 1337) == run_sim(50, 1337)


def test_probability_bounds() -> None:
    assert clamp_probability(-2.0) == 0.0
    assert clamp_probability(2.0) == 1.0


def test_usb_probability_extremes() -> None:
    assert sim_usb_drop(random.Random(1), 0.0)[0] is False
    assert sim_usb_drop(random.Random(1), 1.0)[0] is True
