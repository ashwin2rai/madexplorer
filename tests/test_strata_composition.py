"""MVP 3 Stage 2: passive heterogeneous strata and their composition rules.

Fusion inheritance, differentiated fission, the zero-stock rule, capacity coalescence, the
controlled-fixture API and the sidecar stream. Strata stay passive: the MVP 2.1 oracles and
golden fixtures (and the record-on/off comparison here) check that nothing reads them.
"""

import copy
import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.mobility.migration import Relocation
from madexplorer.population.composition import MergeMode
from madexplorer.population.familiarity import familiarity_rule
from madexplorer.population.lifecycle import merge_units, split_unit
from madexplorer.population.strata import (
    S_MAX,
    STRATUM_COLUMNS,
    UNASSIGNED,
    Compaction,
    StrataBlock,
    StrataTable,
    coalesce_to_capacity,
    compact_exact_strata,
    fuse_strata,
    has_exact_duplicates,
    normalize_strata,
    positions,
)
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, step_context
from tests.test_unit_table import assert_same_simulation, unit_state

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"


def block(
    share: list[float], field: list[float], store: list[float], ids: list[int] | None = None
) -> StrataBlock:
    """A strata block from plain lists (ids default to 0, 1, ...)."""
    return StrataBlock(
        {
            "share": np.array(share, dtype=float),
            "field_claim": np.array(field, dtype=float),
            "store_claim": np.array(store, dtype=float),
        },
        np.array(ids if ids is not None else range(len(share)), dtype=np.int64),
    )


def counter(start: int = 1000):  # type: ignore[no-untyped-def]
    """A deterministic stratum-id allocator for pure-function tests."""
    state = [start]

    def new_ids(n: int) -> np.ndarray:
        ids = np.arange(state[0], state[0] + n, dtype=np.int64)
        state[0] += n
        return ids

    return new_ids


def state_multiset(strata: StrataBlock) -> list[tuple[float, ...]]:
    """Scientific state of the components, independent of storage order and ids."""
    return sorted(zip(*(strata.columns[n].tolist() for n in STRATUM_COLUMNS), strict=True))


NEUTRAL = block([1.0], [1.0], [1.0])


# ---------------------------------------------------------------- fusion inheritance


def test_equal_population_unequal_land_gives_unequal_field_positions() -> None:
    # A: 50 people, 10 ha; B: 50 people, 2 ha; both one neutral stratum.
    fused = fuse_strata([(NEUTRAL, 50, [10.0, 0.0]), (block([1], [1], [1], [7]), 50, [2.0, 0.0])])
    assert fused.columns["share"].tolist() == [0.5, 0.5]
    assert fused.columns["field_claim"].tolist() == [10 / 12, 2 / 12]
    assert positions(fused)[:, 0].tolist() == pytest.approx([20 / 12, 4 / 12])
    assert fused.columns["store_claim"].tolist() == [0.5, 0.5]  # no stores: neutral
    assert fused.stratum_id.tolist() == [0, 7]  # predecessor components keep their identity


def test_unequal_population_equal_land_and_independent_stores() -> None:
    fused = fuse_strata([(NEUTRAL, 75, [4.0, 1e5]), (NEUTRAL, 25, [4.0, 3e5])])
    assert fused.columns["share"].tolist() == [0.75, 0.25]
    assert fused.columns["field_claim"].tolist() == [0.5, 0.5]
    assert fused.columns["store_claim"].tolist() == [0.25, 0.75]
    field, store = positions(fused).T
    assert field[1] > 1 and store[1] > 1 and field[0] < 1 and store[0] < 1


@pytest.mark.parametrize(
    ("fields", "expected"),
    [((0.0, 5.0), [0.0, 1.0]), ((5.0, 0.0), [1.0, 0.0]), ((0.0, 0.0), [0.6, 0.4])],
)
def test_zero_fields_on_one_or_both_sides(
    fields: tuple[float, float], expected: list[float]
) -> None:
    fused = fuse_strata([(NEUTRAL, 60, [fields[0], 1.0]), (NEUTRAL, 40, [fields[1], 1.0])])
    assert fused.columns["field_claim"].tolist() == expected  # both zero: population shares


