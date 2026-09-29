"""Practiced foraging familiarity: lazy decay, merge and split semantics (P4b reform)."""

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.population.composition import MergeMode, merge_state, split_off
from madexplorer.population.familiarity import (
    REPRESENTATION_EPSILON,
    FamiliarityMap,
    FamiliarityRule,
    decayed_familiarity,
)
from madexplorer.population.unit import BeliefMap, Observation, PopulationUnit
from tests.conftest import ROOT, small_scenario_dict

F0, TAU, RATE = 0.6, 20.0, 0.3
DECAY = FamiliarityRule(baseline=F0, time_constant_years=TAU)
PERMANENT = FamiliarityRule(baseline=F0, time_constant_years=None)  # pre-reform rules


def _practiced(value: float, year: int, cell: int = 0) -> FamiliarityMap:
    return FamiliarityMap({cell: value}, {cell: year})


def _unit(uid: str, n: int, familiarity: FamiliarityMap) -> PopulationUnit:
    females = np.zeros(91, dtype=np.int64)
    males = np.zeros(91, dtype=np.int64)
    females[20], males[25] = n - n // 2, n // 2
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=0,
        females=females,
        males=males,
        reserve_kcal_per_capita=0.0,
        founded_year=0,
        familiarity=familiarity,
    )


def test_fresh_and_continuously_practiced_familiarity_does_not_decay() -> None:
    m = _practiced(0.95, year=10)
    assert m.effective(0, 10, DECAY) == 0.95  # same year
    assert m.effective(0, 11, DECAY) == 0.95  # practiced last year: no idle year
    assert m.effective(0, 12, DECAY) < 0.95  # one year unpracticed


def test_familiarity_decays_monotonically_toward_the_baseline() -> None:
    m = _practiced(1.0, year=0)
    values = [m.effective(0, year, DECAY) for year in range(1, 400, 7)]
    assert all(a >= b for a, b in itertools.pairwise(values))
    assert values[0] == 1.0 and values[-1] == pytest.approx(F0, abs=1e-6)


def test_after_one_time_constant_the_excess_is_one_over_e() -> None:
    m = _practiced(1.0, year=0)
    idle_one_tau = int(TAU) + 1  # year - last - 1 = tau
    excess = m.effective(0, idle_one_tau, DECAY) - F0
    assert excess == pytest.approx((1.0 - F0) / math.e, rel=1e-12)


@settings(max_examples=200, deadline=None)
@given(stored=st.floats(F0, 1.0), idle=st.floats(0, 1e4))
def test_familiarity_never_decays_below_the_baseline(stored: float, idle: float) -> None:
    value = decayed_familiarity(stored, idle, F0, TAU)
    assert F0 <= value <= stored


def test_renewed_practice_starts_from_the_decayed_value() -> None:
    m = _practiced(1.0, year=0)
    decayed = m.effective(0, 51, DECAY)  # 50 idle years
    m.practice(0, 51, RATE, DECAY)
    stored = m.stored(0)
    assert stored is not None and stored[1] == 51
    assert stored[0] == pytest.approx(decayed + RATE * (1 - decayed))
    assert m.effective(0, 52, DECAY) == stored[0]


def test_merge_is_population_weighted_and_counts_a_missing_cell_as_baseline() -> None:
    a, b = _unit("a", 30, _practiced(1.0, 7)), _unit("b", 10, _practiced(0.8, 7))
    b.familiarity.practice(5, 7, RATE, DECAY)  # b alone knows cell 5 (0.72)
    merge_state(a, b, MergeMode.FUSION, 7, DECAY)
    assert a.familiarity.effective(0, 7, DECAY) == pytest.approx(0.75 * 1.0 + 0.25 * 0.8)
    assert a.familiarity.effective(5, 7, DECAY) == pytest.approx(0.75 * F0 + 0.25 * 0.72)


def test_merge_uses_values_decayed_to_the_merge_year() -> None:
    a, b = _unit("a", 20, _practiced(1.0, 100)), _unit("b", 20, _practiced(1.0, 0))
    expected_b = b.familiarity.effective(0, 100, DECAY)  # 99 idle years
    merge_state(a, b, MergeMode.FUSION, 100, DECAY)
    assert a.familiarity.effective(0, 100, DECAY) == pytest.approx(0.5 * 1.0 + 0.5 * expected_b)
    assert expected_b < 0.61  # a stale maximum would have given 1.0


