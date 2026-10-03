"""MVP 3 Stage 4B: strata resolution hardening (representation engineering only).

Configurable capacity (``strata.max_strata``) owned by the population store and its padded
table, the bounded exact-duplicate check, the vectorized capacity coalescence (checked
against the scalar reference it replaced) and the per-dimension representation-error
diagnostics. No socioeconomic semantics change: at the default capacity the Stage 3B/3C
fixtures and the MVP 2.1 oracles are unchanged.
"""

import copy
import tracemalloc

import numpy as np
import pytest
from pydantic import ValidationError

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.core.static import static_key
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.strata import (
    DEFAULT_MAX_STRATA,
    DUPLICATE_CHUNK_ROWS,
    STRATUM_COLUMNS,
    Coalescence,
    StrataBlock,
    StrataTable,
    coalesce_to_capacity,
    coalesce_to_capacity_reference,
    has_exact_duplicates,
    normalize_strata,
    positions,
)
from tests.conftest import ROOT
from tests.test_strata_composition import block, counter, spread
from tests.test_unit_table import assert_same_simulation

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"
CAPACITIES = (1, 8, 16, 32)


def _scenario(max_strata: int, seed: int = 4) -> Scenario:
    base = Scenario.from_yaml(SCENARIO).with_overrides(seed=seed)
    if max_strata == DEFAULT_MAX_STRATA:
        return base
    return base.with_settings({"strata.max_strata": max_strata})


# ---------------------------------------------------------------- configuration


def test_capacity_is_a_validated_run_setting_outside_the_static_key() -> None:
    scenario = Scenario.from_yaml(SCENARIO)
    assert scenario.config.strata.max_strata == DEFAULT_MAX_STRATA == 8
    for bad in (0, 128):
        with pytest.raises(ValidationError):
            scenario.with_settings({"strata.max_strata": bad})
    wider = scenario.with_settings({"strata.max_strata": 16})
    assert wider.config_hash() != scenario.config_hash()  # recorded in provenance
    assert static_key(wider) == static_key(scenario)  # the world/static cache is shared
    sim = Simulator(wider)
    population = sim.state.population
    assert population.max_strata == 16
    assert population.strata is not None and population.strata.max_strata == 16
    assert population.strata.columns["share"].shape[1] == 16


@pytest.mark.parametrize("bad", [0, 128])
def test_a_table_refuses_capacities_its_int8_count_cannot_hold(bad: int) -> None:
    with pytest.raises(ValueError, match="max_strata"):
        StrataTable(bad)


# ---------------------------------------------------------------- construction, lifecycle


@pytest.mark.parametrize("capacity", CAPACITIES)
def test_stores_of_any_capacity_start_neutral_with_fixed_width_rows(capacity: int) -> None:
    sim = synthetic_simulator(_scenario(capacity), 5)
    strata = sim.state.population.strata
    assert strata is not None and strata.max_strata == capacity
    for name in STRATUM_COLUMNS:
        assert strata.columns[name].shape == (strata.capacity, capacity)
    assert strata.stratum_id.shape == (strata.capacity, capacity)
    assert strata.nbytes == strata.capacity * (32 * capacity + 1)  # 3 x f64 + i64, + i8 count
    for unit in sim.state.units.values():
        assert unit.strata.is_neutral() and unit.strata.is_valid(capacity)
    assert strata.check(sim.state.units.slots()).all()


def _differentiated(capacity: int, table: bool, n: int) -> Simulator:
    """Six farming units; the first holds ``n`` distinct positions (n <= capacity)."""
    sim = synthetic_simulator(_scenario(capacity), 6, farming=True, unit_table=table)
    sim.state.population.strata_log, sim.state.population.strata_flows = [], []
    unit = next(iter(sim.state.units.values()))
    unit.fields_ha, unit.stores_kcal = 5.0, 2e5
    sim.state.population.replace_strata(unit, spread(n))
    return sim


@pytest.mark.parametrize(("capacity", "n"), [(16, 12), (32, 20), (1, 1)])
def test_engines_agree_at_non_default_capacities(capacity: int, n: int) -> None:
    sims = [_differentiated(capacity, table, n) for table in (True, False)]
    assert len(next(iter(sims[0].state.units.values())).strata) == n
    for _ in range(25):  # fission, fusion, removal, slot reuse, accounting
        for sim in sims:
            sim.step()
    assert_same_simulation(*sims)
    assert sims[0].state.population.strata_log == sims[1].state.population.strata_log
    for unit in sims[0].state.units.values():
        assert 1 <= len(unit.strata) <= capacity and unit.strata.is_valid(capacity)
    population = sims[0].state.population
    copied = copy.deepcopy(population)  # the copy keeps the capacity and its rows
    assert copied.max_strata == capacity
    assert copied.strata is not None and copied.strata.max_strata == capacity
    for (uid, unit), (cid, twin) in zip(
        population.units.items(), copied.units.items(), strict=True
    ):
        assert uid == cid
        assert unit.strata.stratum_id.tolist() == twin.strata.stratum_id.tolist()
        for name in STRATUM_COLUMNS:
            assert unit.strata.columns[name].tolist() == twin.strata.columns[name].tolist()


