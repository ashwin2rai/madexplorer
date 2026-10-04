"""MVP 3 strata representation (Stages 1-2; passive, MVP 2.1 behavior unchanged).

The MVP 2.1 golden fixtures and exactness oracles are the scientific-neutrality test; these
tests cover the representation itself: initialization, conservation, ownership, fission,
fusion, removal and slot reuse, copying and id neutrality. Composition rules (inheritance,
capacity coalescence, zero stock) are in ``tests/test_strata_composition.py``.
"""

import copy

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.composition import MergeMode
from madexplorer.population.familiarity import familiarity_rule
from madexplorer.population.fields import UNIT_FIELDS, Storage
from madexplorer.population.lifecycle import create_unit, merge_units, remove_unit, split_unit
from madexplorer.population.store import PopulationStore
from madexplorer.population.strata import (
    DEFAULT_MAX_STRATA,
    STRATUM_COLUMNS,
    UNASSIGNED,
    StrataBlock,
    StrataTable,
)
from madexplorer.population.unit import PopulationUnit, belief_slot
from tests.conftest import ROOT
from tests.test_unit_table import unit_state

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"


def _live_strata(population: PopulationStore) -> list[int]:
    """Check every structural invariant of a table-mode store; return the live stratum ids."""
    strata = population.strata
    assert strata is not None
    slots = population.units.slots()
    assert strata.check(slots).all()
    for unit, slot in zip(population.units.values(), slots.tolist(), strict=True):
        assert unit.__dict__["_strata"] is strata and belief_slot(unit) == slot
    live = set(slots.tolist())
    for slot in range(strata.capacity):  # no active strata outside live unit rows
        if slot not in live:
            assert strata.n_strata[slot] == 0
            assert (strata.stratum_id[slot] == UNASSIGNED).all()
            assert all(not strata.columns[name][slot].any() for name in STRATUM_COLUMNS)
    ids: list[int] = strata.stratum_id[slots][strata.stratum_id[slots] != UNASSIGNED].tolist()
    assert len(ids) == len(set(ids)) == int(strata.n_strata[slots].sum())  # unique in the store
    return ids


def _farming_sim(unit_table: bool = True) -> Simulator:
    """A crowded farming state: fission, fusion and extinction all happen within years."""
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=3)
    return synthetic_simulator(scenario, 60, farming=True, unit_table=unit_table)


def test_stratum_columns_have_their_own_schema() -> None:
    unit_fields = {f.name for f in UNIT_FIELDS}
    assert not unit_fields & set(STRATUM_COLUMNS)  # not flattened into the unit fields
    (strata,) = [f for f in UNIT_FIELDS if f.storage is Storage.STRATA]
    assert strata.name == "strata" and DEFAULT_MAX_STRATA == 16


def test_every_new_unit_has_one_neutral_stratum_with_a_store_id() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 12)
    ids = _live_strata(sim.state.population)
    assert all(i >= 0 for i in ids)
    detached = StrataBlock.neutral()
    assert detached.is_neutral() and detached.stratum_id.tolist() == [UNASSIGNED]


@pytest.mark.parametrize("unit_table", [True, False])
def test_strata_stay_valid_and_conserved_through_fission_and_fusion(
    unit_table: bool,
) -> None:
    sim = _farming_sim(unit_table)
    fissions = fusions = 0
    for _ in range(25):
        ctx = sim.step()
        fissions += ctx.ledger.fissions
        fusions += ctx.ledger.fusions
        if unit_table:
            _live_strata(sim.state.population)
        else:
            for unit in sim.state.units.values():
                assert unit.strata.is_valid() and (unit.strata.stratum_id >= 0).all()
    assert fissions > 0 and fusions > 0  # both lifecycle paths were exercised


def test_strata_use_no_unit_ids() -> None:
    sim = _farming_sim()
    for _ in range(30):
        sim.step()
    assert set(sim.ids._counters) == {"u"}  # unit ids come from the allocator alone


def test_fission_copies_strata_as_new_components() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 4, group_size=40)
    population = sim.state.population
    parent = next(iter(sim.state.units.values()))
    parent_id = parent.strata.stratum_id.tolist()
    rule = familiarity_rule(
        next(iter(sim.scenario.species.values())), sim.scenario.config.mechanisms
    )
    daughter = split_unit(
        population, parent.id, parent.females // 2, parent.males // 2, "d", sim.state.year, rule
    )
    assert parent.strata.stratum_id.tolist() == parent_id  # the parent's component persists
    assert daughter.strata.is_neutral()
    assert daughter.strata.stratum_id.tolist() != parent_id  # a new component
    _live_strata(population)


def test_fusing_two_neutral_units_keeps_both_as_inherited_components() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 4)
    population = sim.state.population
    target, source = list(sim.state.units.values())[:2]
    source.cell = target.cell
    target.fields_ha, source.fields_ha = 6.0, 2.0
    ids = target.strata.stratum_id.tolist() + source.strata.stratum_id.tolist()
    n_t, n_s = target.population, source.population
    s = belief_slot(source)
    rule = familiarity_rule(
        next(iter(sim.scenario.species.values())), sim.scenario.config.mechanisms
    )
    merge_units(population, source.id, target.id, MergeMode.FUSION, sim.state.year, rule)
    strata = target.strata
    assert strata.stratum_id.tolist() == ids  # both predecessor components persist
    assert strata.columns["share"].tolist() == [n_t / (n_t + n_s), n_s / (n_t + n_s)]
    assert strata.columns["field_claim"].tolist() == [0.75, 0.25]
    assert population.strata is not None and population.strata.n_strata[s] == 0
    _live_strata(population)