def test_merge_keeps_the_idle_clock_when_folding_in_decay() -> None:
    a, b = _unit("a", 20, _practiced(0.9, 50)), _unit("b", 20, _practiced(0.9, 50))
    merge_state(a, b, MergeMode.FUSION, 80, DECAY)
    reference = _practiced(0.9, 50)
    for year in (80, 81, 120):
        assert a.familiarity.effective(0, year, DECAY) == pytest.approx(
            reference.effective(0, year, DECAY), rel=1e-12
        )


def test_fission_gives_the_daughter_the_parents_current_familiarity() -> None:
    parent = _unit("p", 40, _practiced(1.0, 10))
    parent.familiarity.practice(3, 60, RATE, DECAY)
    leave_f = np.zeros(91, dtype=np.int64)
    leave_f[20] = 5
    daughter = split_off(parent, leave_f, np.zeros(91, dtype=np.int64), "d", 60, DECAY)
    for cell in (0, 3):
        assert daughter.familiarity.effective(cell, 60, DECAY) == pytest.approx(
            parent.familiarity.effective(cell, 60, DECAY), rel=1e-12
        )
    assert daughter.familiarity.stored(0)[1] == 59  # type: ignore[index]  # decay folded in
    daughter.familiarity.practice(0, 61, RATE, DECAY)  # lineages now evolve independently
    assert daughter.familiarity.effective(0, 61, DECAY) > parent.familiarity.effective(0, 61, DECAY)


def test_entries_indistinguishable_from_the_baseline_are_dropped_when_materialized() -> None:
    m = FamiliarityMap({0: 1.0, 1: 1.0}, {0: 0, 1: 990})
    copy = m.materialized(1000, DECAY)
    assert 0 not in copy and 1 in copy  # cell 0: excess 0.4 exp(-999/20) < epsilon
    assert copy.effective(0, 1000, DECAY) == F0
    assert abs(m.effective(0, 1000, DECAY) - F0) < REPRESENTATION_EPSILON


def test_decayed_familiarity_does_not_erase_geographic_beliefs() -> None:
    unit = _unit("u", 30, _practiced(1.0, 0, cell=3))
    unit.beliefs = BeliefMap.from_observations(8, {3: Observation(99, 5e5, 0, hops=1)})
    leave_f = np.zeros(91, dtype=np.int64)
    leave_f[20] = 5
    daughter = split_off(unit, leave_f, np.zeros(91, dtype=np.int64), "d", 100, DECAY)
    for group in (unit, daughter):
        assert group.familiarity.effective(3, 100, DECAY) < F0 + 0.005  # skill nearly gone
        assert bool(group.beliefs.current(np.array([3]), 100, memory_years=20)[0])
        assert group.beliefs[3].food_kcal == pytest.approx(5e5)


def test_without_the_switch_familiarity_is_permanent_and_merges_keep_the_maximum() -> None:
    m = _practiced(0.9, year=0)
    assert m.effective(0, 500, PERMANENT) == 0.9
    a, b = _unit("a", 30, _practiced(0.7, 1)), _unit("b", 10, _practiced(0.95, 1))
    merge_state(a, b, MergeMode.FUSION, 400, PERMANENT)
    assert a.familiarity.effective(0, 400, PERMANENT) == 0.95


@pytest.mark.parametrize("decay", [True, False])
def test_foraging_reads_and_practices_the_decayed_value(decay: bool) -> None:
    data = small_scenario_dict(n_years=1)
    data["mechanisms"] = {"familiarity_decay": decay}
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    unit = next(iter(sim.state.units.values()))
    cell, last = unit.cell, sim.state.year - 40
    unit.familiarity = _practiced(0.9, last, cell=cell)
    sim.step()
    stored, year = unit.familiarity.stored(cell)  # type: ignore[misc]
    known = decayed_familiarity(0.9, year - last - 1, F0, TAU) if decay else 0.9
    assert year == sim.state.year
    assert stored == pytest.approx(known + RATE * (1 - known), rel=1e-12)