def test_more_distinct_positions_than_capacity_are_refused_unless_coalesced() -> None:
    sim = synthetic_simulator(_scenario(16), 3)
    unit = next(iter(sim.state.units.values()))
    with pytest.raises(ValueError, match="max_strata = 16"):
        sim.state.population.replace_strata(unit, spread(17))
    sim.state.population.replace_strata(unit, spread(17), coalesce=True)
    assert len(unit.strata) == 16


@pytest.mark.parametrize("capacity", [16, 32])
def test_capacity_threshold(capacity: int) -> None:
    at, at_records = normalize_strata(spread(capacity), counter(), capacity)
    assert len(at) == capacity and at_records == []  # exactly capacity: lossless
    over, over_records = normalize_strata(spread(capacity + 3), counter(), capacity)
    assert len(over) == capacity
    assert [type(r) for r in over_records] == [Coalescence] * 3  # exactly enough merges
    for name in STRATUM_COLUMNS:
        assert over.columns[name].sum() == pytest.approx(1.0, abs=1e-12)


def test_exact_duplicates_compact_before_any_capacity_coalescence() -> None:
    twins = spread(10)
    doubled = StrataBlock(
        {k: np.concatenate([v, v]) / 2 for k, v in twins.columns.items()}, np.arange(20)
    )  # 20 components, 10 distinct positions
    normalized, records = normalize_strata(doubled, counter(), 16)
    assert len(normalized) == 10 and not any(isinstance(r, Coalescence) for r in records)


# ---------------------------------------------------------------- optimized coalescence


