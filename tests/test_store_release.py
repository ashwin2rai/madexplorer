"""MVP 3 Stage 4D: counterfactual store release (reserve management). NOT ACTIVE.

``madexplorer.population.store_release`` answers *how much* a unit releases from its stores
in a shortage year: the MVP 2.1 rule ``X = min(D, K)`` and the candidate reserve-target rule
``X = min(D, max(K - R, 0))`` with ``R = b * Need``. No simulator path calls it; the
observation used here leaves every authoritative output identical.
"""

import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import madexplorer.core.simulation as simulation
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.population.energetics import EnergyUpdates
from madexplorer.population.store_release import (
    StoreRelease,
    need_buffer_target,
    release_current,
    release_with_reserve_target,
)
from tests.conftest import ROOT


def _conserved(r: StoreRelease, deficit: float, stores: float) -> None:
    assert 0.0 <= r.withdrawal <= min(deficit, stores)
    assert r.retained_by_policy >= 0.0
    assert r.withdrawal + r.retained_by_policy == pytest.approx(min(deficit, stores), abs=1e-9)
    assert r.withdrawal + r.unmet_external_need == pytest.approx(deficit, abs=1e-9)


def test_current_rule_covers_the_deficit_up_to_the_whole_store() -> None:
    assert release_current(300.0, 1000.0) == StoreRelease(300.0, 0.0, 0.0)
    assert release_current(300.0, 120.0) == StoreRelease(120.0, 0.0, 180.0)
    assert release_current(0.0, 500.0) == StoreRelease(0.0, 0.0, 0.0)  # no shortage
    assert release_current(300.0, 0.0) == StoreRelease(0.0, 0.0, 300.0)  # no stores


def test_zero_target_is_the_current_rule_exactly() -> None:
    rng = np.random.default_rng(1)
    for d, k in rng.uniform(0, 1e6, size=(200, 2)).tolist():
        assert release_with_reserve_target(d, k, 0.0) == release_current(d, k)


def test_reserve_target_cases() -> None:
    below = release_with_reserve_target(300.0, 150.0, 200.0)  # stores below the target
    assert below == StoreRelease(0.0, 150.0, 300.0)
    small = release_with_reserve_target(100.0, 1000.0, 200.0)  # deficit < releasable
    assert small == StoreRelease(100.0, 0.0, 0.0)
    large = release_with_reserve_target(900.0, 1000.0, 200.0)  # deficit > releasable
    assert large == StoreRelease(800.0, 100.0, 100.0)
    boundary = release_with_reserve_target(800.0, 1000.0, 200.0)  # exactly releasable
    assert boundary == StoreRelease(800.0, 0.0, 0.0)
    at_target = release_with_reserve_target(50.0, 200.0, 200.0)  # stores exactly at target
    assert at_target == StoreRelease(0.0, 50.0, 50.0)
    none = release_with_reserve_target(0.0, 1000.0, 200.0)
    assert none == StoreRelease(0.0, 0.0, 0.0)


def test_invariants_over_many_states() -> None:
    rng = np.random.default_rng(2)
    for d, k, t in rng.uniform(0, 1e6, size=(500, 3)).tolist():
        for deficit, stores, target in ((d, k, t), (d, 0.0, t), (0.0, k, t), (d, k, k)):
            r = release_with_reserve_target(deficit, stores, target)
            _conserved(r, deficit, stores)
            assert r.withdrawal <= max(stores - target, 0.0)


def test_release_is_continuous_and_monotone_in_the_buffer_fraction() -> None:
    need, deficit, stores = 1000.0, 600.0, 800.0
    grid = np.linspace(0.0, 2.0, 4001).tolist()
    x = [
        release_with_reserve_target(deficit, stores, need_buffer_target(need, b)).withdrawal
        for b in grid
    ]
    steps = np.diff(x)
    assert (steps <= 0).all()  # more protection never releases more
    assert np.abs(steps).max() <= need * (grid[1] - grid[0]) + 1e-9  # Lipschitz, constant Need
    assert x[0] == 600.0 and x[-1] == 0.0


def test_inputs_are_validated() -> None:
    for bad in (-1.0, math.nan, math.inf):
        with pytest.raises(ValueError):
            release_current(bad, 1.0)
        with pytest.raises(ValueError):
            release_with_reserve_target(1.0, 1.0, bad)
    with pytest.raises(ValueError):
        need_buffer_target(1000.0, -0.1)
    assert need_buffer_target(1000.0, 0.0) == 0.0 and need_buffer_target(1000.0, 0.5) == 500.0


# ---------------------------------------------------------------- decision-time signals


def _authoritative(sim: Simulator) -> Any:
    units = [
        (u.id, u.cell, u.population, u.stores_kcal, u.reserve_kcal_per_capita, u.food_ratio,
         u.energy_deficit, u.fields_ha, {k: v.tolist() for k, v in u.strata.columns.items()})
        for u in sim.state.units.values()
    ]  # fmt: skip
    rng = {name: repr(sim.rng.stream(name).bit_generator.state) for name in sim.rng._streams}
    return units, rng, [(e.year, e.kind, repr(e.data)) for e in sim.events]


def _run(years: int = 120) -> Simulator:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_pressure.yaml").with_overrides(
        seed=1, n_years=years
    )
    sim = Simulator(scenario)
    for _ in range(years):
        sim.step()
    return sim


def test_the_current_rule_is_reproduced_from_decision_time_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The policy inputs (Need, post-trade H, post-trade stores K) are all known at the
    energetics decision, and min(Need - H, K) reproduces the authoritative withdrawal; the
    observation changes nothing."""
    plain = _authoritative(_run())
    seen: list[tuple[float, float, float, float]] = []
    apply = EnergyUpdates.apply

    def observed(updates: EnergyUpdates, state: Any, ctx: Any) -> None:
        cols = updates.cols
        opening, harvest = cols.get("stores_kcal").copy(), cols.get("harvest_kcal").copy()
        apply(updates, state, ctx)
        withdrawn = np.maximum(opening - updates.stores_kcal, 0.0)
        for row in zip(
            updates.need_kcal.tolist(),
            harvest.tolist(),
            opening.tolist(),
            withdrawn.tolist(),
            strict=True,
        ):
            seen.append(row)

    monkeypatch.setattr(EnergyUpdates, "apply", observed)
    observed_run = _run()
    assert _authoritative(observed_run) == plain
    shortages = [(n, h, k, x) for n, h, k, x in seen if h < n]
    assert any(x > 0 for *_, x in shortages)
    for need, harvest, stores, x in shortages:
        rule = release_current(need - harvest, stores).withdrawal
        assert abs(x - rule) <= 1e-12 * max(stores, need)


def test_no_production_module_uses_the_release_candidate() -> None:
    src = Path(simulation.__file__).parents[1]
    users = [
        p
        for p in src.rglob("*.py")
        if "store_release" in p.read_text() and p.name != "store_release.py"
    ]
    assert users == []
