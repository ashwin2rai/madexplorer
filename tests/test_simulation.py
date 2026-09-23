import json
from pathlib import Path

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.governance import RULES
from madexplorer.core.simulation import Simulator
from tests.conftest import ROOT, small_scenario_dict


def _summary(scenario: Scenario) -> list[tuple[float | int, ...]]:
    result = Simulator(scenario).run()
    return [tuple(row.values()) for row in result.metrics]


def test_deterministic_replay(small_scenario: Scenario) -> None:
    assert _summary(small_scenario) == _summary(small_scenario)


def test_different_seeds_diverge(small_scenario: Scenario) -> None:
    assert _summary(small_scenario) != _summary(small_scenario.with_overrides(seed=2))


def test_run_records_metrics_events_and_snapshots(small_scenario: Scenario) -> None:
    result = Simulator(small_scenario).run()
    assert len(result.metrics) == 40
    assert result.metrics[-1]["population"] > 0
    kinds = {event.kind for event in result.events}
    assert "unit_founded" in kinds
    assert result.snapshot_years[0] == 0
    assert result.manifest["config_hash"] == small_scenario.config_hash()


def test_ablation_disables_mechanisms() -> None:
    data = small_scenario_dict(n_years=60)
    data["mechanisms"] = {"migration": False, "fission": False}
    result = Simulator(Scenario.from_dict(data, base_dir=ROOT)).run()
    assert all(row["migrations"] == 0 and row["fissions"] == 0 for row in result.metrics)
    assert result.metrics[-1]["occupied_cells"] <= 1


def test_save_writes_all_outputs(small_scenario: Scenario, tmp_path: Path) -> None:
    directory = Simulator(small_scenario).run().save(tmp_path / "run")
    for name in (
        "manifest.json",
        "scenario.json",
        "metrics.csv",
        "events.jsonl",
        "spatial.npz",
        "world.npz",
    ):
        assert (directory / name).is_file()
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["seed"] == 1
    spatial = np.load(directory / "spatial.npz")
    assert spatial["population"].shape[1:] == (16, 16)


def test_trace_emits_component_scores() -> None:
    data = small_scenario_dict(n_years=10)
    result = Simulator(Scenario.from_dict(data, base_dir=ROOT), trace_units=["u1"]).run()
    traces = [e for e in result.events if e.kind == "trace_migration"]
    assert traces and "expected_food" in traces[0].data["current"]


def test_model_rules_have_provenance() -> None:
    assert len(RULES) >= 15
    for rule in RULES.values():
        assert rule.rationale and rule.source_type in {
            "empirical",
            "theoretical",
            "heuristic",
            "placeholder",
        }
