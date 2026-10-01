"""PH4b semantic audit: an expired belief is indistinguishable from a never-observed cell.

A belief entry is current in year ``t`` while ``year > t - memory_years``; afterwards every
model path ignores it (migration and report selection filter on it; report receipt only
compares it with strictly fresher same-species reports; merges keep the freshest entry;
perception only writes). Expiry is monotone: an entry's year never changes, so an expired
entry never becomes current again.

These tests pin that claim on whole simulations: erasing every expired entry from the
dense store before each tick (turning it into "never observed") must leave everything
scientific identical, including events and every RNG stream. Only the raw bytes of
expired entries may differ, so beliefs are compared in their logical form: the current
entries of each unit. This is what licenses a store that physically deletes expired
entries (PH4b, Level A).
"""

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.unit import NEVER_OBSERVED, belief_slot
from tests.conftest import ROOT
from tests.test_unit_table import _same, current_beliefs, unit_state


def memory_of(sim: Simulator, species_id: str) -> int:
    return sim.scenario.species[species_id].cognition.memory_years


def erase_expired(sim: Simulator, horizon_year: int) -> int:
    """Turn every entry expired as of ``horizon_year`` into never-observed; returns how many."""
    store = sim.state.belief_store
    erased = 0
    for unit in sim.state.units.values():
        slot = belief_slot(unit)
        stale = store.year[slot] <= horizon_year - memory_of(sim, unit.species_id)
        stale &= store.year[slot] != NEVER_OBSERVED
        erased += int(stale.sum())
        store.year[slot, stale] = NEVER_OBSERVED
        store.food_kcal[slot, stale] = 0
        store.population[slot, stale] = 0
        store.hops[slot, stale] = 0
    return erased


def assert_logically_equal(a: Simulator, b: Simulator) -> None:
    assert list(a.state.units) == list(b.state.units)
    for uid in a.state.units:
        sa, sb = unit_state(a.state.units[uid]), unit_state(b.state.units[uid])
        for key, value in sa.items():
            if key != "beliefs":  # raw bytes: compared logically below
                assert _same(value, sb[key]), (uid, key)
    assert current_beliefs(a) == current_beliefs(b)
    for name in ("plant_stock_kcal", "game_stock_kcal", "soil_nutrients"):
        assert np.array_equal(getattr(a.state.ecology, name), getattr(b.state.ecology, name))
    assert [(e.year, e.kind, e.data) for e in a.events] == [
        (e.year, e.kind, e.data) for e in b.events
    ]
    for name in set(a.rng._streams) | set(b.rng._streams):
        assert a.rng.stream(name).bit_generator.state == b.rng.stream(name).bit_generator.state


def run_pruned_and_lazy(a: Simulator, b: Simulator, years: int) -> tuple[int, int]:
    """Step both; ``b`` has its expired entries erased before every step.

    Returns ``(entries erased, migrations)``.
    """
    erased = migrations = 0
    for _ in range(years):
        erased += erase_expired(b, b.state.year + 1)
        la, lb = vars(a.step().ledger), vars(b.step().ledger)
        assert la == lb
        migrations += la["migrations"]
    return erased, migrations


@pytest.mark.parametrize(
    ("path", "seed", "years"),
    [
        ("scenarios/mvp2_neolithic.yaml", 0, 260),
        ("scenarios/mvp2_pressure.yaml", 1, 200),
        ("scenarios/mvp1_sandbox.yaml", 2, 150),
    ],
)
def test_erasing_expired_beliefs_changes_nothing(path: str, seed: int, years: int) -> None:
    scenario = Scenario.from_yaml(ROOT / path).with_overrides(seed=seed, n_years=years)
    # The dense store keeps expired entries (lazy expiry): that is what is being erased.
    a, b = Simulator(scenario, belief_backend="dense"), Simulator(scenario, belief_backend="dense")
    erased, _ = run_pruned_and_lazy(a, b, years)
    assert erased > 100  # expiry actually happened
    assert_logically_equal(a, b)
    ledger_events = {e.kind for e in a.events}
    assert {"population_split", "population_merge"} <= ledger_events  # fission and fusion ran


def test_erasing_expired_beliefs_with_movement_and_sharing_at_density() -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(seed=5)
    a = synthetic_simulator(scenario, 300, belief_backend="dense")
    b = synthetic_simulator(scenario, 300, belief_backend="dense")
    erased, migrations = run_pruned_and_lazy(a, b, 40)
    assert erased > 1000 and migrations > 50  # moving groups revisit and forget cells
    assert_logically_equal(a, b)