def _cases(capacity: int) -> list[StrataBlock]:
    """Deterministic over-capacity blocks covering the cases the greedy rule must agree on."""
    rng = np.random.default_rng(capacity)  # explicit, test-stable seed
    cases = []
    for n in (capacity + 1, capacity + 3, 2 * capacity):
        cases.append(_from_parts(rng.dirichlet(np.ones(n)), rng.dirichlet(np.ones(n)),
                                 rng.dirichlet(np.ones(n))))  # fmt: skip
        share = np.full(n, 1.0 / n)  # exact ties: every pair at the same distance
        ring = np.where(np.arange(n) % 2 == 0, 1.0, 2.0)
        cases.append(_from_parts(share, share * ring, share * ring[::-1]))
        cross = np.linspace(0.5, 2.0, n)  # cross-cutting field and store positions
        cases.append(_from_parts(share, share * cross, share * cross[::-1]))
        dominant = np.full(n, 1e-3)
        dominant[0] = 1.0  # one dominant share, many small ones
        cases.append(_from_parts(dominant, rng.dirichlet(np.ones(n)), rng.dirichlet(np.ones(n))))
        tiny = np.full(n, 1e-12)
        tiny[: n // 2] = 1.0  # many tiny shares
        cases.append(_from_parts(tiny, rng.dirichlet(np.ones(n)), rng.dirichlet(np.ones(n))))
        near = share * (1.0 + np.nextafter(0.0, 1.0) * np.arange(n))  # one-ulp neighbors
        cases.append(_from_parts(share, near, share.copy()))
    return cases


def _from_parts(share: np.ndarray, field: np.ndarray, store: np.ndarray) -> StrataBlock:
    columns = {"share": share, "field_claim": field, "store_claim": store}
    return StrataBlock(
        {k: v / v.sum() for k, v in columns.items()}, np.arange(share.size, dtype=np.int64)
    )


@pytest.mark.parametrize("capacity", [8, 16, 32])
def test_vectorized_coalescence_is_bit_identical_to_the_reference(capacity: int) -> None:
    for case in _cases(capacity):
        for target in (capacity, max(capacity // 2, 1)):  # repeated coalescence too
            fast, fast_records = coalesce_to_capacity(case, counter(), target)
            slow, slow_records = coalesce_to_capacity_reference(case, counter(), target)
            assert fast_records == slow_records  # pairs, ids and every error, bit for bit
            assert fast.stratum_id.tolist() == slow.stratum_id.tolist()
            for name in STRATUM_COLUMNS:
                assert fast.columns[name].tolist() == slow.columns[name].tolist()


@pytest.mark.parametrize("capacity", [8, 16, 32])
def test_coalescence_ignores_storage_order_and_ids(capacity: int) -> None:
    def states(strata: StrataBlock) -> list[tuple[float, ...]]:
        return sorted(zip(*(strata.columns[n].tolist() for n in STRATUM_COLUMNS), strict=True))

    rng = np.random.default_rng(99)
    for case in _cases(capacity)[::3]:
        reference, _ = coalesce_to_capacity(case, counter(), capacity)
        for _ in range(3):
            order = rng.permutation(len(case))
            shuffled = StrataBlock(
                {k: v[order] for k, v in case.columns.items()},
                np.array(rng.permutation(10**6)[: len(case)], dtype=np.int64),
            )
            result, _ = coalesce_to_capacity(shuffled, counter(), capacity)
            assert states(result) == states(reference)


# ---------------------------------------------------------------- error accounting


def test_per_dimension_errors_of_a_hand_constructed_merge() -> None:
    # Positions (field, store): A = (2, 0.4), B = (2/3, 1.2); weight = 0.25 * 0.75 / 1.
    pair = block([0.25, 0.75], [0.5, 0.5], [0.1, 0.9])
    pos = positions(pair)
    weight = 0.25 * 0.75
    _, (record,) = coalesce_to_capacity(pair, counter(), 1)
    assert record.field_error == pytest.approx(weight * (pos[0, 0] - pos[1, 0]) ** 2, rel=1e-15)
    assert record.store_error == pytest.approx(weight * (pos[0, 1] - pos[1, 1]) ** 2, rel=1e-15)
    assert record.cost == pytest.approx(record.field_error + record.store_error, rel=1e-15)
    field_only = block([0.25, 0.75], [0.5, 0.5], [0.25, 0.75])  # equal store positions
    _, (only,) = coalesce_to_capacity(field_only, counter(), 1)
    assert only.store_error == 0.0 and only.field_error == only.cost == pytest.approx(1 / 3)


def test_coalescence_events_carry_errors_that_sum_consistently() -> None:
    scenario = _scenario(2, seed=0).with_overrides(n_years=260)
    result = Simulator(scenario, record_strata=True).run()
    events = [e for e in result.strata_events if e["event"] == "capacity_coalescence"]
    assert events  # capacity 2 forces lossy merges
    for e in events:
        assert e["combined_error"] == e["cost"]
        total = e["field_error"] + e["store_error"]
        assert e["combined_error"] == pytest.approx(total, rel=1e-12, abs=1e-300)
        assert e["field_error"] >= 0 and e["store_error"] >= 0
    combined = sum(e["combined_error"] for e in events)
    parts = sum(e["field_error"] + e["store_error"] for e in events)
    assert combined == pytest.approx(parts, rel=1e-12)


# ---------------------------------------------------------------- duplicate check


def _naive_duplicates(table: StrataTable, slots: np.ndarray) -> np.ndarray:
    out = []
    for slot in slots.tolist():
        out.append(has_exact_duplicates(table.unload(slot)) if table.n_strata[slot] else False)
    return np.array(out)


def _filled(width: int, rows: int) -> StrataTable:
    rng = np.random.default_rng(width)
    table = StrataTable(width)
    table.ensure(rows - 1)
    for r in range(rows):
        n = 1 if r % 4 == 0 else int(rng.integers(2, width + 1))
        b = _from_parts(rng.dirichlet(np.ones(n)), rng.dirichlet(np.ones(n)),
                        rng.dirichlet(np.ones(n))) if n > 1 else StrataBlock.neutral()  # fmt: skip
        if r % 7 == 0 and n > 2:  # an exact duplicate position (same share and claims)
            for name in STRATUM_COLUMNS:
                b.columns[name][1] = b.columns[name][0]
        table.load(r, StrataBlock(b.columns, np.arange(n, dtype=np.int64) + 100 * r))
    return table


@pytest.mark.parametrize("width", [3, 8, 32])
def test_chunked_duplicate_check_matches_the_pairwise_definition(width: int) -> None:
    rows = DUPLICATE_CHUNK_ROWS * 2 + 37  # several chunks
    table = _filled(width, rows)
    slots = np.arange(rows, dtype=np.int64)[::-1].copy()  # any order
    expected = _naive_duplicates(table, slots)
    assert expected.any() and not expected.all()
    assert table.duplicate_rows(slots).tolist() == expected.tolist()


def test_duplicate_check_temporaries_are_bounded() -> None:
    rows = 20_000
    table = _filled(32, rows)
    slots = np.arange(rows, dtype=np.int64)
    tracemalloc.start()
    table.check(slots)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # An unchunked [rows, 32, 32] comparison would hold tens of MB per temporary.
    assert peak < 8e6
