"""Merge/split semantics and network rewiring (spec §6.4, §6.5, §38)."""

from dataclasses import fields

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
)
from madexplorer.population.familiarity import FamiliarityMap, FamiliarityRule
from madexplorer.population.unit import PopulationUnit

RULE = FamiliarityRule(baseline=0.6, time_constant_years=20.0)


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
    assert set(FIELD_RULES) == {f.name for f in fields(PopulationUnit)}


def test_merge_rejects_units_in_different_cells() -> None:
    with pytest.raises(ValueError):
        merge_state(_unit("a", 5), _unit("b", 5, cell=1), MergeMode.FUSION, 5, RULE)


def test_aggregation_keeps_groups_and_fusion_absorbs_them() -> None:
    a, b = _unit("a", 10), _unit("b", 10)
    merge_state(a, b, MergeMode.AGGREGATION, 5, RULE)
    assert a.groups == 2
    c, d = _unit("c", 10), _unit("d", 10)
    merge_state(c, d, MergeMode.FUSION, 5, RULE)
    assert c.groups == 1


def test_merge_weights_intensive_state_by_people() -> None:
    a, b = _unit("a", 30), _unit("b", 10)
    a.food_ratio, b.food_ratio = 1.0, 0.6
    a.harvest_history.extend([100.0, 200.0])
    b.harvest_history.extend([50.0])
    merge_state(a, b, MergeMode.FUSION, 5, RULE)
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
    daughter = split_off(parent, leave_f, leave_m, "d", year=5, familiarity=RULE)
    assert daughter.population + parent.population == totals[0]
    assert daughter.stores_kcal + parent.stores_kcal == pytest.approx(totals[2])
    assert daughter.stores_kcal / daughter.population == pytest.approx(
        parent.stores_kcal / parent.population
    )
    merge_state(parent, daughter, MergeMode.FUSION, 5, RULE)
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
        split_off(parent, parent.females.copy(), parent.males.copy(), "d", year=1, familiarity=RULE)


def _network() -> dict[str, PopulationUnit]:
    units = {uid: _unit(uid, 10) for uid in ("a", "b", "c", "d")}
    units["a"].trade_ties = {"b": 0.4, "c": 0.2}
    units["b"].trade_ties = {"a": 0.4, "c": 0.3, "d": 0.1}
    units["c"].trade_ties = {"a": 0.2, "b": 0.3}
    units["d"].trade_ties = {"b": 0.1}
    return units


def test_absorb_rewires_incoming_ties_to_the_surviving_unit() -> None:
    units = _network()
    absorb(units, "b", "a", MergeMode.AGGREGATION, 5, RULE)
    assert "b" not in units
    assert all("b" not in u.trade_ties for u in units.values())
    assert units["d"].trade_ties == {"a": pytest.approx(0.1)}  # was only linked to b


def test_absorb_combines_duplicate_edges_and_drops_self_edges() -> None:
    units = _network()
    absorb(units, "b", "a", MergeMode.AGGREGATION, 5, RULE)
    assert "a" not in units["a"].trade_ties
    assert units["a"].trade_ties == {"c": pytest.approx(0.5), "d": pytest.approx(0.1)}
    assert units["c"].trade_ties == {"a": pytest.approx(0.5)}


def test_absorb_preserves_total_tie_weight_except_the_internal_edge() -> None:
    units = _network()
    before = sum(sum(u.trade_ties.values()) for u in units.values())
    internal = units["a"].trade_ties["b"] + units["b"].trade_ties["a"]
    absorb(units, "b", "a", MergeMode.FUSION, 5, RULE)
    after = sum(sum(u.trade_ties.values()) for u in units.values())
    assert after == pytest.approx(before - internal)


def test_merge_decays_familiarity_to_the_merge_year() -> None:
    """MVP 2.1 (B1). The frozen MVP 2 reference decayed merged familiarity to the source's
    last residence year (a shadowed loop variable), preserved there for freeze
    equivalence; familiarity is now combined as both units' effective values at the
    merge year."""
    rule = FamiliarityRule(baseline=0.6, time_constant_years=20.0)
    a, b = _unit("a", 5), _unit("b", 5)
    for unit in (a, b):
        unit.familiarity = FamiliarityMap({4: 0.9}, {4: 0})
    b.recent_residence = {7: 3}  # an old residence record must not set the decay year
    merge_state(a, b, MergeMode.FUSION, 40, rule)
    expected = FamiliarityMap({4: 0.9}, {4: 0}).effective(4, 40, rule)
    assert a.familiarity.stored(4) == (expected, 39)  # value at 40; idle clock kept
    assert a.familiarity.effective(4, 40, rule) == expected


