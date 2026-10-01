"""Compiled kernels of :class:`~madexplorer.population.beliefs.SparseBeliefStore` (PH4b).

A unit's beliefs are one row of the store: entries sorted by cell id in shared pool
arrays (``cell``, ``year``, ``food``, ``population``, ``hops``), the row being
``pool[start : start + length]`` within a reserved ``capacity``. Lookups are binary
searches; a missing cell reads as never observed (``NEVER_OBSERVED``, 0, 0, 0), exactly
what the dense store holds for it.

Expiry (``year <= horizon``, with ``horizon = clock - memory_years`` of the row's
species) is semantically invisible (``tests/test_belief_expiry.py``), so entries are
dropped wherever a row is rewritten anyway: when a full row must grow, when a row is
copied or merged, and when the pool is compacted. ``horizon = NO_HORIZON`` keeps every
entry.

Kernels that may need more pool space return the index where they stopped; the store
grows the pool and calls again from there (no allocation inside kernels).
"""

import numpy as np

from madexplorer.core.jit import kernel

NEVER_YEAR = -(2**31)  # NEVER_OBSERVED (population.unit)
NO_HORIZON = -(2**62)  # prune nothing
MIN_ROW_CAPACITY = 8


@kernel
def find(pool_cell: np.ndarray, start: int, length: int, cell: int) -> int:
    """Insertion point of ``cell`` in a sorted row (its index if present)."""
    lo = start
    hi = start + length
    while lo < hi:
        mid = (lo + hi) >> 1
        if pool_cell[mid] < cell:
            lo = mid + 1
        else:
            hi = mid
    return lo


@kernel
def lookup(
    row_start: np.ndarray,
    row_length: np.ndarray,
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
    slots: np.ndarray,
    cells: np.ndarray,
    out_year: np.ndarray,
    out_food: np.ndarray,
    out_population: np.ndarray,
    out_hops: np.ndarray,
    fields: int,  # 4 = all fields, 2 = year and hops, 1 = year only
) -> None:
    for i in range(slots.size):
        s = slots[i]
        start = row_start[s]
        length = row_length[s]
        cell = cells[i]
        j = find(pool_cell, start, length, cell)
        if j < start + length and pool_cell[j] == cell:
            out_year[i] = pool_year[j]
            if fields >= 2:
                out_hops[i] = pool_hops[j]
            if fields == 4:
                out_food[i] = pool_food[j]
                out_population[i] = pool_population[j]
        else:
            out_year[i] = NEVER_YEAR
            if fields >= 2:
                out_hops[i] = 0
            if fields == 4:
                out_food[i] = 0.0
                out_population[i] = 0


@kernel
def _prune_row(
    start: int,
    length: int,
    horizon: int,
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
) -> int:
    """Drop expired entries of a row in place (order kept); returns the new length."""
    k = start
    for m in range(start, start + length):
        if pool_year[m] > horizon:
            if k != m:
                pool_cell[k] = pool_cell[m]
                pool_year[k] = pool_year[m]
                pool_food[k] = pool_food[m]
                pool_population[k] = pool_population[m]
                pool_hops[k] = pool_hops[m]
            k += 1
    return k - start


@kernel
def scatter(
    row_start: np.ndarray,
    row_length: np.ndarray,
    row_capacity: np.ndarray,
    row_horizon: np.ndarray,  # per slot: expiry horizon (NO_HORIZON keeps everything)
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
    used: int,
    slots: np.ndarray,
    cells: np.ndarray,
    years: np.ndarray,
    food: np.ndarray,
    population: np.ndarray,
    hops: np.ndarray,
    first: int,
) -> tuple[int, int, int]:
    """Write entries ``first..``; returns ``(next index, used, garbage released)``.

    ``next index < slots.size`` means the pool is full: grow it and call again from there.
    """
    garbage = 0
    for i in range(first, slots.size):
        s = slots[i]
        cell = cells[i]
        start = row_start[s]
        length = row_length[s]
        j = find(pool_cell, start, length, cell)
        if j < start + length and pool_cell[j] == cell:
            pool_year[j] = years[i]
            pool_food[j] = food[i]
            pool_population[j] = population[i]
            pool_hops[j] = hops[i]
            continue
        if length == row_capacity[s]:  # full: drop expired entries first
            length = _prune_row(
                start,
                length,
                row_horizon[s],
                pool_cell,
                pool_year,
                pool_food,
                pool_population,
                pool_hops,
            )
            row_length[s] = length
            if length == row_capacity[s]:  # still full: move to a row twice as large
                capacity = max(2 * length, MIN_ROW_CAPACITY)
                if used + capacity > pool_cell.size:
                    return i, used, garbage
                for m in range(length):
                    pool_cell[used + m] = pool_cell[start + m]
                    pool_year[used + m] = pool_year[start + m]
                    pool_food[used + m] = pool_food[start + m]
                    pool_population[used + m] = pool_population[start + m]
                    pool_hops[used + m] = pool_hops[start + m]
                garbage += row_capacity[s]
                row_start[s] = used
                row_capacity[s] = capacity
                start = used
                used += capacity
            j = find(pool_cell, start, length, cell)
        for m in range(start + length, j, -1):  # open a gap at j
            pool_cell[m] = pool_cell[m - 1]
            pool_year[m] = pool_year[m - 1]
            pool_food[m] = pool_food[m - 1]
            pool_population[m] = pool_population[m - 1]
            pool_hops[m] = pool_hops[m - 1]
        pool_cell[j] = cell
        pool_year[j] = years[i]
        pool_food[j] = food[i]
        pool_population[j] = population[i]
        pool_hops[j] = hops[i]
        row_length[s] = length + 1
    return slots.size, used, garbage