@pytest.mark.parametrize(
    ("stores", "expected"),
    [((0.0, 9.0), [0.0, 1.0]), ((0.0, 0.0), [0.6, 0.4])],
)
def test_zero_stores_on_one_or_both_sides(
    stores: tuple[float, float], expected: list[float]
) -> None:
    fused = fuse_strata([(NEUTRAL, 60, [1.0, stores[0]]), (NEUTRAL, 40, [1.0, stores[1]])])
    assert fused.columns["store_claim"].tolist() == expected


def test_multiple_strata_on_both_sides_keep_absolute_positions() -> None:
    a = block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2], [1, 2])
    b = block([0.5, 0.5], [0.9, 0.1], [0.3, 0.7], [3, 4])
    fused = fuse_strata([(a, 100, [10.0, 400.0]), (b, 50, [30.0, 100.0])])
    people = np.array([80, 20, 25, 25]) / 150
    fields = np.array([5.0, 5.0, 27.0, 3.0]) / 40
    stores = np.array([320.0, 80.0, 30.0, 70.0]) / 500
    assert fused.columns["share"] == pytest.approx(people, rel=1e-15)
    assert fused.columns["field_claim"] == pytest.approx(fields, rel=1e-15)
    assert fused.columns["store_claim"] == pytest.approx(stores, rel=1e-15)
    assert fused.stratum_id.tolist() == [1, 2, 3, 4]
    fused_absolute = fused.columns["field_claim"] * 40
    assert fused_absolute == pytest.approx([5, 5, 27, 3])  # nobody's hectares changed


def test_a_predecessor_without_people_contributes_no_strata() -> None:
    fused = fuse_strata([(NEUTRAL, 30, [2.0, 0.0]), (block([1], [1], [1], [5]), 0, [3.0, 0.0])])
    assert len(fused) == 1 and fused.columns["field_claim"].tolist() == [1.0]


# ---------------------------------------------------------------- capacity coalescence


def spread(n: int, offset: float = 0.0) -> StrataBlock:
    """``n`` equal-share strata with distinct, well separated positions."""
    share = np.full(n, 1.0 / n)
    field = np.arange(1, n + 1, dtype=float) + offset
    store = np.arange(n, 0, -1, dtype=float) ** 2 + offset
    return StrataBlock(
        {"share": share, "field_claim": field / field.sum(), "store_claim": store / store.sum()},
        np.arange(n, dtype=np.int64),
    )


def test_exactly_capacity_is_not_coalesced() -> None:
    strata, records = coalesce_to_capacity(spread(S_MAX), counter())
    assert records == [] and len(strata) == S_MAX


def test_one_over_capacity_coalesces_once_and_conserves_totals() -> None:
    source = spread(S_MAX + 1)
    strata, records = coalesce_to_capacity(source, counter())
    assert len(records) == 1 and len(strata) == S_MAX
    for name in STRATUM_COLUMNS:
        assert strata.columns[name].sum() == pytest.approx(source.columns[name].sum(), abs=1e-15)
    assert records[0].new_id == 1000 and strata.stratum_id[-1] == 1000
    assert set(records[0].merged_ids).isdisjoint(strata.stratum_id.tolist())


def test_the_closest_pair_in_position_space_is_coalesced() -> None:
    source = spread(S_MAX + 1)
    for name in ("field_claim", "store_claim"):  # stratum 7 moves next to stratum 3
        values = source.columns[name]
        values[7] = values[3] * 1.001
    for name in ("field_claim", "store_claim"):
        source.columns[name] /= source.columns[name].sum()
    _, records = coalesce_to_capacity(source, counter())
    assert set(records[0].merged_ids) == {3, 7}


