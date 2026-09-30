"""P5 field investment: growth toward a target (A, accepted) and expected tenure (B, off)."""

import itertools
import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy import agriculture
from madexplorer.economy.agriculture import (
    FieldPlanningSubsystem,
    adjusted_fields_ha,
    expected_tenure_years,
    fields_toward_target,
    unit_labor_hours,
)
from madexplorer.population.composition import MergeMode, merge_state, split_off
from madexplorer.population.familiarity import FamiliarityRule
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, mvp2_scenario_dict, step_context

CULT, CLEAR, RATE, MARGIN, SHARE = 600.0, 800.0, 0.3, 0.1, 0.9
PAYS = {"yield_per_ha": 6e5, "forage_marginal": 400.0}  # new land beats foraging x 1.1


def _grow(fields: float, need: float, labor: float, tenure: float = 5.0, **returns: float):  # type: ignore[no-untyped-def]
    r = PAYS | returns
    return fields_toward_target(
        fields, r["yield_per_ha"], CULT, CLEAR, tenure, r["forage_marginal"],
        RATE, MARGIN, need, labor * SHARE, SHARE,
    )  # fmt: skip


def test_growth_closes_a_fraction_of_the_gap_even_from_zero_fields() -> None:
    fields, gap, limit = _grow(0.0, need=50.0, labor=1e6)
    assert gap > 0 and limit == "target"
    assert fields == pytest.approx(RATE * 50.0)


def test_growth_is_limited_by_the_labor_to_clear_and_then_work_the_fields() -> None:
    labor = 10_000.0
    fields, _, limit = _grow(2.0, need=50.0, labor=labor)
    assert limit == "labor"
    added = fields - 2.0
    # Next year, after paying the clearing labor, the farm labor share works every field.
    assert (labor - added * CLEAR) * SHARE == pytest.approx(fields * CULT)


def test_ongoing_cultivation_labor_is_counted_before_new_clearing() -> None:
    small = _grow(1.0, need=100.0, labor=10_000.0)[0] - 1.0
    large = _grow(10.0, need=100.0, labor=10_000.0)[0] - 10.0
    assert 0 <= large < small


def test_no_expansion_when_farming_does_not_pay_and_shrinking_is_unchanged() -> None:
    fields, gap, limit = _grow(5.0, need=50.0, labor=1e6, forage_marginal=1000.0)
    old, old_gap = adjusted_fields_ha(5.0, 6e5, CULT, CLEAR, 5.0, 1000.0, RATE, 2.0, MARGIN)
    assert gap < 0 and limit == "" and fields < 5.0
    assert (fields, gap) == (old, old_gap)
    assert _grow(0.0, need=50.0, labor=1e6, forage_marginal=1000.0)[0] == 0.0


def test_growth_stops_at_the_need_area() -> None:
    assert _grow(50.0, need=50.0, labor=1e6)[0] == 50.0
    assert _grow(49.0, need=50.0, labor=1e6)[0] <= 50.0


def test_the_bootstrap_trap_is_gone() -> None:
    new, old = 0.0, 0.0
    for _ in range(10):
        new = _grow(new, need=50.0, labor=1e6)[0]
        old = min(adjusted_fields_ha(old, 6e5, CULT, CLEAR, 5.0, 400.0, RATE, 2.0, MARGIN)[0], 50)
    assert new > 0.95 * 50.0  # 1 - 0.7^10 = 0.97
    assert old < 0.25 * 50.0  # the old rule compounds from a tiny first plot


@settings(max_examples=100, deadline=None)
@given(
    fields=st.floats(0, 200),
    need=st.floats(0, 300),
    labor=st.floats(0, 1e5),
    forage=st.floats(0, 2000),
)
def test_expansion_never_exceeds_the_need_area_or_the_labor_budget(
    fields: float, need: float, labor: float, forage: float
) -> None:
    new, _, _ = _grow(fields, need, labor, forage_marginal=forage)
    added = new - fields
    if added > 0:
        assert new <= max(need, fields) + 1e-9
        assert (labor - added * CLEAR) * SHARE >= new * CULT - 1e-6 * max(new * CULT, 1)


