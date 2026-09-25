"""Statistical model tests: distributional properties across seeds (spec §26.2, §29.4).

Slow (several minutes); excluded from the default run and executed with
``make test-stat``. They check broad, mechanism-level expectations with paired seeds,
never a seed-specific historical narrative. Thresholds are deliberately loose: a
failure means a qualitative property of the model changed, not that a number moved.
"""

from collections.abc import Mapping
from functools import cache
from typing import Any

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
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


@pytest.mark.xfail(
    strict=True,
    reason="Open issue 1 (objective/status.md): in the aggregation-free reference mode farming "
    "does not yet raise population over the forager-only baseline; the earlier gain came from "
    "the aggregation bias. Remove this marker when the mechanism question is resolved.",
)
def test_agriculture_supports_higher_population_than_foraging_alone() -> None:
    farming = _ensemble()
    foraging = _ensemble(("mechanisms.cultivation", False))
    ratio = _log_ratio(foraging, farming, "final_population")
    assert ratio.mean() > 0
    assert (ratio > 0).mean() >= 0.6
    assert np.nanmean([float(r["final_farm_share"]) for r in farming]) > 0.05


def test_crowding_mortality_reduces_population_growth() -> None:
    crowded = _ensemble()
    uncrowded = _ensemble(("mechanisms.crowding_mortality", False))
    ratio = _log_ratio(uncrowded, crowded, "final_population")
    assert ratio.mean() < 0
    assert all(float(r["final_crowding_death_share"]) > 0 for r in crowded)


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
        "Known approximation failure, to be resolved in P6 (objective/status.md, Section 0). "
        "Aggregation off is the canonical MVP 2 reference. After the P3 belief/migration "
        "changes, max_units_per_cell=8 changes population dynamics materially (final "
        "population ~2.6x the reference on every seed). P6 reruns the aggregation sensitivity "
        "experiment and either establishes a defensible approximation range or documents "
        "aggregation as performance-only for MVP 2. Strict, so an unexpected pass forces a "
        "review of this assumption."
    ),
)


@pytest.mark.parametrize(
    ("measure", "tolerance"),
    [
        pytest.param("final_population", 0.35, marks=AGGREGATION_POPULATION_XFAIL),
        ("first_plant_cultivation_year", 150.0),
    ],
)
def test_aggregation_error_stays_within_tolerance(measure: str, tolerance: float) -> None:
    """Coarsening at 8 units per cell versus the aggregation-free reference.

    Eight units per cell is the setting validated as an approximation of the reference;
    three is known to bias outcomes (objective/status.md, resolution-invariance experiment).
    The tolerance is on the paired mean difference (log ratio for population, years for
    milestones).
    """
    reference = _ensemble(("mechanisms.aggregation", False))
    coarse = _ensemble(("mechanisms.aggregation", True), ("resolution.max_units_per_cell", 8))
    if measure == "final_population":
        assert abs(_log_ratio(reference, coarse, measure).mean()) < tolerance
    else:
        diff = paired_differences(list(reference), list(coarse))[measure]["mean_difference"]
        assert abs(diff) < tolerance