def test_merged_component_sits_at_the_population_weighted_centroid() -> None:
    source = spread(S_MAX + 1)
    strata, records = coalesce_to_capacity(source, counter())
    i, j = records[0].merged_ids
    merged = positions(strata)[-1]
    w = source.columns["share"][[i, j]]
    expected = (positions(source)[[i, j]] * w[:, None]).sum(axis=0) / w.sum()
    assert merged == pytest.approx(expected, rel=1e-12)


def test_cross_cutting_positions_coalesce_by_distance_not_by_one_rank_axis() -> None:
    # Positions (field, store): A (2.0, 0.5) and B (0.5, 2.0) cross-cut; C (2.0, 0.6) is close
    # to A in both dimensions, though a single wealth rank (field + store) would put C next
    # to B (2.6 vs 2.5) rather than A (2.5).
    s = 1.0 / (S_MAX + 1)
    field = [2.0, 0.5, 2.0] + [1.0] * (S_MAX - 2)
    store = [0.5, 2.0, 0.6] + [1.0 + 0.3 * k for k in range(S_MAX - 2)]
    share = np.full(S_MAX + 1, s)
    source = StrataBlock(
        {
            "share": share,
            "field_claim": np.array(field) * share / (np.array(field) * share).sum(),
            "store_claim": np.array(store) * share / (np.array(store) * share).sum(),
        },
        np.arange(S_MAX + 1, dtype=np.int64),
    )
    _, records = coalesce_to_capacity(source, counter())
    assert set(records[0].merged_ids) == {0, 2}


def test_coalescence_is_independent_of_storage_order_and_ids() -> None:
    source = spread(S_MAX + 3)
    reference, _ = coalesce_to_capacity(source, counter())
    rng = np.random.default_rng(0)
    for _ in range(5):
        order = rng.permutation(len(source))
        shuffled = StrataBlock(
            {n: v[order].copy() for n, v in source.columns.items()},
            (10**6 - source.stratum_id[order]).astype(np.int64),  # renumbered too
        )
        result, _ = coalesce_to_capacity(shuffled, counter())
        assert state_multiset(result) == state_multiset(reference)  # exact


def test_identical_candidates_give_a_deterministic_state_multiset() -> None:
    twins = block([0.1] * 10, [0.1] * 10, [0.1] * 10)  # every pair costs 0
    result, records = coalesce_to_capacity(twins, counter())
    assert len(records) == 2 and state_multiset(result) == sorted(
        [(0.1, 0.1, 0.1)] * 6 + [(0.2, 0.2, 0.2)] * 2
    )


def test_fusion_beyond_capacity_coalesces_to_capacity() -> None:
    fused = fuse_strata([(spread(5), 40, [3.0, 10.0]), (spread(4, 0.5), 60, [1.0, 30.0])])
    assert len(fused) == 9
    strata, records = coalesce_to_capacity(fused, counter())
    assert len(strata) == S_MAX and len(records) == 1
    for name in STRATUM_COLUMNS:
        assert abs(strata.columns[name].sum() - 1.0) <= 1e-12


# ---------------------------------------------------------------- controlled fixtures


UNEQUAL_FIELDS = block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2])  # minority: 4x field position
UNEQUAL_STORES = block([0.6, 0.4], [0.6, 0.4], [0.3, 0.7])  # stores diverge, fields don't
CROSS_CUTTING = block([0.5, 0.5], [0.7, 0.3], [0.2, 0.8])  # one leads on fields, one on stores


def _sims(**kwargs: object) -> list[Simulator]:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=5)
    return [
        synthetic_simulator(scenario, 6, unit_table=table, **kwargs)  # type: ignore[arg-type]
        for table in (True, False)
    ]


@pytest.mark.parametrize("fixture", [UNEQUAL_FIELDS, UNEQUAL_STORES, CROSS_CUTTING])
def test_fixtures_install_with_fresh_ids_on_both_engines(fixture: StrataBlock) -> None:
    for sim in _sims():
        unit = next(iter(sim.state.units.values()))
        sim.state.population.replace_strata(unit, fixture)
        strata = unit.strata
        for name in STRATUM_COLUMNS:
            assert strata.columns[name].tolist() == fixture.columns[name].tolist()
        assert UNASSIGNED not in strata.stratum_id.tolist()
        assert set(strata.stratum_id.tolist()).isdisjoint(fixture.stratum_id.tolist())
    field, store = positions(CROSS_CUTTING).T
    assert field[0] > field[1] and store[1] > store[0]  # no single rank axis


