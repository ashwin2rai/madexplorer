"""Statistical model tests: distributional properties across seeds (spec §26.2, §29.4).

Excluded from the default run. Two tiers:

- ``make test-stat``: the compact statistical tests (the intensification-pressure
  agriculture test, 2 seeds x 400 years, well under a minute). Part of MVP freezes.
- ``make test-stat-long`` (marker ``slow``): the extended / research validation suite,
  8 paired seeds x 900 years on a 16 x 16 world (tens of minutes). Manual; not required
  for normal development, CI or MVP freezes. Kept because it checks useful long-run
  properties.

They check broad, mechanism-level expectations with paired seeds, never a seed-specific
historical narrative. Thresholds are deliberately loose: a failure means a qualitative
property of the model changed, not that a number moved.
"""

from collections.abc import Mapping
from functools import cache
from typing import Any

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.ensemble import Row, paired_differences, run_ensemble
from tests.conftest import ROOT, mvp2_scenario_dict

SEEDS = tuple(range(8))
YEARS = 900
JOBS = 2


def _world(settings: Mapping[str, Any]) -> Scenario:
    """A 16 x 16 fully terrestrial world that saturates with foragers well before 900 years."""
    data = mvp2_scenario_dict(n_years=YEARS, seed=0)
    data["initial_populations"] = [{"species": "human", "cell": [8, 8], "population": 40}]
    data["mechanisms"] = {"aggregation": False}  # reference calibration mode
    scenario = Scenario.from_dict(data, base_dir=ROOT)
    return scenario.with_settings(dict(settings)) if settings else scenario


@cache
def _ensemble(*settings: tuple[str, Any]) -> tuple[Row, ...]:
    return tuple(run_ensemble(_world(dict(settings)), SEEDS, jobs=JOBS))


def _log_ratio(baseline: tuple[Row, ...], variant: tuple[Row, ...], key: str) -> np.ndarray:
    a = np.array([float(r[key]) for r in baseline])
    b = np.array([float(r[key]) for r in variant])
    ratio: np.ndarray = np.log(np.maximum(b, 1.0) / np.maximum(a, 1.0))
    return ratio


PRESSURE_SEEDS = (0, 1)
PRESSURE_YEARS = 400
PRESSURE_WINDOW = 50


@cache
def _pressure_tail(seed: int, cultivation: bool) -> dict[str, float]:
    """Last-window means of the intensification-pressure scenario for one seed and arm."""
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_pressure.yaml").with_settings(
        {"mechanisms.cultivation": cultivation}
    )
    sim = Simulator(scenario.with_overrides(seed=seed, n_years=PRESSURE_YEARS))
    tail = sim.run(light=False).metrics[-PRESSURE_WINDOW:]
    keys = ("population", "occupied_cells", "farm_share_of_harvest", "mean_energy_deficit")
    means = {k: float(np.mean([float(r[k]) for r in tail])) for k in keys}
    means["density"] = float(
        np.mean([float(r["population"]) / max(float(r["occupied_cells"]), 1.0) for r in tail])
    )
    return means


@pytest.mark.parametrize("seed", PRESSURE_SEEDS)
def test_cultivation_raises_carrying_capacity_under_intensification_pressure(seed: int) -> None:
    """P5 validation (objective/status.md): in a bounded world that foragers saturate early,
    cultivation emerges and sustains a materially denser, less food-stressed population than
    the same system without cultivation. Matched seeds; thresholds far below the observed
    effect (population ~3x, density ~2x, farm share ~0.6 in years 351-400)."""
    farming = _pressure_tail(seed, cultivation=True)
    foraging = _pressure_tail(seed, cultivation=False)
    assert farming["farm_share_of_harvest"] > 0.25
    assert foraging["farm_share_of_harvest"] == 0.0
    assert farming["population"] > 1.5 * foraging["population"]
    assert farming["density"] > 1.3 * foraging["density"]


def test_cultivated_populations_are_less_food_stressed_on_average() -> None:
    """The denser farming population is not more food-stressed: mean energy deficit over
    the matched seeds. Pooled since MVP 2.1: per seed, the last-window deficit (~0.02-0.06)
    is too noisy for a strict comparison (MVP 2.1, 6 seeds: farming lower in 4/6, mean
    0.029 vs 0.038; MVP 2: 6/6, 0.028 vs 0.043; objective/status.md, MVP 2.1)."""
    farming = np.mean([_pressure_tail(s, True)["mean_energy_deficit"] for s in PRESSURE_SEEDS])
    foraging = np.mean([_pressure_tail(s, False)["mean_energy_deficit"] for s in PRESSURE_SEEDS])
    assert farming <= foraging


@pytest.mark.slow
def test_crowding_mortality_reduces_population_growth() -> None:
    crowded = _ensemble()
    uncrowded = _ensemble(("mechanisms.crowding_mortality", False))
    ratio = _log_ratio(uncrowded, crowded, "final_population")
    assert ratio.mean() < 0
    assert all(float(r["final_crowding_death_share"]) > 0 for r in crowded)


@pytest.mark.slow
def test_technologies_appear_within_broad_stochastic_ranges() -> None:
    rows = _ensemble()
    storage = np.array([float(r["first_storage_pits_year"]) for r in rows])
    cultivation = np.array([float(r["first_plant_cultivation_year"]) for r in rows])
    assert (~np.isnan(storage)).mean() >= 0.5
    assert (~np.isnan(cultivation)).mean() >= 0.5
    assert 20 <= np.nanmedian(storage) <= 700
    assert 20 <= np.nanmedian(cultivation) <= 800


AGGREGATION_POPULATION_XFAIL = pytest.mark.xfail(
    strict=True,
    reason=(
        "Accepted limitation (objective/status.md): computational aggregation is not "
        "scientifically neutral and is disabled for canonical/reference runs. With "
        "max_units_per_cell=8, final population is ~2.6x the reference on every seed here "
        "(after P3), and even rare merges shift trajectories (mvp2_pressure, 2 seeds: +9%). "
        "Correct aggregation belongs to MVP 3's statistical super-agents. Strict, so an "
        "unexpected pass forces a review of this assumption."
    ),
)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("measure", "tolerance"),
    [
        pytest.param("final_population", 0.35, marks=AGGREGATION_POPULATION_XFAIL),
        ("first_plant_cultivation_year", 150.0),
    ],
)
def test_aggregation_error_stays_within_tolerance(measure: str, tolerance: float) -> None:
    """Coarsening at 8 units per cell versus the aggregation-free reference.

    Eight units per cell was once expected to approximate the reference; the population
    check fails (strict xfail), so no coarsening setting is treated as neutral. The
    tolerance is on the paired mean difference (log ratio for population, years for
    milestones).
    """
    reference = _ensemble(("mechanisms.aggregation", False))
    coarse = _ensemble(("mechanisms.aggregation", True), ("resolution.max_units_per_cell", 8))
    if measure == "final_population":
        assert abs(_log_ratio(reference, coarse, measure).mean()) < tolerance
    else:
        diff = paired_differences(list(reference), list(coarse))[measure]["mean_difference"]
        assert abs(diff) < tolerance
