"""PH3b lifecycle: row-level create / split / move / merge / remove against the reference.

Random operation sequences run on a table-mode simulator and on the object-authoritative
reference engine with identical choices. After every operation the complete unit state and
processing order must agree; freed rows must be reset (no stale cohorts, technology bits,
knowledge, scalars or beliefs) and reused; afterwards ordinary simulation steps from the
two states must stay identical.
"""

from dataclasses import fields

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.core.state import UnitRegistry
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.composition import MergeMode
from madexplorer.population.familiarity import familiarity_rule
from madexplorer.population.lifecycle import create_unit, merge_units, remove_unit, split_unit
from madexplorer.population.table import TABLE_FIELDS
from madexplorer.population.unit import (
    EXTERNAL_FIELDS,
    NEVER_OBSERVED,
    PopulationUnit,
    belief_slot,
)
from tests.conftest import ROOT
from tests.test_unit_table import _same, assert_same_simulation, unit_state

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"


def test_external_fields_complete_the_table_fields() -> None:
    names = {f.name for f in fields(PopulationUnit)}
    assert set(EXTERNAL_FIELDS) == names - set(TABLE_FIELDS) - {"beliefs"}


def _assert_same_units(a: Simulator, b: Simulator) -> None:
    assert list(a.state.units) == list(b.state.units)
    for uid in a.state.units:
        sa, sb = unit_state(a.state.units[uid]), unit_state(b.state.units[uid])
        for key, value in sa.items():
            assert _same(value, sb[key]), (uid, key)


def _assert_rows_consistent(sim: Simulator) -> None:
    registry = sim.state.units
    assert isinstance(registry, UnitRegistry)
    table, store = registry.table, registry.store
    assert table is not None and store is not None
    technologies = sim.compiled.technologies if sim.compiled else None
    assert technologies is not None
    slots = registry.slots()
    assert len(set(slots.tolist())) == len(registry) == store.active
    assert table.check_population(slots).all()
    for unit, slot in zip(registry.values(), slots.tolist(), strict=True):
        assert belief_slot(unit) == slot
        assert table.technology_mask[slot] == technologies.mask(unit.technologies)
    for slot in registry._free:  # released rows are reset: nothing can leak into a reuse
        assert all(not array[slot] for array in table.columns.values())
        assert not table.females[slot].any() and not table.males[slot].any()
        assert table.population[slot] == 0 and table.n_ages[slot] == 0
        assert not table.knowledge[slot].any()
        assert table.technologies[slot] == frozenset() and table.technology_mask[slot] == 0
        assert (store.year[slot] == NEVER_OBSERVED).all() and not store.hops[slot].any()


def _new_unit(
    template: PopulationUnit, uid: str, rng: np.random.Generator, techs: list[str]
) -> tuple[PopulationUnit, PopulationUnit]:
    """Two identical detached units (one per engine) with random state."""
    females = rng.integers(0, 4, size=template.females.size)
    males = rng.integers(0, 4, size=template.males.size)
    knowledge = rng.uniform(0, 3, size=template.knowledge.size)
    chosen = frozenset(t for t in techs if rng.random() < 0.5)
    cell = template.cell
    reserve, stores = float(rng.uniform(0, 1e5)), float(rng.uniform(0, 1e6))

    def build() -> PopulationUnit:
        return PopulationUnit(
            id=uid,
            species_id=template.species_id,
            cell=cell,
            females=females.copy(),
            males=males.copy(),
            reserve_kcal_per_capita=reserve,
            founded_year=0,
            knowledge=knowledge.copy(),
            technologies=chosen,
            stores_kcal=stores,
            fields_ha=1.5,
            ever_cultivated=bool(chosen),
        )

    return build(), build()


