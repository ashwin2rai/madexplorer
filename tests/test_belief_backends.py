"""PH4b: the sparse belief store against the dense reference (Level A, logical equality).

The sparse store physically drops expired entries, which are semantically invisible
(``tests/test_belief_expiry.py``); everything else must be identical: trajectories,
events, every RNG stream and each unit's current beliefs.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.beliefs import (
    DenseBeliefStore,
    SparseBeliefStore,
    make_belief_store,
    resolve_backend,
)
from madexplorer.population.unit import NEVER_OBSERVED, BeliefMap
from tests.conftest import ROOT
from tests.test_belief_expiry import assert_logically_equal
from tests.test_unit_table import current_beliefs


def _pair(scenario: Scenario, **kwargs: object) -> tuple[Simulator, Simulator]:
    return (
        Simulator(scenario, belief_backend="dense", **kwargs),  # type: ignore[arg-type]
        Simulator(scenario, belief_backend="sparse", **kwargs),  # type: ignore[arg-type]
    )


def _step_both(a: Simulator, b: Simulator, years: int) -> None:
    for _ in range(years):
        assert vars(a.step().ledger) == vars(b.step().ledger)


@pytest.mark.parametrize(
    ("path", "seed", "years"),
    [
        ("scenarios/mvp2_neolithic.yaml", 0, 320),
        ("scenarios/mvp2_pressure.yaml", 1, 220),
        ("scenarios/mvp1_sandbox.yaml", 2, 160),
    ],
)
def test_sparse_engine_equals_dense(path: str, seed: int, years: int) -> None:
    scenario = Scenario.from_yaml(ROOT / path).with_overrides(seed=seed, n_years=years)
    dense, sparse = _pair(scenario)
    assert sparse.state.belief_store.kind == "sparse"
    _step_both(dense, sparse, years)
    assert_logically_equal(dense, sparse)
    kinds = {e.kind for e in dense.events}
    assert {"population_split", "population_merge"} <= kinds
    store = sparse.state.belief_store
    assert isinstance(store, SparseBeliefStore)
    # Stored entries stay within a small multiple of the current ones (pruning works).
    current = sum(len(v) for v in current_beliefs(sparse).values())
    assert store.stored_entries <= 3 * current + 64 * len(sparse.state.units)


def test_sparse_reference_engine_equals_dense() -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_pressure.yaml").with_overrides(
        seed=4, n_years=150
    )
    dense, sparse = _pair(scenario, unit_table=False)  # object-authoritative paths
    _step_both(dense, sparse, 150)
    assert_logically_equal(dense, sparse)


@settings(max_examples=4, deadline=None)
@given(st.integers(0, 10_000), st.booleans())
def test_sparse_synthetic_dense_states_equal_dense(seed: int, farming: bool) -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    a = synthetic_simulator(scenario, 250, farming=farming)
    b = synthetic_simulator(scenario, 250, farming=farming, belief_backend="sparse")
    _step_both(a, b, 30)
    assert_logically_equal(a, b)


def test_backend_resolution_is_static() -> None:
    assert resolve_backend("dense", 10**6) == "dense"
    assert resolve_backend("sparse", 4) == "sparse"
    assert resolve_backend("auto", 4) == "dense"
    assert resolve_backend("auto", 10**6) == "sparse"
    with pytest.raises(ValueError):
        resolve_backend("hash", 100)
    assert isinstance(make_belief_store("sparse", 9), SparseBeliefStore)
    assert isinstance(make_belief_store("dense", 9), DenseBeliefStore)


def test_sparse_view_is_read_only_and_patches_write_through_the_store() -> None:
    store = SparseBeliefStore.empty(16)
    store.claim(0)
    store.scatter(np.array([0]), np.array([3]), 5, np.array([2.0]), np.array([1]), 0)
    view = store.view(0)
    assert view[3].year == 5 and 4 not in view
    with pytest.raises(ValueError):
        view.year[3] = 9


def _logical(
    store: DenseBeliefStore | SparseBeliefStore, slot: int, horizon: int
) -> list[tuple[int, int, float, int, int]]:
    cells, year, food, population, hops = store.entries(slot)
    keep = year > horizon
    return list(
        zip(
            cells[keep].tolist(),
            year[keep].tolist(),
            food[keep].tolist(),
            population[keep].tolist(),
            hops[keep].tolist(),
            strict=True,
        )
    )


@settings(max_examples=60, deadline=None)
@given(st.integers(0, 2**32 - 1))
def test_random_store_operations_equal_dense(seed: int) -> None:
    """claim / release / write / read / copy / merge / assign with an advancing clock:
    observe, expire, get deleted, revisit; a tiny pool forces growth and compaction."""
    rng = np.random.default_rng(seed)
    n_cells, memory = int(rng.integers(20, 400)), int(rng.integers(2, 12))
    dense, sparse = DenseBeliefStore.empty(n_cells, 4), SparseBeliefStore(n_cells, 4, pool=16)
    for store in (dense, sparse):
        store.configure_expiry(np.array([memory]))
    live: list[int] = []
    free: list[int] = []
    next_slot = 0
    year = 0
    for _ in range(300):
        year += int(rng.integers(0, 3))
        for store in (dense, sparse):
            store.set_clock(year)
        horizon = year - memory
        op = rng.choice(["claim", "release", "write", "write", "write", "copy", "merge", "assign"])
        if op == "claim" or not live:
            slot = free.pop() if free else next_slot
            next_slot += slot == next_slot
            for store in (dense, sparse):
                store.claim(slot)
            live.append(slot)
        elif op == "release" and len(live) > 1:
            slot = live.pop(int(rng.integers(len(live))))
            for store in (dense, sparse):
                store.release(slot)
            free.append(slot)
        elif op == "write":
            k = int(rng.integers(1, 60))
            slots = rng.choice(live, k)
            cells = rng.integers(0, n_cells, k)
            pairs = np.unique(np.stack([slots, cells]), axis=1)  # distinct pairs
            slots, cells = pairs[0], pairs[1]
            k = slots.size
            # Observations of this year or older (relayed reports), some already stale.
            years = (year - rng.integers(0, memory + 3, k)).astype(np.int32)
            food = rng.lognormal(10, 2, k).astype(np.float32)
            population = rng.integers(0, 500, k).astype(np.int32)
            hops = rng.integers(0, 6, k).astype(np.int8)
            for store in (dense, sparse):
                store.scatter(slots, cells, years, food, population, hops)
        elif op == "copy" and free:
            source = live[int(rng.integers(len(live)))]
            target = free.pop()
            for store in (dense, sparse):
                store.claim(target)
                store.copy_row(source, target)
            live.append(target)
        elif op == "merge" and len(live) > 1:
            i, j = rng.choice(len(live), 2, replace=False)
            for store in (dense, sparse):
                store.merge_row(live[i], live[j])
        elif op == "assign":
            slot = live[int(rng.integers(len(live)))]
            beliefs = BeliefMap.empty(n_cells)
            cells = rng.integers(0, n_cells, 10)
            beliefs.write(cells, year, np.full(10, 7.0), np.full(10, 3), 1)
            for store in (dense, sparse):
                store.assign(slot, beliefs)
        for slot in live:  # logical rows agree, and reads agree on current entries
            assert _logical(dense, slot, horizon) == _logical(sparse, slot, horizon)
        slots = np.repeat(np.array(live), 5)
        cells = rng.integers(0, n_cells, slots.size)
        got, want = sparse.gather(slots, cells), dense.gather(slots, cells)
        current = want[0] > horizon
        fields: list[tuple[np.ndarray, np.ndarray]] = list(zip(got, want, strict=True))
        for g, w in fields:
            assert np.array_equal(g[current], w[current])
        assert (got[0][~current] <= horizon).all()  # absent or expired, never current
        assert np.array_equal(sparse.years(slots, cells) > horizon, current)
        _, h = sparse.years_and_hops(slots, cells)
        assert np.array_equal(h[current], want[3][current])
    assert sparse.compactions + sparse.resizes > 0
    assert (dense.year[live] != NEVER_OBSERVED).sum() >= sparse.stored_entries
