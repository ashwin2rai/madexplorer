"""Exact software regressions: same code + configuration + seed must replay exactly.

These tests say nothing about whether the model is right; they detect *any* change in
seeded output. A behavior-preserving change (refactor, optimization) must leave the
fixtures untouched. An intended model change re-records them with ``make golden`` and
says so in the commit message.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import SimulationResult, Simulator
from tests.conftest import ROOT, mvp2_scenario_dict, replay_key, small_scenario_dict

GOLDEN = Path(__file__).parent / "golden"


def _farming_small() -> Scenario:
    data = mvp2_scenario_dict(n_years=150, seed=4)
    data["initial_populations"] = [
        {
            "species": "human",
            "cell": [8, 8],
            "population": 80,
            "technologies": ["plant_cultivation", "storage_pits"],
            "initial_knowledge": {"agriculture": 4.5, "storage": 1.0},
        }
    ]
    return Scenario.from_dict(data, base_dir=ROOT)


CASES = {
    "mvp1_sandbox_150y_seed0": lambda: Scenario.from_yaml(
        ROOT / "scenarios" / "mvp1_sandbox.yaml"
    ).with_overrides(n_years=150),
    "mvp2_neolithic_250y_seed0": lambda: Scenario.from_yaml(
        ROOT / "scenarios" / "mvp2_neolithic.yaml"
    ).with_overrides(n_years=250, seed=0),
    "mvp2_neolithic_250y_seed1": lambda: Scenario.from_yaml(
        ROOT / "scenarios" / "mvp2_neolithic.yaml"
    ).with_overrides(n_years=250, seed=1),
    "small_foragers_120y_seed2": lambda: Scenario.from_dict(
        small_scenario_dict(n_years=120, seed=2), base_dir=ROOT
    ),
    "small_farmers_150y_seed4": _farming_small,
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=repr).encode()).hexdigest()


def _fingerprint(result: SimulationResult) -> dict[str, Any]:
    last = result.metrics[-1]
    totals = {
        key: sum(float(r[key]) for r in result.metrics)
        for key in ("births", "deaths", "migrations", "fissions", "fusions", "inventions")
    }
    return {
        "final_year": last["year"],
        "final_population": last["population"],
        "final_units": last["units"],
        "final_occupied_cells": last["occupied_cells"],
        "totals": totals,
        "event_count": len(result.events),
        "metrics_sha256": _digest(replay_key(result.metrics)),
        "events_sha256": _digest([e.to_record() for e in result.events]),
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_seeded_output_matches_recorded_fixture(name: str) -> None:
    fingerprint = _fingerprint(Simulator(CASES[name]()).run())
    path = GOLDEN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") or not path.exists():
        path.write_text(json.dumps(fingerprint, indent=2) + "\n")
        pytest.skip(f"recorded {path.name}")
    assert fingerprint == json.loads(path.read_text())


def test_replay_is_deterministic_within_a_process() -> None:
    scenario = Scenario.from_dict(mvp2_scenario_dict(n_years=80), base_dir=ROOT)
    assert replay_key(Simulator(scenario).run().metrics) == replay_key(
        Simulator(scenario).run().metrics
    )


def test_different_seeds_diverge() -> None:
    runs = [
        replay_key(
            Simulator(Scenario.from_dict(small_scenario_dict(seed=s), base_dir=ROOT)).run().metrics
        )
        for s in (1, 2)
    ]
    assert runs[0] != runs[1]
