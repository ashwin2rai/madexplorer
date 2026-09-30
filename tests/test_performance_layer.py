"""Performance-layer contracts: compiled scenario data and the shared spatial index.

These structures change no equation; the tests check that they reproduce the domain
representation exactly (order included), which exact seeded replay depends on.
"""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.compiled import CompiledScenario
from madexplorer.core.simulation import Simulator
from madexplorer.core.spatial import SpatialIndex
from madexplorer.experiments.benchmark import synthetic_simulator
from tests.conftest import ROOT, mvp2_scenario_dict, step_context


def _mvp2() -> Scenario:
    return Scenario.from_dict(mvp2_scenario_dict(), base_dir=ROOT)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.integers(0, 12), min_size=0, max_size=60))
def test_spatial_index_reproduces_units_by_cell_order(cells: list[int]) -> None:
    sim = Simulator(_mvp2())
    (template,) = sim.state.units.values()
    sim.state.units.clear()
    for k, cell in enumerate(cells):
        unit = type(template)(
            id=f"u{1000 - k}",  # ids deliberately not in insertion order
            species_id=template.species_id,
            cell=cell,
            females=template.females,
            males=template.males,
            reserve_kcal_per_capita=0.0,
            founded_year=0,
        )
        sim.state.units[unit.id] = unit
    index = SpatialIndex.build(tuple(sim.state.units.values()))
    reference = sim.state.units_by_cell()
    assert list(index.by_cell) == list(reference)
    for cell, units in reference.items():
        assert [u.id for u in index.by_cell[cell]] == [u.id for u in units]
    for k, cell in enumerate(index.cells.tolist()):
        rows = index.order[index.starts[k] : index.starts[k + 1]]
        assert [index.units[r].id for r in rows] == [u.id for u in reference[cell]]
    assert all(index.row_of[u.id] == i for i, u in enumerate(index.units))


def test_spatial_index_is_shared_within_a_phase_and_rebuilt_after_membership_changes() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml"), 60)
    for _ in range(12):  # through fissions, fusions and migrations
        ctx = step_context(sim)
        first = ctx.spatial(sim.state)
        assert ctx.spatial(sim.state) is first
        sim.step()
        fresh = step_context(sim).spatial(sim.state)
        reference = sim.state.units_by_cell()
        assert list(fresh.by_cell) == list(reference)
        assert all(
            [u.id for u in fresh.by_cell[c]] == [u.id for u in units]
            for c, units in reference.items()
        )


def test_membership_changing_applies_invalidate_the_index() -> None:
    from madexplorer.mobility.migration import Relocation
    from madexplorer.population.groups import Extinction

    sim = Simulator(_mvp2())
    ctx = step_context(sim)
    (unit,) = sim.state.units.values()
    before = ctx.spatial(sim.state)
    Relocation(unit.id, unit.cell, unit.cell + 1, 1.0, 0.0, 0.5, 0.0).apply(sim.state, ctx)
    moved = ctx.spatial(sim.state)
    assert moved is not before and moved.cell[0] == unit.cell
    unit.females, unit.males = unit.females * 0, unit.males * 0
    Extinction(unit.id).apply(sim.state, ctx)
    assert ctx.spatial(sim.state).units == ()


def test_compiled_scenario_matches_configuration() -> None:
    scenario = _mvp2()
    sim = Simulator(scenario)
    compiled = CompiledScenario.build(scenario, sim.knowledge)
    human = scenario.species["human"]
    k = compiled.species_index["human"]
    assert compiled.parameter("metabolism.adult_daily_kcal")[k] == human.metabolism.adult_daily_kcal
    assert compiled.parameter("cognition.memory_years")[k] == human.cognition.memory_years
    table = compiled.technologies
    assert table is not None and sim.knowledge is not None
    for tech_id, tech in sim.knowledge.technologies.items():
        i = table.position[tech_id]
        required = {t for t in table.ids if table.requires_mask[i] >> table.position[t] & 1}
        assert required == set(tech.requires)
        for domain, level in tech.min_knowledge.items():
            assert table.min_knowledge[i, sim.knowledge.index[domain]] == level
    sets = [frozenset(), frozenset(table.ids[:2]), frozenset(table.ids)]
    held = table.holds(table.masks(sets))
    for row, techs in zip(held, sets, strict=True):
        assert {table.ids[i] for i in np.flatnonzero(row)} == techs


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from([0.0, 1.0, 5e5, 1e6]) | st.floats(1.0, 2e6),
            st.sampled_from([0.0, 1e6]) | st.floats(0.0, 3e6),
            st.floats(0.0, 1e6),
            st.floats(0.0, 1e6),
            st.floats(0.0, 1e6),
            st.booleans(),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_batched_energy_balance_equals_the_scalar_rule(rows: list[tuple]) -> None:  # type: ignore[type-arg]
    from madexplorer.population.energetics import energy_balance, energy_balance_batch

    need, harvest, reserve, cap, stores, can = (np.array(c) for c in zip(*rows, strict=True))
    batched = energy_balance_batch(need, harvest, reserve, cap, stores, can.astype(bool))
    for i, row in enumerate(rows):
        b = energy_balance(*row)
        expected = (
            b.food_ratio,
            b.deficit,
            b.reserve_kcal,
            b.stores_kcal,
            b.stored_kcal,
            b.spoiled_kcal,
        )
        assert tuple(float(a[i]) for a in batched) == expected