def test_expected_tenure_matches_the_geometric_sum_and_its_limits() -> None:
    for m in (0.05, 0.3, 0.9):
        p = 1 - m
        assert expected_tenure_years(m, 10, 3) == pytest.approx(sum(p**t for t in range(1, 11)))
    assert expected_tenure_years(0.0, 10, 3) == 10.0
    assert expected_tenure_years(1e-15, 10, 3) == 10.0  # p ~ 1 handled without 0/0
    assert expected_tenure_years(1.0, 10, 3) == 0.0
    assert expected_tenure_years(math.nan, 10, 3) == 3.0  # unknown: past-residence proxy
    assert expected_tenure_years(math.nan, 10, 0) == 1.0
    values = [expected_tenure_years(m, 10, 3) for m in np.linspace(0, 1, 21)]
    assert all(a >= b for a, b in itertools.pairwise(values))


def _unit(uid: str, n: int, hazard: float) -> PopulationUnit:
    females = np.zeros(91, dtype=np.int64)
    females[20] = n
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=0,
        females=females,
        males=np.zeros(91, dtype=np.int64),
        reserve_kcal_per_capita=0.0,
        founded_year=0,
        move_hazard=hazard,
    )


def test_move_hazard_merges_by_population_and_splits_by_copy() -> None:
    rule = FamiliarityRule(0.6, 20.0)
    a, b = _unit("a", 30, 0.1), _unit("b", 10, 0.5)
    merge_state(a, b, MergeMode.FUSION, 1, rule)
    assert a.move_hazard == pytest.approx(0.2)
    c, d = _unit("c", 30, math.nan), _unit("d", 10, 0.5)
    merge_state(c, d, MergeMode.FUSION, 1, rule)
    assert c.move_hazard == 0.5
    leave = np.zeros(91, dtype=np.int64)
    leave[20] = 5
    daughter = split_off(a, leave, np.zeros(91, dtype=np.int64), "x", 1, rule)
    assert daughter.move_hazard == a.move_hazard


def _farmers(**mechanisms: bool) -> Simulator:
    data = mvp2_scenario_dict(n_years=60, seed=4)
    data["initial_populations"] = [
        {
            "species": "human",
            "cell": [8, 8],
            "population": 80,
            "technologies": ["plant_cultivation", "storage_pits"],
            "initial_knowledge": {"agriculture": 4.5, "storage": 1.0},
        }
    ]
    data["mechanisms"] = mechanisms
    return Simulator(Scenario.from_dict(data, base_dir=ROOT))


def test_migration_records_last_years_hazard_and_moving_resets_it() -> None:
    sim = _farmers()
    for _ in range(30):
        cells = {u.id: u.cell for u in sim.state.units.values()}
        sim.step()
        for unit in sim.state.units.values():
            if unit.id in cells and unit.cell != cells[unit.id]:
                assert math.isnan(unit.move_hazard)  # just arrived
            else:
                assert math.isnan(unit.move_hazard) or 0.0 <= unit.move_hazard <= 1.0
    assert any(not math.isnan(u.move_hazard) for u in sim.state.units.values())


def test_field_planning_amortizes_over_tenure_expected_from_the_stored_hazard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[float] = []
    original = agriculture.adjusted_fields_ha

    def spy(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(args[4])  # expected_tenure_years
        return original(*args, **kwargs)

    monkeypatch.setattr(agriculture, "adjusted_fields_ha", spy)
    cases = ((True, 0.5, 1 - 0.5**10), (True, math.nan, 7.0), (False, 0.5, 7.0))
    for enabled, hazard, expected in cases:
        # The spy watches the proportional rule, so pin it (A, the default, bypasses it).
        sim = _farmers(expected_tenure=enabled, field_growth_to_target=False)
        unit = next(iter(sim.state.units.values()))
        unit.move_hazard, unit.residence_years = hazard, 7
        seen.clear()
        FieldPlanningSubsystem().evaluate(sim.state, step_context(sim))
        assert seen == [pytest.approx(expected)]


def test_with_target_growth_fields_stay_within_labor_and_arable_land() -> None:
    sim = _farmers(field_growth_to_target=True, expected_tenure=True)
    grew = False
    for _ in range(60):
        sim.step()
        ctx = step_context(sim)
        config = sim.scenario.config.agriculture
        for unit in sim.state.units.values():
            share = sim.scenario.species["human"].subsistence.max_farm_labor_share
            assert unit.fields_ha * config.cultivation_hours_per_ha <= (
                share * unit_labor_hours(unit, ctx) + 1e-6
            )
            grew |= unit.fields_ha > 5.0
        fields = sim.state.cell_fields_ha()
        assert (fields <= ctx.arable_ha + 1e-6).all()
    assert grew