@pytest.mark.parametrize(
    "bad",
    [
        block([0.5, 0.5, 0.0], [0.5, 0.5, 0.0], [0.5, 0.5, 0.0]),  # zero share
        block([0.5, 0.6], [0.5, 0.5], [0.5, 0.5]),  # not normalized
        block([0.5, 0.5], [np.nan, 0.5], [0.5, 0.5]),  # NaN
        block([0.5, 0.5], [1.5, -0.5], [0.5, 0.5]),  # negative claim
        spread(S_MAX + 1),  # over capacity without coalescence
    ],
)
def test_invalid_fixtures_are_refused_before_anything_changes(bad: StrataBlock) -> None:
    for sim in _sims():
        unit = next(iter(sim.state.units.values()))
        before = repr(unit_state(unit))
        next_id = sim.state.population._next_stratum_id
        with pytest.raises(ValueError):
            sim.state.population.replace_strata(unit, bad)
        assert repr(unit_state(unit)) == before
        assert sim.state.population._next_stratum_id == next_id


def test_over_capacity_fixture_can_ask_for_coalescence() -> None:
    sim = _sims()[0]
    unit = next(iter(sim.state.units.values()))
    sim.state.population.replace_strata(unit, spread(S_MAX + 2), coalesce=True)
    assert len(unit.strata) == S_MAX


# ---------------------------------------------------------------- lifecycle on both engines


def _rule(sim: Simulator):  # type: ignore[no-untyped-def]
    return familiarity_rule(
        next(iter(sim.scenario.species.values())), sim.scenario.config.mechanisms
    )


def _same_engines(a: Simulator, b: Simulator) -> None:
    """Complete unit state, strata values and ids included (beliefs compared logically)."""
    assert_same_simulation(a, b)


def test_heterogeneous_fusion_agrees_between_table_and_object_engines() -> None:
    sims = _sims()
    for sim in sims:
        units = list(sim.state.units.values())
        units[1].cell = units[0].cell
        units[0].fields_ha, units[1].fields_ha = 12.0, 3.0
        units[0].stores_kcal, units[1].stores_kcal = 0.0, 5e5
        sim.state.population.replace_strata(units[0], spread(5))
        sim.state.population.replace_strata(units[1], CROSS_CUTTING)
        merge_units(sim.state.population, units[1].id, units[0].id, MergeMode.FUSION, 1, _rule(sim))
        strata = units[0].strata
        assert len(strata) == 7 and strata.is_valid()
        absolute = strata.columns["field_claim"] * 15.0  # 12 + 3 ha after fusion
        assert absolute[:5] == pytest.approx(spread(5).columns["field_claim"] * 12.0)
        assert absolute[5:] == pytest.approx(CROSS_CUTTING.columns["field_claim"] * 3.0)
        assert strata.columns["store_claim"][:5].tolist() == [0.0] * 5  # no stores of its own
    _same_engines(*sims)


def test_fusion_beyond_capacity_agrees_between_engines() -> None:
    sims = _sims()
    for sim in sims:
        units = list(sim.state.units.values())
        units[1].cell = units[0].cell
        units[0].fields_ha, units[1].fields_ha = 4.0, 6.0
        sim.state.population.replace_strata(units[0], spread(6))
        sim.state.population.replace_strata(units[1], spread(5, 0.3))
        merge_units(sim.state.population, units[1].id, units[0].id, MergeMode.FUSION, 1, _rule(sim))
        assert len(units[0].strata) == S_MAX and units[0].strata.is_valid()
    _same_engines(*sims)