@pytest.mark.parametrize("residence", [{}, {7: 3}, {7: 3, 9: 31, 2: 12}, {9: 31, 7: 3}])
def test_source_residence_cannot_change_merged_familiarity(residence: dict[int, int]) -> None:
    rule = FamiliarityRule(baseline=0.6, time_constant_years=20.0)
    a, b = _unit("a", 10), _unit("b", 30)
    a.familiarity = FamiliarityMap({4: 0.95, 5: 0.7}, {4: 10, 5: 2})
    b.familiarity = FamiliarityMap({4: 0.75, 6: 0.99}, {4: 30, 6: 34})
    b.recent_residence = dict(residence)
    merge_state(a, b, MergeMode.FUSION, 35, rule)
    reference_a, reference_b = _unit("a", 10), _unit("b", 30)
    reference_a.familiarity = FamiliarityMap({4: 0.95, 5: 0.7}, {4: 10, 5: 2})
    reference_b.familiarity = FamiliarityMap({4: 0.75, 6: 0.99}, {4: 30, 6: 34})
    merge_state(reference_a, reference_b, MergeMode.FUSION, 35, rule)
    assert a.familiarity._value == reference_a.familiarity._value
    assert a.familiarity._year == reference_a.familiarity._year


def test_merged_familiarity_weights_effective_values_at_the_same_time() -> None:
    """Very different last-practiced years: both values are decayed to the merge year,
    then weighted by population."""
    rule = FamiliarityRule(baseline=0.6, time_constant_years=20.0)
    a, b = _unit("a", 10), _unit("b", 30)  # populations 10 and 30
    a.familiarity = FamiliarityMap({4: 0.95}, {4: 1})  # practiced long ago
    b.familiarity = FamiliarityMap({4: 0.75}, {4: 34})  # practiced last year
    b.recent_residence = {4: 34, 8: 5}
    merge_year = 35
    eff_a = FamiliarityMap({4: 0.95}, {4: 1}).effective(4, merge_year, rule)
    eff_b = FamiliarityMap({4: 0.75}, {4: 34}).effective(4, merge_year, rule)
    assert eff_a < 0.95 and eff_b == 0.75  # a decayed, b practiced last year (not idle)
    merge_state(a, b, MergeMode.FUSION, merge_year, rule)
    value, stamp = a.familiarity.stored(4) or (None, None)
    assert value == (eff_a * 10 + eff_b * 30) / 40
    assert stamp == 34  # the later of the two materialized stamps


def test_row_level_merge_uses_the_merge_year() -> None:
    """The production (unit-table) merge agrees with the reference rule."""
    from madexplorer.config.loader import Scenario
    from madexplorer.experiments.benchmark import synthetic_simulator
    from madexplorer.population.familiarity import familiarity_rule
    from madexplorer.population.lifecycle import merge_units
    from tests.conftest import ROOT

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    sim = synthetic_simulator(scenario, 4)
    target, source = list(sim.state.units.values())[:2]
    source.cell = target.cell
    target.familiarity = FamiliarityMap({4: 0.95}, {4: 1})
    source.familiarity = FamiliarityMap({4: 0.75}, {4: 30})
    source.recent_residence = {9: 2}
    n_t, n_s, year = target.population, source.population, sim.state.year
    rule = familiarity_rule(next(iter(scenario.species.values())), scenario.config.mechanisms)
    expected = FamiliarityMap({4: 0.95}, {4: 1})
    expected.merge(FamiliarityMap({4: 0.75}, {4: 30}), n_t, n_s, year, rule)
    merge_units(sim.state.units, source.id, target.id, MergeMode.FUSION, year, rule)
    assert target.familiarity._value == expected._value
    assert target.familiarity._year == expected._year