def _random_operations(a: Simulator, b: Simulator, seed: int, n_ops: int) -> int:
    """Apply the same random lifecycle operations to both; returns reused slots."""
    rng = np.random.default_rng(seed)
    species = next(iter(a.scenario.species))
    rule = familiarity_rule(a.scenario.species[species], a.scenario.config.mechanisms)
    techs = list(a.compiled.technologies.ids) if a.compiled and a.compiled.technologies else []
    year = a.state.year
    reused = 0
    for k in range(n_ops):
        ids = list(a.state.units)
        op = rng.choice(["split", "move", "merge", "remove", "create", "retech"])
        before_free = set(a.state.units._free)  # type: ignore[attr-defined]
        if op == "split":
            uid = ids[rng.integers(len(ids))]
            unit = a.state.units[uid]
            leave_f = rng.binomial(unit.females, 0.4)
            leave_m = rng.binomial(unit.males, 0.4)
            moved = int(leave_f.sum() + leave_m.sum())
            if not 0 < moved < unit.population:
                continue
            for sim in (a, b):
                split_unit(
                    sim.state.units, uid, leave_f.copy(), leave_m.copy(), f"s{k}", year, rule
                )
        elif op == "move" and len(ids) > 1:
            uid, other = (ids[i] for i in rng.choice(len(ids), 2, replace=False))
            for sim in (a, b):
                sim.state.units[uid].cell = sim.state.units[other].cell
        elif op == "merge":
            by_cell: dict[int, list[str]] = {}
            for uid, unit in a.state.units.items():
                by_cell.setdefault(unit.cell, []).append(uid)
            pairs = [ids_ for ids_ in by_cell.values() if len(ids_) > 1]
            if not pairs:
                continue
            group = pairs[rng.integers(len(pairs))]
            source, target = (group[i] for i in rng.choice(len(group), 2, replace=False))
            mode = MergeMode.FUSION if rng.random() < 0.5 else MergeMode.AGGREGATION
            for sim in (a, b):
                merge_units(sim.state.units, source, target, mode, year, rule)
        elif op == "remove" and len(ids) > 4:
            uid = ids[rng.integers(len(ids))]
            for sim in (a, b):
                remove_unit(sim.state.units, uid)
        elif op == "create":
            template = a.state.units[ids[rng.integers(len(ids))]]
            ua, ub = _new_unit(template, f"c{k}", rng, techs)
            create_unit(a.state.units, ua)
            create_unit(b.state.units, ub)
        elif op == "retech" and techs:
            uid = ids[rng.integers(len(ids))]
            chosen = frozenset(t for t in techs if rng.random() < 0.5)
            for sim in (a, b):
                sim.state.units[uid].technologies = chosen
        added = set(a.state.units) - set(ids)
        reused += sum(belief_slot(a.state.units[u]) in before_free for u in added)
        _assert_same_units(a, b)
        _assert_rows_consistent(a)
    return reused


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000), st.booleans())
def test_random_lifecycle_equals_the_object_reference(seed: int, farming: bool) -> None:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=seed)
    sims = [synthetic_simulator(scenario, 24, farming=farming, unit_table=m) for m in (True, False)]
    for _ in range(3):  # fill beliefs, familiarity, ties and harvest history
        for sim in sims:
            sim.step()
    a, b = sims
    reused = _random_operations(a, b, seed, 80)
    assert reused > 0  # slot reuse was exercised
    for _ in range(4):  # ordinary ticks from the operated-on states
        a.step()
        b.step()
    assert_same_simulation(a, b)
    _assert_rows_consistent(a)


def test_removed_unit_keeps_only_external_state() -> None:
    scenario = Scenario.from_yaml(SCENARIO)
    sim = synthetic_simulator(scenario, 6)
    ids = list(sim.state.units)
    sim.state.units[ids[1]].cell = sim.state.units[ids[0]].cell
    source = sim.state.units[ids[1]]
    rule = familiarity_rule(next(iter(scenario.species.values())), scenario.config.mechanisms)
    merge_units(sim.state.units, ids[1], ids[0], MergeMode.FUSION, sim.state.year, rule)
    assert ids[1] not in sim.state.units and source.id == ids[1]
    with pytest.raises(AttributeError, match="removed"):
        _ = source.food_ratio
