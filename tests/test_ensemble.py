"""Ensemble tooling and parameter overrides."""

import math
from pathlib import Path

import pytest

from madexplorer.cli.main import main
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.ensemble import (
    aggregate,
    paired_differences,
    read_runs,
    run_ensemble,
)
from madexplorer.metrics.recorder import LIGHT_FIELDS
from tests.conftest import ROOT, mvp2_scenario_dict, replay_key


def _scenario() -> Scenario:
    return Scenario.from_dict(mvp2_scenario_dict(n_years=40), base_dir=ROOT)


def test_settings_override_scenario_species_and_knowledge_parameters() -> None:
    variant = _scenario().with_settings(
        {
            "resolution.max_units_per_cell": 1,
            "species.human.cognition.observation_noise_sigma": 0.1,
            "knowledge.innovation.baseline_logit": -5.0,
        }
    )
    assert variant.config.resolution.max_units_per_cell == 1
    assert variant.species["human"].cognition.observation_noise_sigma == 0.1
    assert variant.knowledge is not None and variant.knowledge.innovation.baseline_logit == -5.0
    assert variant.config_hash() != _scenario().config_hash()


@pytest.mark.parametrize(
    "path",
    ["resolution.no_such_field", "species.elf.cognition.memory_years", "nope.x"],
)
def test_unknown_setting_paths_are_rejected(path: str) -> None:
    with pytest.raises(KeyError):
        _scenario().with_settings({path: 1})


def test_ensemble_rows_are_seed_ordered_and_parallel_matches_serial() -> None:
    serial = run_ensemble(_scenario(), [3, 1, 2], jobs=1)
    parallel = run_ensemble(_scenario(), [3, 1, 2], jobs=2)
    assert [r["seed"] for r in serial] == [1, 2, 3]
    for a, b in zip(serial, parallel, strict=True):
        assert {k: v for k, v in a.items() if k != "runtime_seconds"} == pytest.approx(
            {k: v for k, v in b.items() if k != "runtime_seconds"}, nan_ok=True
        )


def _farming_scenario() -> Scenario:
    data = mvp2_scenario_dict(n_years=80, seed=4)
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


def test_light_recorder_rows_equal_the_same_fields_of_full_rows() -> None:
    scenario = _farming_scenario()
    full = Simulator(scenario).run()
    light = Simulator(scenario, record_events=False).run(light=True)
    assert len(light.events) == 0 and light.population_snapshots == []
    assert any(float(r["cultivated_ha"]) > 0 for r in full.metrics)  # farming paths exercised
    assert scenario.knowledge is not None
    fields = [*LIGHT_FIELDS, *(f"tech_share_{t.id}" for t in scenario.knowledge.technologies)]
    assert all(list(row) == fields for row in light.metrics)
    projected = [{k: row[k] for k in fields} for row in full.metrics]
    assert replay_key(light.metrics) == replay_key(projected)  # exact, NaN included


def test_ensemble_summary_is_the_same_from_light_and_full_recorders() -> None:
    scenario = _farming_scenario()
    light, full = (run_ensemble(scenario, [4], light=flag)[0] for flag in (True, False))
    light.pop("runtime_seconds")
    full.pop("runtime_seconds")
    assert replay_key([light]) == replay_key([full])


def test_aggregate_reports_reach_rates_and_quantiles() -> None:
    rows = [{"seed": s, "x": float(s), "milestone": math.nan if s < 2 else 10.0} for s in range(4)]
    summary = aggregate(rows)
    assert summary["x"]["q50"] == pytest.approx(1.5)
    assert summary["milestone"]["reached"] == 0.5
    assert "seed" not in summary


def test_paired_differences_use_shared_seeds_only() -> None:
    base = [{"seed": s, "x": float(s)} for s in range(4)]
    variant = [{"seed": s, "x": float(s) + 2.0} for s in range(1, 6)]
    table = paired_differences(base, variant)
    assert table["x"]["pairs"] == 3
    assert table["x"]["mean_difference"] == pytest.approx(2.0)


def test_ensemble_cli_writes_rows_summary_and_manifest(tmp_path: Path) -> None:
    scenario_path = ROOT / "scenarios" / "mvp2_neolithic.yaml"
    out = tmp_path / "ens"
    code = main(
        [
            "ensemble",
            str(scenario_path),
            "--seeds",
            "0:1",
            "--years",
            "20",
            "--out",
            str(out),
            "--set",
            "resolution.max_units_per_cell=2",
            "--quiet",
        ]
    )
    assert code == 0
    rows = read_runs(out / "runs.csv")
    assert [r["seed"] for r in rows] == [0, 1]
    assert (out / "summary.json").is_file() and (out / "manifest.json").is_file()
    assert "resolution.max_units_per_cell" in (out / "manifest.json").read_text()


def test_ensemble_cli_full_recorder_gives_the_same_rows(tmp_path: Path) -> None:
    scenario_path = str(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    base = [scenario_path, "--seeds", "0", "--years", "30", "--quiet"]
    assert main(["ensemble", *base, "--out", str(tmp_path / "light")]) == 0
    assert main(["ensemble", *base, "--out", str(tmp_path / "full"), "--full-recorder"]) == 0
    light, full = (read_runs(tmp_path / name / "runs.csv") for name in ("light", "full"))
    for rows in (light, full):
        for row in rows:
            row.pop("runtime_seconds")
    assert replay_key(light) == replay_key(full)