@kernel
def copy_row(
    source: int,
    target: int,
    horizon: int,
    row_start: np.ndarray,
    row_length: np.ndarray,
    row_capacity: np.ndarray,
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
    used: int,
) -> int:
    """``target`` (empty) becomes a copy of ``source``'s current entries, placed at
    ``used`` (the caller reserved ``row_length[source]`` entries); returns the new used."""
    start = row_start[source]
    k = used
    for m in range(start, start + row_length[source]):
        if pool_year[m] > horizon:
            pool_cell[k] = pool_cell[m]
            pool_year[k] = pool_year[m]
            pool_food[k] = pool_food[m]
            pool_population[k] = pool_population[m]
            pool_hops[k] = pool_hops[m]
            k += 1
    row_start[target] = used
    row_length[target] = k - used
    capacity = max(row_length[source], MIN_ROW_CAPACITY)
    row_capacity[target] = capacity
    return int(used + capacity)


@kernel
def merge_rows(
    source: int,
    target: int,
    horizon: int,
    row_start: np.ndarray,
    row_length: np.ndarray,
    row_capacity: np.ndarray,
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
    used: int,
) -> int:
    """``target`` takes ``source``'s entry wherever it is better (fresher, or equally fresh
    with fewer relays), as ``DenseBeliefStore.merge_row``; current entries only. The merged
    row is written at ``used`` (the caller reserved both rows' lengths); returns new used."""
    a, na = row_start[target], row_length[target]
    b, nb = row_start[source], row_length[source]
    k = used
    i = a
    j = b
    while i < a + na or j < b + nb:
        if i == a + na:
            pick = j
            j += 1
        elif j == b + nb or pool_cell[i] < pool_cell[j]:
            pick = i
            i += 1
        elif pool_cell[j] < pool_cell[i]:
            pick = j
            j += 1
        else:  # same cell: the better entry wins
            better = (pool_year[j] > pool_year[i]) or (
                pool_year[j] == pool_year[i] and pool_hops[j] < pool_hops[i]
            )
            pick = j if better else i
            i += 1
            j += 1
        if pool_year[pick] > horizon:
            pool_cell[k] = pool_cell[pick]
            pool_year[k] = pool_year[pick]
            pool_food[k] = pool_food[pick]
            pool_population[k] = pool_population[pick]
            pool_hops[k] = pool_hops[pick]
            k += 1
    row_start[target] = used
    row_length[target] = k - used
    capacity = max(na + nb, MIN_ROW_CAPACITY)
    row_capacity[target] = capacity
    return int(used + capacity)


@kernel
def compact(
    slots: np.ndarray,  # active slots, any order
    row_horizon: np.ndarray,
    row_start: np.ndarray,
    row_length: np.ndarray,
    row_capacity: np.ndarray,
    pool_cell: np.ndarray,
    pool_year: np.ndarray,
    pool_food: np.ndarray,
    pool_population: np.ndarray,
    pool_hops: np.ndarray,
    new_cell: np.ndarray,
    new_year: np.ndarray,
    new_food: np.ndarray,
    new_population: np.ndarray,
    new_hops: np.ndarray,
) -> int:
    """Rewrite every active row contiguously into the new pool without expired entries,
    with ``capacity = length + length // 4`` (at least ``MIN_ROW_CAPACITY``); returns used.
    The caller sized the new pool from the current lengths (an upper bound)."""
    k = 0
    for t in range(slots.size):
        s = slots[t]
        start = row_start[s]
        horizon = row_horizon[s]
        begin = k
        for m in range(start, start + row_length[s]):
            if pool_year[m] > horizon:
                new_cell[k] = pool_cell[m]
                new_year[k] = pool_year[m]
                new_food[k] = pool_food[m]
                new_population[k] = pool_population[m]
                new_hops[k] = pool_hops[m]
                k += 1
        length = k - begin
        capacity = max(length + length // 4, MIN_ROW_CAPACITY)
        row_start[s] = begin
        row_length[s] = length
        row_capacity[s] = capacity
        k = begin + capacity
    return k