def test_differentiated_fission_is_a_representative_copy() -> None:
    sims = _sims(group_size=60)
    for sim in sims:
        parent = next(iter(sim.state.units.values()))
        sim.state.population.replace_strata(parent, CROSS_CUTTING)
        parent_ids = parent.strata.stratum_id.tolist()
        daughter = split_unit(
            sim.state.population,
            parent.id,
            parent.females // 3,
            parent.males // 3,
            "d1",
            1,
            _rule(sim),
        )
        for name in STRATUM_COLUMNS:
            assert parent.strata.columns[name].tolist() == CROSS_CUTTING.columns[name].tolist()
            assert daughter.strata.columns[name].tolist() == CROSS_CUTTING.columns[name].tolist()
        assert parent.strata.stratum_id.tolist() == parent_ids
        assert set(daughter.strata.stratum_id.tolist()).isdisjoint(parent_ids)
        assert set(sim.ids._counters) == {"u"}
    _same_engines(*sims)


@pytest.mark.parametrize("stock", ["fields_ha", "stores_kcal"])
def test_an_empty_stock_resets_its_claims_to_population_shares(stock: str) -> None:
    claim = {"fields_ha": "field_claim", "stores_kcal": "store_claim"}[stock]
    for sim in _sims():
        unit = next(iter(sim.state.units.values()))
        setattr(unit, stock, 5.0)
        sim.state.population.replace_strata(unit, CROSS_CUTTING)
        sim.state.population.settle_empty_claims(1)  # positive stock: claims persist
        assert unit.strata.columns[claim].tolist() == CROSS_CUTTING.columns[claim].tolist()
        setattr(unit, stock, 0.0)
        sim.state.population.settle_empty_claims(1)
        assert unit.strata.columns[claim].tolist() == unit.strata.columns["share"].tolist()
        setattr(unit, stock, 8.0)  # the stock reappears: it starts from the neutral split
        sim.state.population.settle_empty_claims(1)
        assert unit.strata.columns[claim].tolist() == unit.strata.columns["share"].tolist()
        assert np.isfinite(positions(unit.strata)).all()


def test_migration_carries_composition_and_empties_field_claims() -> None:
    for sim in _sims():
        unit = next(iter(sim.state.units.values()))
        unit.fields_ha, unit.stores_kcal = 7.0, 9e5
        sim.state.population.replace_strata(unit, CROSS_CUTTING)
        ctx = step_context(sim)
        Relocation(unit.id, unit.cell, unit.cell + 1, 10.0, 100.0, 0.5, 4e5).apply(sim.state, ctx)
        sim.state.population.settle_empty_claims(1)
        strata = unit.strata
        assert strata.columns["share"].tolist() == [0.5, 0.5]  # composition travels
        assert strata.columns["field_claim"].tolist() == [0.5, 0.5]  # fields abandoned
        assert strata.columns["store_claim"].tolist() == [0.2, 0.8]  # stores shrink only


# ---------------------------------------------------------------- whole runs and the sidecar


def _run(unit_table: bool, record: bool) -> Simulator:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=3)
    sim = synthetic_simulator(scenario, 60, farming=True, unit_table=unit_table)
    if record:
        sim.record_strata = True
        sim.state.population.strata_log = []
    return sim


def test_engines_agree_on_heterogeneous_strata_through_ordinary_steps() -> None:
    a, b = _run(True, True), _run(False, True)
    differentiated = 0
    for _ in range(25):
        a.step()
        b.step()
        differentiated += sum(len(u.strata) > 1 for u in a.state.units.values())
    assert differentiated > 0
    _same_engines(a, b)
    assert a.state.population.strata_log == b.state.population.strata_log


