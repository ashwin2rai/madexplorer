"""PH3b: the authoritative unit table against the object-authoritative reference engine.

Whole-engine differential tests run complete simulations in both storage modes from the
same seeds and compare every scientifically relevant piece of state, events and RNG
streams. Lifecycle stress tests exercise slot reuse, where stale state could leak.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.unit import PopulationUnit, belief_slot
from tests.conftest import ROOT

SCALARS = (
    "cell",
    "reserve_kcal_per_capita",
    "energy_debt_kcal",
    "harvest_kcal",
    "food_ratio",
    "energy_deficit",
    "food_log_prior",
    "food_log_signal_var",
    "groups",
    "stores_kcal",
    "fields_ha",
    "ever_cultivated",
    "labor_debt_hours",
    "farm_harvest_kcal",
    "farm_hours",
    "forage_harvest_kcal",
    "forage_hours",
    "forage_marginal_kcal_per_hour",
    "forage_plant_share",
    "crop_yield_kcal_per_ha",
    "clearing_hours",
    "stored_kcal",
    "residence_years",
    "move_hazard",
    "founded_year",
    "population",
)


def _same(a: object, b: object) -> bool:
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    return a == b


def unit_state(unit: PopulationUnit) -> dict[str, object]:
    """Everything scientifically relevant about one unit, in comparable form."""
    beliefs = unit.beliefs
    state: dict[str, object] = {name: getattr(unit, name) for name in SCALARS}
    state.update(
        species=unit.species_id,
        parent=unit.parent_id,
        females=unit.females.tolist(),
        males=unit.males.tolist(),
        knowledge=unit.knowledge.tolist(),
        technologies=sorted(unit.technologies),
        beliefs=tuple(
            getattr(beliefs, f).tobytes() for f in ("year", "food_kcal", "population", "hops")
        ),
        report_cells=unit.report_cells.tolist(),
        residence=dict(unit.recent_residence),
        familiarity=(dict(unit.familiarity._value), dict(unit.familiarity._year)),
        history=list(unit.harvest_history),
        ties=dict(unit.trade_ties),
    )
    return state


def current_beliefs(sim: Simulator) -> dict[str, list[tuple[int, int, float, int, int]]]:
    """Each unit's current entries ``(cell, year, food, population, hops)`` by cell: the
    logical belief state (what any model path can observe), for any store backend."""
    store, year = sim.state.belief_store, sim.state.year
    logical = {}
    for uid, unit in sim.state.units.items():
        memory = sim.scenario.species[unit.species_id].cognition.memory_years
        cells, years, food, population, hops = store.entries(belief_slot(unit))
        current = years > year - memory
        logical[uid] = list(
            zip(
                cells[current].tolist(),
                years[current].tolist(),
                food[current].tolist(),
                population[current].tolist(),
                hops[current].tolist(),
                strict=True,
            )
        )
    return logical


def assert_same_simulation(a: Simulator, b: Simulator) -> None:
    """Complete-state comparison of two simulators (order included).

    Beliefs are compared byte for byte on dense stores (expired entries included) and
    logically (current entries) when a store may drop expired entries (sparse, PH4b).
    """
    assert list(a.state.units) == list(b.state.units)  # identity and processing order
    raw = a.state.belief_store.kind == b.state.belief_store.kind == "dense"
    for uid in a.state.units:
        sa, sb = unit_state(a.state.units[uid]), unit_state(b.state.units[uid])
        for key, value in sa.items():
            if key == "beliefs" and not raw:
                continue
            assert _same(value, sb[key]), (uid, key, value, sb[key])
    if not raw:
        assert current_beliefs(a) == current_beliefs(b)
    for name in ("plant_stock_kcal", "game_stock_kcal", "soil_nutrients"):
        assert np.array_equal(getattr(a.state.ecology, name), getattr(b.state.ecology, name))
    events_a = [(e.year, e.kind, e.data) for e in a.events]
    events_b = [(e.year, e.kind, e.data) for e in b.events]
    assert events_a == events_b
    streams = set(a.rng._streams) | set(b.rng._streams)
    for name in streams:
        assert a.rng.stream(name).bit_generator.state == b.rng.stream(name).bit_generator.state, (
            name
        )


def _pair(build):  # type: ignore[no-untyped-def]  # noqa: ANN
    return build(True), build(False)


def run_both(scenario: Scenario, years: int) -> tuple[Simulator, Simulator]:
    """The same scenario in table mode and object (reference) mode."""
    table, reference = _pair(lambda mode: Simulator(scenario, unit_table=mode))  # type: ignore[no-untyped-call]
    rows_a, rows_b = [], []
    for _ in range(years):
        rows_a.append(table.step().ledger)
        rows_b.append(reference.step().ledger)
    assert [vars(r) for r in rows_a] == [vars(r) for r in rows_b]
    return table, reference


def test_reference_engine_is_object_authoritative() -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_pressure.yaml")
    table, reference = _pair(lambda mode: Simulator(scenario, unit_table=mode))  # type: ignore[no-untyped-call]
    assert table.state.table is not None and reference.state.table is None
    unit = next(iter(reference.state.units.values()))
    assert "food_ratio" in unit.__dict__  # plain attribute in the reference engine
    unit = next(iter(table.state.units.values()))
    assert "food_ratio" not in unit.__dict__  # lives only in the table


@pytest.mark.parametrize(
    ("path", "seed", "years"),
    [
        ("scenarios/mvp2_pressure.yaml", 0, 160),
        ("scenarios/mvp2_neolithic.yaml", 3, 220),
        ("scenarios/mvp1_sandbox.yaml", 1, 120),
    ],
)
def test_whole_engine_equals_the_object_reference(path: str, seed: int, years: int) -> None:
    scenario = Scenario.from_yaml(ROOT / path).with_overrides(seed=seed, n_years=years)
    table, reference = run_both(scenario, years)
    assert_same_simulation(table, reference)
    assert len(table.state.units) > 5


@settings(max_examples=5, deadline=None)
@given(st.integers(0, 10_000), st.booleans())
def test_synthetic_states_equal_the_object_reference(seed: int, farming: bool) -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    sims = []
    for mode in (True, False):
        sim = synthetic_simulator(scenario, 70, farming=farming, unit_table=mode)
        for _ in range(12):
            sim.step()
        sims.append(sim)
    assert_same_simulation(*sims)
