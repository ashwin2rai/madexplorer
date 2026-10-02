"""PH3b lifecycle: row-level create / split / move / merge / remove against the reference.

Random operation sequences run on a table-mode simulator and on the object-authoritative
reference engine with identical choices. After every operation the complete unit state and
processing order must agree; freed rows must be reset (no stale cohorts, technology bits,
knowledge, scalars or beliefs) and reused; afterwards ordinary simulation steps from the
two states must stay identical.
"""

import copy
from dataclasses import fields

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.rng import Streams
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.composition import MergeMode
from madexplorer.population.familiarity import familiarity_rule
from madexplorer.population.fields import TABLE_FIELDS
from madexplorer.population.groups import Fission, FissionSubsystem
from madexplorer.population.lifecycle import create_unit, merge_units, remove_unit, split_unit
from madexplorer.population.store import PopulationStore
from madexplorer.population.unit import (
    EXTERNAL_FIELDS,
    PopulationUnit,
    belief_slot,
)
from tests.conftest import ROOT, step_context
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
    population = sim.state.population
    registry, table, store = population.units, population.table, population.beliefs
    assert table is not None
    technologies = sim.compiled.technologies if sim.compiled else None
    assert technologies is not None
    slots = registry.slots()
    assert len(set(slots.tolist())) == len(registry) == store.active
    assert table.check_population(slots).all()
    for unit, slot in zip(registry.values(), slots.tolist(), strict=True):
        assert belief_slot(unit) == slot
        assert table.technology_mask[slot] == technologies.mask(unit.technologies)
    for slot in population._free:  # released rows are reset: nothing can leak into a reuse
        assert all(not array[slot] for array in table.columns.values())
        assert not table.females[slot].any() and not table.males[slot].any()
        assert table.population[slot] == 0 and table.n_ages[slot] == 0
        assert not table.knowledge[slot].any()
        assert table.technologies[slot] == frozenset() and table.technology_mask[slot] == 0
        assert store.entries(slot)[0].size == 0  # no belief survives into a reuse


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
        before_free = set(a.state.population._free)
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
                    sim.state.population, uid, leave_f.copy(), leave_m.copy(), f"s{k}", year, rule
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
                merge_units(sim.state.population, source, target, mode, year, rule)
        elif op == "remove" and len(ids) > 4:
            uid = ids[rng.integers(len(ids))]
            for sim in (a, b):
                remove_unit(sim.state.population, uid)
        elif op == "create":
            template = a.state.units[ids[rng.integers(len(ids))]]
            ua, ub = _new_unit(template, f"c{k}", rng, techs)
            create_unit(a.state.population, ua)
            create_unit(b.state.population, ub)
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
    merge_units(sim.state.population, ids[1], ids[0], MergeMode.FUSION, sim.state.year, rule)
    assert ids[1] not in sim.state.units and source.id == ids[1]
    with pytest.raises(AttributeError, match="removed"):
        _ = source.food_ratio


def _same_unit(a: PopulationUnit, b: PopulationUnit) -> None:
    sa, sb = unit_state(a), unit_state(b)
    for key, value in sa.items():
        assert _same(value, sb[key]), key


def test_detach_and_rebind_round_trips_unit_state_between_stores() -> None:
    scenario = Scenario.from_yaml(SCENARIO)
    sim = synthetic_simulator(scenario, 6, belief_backend="dense")
    for _ in range(2):
        sim.step()
    uid = list(sim.state.units)[2]
    before = copy.deepcopy(sim.state.units[uid])
    slot = belief_slot(sim.state.units[uid])
    unit = sim.state.units.pop(uid)  # state copied back onto the object, slot freed
    assert belief_slot(unit) == -1
    _same_unit(unit, before)
    assert slot in sim.state.population._free
    _assert_rows_consistent(sim)
    other = PopulationStore(
        sim.world.n_cells,
        belief_backend="dense",
        technology_table=sim.compiled.technologies,
        species_index=sim.compiled.species_index,
    )
    other.units[uid] = unit  # bound to the other store's rows
    assert unit.__dict__["_table"] is other.table
    _same_unit(unit, before)
    other.units.pop(uid)  # a unit leaves one store before joining another
    sim.state.units[uid] = unit  # rebound to the freed slot (last freed, first reused)
    assert belief_slot(unit) == slot
    _same_unit(unit, before)
    _assert_rows_consistent(sim)


def test_deepcopy_gives_an_independent_consistently_bound_state() -> None:
    scenario = Scenario.from_yaml(SCENARIO)
    sim = synthetic_simulator(scenario, 8, farming=True)
    sim.step()
    state = copy.deepcopy(sim.state)
    population = state.population
    assert population is not sim.state.population
    for uid, unit in state.units.items():
        assert unit.__dict__["_table"] is population.table
        assert unit.__dict__["_belief_store"] is population.beliefs
        assert belief_slot(unit) == belief_slot(sim.state.units[uid])
        _same_unit(unit, sim.state.units[uid])
    uid = next(iter(state.units))
    original = sim.state.units[uid].stores_kcal
    state.units[uid].stores_kcal = original + 1e6
    del state.units[list(state.units)[-1]]
    state.units[uid] = state.units.pop(uid)  # rebinding within the copy
    assert sim.state.units[uid].stores_kcal == original
    assert state.units[uid].stores_kcal == original + 1e6
    assert len(sim.state.units) == 8 and len(state.units) == 7
    _assert_rows_consistent(sim)
    sim.step()  # the original runs on, unaffected


def test_population_views_cannot_be_rebound() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 3)
    with pytest.raises(AttributeError):
        sim.state.units = {}  # type: ignore[misc, assignment]
    with pytest.raises(AttributeError):
        sim.state.table = None  # type: ignore[misc]


def test_fission_apply_is_deterministic_and_draws_nothing() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 4, group_size=60)
    ctx = step_context(sim)
    uid = next(iter(sim.state.units))
    parent = sim.state.units[uid]
    leave_f, leave_m = parent.females // 2, parent.males // 2
    before_f, before_m = parent.females, parent.males
    stream = ctx.rng.stream(Streams.FISSION)
    drawn = copy.deepcopy(stream.bit_generator.state)
    Fission(uid, leave_f, leave_m, 0.5, {}).apply(sim.state, ctx)
    assert stream.bit_generator.state == drawn
    daughter = list(sim.state.units.values())[-1]
    assert daughter.parent_id == uid
    assert (daughter.females == leave_f).all() and (daughter.males == leave_m).all()
    assert (parent.females == before_f - leave_f).all()
    assert (parent.males == before_m - leave_m).all()


def test_fission_proposals_carry_the_departing_cohorts() -> None:
    data = Scenario.from_yaml(SCENARIO).with_settings(
        {"species.human.social.fission_baseline_logit": 50.0}  # every group splits
    )
    sim = synthetic_simulator(data, 5, group_size=40)
    proposals = FissionSubsystem().evaluate(sim.state, step_context(sim))
    assert len(proposals) == 5
    for proposal in proposals:
        parent = sim.state.units[proposal.parent_id]
        assert (proposal.leave_f <= parent.females).all()
        assert (proposal.leave_m <= parent.males).all()
