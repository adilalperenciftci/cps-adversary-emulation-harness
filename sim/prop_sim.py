import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any

import networkx as nx

from sim.models import NodeState, SimConfig, clamp_probability

LOG = logging.getLogger("prop_sim")


def build_graph() -> nx.Graph:
    graph = nx.Graph()
    attrs = {
        "corp01": ("windows", 0.72, "enterprise", False, 0.45, True),
        "corp02": ("windows", 0.88, "enterprise", False, 0.30, True),
        "corp03": ("linux", 0.80, "enterprise", False, 0.25, True),
        "historian": ("linux", 0.76, "dmz", False, 0.35, True),
        "eng01": ("windows", 0.65, "ot", True, 0.40, True),
        "hmi01": ("windows", 0.70, "ot", True, 0.25, True),
        "openplc01": ("linux", 0.82, "ot", True, 0.15, False),
    }
    for name, values in attrs.items():
        graph.add_node(
            name,
            os_type=values[0], patch_level=values[1], zone=values[2],
            air_gap=values[3], exposure=values[4], edr_present=values[5],
            state=NodeState.SUSCEPTIBLE,
        )
    graph.add_edges_from(
        [
            ("corp01", "corp02", {"bandwidth": 1000, "trust": 0.7, "usb_probability": 0.0, "transfer_frequency": 0.8}),
            ("corp02", "corp03", {"bandwidth": 1000, "trust": 0.6, "usb_probability": 0.0, "transfer_frequency": 0.6}),
            ("corp03", "historian", {"bandwidth": 100, "trust": 0.5, "usb_probability": 0.0, "transfer_frequency": 0.5}),
            ("historian", "eng01", {"bandwidth": 0, "trust": 0.2, "usb_probability": 0.05, "transfer_frequency": 0.1}),
            ("eng01", "hmi01", {"bandwidth": 100, "trust": 0.6, "usb_probability": 0.0, "transfer_frequency": 0.4}),
            ("eng01", "openplc01", {"bandwidth": 100, "trust": 0.5, "usb_probability": 0.0, "transfer_frequency": 0.4}),
        ]
    )
    graph.nodes["corp01"]["state"] = NodeState.INFECTED
    return graph


def sim_usb_drop(rng: random.Random, probability: float) -> tuple[bool, float]:
    probability = clamp_probability(probability)
    sample = rng.random()
    return sample < probability, sample


def run_sim(epochs: int, seed: int, cfg: SimConfig | None = None) -> list[dict[str, Any]]:
    cfg = cfg or SimConfig()
    graph = build_graph()
    rng = random.Random(seed)
    events: list[dict[str, Any]] = []
    exp_id = f"prop-{seed}-{epochs}"
    for epoch in range(epochs):
        transitions: dict[str, NodeState] = {}
        for src, dst, edge in sorted(graph.edges(data=True)):
            for infected, candidate in ((src, dst), (dst, src)):
                if graph.nodes[infected]["state"] != NodeState.INFECTED:
                    continue
                if graph.nodes[candidate]["state"] != NodeState.SUSCEPTIBLE:
                    continue
                if graph.nodes[candidate]["air_gap"] and edge["usb_probability"] > 0:
                    hit, sample = sim_usb_drop(rng, edge["usb_probability"])
                    events.append(_event(exp_id, epoch, "usb_sample", src=infected, dst=candidate, probability=edge["usb_probability"], sample=sample))
                    if hit:
                        transitions[candidate] = NodeState.INFECTED
                        events.append(_event(exp_id, epoch, "usb_transfer", src=infected, dst=candidate))
                    continue
                probability = clamp_probability(
                    cfg.base_rate * edge["trust"] * graph.nodes[candidate]["exposure"]
                    * (1.0 - graph.nodes[candidate]["patch_level"])
                )
                if rng.random() < probability:
                    transitions[candidate] = NodeState.INFECTED
                    events.append(_event(exp_id, epoch, "infection", src=infected, dst=candidate, probability=probability))
        for node, state in sorted(transitions.items()):
            previous = graph.nodes[node]["state"]
            graph.nodes[node]["state"] = state
            events.append(_event(exp_id, epoch, "state_transition", node=node, previous=previous, current=state))
        for node in sorted(graph.nodes):
            if graph.nodes[node]["state"] == NodeState.INFECTED:
                sample = rng.random()
                if sample < cfg.quarantine_rate:
                    graph.nodes[node]["state"] = NodeState.QUARANTINED
                elif sample < cfg.quarantine_rate + cfg.recovery_rate:
                    graph.nodes[node]["state"] = NodeState.RECOVERED
    return events


def _event(exp_id: str, epoch: int, event_type: str, **fields: Any) -> dict[str, Any]:
    return {"timestamp": epoch, "component": "prop_sim", "event_type": event_type, "experiment_id": exp_id, **fields}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--jsonl", type=Path, required=True)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("epochs must be positive")
    events = run_sim(args.epochs, args.seed)
    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.jsonl.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    LOG.info("experiment=prop-%d-%d epochs=%d events=%d", args.seed, args.epochs, args.epochs, len(events))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