def test_reordering_strata_storage_leaves_the_simulation_unchanged() -> None:
    a, b = _run(True, False), _run(True, False)
    for _ in range(12):
        a.step()
        b.step()
    strata = b.state.population.strata
    assert strata is not None
    permuted = 0
    for slot in b.state.units.slots().tolist():
        n = int(strata.n_strata[slot])
        if n > 1:
            order = np.arange(n)[::-1]
            for values in (*strata.columns.values(), strata.stratum_id):
                values[slot, :n] = values[slot, order]
            permuted += 1
    assert permuted > 0
    for _ in range(12):
        a.step()
        b.step()
    for uid in a.state.units:
        ua, ub = a.state.units[uid], b.state.units[uid]
        sa, sb = unit_state(ua), unit_state(ub)
        sa.pop("strata"), sb.pop("strata")
        assert repr(sa) == repr(sb), uid  # unit-level state: bit-identical
        ma, mb = state_multiset(ua.strata), state_multiset(ub.strata)
        assert len(ma) == len(mb)
        assert np.allclose(ma, mb, rtol=1e-12, atol=1e-15), uid  # strata: float tolerance
        for name in STRATUM_COLUMNS:
            assert abs(ua.strata.columns[name].sum() - ub.strata.columns[name].sum()) <= 1e-12


def test_sidecar_is_opt_in_and_does_not_change_the_simulation(tmp_path: Path) -> None:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=0, n_years=120)
    plain = Simulator(scenario).run()
    recorded = Simulator(scenario, record_strata=True).run()
    assert plain.strata_rows == [] and plain.strata_events == []
    assert repr(recorded.metrics) == repr(plain.metrics)  # NaN-safe, exact
    assert [e.to_record() for e in recorded.events] == [e.to_record() for e in plain.events]
    row = recorded.strata_rows[-1]
    assert list(row) == [
        "year",
        "unit_id",
        "stratum_id",
        "share",
        "field_claim",
        "store_claim",
        "relative_field_position",
        "relative_store_position",
    ]
    keys = [(r["year"], r["unit_id"], r["stratum_id"]) for r in recorded.strata_rows]
    assert len(keys) == len(set(keys))
    kinds = {e["event"] for e in recorded.strata_events}
    assert kinds <= {
        "fusion_inheritance",
        "exact_compaction",
        "capacity_coalescence",
        "fission_copy",
    }
    plain.save(tmp_path / "plain")
    recorded.save(tmp_path / "recorded")
    assert not (tmp_path / "plain" / "strata.csv").exists()
    assert (tmp_path / "recorded" / "strata.csv").exists()
    lines = (tmp_path / "recorded" / "strata_events.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == recorded.strata_events


def test_copies_of_heterogeneous_state_are_independent() -> None:
    sim = _sims()[0]
    unit = next(iter(sim.state.units.values()))
    sim.state.population.replace_strata(unit, UNEQUAL_FIELDS)
    state = copy.deepcopy(sim.state)
    clone = state.units[unit.id]
    state.population.replace_strata(clone, CROSS_CUTTING)
    assert unit.strata.columns["field_claim"].tolist() == [0.5, 0.5]
    assert isinstance(clone, PopulationUnit) and clone.strata.columns["store_claim"].tolist() == [
        0.2,
        0.8,
    ]


def test_all_column_orders_of_a_fusion_give_the_same_state() -> None:
    a = block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2], [1, 2])
    b = block([0.25, 0.25, 0.5], [0.2, 0.3, 0.5], [0.6, 0.3, 0.1], [3, 4, 5])
    reference = state_multiset(fuse_strata([(a, 90, [8.0, 50.0]), (b, 30, [2.0, 70.0])]))
    for order in itertools.permutations(range(3)):
        idx = np.array(order)
        permuted = StrataBlock({n: v[idx] for n, v in b.columns.items()}, b.stratum_id[idx])
        result = state_multiset(fuse_strata([(a, 90, [8.0, 50.0]), (permuted, 30, [2.0, 70.0])]))
        assert np.allclose(result, reference, rtol=1e-15, atol=0)


# ---------------------------------------------------------------- exact compaction (Stage 2.1)


