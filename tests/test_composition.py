"""Merge/split semantics and network rewiring (spec §6.4, §6.5, §38)."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.population.composition import (
    FIELD_RULES,
    MergeMode,
    absorb,
    merge_state,
    split_off,
    unit_field_names,
)
from madexplorer.population.unit import PopulationUnit


def _unit(uid: str, n_female: int, n_male: int = 0, cell: int = 0) -> PopulationUnit:
    females = np.zeros(91, dtype=np.int64)
    males = np.zeros(91, dtype=np.int64)
    females[20], males[25] = n_female, n_male
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=cell,
        females=females,
        males=males,
        reserve_kcal_per_capita=100.0,
        founded_year=0,
        knowledge=np.array([1.0, 2.0]),
        stores_kcal=50.0,
        fields_ha=3.0,
        energy_debt_kcal=10.0,
        labor_debt_hours=4.0,
    )


def test_every_unit_field_has_merge_and_split_rules() -> None:
    assert set(FIELD_RULES) == unit_field_names()


def test_merge_rejects_units_in_different_cells() -> None:
    with pytest.raises(ValueError):
        merge_state(_unit("a", 5), _unit("b", 5, cell=1), MergeMode.FUSION)


def test_aggregation_keeps_groups_and_fusion_absorbs_them() -> None:
    a, b = _unit("a", 10), _unit("b", 10)
    merge_state(a, b, MergeMode.AGGREGATION)
    assert a.groups == 2
    c, d = _unit("c", 10), _unit("d", 10)
    merge_state(c, d, MergeMode.FUSION)
    assert c.groups == 1


def test_merge_weights_intensive_state_by_people() -> None:
    a, b = _unit("a", 30), _unit("b", 10)
    a.food_ratio, b.food_ratio = 1.0, 0.6
    a.harvest_history.extend([100.0, 200.0])
    b.harvest_history.extend([50.0])
    merge_state(a, b, MergeMode.FUSION)
    assert a.food_ratio == pytest.approx(0.9)
    assert list(a.harvest_history) == [pytest.approx(0.75 * 200 + 0.25 * 50)]


@settings(max_examples=60, deadline=None)
@given(
    n_f=st.integers(2, 200),
    n_m=st.integers(0, 200),
    fraction=st.floats(0.05, 0.95),
    seed=st.integers(0, 10_000),
)
def test_split_then_merge_conserves_people_food_fields_and_debts(
    n_f: int, n_m: int, fraction: float, seed: int
) -> None:
    parent = _unit("p", n_f, n_m)
    totals = (
        parent.population,
        parent.total_reserve_kcal,
        parent.stores_kcal,
        parent.fields_ha,
        parent.energy_debt_kcal,
        parent.labor_debt_hours,
    )
    rng = np.random.default_rng(seed)
    leave_f = rng.binomial(parent.females, fraction)
    leave_m = rng.binomial(parent.males, fraction)
    moved = int(leave_f.sum() + leave_m.sum())
    if not 0 < moved < parent.population:
        return
    daughter = split_off(parent, leave_f, leave_m, "d", year=5)
    assert daughter.population + parent.population == totals[0]
    assert daughter.stores_kcal + parent.stores_kcal == pytest.approx(totals[2])
    assert daughter.stores_kcal / daughter.population == pytest.approx(
        parent.stores_kcal / parent.population
    )
    merge_state(parent, daughter, MergeMode.FUSION)
    after = (
        parent.population,
        parent.total_reserve_kcal,
        parent.stores_kcal,
        parent.fields_ha,
        parent.energy_debt_kcal,
        parent.labor_debt_hours,
    )
    assert after == pytest.approx(totals)
    assert parent.knowledge == pytest.approx(np.array([1.0, 2.0]))


def test_split_requires_people_on_both_sides() -> None:
    parent = _unit("p", 10)
    with pytest.raises(ValueError):
        split_off(parent, parent.females.copy(), parent.males.copy(), "d", year=1)


def _network() -> dict[str, PopulationUnit]:
    units = {uid: _unit(uid, 10) for uid in ("a", "b", "c", "d")}
    units["a"].trade_ties = {"b": 0.4, "c": 0.2}
    units["b"].trade_ties = {"a": 0.4, "c": 0.3, "d": 0.1}
    units["c"].trade_ties = {"a": 0.2, "b": 0.3}
    units["d"].trade_ties = {"b": 0.1}
    return units


def test_absorb_rewires_incoming_ties_to_the_surviving_unit() -> None:
    units = _network()
    absorb(units, "b", "a", MergeMode.AGGREGATION)
    assert "b" not in units
    assert all("b" not in u.trade_ties for u in units.values())
    assert units["d"].trade_ties == {"a": pytest.approx(0.1)}  # was only linked to b


def test_absorb_combines_duplicate_edges_and_drops_self_edges() -> None:
    units = _network()
    absorb(units, "b", "a", MergeMode.AGGREGATION)
    assert "a" not in units["a"].trade_ties
    assert units["a"].trade_ties == {"c": pytest.approx(0.5), "d": pytest.approx(0.1)}
    assert units["c"].trade_ties == {"a": pytest.approx(0.5)}


def test_absorb_preserves_total_tie_weight_except_the_internal_edge() -> None:
    units = _network()
    before = sum(sum(u.trade_ties.values()) for u in units.values())
    internal = units["a"].trade_ties["b"] + units["b"].trade_ties["a"]
    absorb(units, "b", "a", MergeMode.FUSION)
    after = sum(sum(u.trade_ties.values()) for u in units.values())
    assert after == pytest.approx(before - internal)