def test_removal_resets_strata_and_a_reused_slot_starts_fresh() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 6)
    population = sim.state.population
    strata = population.strata
    assert strata is not None
    template = next(iter(sim.state.units.values()))
    victim = list(sim.state.units.values())[3]
    slot, old_id = belief_slot(victim), int(victim.strata.stratum_id[0])
    strata.columns["share"][slot, 1] = 0.25  # stale junk that must not survive
    strata.stratum_id[slot, 1] = 999
    remove_unit(population, victim.id)
    assert strata.n_strata[slot] == 0 and (strata.stratum_id[slot] == UNASSIGNED).all()
    assert all(not strata.columns[name][slot].any() for name in STRATUM_COLUMNS)
    with pytest.raises(AttributeError, match="removed"):
        _ = victim.strata
    newcomer = PopulationUnit(
        id="newcomer",
        species_id=template.species_id,
        cell=template.cell,
        females=template.females,
        males=template.males,
        reserve_kcal_per_capita=1e4,
        founded_year=sim.state.year,
        knowledge=template.knowledge,
    )
    create_unit(population, newcomer)
    assert belief_slot(newcomer) == slot  # the only free slot is reused
    assert newcomer.strata.is_neutral() and int(newcomer.strata.stratum_id[0]) != old_id
    _live_strata(population)


def test_deepcopied_strata_are_independent() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(SCENARIO), 5)
    sim.step()
    state = copy.deepcopy(sim.state)
    copied, original = state.population.strata, sim.state.population.strata
    assert copied is not None and original is not None and copied is not original
    unit = next(iter(state.units.values()))
    assert unit.__dict__["_strata"] is copied
    before = repr(unit_state(sim.state.units[unit.id]))
    copied.columns["store_claim"][belief_slot(unit), 0] = 0.5
    assert repr(unit_state(sim.state.units[unit.id])) == before
    state.population.new_stratum_ids(10)
    assert sim.state.population.new_stratum_ids(1)[0] < state.population.new_stratum_ids(1)[0]


def test_renumbering_stratum_ids_does_not_change_the_simulation() -> None:
    sims = [_farming_sim(), _farming_sim()]
    for _ in range(10):
        for sim in sims:
            sim.step()
    strata = sims[1].state.population.strata
    assert strata is not None
    active = strata.stratum_id != UNASSIGNED
    strata.stratum_id[active] = 10**9 - strata.stratum_id[active]  # reverse the numbering
    sims[1].state.population._next_stratum_id = 2 * 10**9
    rows: list[list[tuple[int, int, int]]] = [[], []]
    for _ in range(15):
        for k, sim in enumerate(sims):
            ctx = sim.step()
            rows[k].append((sim.state.total_population(), ctx.ledger.births, ctx.ledger.fissions))
    assert rows[0] == rows[1]
    a, b = (sim.state.units for sim in sims)
    assert list(a) == list(b)
    differentiated = 0
    for uid in a:
        sa, sb = unit_state(a[uid]), unit_state(b[uid])
        strata_a, strata_b = sa.pop("strata"), sb.pop("strata")
        assert isinstance(strata_a, tuple) and isinstance(strata_b, tuple)
        assert repr(sa) == repr(sb) and repr(strata_a[0]) == repr(strata_b[0]), uid
        differentiated += len(a[uid].strata) > 1
    assert differentiated > 0  # renumbering acted on heterogeneous strata


def test_strata_table_round_trips_and_detects_broken_partitions() -> None:
    table = StrataTable()
    block = StrataBlock(
        {
            "share": np.array([0.7, 0.3]),
            "field_claim": np.array([0.9, 0.1]),
            "store_claim": np.array([0.5, 0.5]),
        },
        np.array([4, 9], dtype=np.int64),
    )
    table.load(70, block)  # grows to cover the slot
    assert table.capacity > 70 and table.n_strata[70] == 2
    back = table.unload(70)
    assert back.stratum_id.tolist() == [4, 9]
    assert all(np.array_equal(back.columns[n], block.columns[n]) for n in STRATUM_COLUMNS)
    assert table.check(np.array([70])).all() and block.is_valid() and not block.is_neutral()
    table.columns["field_claim"][70, 1] = 0.2  # no longer sums to 1
    assert not table.check(np.array([70])).any()
    table.copy_row(70, 3, np.array([11, 12], dtype=np.int64))
    assert table.stratum_id[3, :2].tolist() == [11, 12]
    table.reset(70)
    assert table.n_strata[70] == 0 and not table.check(np.array([70])).any()
    over = DEFAULT_MAX_STRATA + 1
    with pytest.raises(ValueError):
        table.load(0, StrataBlock({n: np.ones(over) / over for n in STRATUM_COLUMNS},
                                  np.arange(over)))  # fmt: skip