def test_same_position_with_different_masses_compacts_to_one_component() -> None:
    # A and B: field position 1.0, store position 0.5; C differs.
    source = block([0.2, 0.4, 0.4], [0.2, 0.4, 0.4], [0.1, 0.2, 0.7], [1, 2, 3])
    compacted, records = compact_exact_strata(source, counter())
    assert len(compacted) == 2 and len(records) == 1
    assert sorted(records[0].merged_ids) == [1, 2] and records[0].new_id == 1000
    assert records[0].position == (1.0, 0.5)
    merged = compacted.stratum_id.tolist().index(1000)
    assert positions(compacted)[merged] == pytest.approx([1.0, 0.5], rel=1e-15)
    for name in STRATUM_COLUMNS:
        assert compacted.columns[name].sum() == pytest.approx(source.columns[name].sum(), abs=1e-15)


@pytest.mark.parametrize(
    "source",
    [
        block([0.25, 0.25, 0.5], [0.25, 0.25, 0.5], [0.125, 0.375, 0.5]),  # same field position
        block([0.25, 0.25, 0.5], [0.125, 0.375, 0.5], [0.25, 0.25, 0.5]),  # same store position
    ],
)
def test_sharing_one_coordinate_is_not_a_duplicate(source: StrataBlock) -> None:
    compacted, records = compact_exact_strata(source, counter())
    assert compacted is source and records == []


def test_near_but_not_exact_positions_stay_separate() -> None:
    # Stage 4 boundary: the second store position is one ulp above the first.
    store_b = np.nextafter(0.25, 1.0)
    source = StrataBlock(
        {
            "share": np.array([0.25, 0.25, 0.5]),
            "field_claim": np.array([0.25, 0.25, 0.5]),
            "store_claim": np.array([0.25, store_b, 1.0 - 0.25 - store_b]),
        },
        np.array([0, 1, 2], dtype=np.int64),
    )
    assert positions(source)[0, 1] != positions(source)[1, 1]
    compacted, records = compact_exact_strata(source, counter())
    assert records == [] and len(compacted) == 3


def dyadic_duplicates() -> StrataBlock:
    """Ten components with six distinct positions (exact binary fractions)."""
    share = np.array([2, 1, 1, 2, 1, 1, 2, 2, 2, 2], dtype=float) / 16
    field_position = np.array([1, 1, 2, 2, 0.5, 0.5, 0.5, 1.5, 1.25, 0.25])
    store_position = np.array([1, 1, 0.5, 0.5, 2, 2, 2, 0.5, 1.5, 0.75])
    field, store = share * field_position, share * store_position
    return StrataBlock(
        {"share": share, "field_claim": field / field.sum(), "store_claim": store / store.sum()},
        np.arange(10, dtype=np.int64),
    )


def test_compaction_is_independent_of_storage_order_and_ids() -> None:
    source = dyadic_duplicates()
    reference, _ = compact_exact_strata(source, counter())
    assert len(reference) == 6
    rng = np.random.default_rng(1)
    for _ in range(10):
        order = rng.permutation(len(source))
        shuffled = StrataBlock(
            {n: v[order].copy() for n, v in source.columns.items()},
            (77 + 3 * source.stratum_id[order]).astype(np.int64),
        )
        result, _ = compact_exact_strata(shuffled, counter())
        assert state_multiset(result) == state_multiset(reference)  # exact


def test_exact_compaction_avoids_unneeded_capacity_coalescence() -> None:
    source = dyadic_duplicates()  # 10 components > S_MAX, but only 6 distinct positions
    normalized, records = normalize_strata(source, counter())
    assert len(normalized) == 6
    assert records and all(isinstance(r, Compaction) for r in records)
    assert not has_exact_duplicates(normalized)


def test_capacity_coalescence_still_finishes_when_compaction_is_not_enough() -> None:
    distinct = spread(S_MAX + 2)  # 10 distinct positions
    doubled = StrataBlock(  # plus two exact duplicates of the first component: 12 in all
        {
            n: np.concatenate([v[:1] / 3, v[:1] / 3, v[:1] / 3, v[1:]])
            for n, v in distinct.columns.items()
        },
        np.arange(12, dtype=np.int64),
    )
    normalized, records = normalize_strata(doubled, counter())
    kinds = [type(r).__name__ for r in records]
    assert kinds[0] == "Compaction" and kinds.count("Coalescence") == 2
    assert len(normalized) == S_MAX and not has_exact_duplicates(normalized)
    for name in STRATUM_COLUMNS:
        assert abs(normalized.columns[name].sum() - 1.0) <= 1e-12