def test_trade_ties_stay_symmetric_among_live_units_so_rewiring_is_local() -> None:
    """The O(degree) tie rewiring relies on this invariant; check it through a run."""
    sim = synthetic_simulator(Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml"), 150)
    for _ in range(25):
        sim.step()
        units = sim.state.units
        for uid, unit in units.items():
            for partner in unit.trade_ties:
                if partner in units:
                    assert uid in units[partner].trade_ties


@settings(max_examples=300, deadline=None)
@given(
    st.lists(
        st.lists(
            st.floats(allow_nan=False, allow_infinity=False, width=64)
            | st.sampled_from([0.0, -0.0, 1e16, -1e16, 1.0, 1e-16]),
            min_size=3,
            max_size=3,
        ),
        min_size=1,
        max_size=20,
    ),
    st.integers(1, 3),
)
def test_python_sum_columns_equals_the_builtin_sum(rows: list[list[float]], width: int) -> None:
    from madexplorer.core.exactsum import python_sum_columns

    columns = [np.array([r[j] for r in rows]) for j in range(width)]
    result = python_sum_columns(columns)
    for i, row in enumerate(rows):
        expected = sum(row[:width])
        assert result[i] == expected or (np.isnan(result[i]) and np.isnan(expected))
        assert np.signbit(result[i]) == np.signbit(expected) or result[i] != 0.0


def test_batched_unit_kernels_equal_their_per_unit_references() -> None:
    """Differential test on a warmed-up farming state: every batched kernel against the
    per-unit reference rule it replaces, bit for bit."""
    from madexplorer.economy.agriculture import (
        crop_yield_batch,
        labor_hours_batch,
        unit_crop_yield,
        unit_labor_hours,
    )
    from madexplorer.knowledge.learning import (
        LearningSubsystem,
        activity_shares,
        learn,
    )
    from madexplorer.population.energetics import annual_need_batch, annual_need_kcal

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    sim = synthetic_simulator(scenario, 120, farming=True)
    for _ in range(8):
        sim.step()
    ctx = step_context(sim)
    state = sim.state
    units = tuple(state.units.values())
    need = annual_need_batch(units, state, ctx)
    labor = labor_hours_batch(units, ctx)
    potential = ctx.crop_potential(state)
    crop = crop_yield_batch(units, potential, ctx)
    assert sim.knowledge is not None
    (proposal,) = LearningSubsystem(sim.knowledge).evaluate(state, ctx)
    for i, u in enumerate(units):
        profile, tables = ctx.species(u.species_id), ctx.tables[u.species_id]
        temperature = float(state.climate.temperature_c[u.cell])
        assert need[i] == annual_need_kcal(u, profile, tables, temperature)
        assert labor[i] == unit_labor_hours(u, ctx)
        assert crop[i] == unit_crop_yield(u, potential, ctx)
        practice = sim.knowledge.practice_weights(activity_shares(u, unit_labor_hours(u, ctx)))
        expected = learn(
            u.knowledge,
            practice,
            u.population,
            sim.knowledge,
            profile.cognition.learning_speed,
            profile.cognition.knowledge_retention,
        )
        assert np.array_equal(proposal.knowledge[i], expected)
    assert (crop > 0).any() and any(u.fields_ha > 0 for u in units)