def test_a_lineage_refusing_with_itself_compacts_instead_of_coalescing() -> None:
    # A differentiated unit fused with a representative copy of itself (fission then
    # fusion): with stocks per head equal on both sides (exact binary values), every
    # position appears twice, and exact compaction restores the original components.
    lineage = dyadic_duplicates()
    lineage, _ = compact_exact_strata(lineage, counter())  # six distinct positions
    copy_ids = StrataBlock(
        {n: v.copy() for n, v in lineage.columns.items()}, lineage.stratum_id + 100
    )
    fused = fuse_strata([(lineage, 32, [8.0, 4.0]), (copy_ids, 32, [8.0, 4.0])])
    assert len(fused) == 12 > S_MAX
    normalized, records = normalize_strata(fused, counter())
    assert all(isinstance(r, Compaction) for r in records) and len(records) == 6
    # Fusion renormalizes claims by the fused totals, so values agree to the last bits.
    assert np.allclose(state_multiset(normalized), state_multiset(lineage), rtol=1e-15, atol=0)


def test_parent_and_daughter_fusion_is_normalized_on_both_engines() -> None:
    sims = _sims(group_size=64)
    for sim in sims:
        sim.record_strata = True
        sim.state.population.strata_log = []
        parent = next(iter(sim.state.units.values()))
        parent.fields_ha, parent.stores_kcal = 0.0, 0.0  # no stock: claims fall back to shares
        sim.state.population.replace_strata(parent, spread(S_MAX // 2 + 1))
        daughter = split_unit(
            sim.state.population,
            parent.id,
            parent.females // 2,
            parent.males // 2,
            "d",
            1,
            _rule(sim),
        )
        merge_units(sim.state.population, daughter.id, parent.id, MergeMode.FUSION, 1, _rule(sim))
        log = sim.state.population.strata_log
        assert log is not None
        kinds = [e["event"] for e in log if e["event"] != "fission_copy"]
        assert "capacity_coalescence" not in kinds and "exact_compaction" in kinds
        assert len(parent.strata) == 1 and parent.strata.is_valid()  # one position: (1, 1)
    _same_engines(*sims)


@pytest.mark.parametrize("stock", ["fields_ha", "stores_kcal"])
def test_an_emptied_stock_can_make_components_identical_and_they_compact(stock: str) -> None:
    # Two components differ only in the claim on `stock`; once it is empty, they coincide.
    other = {"fields_ha": "store_claim", "stores_kcal": "field_claim"}[stock]
    fixture = block([0.5, 0.5], [0.5, 0.5], [0.5, 0.5])
    fixture.columns[{"fields_ha": "field_claim", "stores_kcal": "store_claim"}[stock]] = np.array(
        [0.75, 0.25]
    )
    fixture.columns[other] = np.array([0.5, 0.5])
    sims = _sims()
    for sim in sims:
        unit = next(iter(sim.state.units.values()))
        unit.fields_ha, unit.stores_kcal = 3.0, 3.0
        sim.state.population.replace_strata(unit, fixture)
        assert len(unit.strata) == 2
        setattr(unit, stock, 0.0)
        sim.state.population.settle_empty_claims(1)
        assert len(unit.strata) == 1 and unit.strata.is_valid()
    _same_engines(*sims)


def test_the_invariant_check_rejects_exact_duplicates() -> None:
    table = StrataTable()
    table.load(0, block([0.25, 0.75], [0.25, 0.75], [0.25, 0.75]))  # both at (1, 1)
    assert not table.check(np.array([0])).any()
    assert not block([0.25, 0.75], [0.25, 0.75], [0.25, 0.75]).is_valid()
