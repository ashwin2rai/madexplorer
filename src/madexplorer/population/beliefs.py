"""Belief storage backends (performance layer; belief semantics live in ``unit.BeliefMap``).

Every unit's beliefs about every cell (observation year, perceived food, perceived
population, relay count) were four small arrays owned by the unit. :class:`DenseBeliefStore`
keeps the same fields, dtypes and sentinel as four global ``(capacity, cells)`` matrices,
one row per *storage slot*, so hot subsystems gather and scatter beliefs for all units in
one indexing operation instead of visiting thousands of separate arrays.

Slots are storage only and are allocated by the unit registry (shared with the unit
table). Processing order stays the registry's insertion order (``state.units``); a slot
is claimed when a unit enters the registry and released when it leaves, and a claimed row
is reset to "never observed" so no stale belief can leak into a later unit. Units outside
a registry (test fixtures, a daughter before insertion) keep a detached
:class:`~madexplorer.population.unit.BeliefMap`.

The interface (``claim``/``release``/``gather``/``scatter``/``assign``/``view``) is what a later
sparse backend must provide; see objective/status.md (PH3a).
"""

import os
from dataclasses import dataclass

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.unit import (
    FOOD_DTYPE,
    HOPS_DTYPE,
    NEVER_OBSERVED,
    POPULATION_DTYPE,
    YEAR_DTYPE,
    BeliefMap,
    CountArray,
    FoodArray,
    HopsArray,
    YearArray,
)

BYTES_PER_CELL = (
    np.dtype(YEAR_DTYPE).itemsize
    + np.dtype(FOOD_DTYPE).itemsize
    + np.dtype(POPULATION_DTYPE).itemsize
    + np.dtype(HOPS_DTYPE).itemsize
)
# Capacity growth (implementation policy, not model semantics): +25% (at least MIN_CAPACITY
# rows) per resize, so allocated but unused rows stay below ~25% of the store. Matrices are
# resized in place (numpy's realloc; for large blocks the kernel remaps pages, so old and new
# stores never coexist); if a view of a matrix is alive numpy refuses and the store falls back
# to copying into new arrays (a transient peak of old + new).
GROWTH_FRACTION = 0.25
MIN_CAPACITY = 64


class BeliefRowView(BeliefMap):
    """A unit's beliefs as views into its store row (compatibility and debugging only).

    Hot subsystems use the store's batched methods; a view is a few numpy row views, cheap
    to build but not meant to be created once per unit per tick.
    """

    store: "DenseBeliefStore"
    slot: int

    def __init__(self, store: "DenseBeliefStore", slot: int) -> None:
        super().__init__(
            store.year[slot], store.food_kcal[slot], store.population[slot], store.hops[slot]
        )
        self.store = store
        self.slot = slot


@dataclass(eq=False)
class DenseBeliefStore:
    """All units' beliefs as global ``(capacity, cells)`` matrices, one row per slot."""

    n_cells: int
    year: YearArray
    food_kcal: FoodArray
    population: CountArray
    hops: HopsArray
    active: int = 0  # rows claimed by registered units
    resizes: int = 0
    peak_resize_bytes: int = 0  # largest transient old + new footprint of a copying resize
    kind = "dense"

    @classmethod
    def empty(cls, n_cells: int, capacity: int = MIN_CAPACITY) -> "DenseBeliefStore":
        """A store with ``capacity`` free slots, all never observed."""
        store = cls(
            n_cells,
            np.full((capacity, n_cells), NEVER_OBSERVED, dtype=YEAR_DTYPE),
            np.zeros((capacity, n_cells), dtype=FOOD_DTYPE),
            np.zeros((capacity, n_cells), dtype=POPULATION_DTYPE),
            np.zeros((capacity, n_cells), dtype=HOPS_DTYPE),
        )
        return store

    @property
    def capacity(self) -> int:
        """Allocated rows."""
        return int(self.year.shape[0])

    @property
    def nbytes(self) -> int:
        """Bytes of the four matrices (allocated capacity, not only active rows)."""
        return int(
            self.year.nbytes + self.food_kcal.nbytes + self.population.nbytes + self.hops.nbytes
        )

    def _grow(self) -> None:
        old = self.capacity
        new = old + max(int(old * GROWTH_FRACTION), MIN_CAPACITY)
        for name, fill in (
            ("year", NEVER_OBSERVED),
            ("food_kcal", 0),
            ("population", 0),
            ("hops", 0),
        ):
            try:
                # Only the store may reference the matrix for numpy to resize it in place.
                getattr(self, name).resize((new, self.n_cells), refcheck=True)
            except ValueError:  # a view is alive: copy instead
                array = getattr(self, name)
                copied = np.empty((new, self.n_cells), dtype=array.dtype)
                copied[:old] = array[:old]
                self.peak_resize_bytes = max(
                    self.peak_resize_bytes, (old + new) * self.n_cells * array.itemsize
                )
                del array
                setattr(self, name, copied)
            getattr(self, name)[old:] = fill
        self.resizes += 1

    def claim(self, slot: int, species_code: int = 0) -> None:
        """Take ``slot`` for a registered unit (growing as needed), reset to never observed."""
        while slot >= self.capacity:
            self._grow()
        self.reset(slot)
        self.active += 1

    def configure_expiry(self, memory_by_code: IntArray) -> None:
        """Memory horizon per species code (unused: dense rows keep expired entries)."""

    def set_clock(self, year: int) -> None:
        """The current simulation year (unused: dense expiry is lazy, readers filter)."""

    def entries(self, slot: int) -> tuple[IntArray, YearArray, FoodArray, CountArray, HopsArray]:
        """Every stored (ever observed) entry of ``slot``, by ascending cell."""
        cells = np.flatnonzero(self.year[slot] != NEVER_OBSERVED)
        return (
            cells,
            self.year[slot, cells],
            self.food_kcal[slot, cells],
            self.population[slot, cells],
            self.hops[slot, cells],
        )

    @property
    def stored_entries(self) -> int:
        """Entries ever observed in active and free rows (dense: never physically removed)."""
        return int((self.year != NEVER_OBSERVED).sum())

    def release(self, slot: int) -> None:
        """Give ``slot`` back (its row is cleared so nothing leaks into a later unit)."""
        self.reset(slot)
        self.active -= 1

    def reset(self, slot: int) -> None:
        """Mark every cell of ``slot`` as never observed."""
        self.year[slot] = NEVER_OBSERVED
        self.food_kcal[slot] = 0
        self.population[slot] = 0
        self.hops[slot] = 0

    def assign(self, slot: int, beliefs: BeliefMap) -> None:
        """Overwrite ``slot`` with a map's content (an empty map means never observed)."""
        if isinstance(beliefs, BeliefRowView) and beliefs.store is self and beliefs.slot == slot:
            return
        if beliefs.n_cells == 0:
            self.reset(slot)
            return
        if beliefs.n_cells != self.n_cells:
            raise ValueError(f"belief map covers {beliefs.n_cells} cells, expected {self.n_cells}")
        self.year[slot] = beliefs.year
        self.food_kcal[slot] = beliefs.food_kcal
        self.population[slot] = beliefs.population
        self.hops[slot] = beliefs.hops

    def copy_row(self, source: int, target: int) -> None:
        """``target`` becomes an independent copy of ``source``."""
        self.year[target] = self.year[source]
        self.food_kcal[target] = self.food_kcal[source]
        self.population[target] = self.population[source]
        self.hops[target] = self.hops[source]

    def merge_row(self, source: int, target: int) -> None:
        """``target`` takes ``source``'s entry wherever it is better (``BeliefMap.merged_with``).

        Better means strictly fresher, or equally fresh with fewer relays.
        """
        year, hops = self.year, self.hops
        better = (year[source] > year[target]) | (
            (year[source] == year[target]) & (hops[source] < hops[target])
        )
        if not better.any():
            return
        for array in (year, self.food_kcal, self.population, hops):
            array[target, better] = array[source, better]

    def detached(self, slot: int) -> BeliefMap:
        """An independent :class:`BeliefMap` copy of ``slot``."""
        return BeliefRowView(self, slot).copy()

    def view(self, slot: int) -> BeliefRowView:
        """Row views of ``slot`` (compatibility; writes go to the store)."""
        return BeliefRowView(self, slot)

    def gather(
        self, slots: IntArray, cells: IntArray
    ) -> tuple[YearArray, FoodArray, CountArray, HopsArray]:
        """Beliefs of ``(slots[i], cells[i])`` pairs, one indexing operation per field."""
        return (
            self.year[slots, cells],
            self.food_kcal[slots, cells],
            self.population[slots, cells],
            self.hops[slots, cells],
        )

    def years(self, slots: IntArray, cells: IntArray) -> YearArray:
        """Observation years of ``(slots[i], cells[i])`` pairs (``NEVER_OBSERVED`` if none)."""
        values: YearArray = self.year[slots, cells]
        return values

    def years_and_hops(self, slots: IntArray, cells: IntArray) -> tuple[YearArray, HopsArray]:
        """Observation years and relay counts of ``(slots[i], cells[i])`` pairs."""
        return self.year[slots, cells], self.hops[slots, cells]

    def scatter(
        self,
        slots: IntArray,
        cells: IntArray,
        year: YearArray | int,
        food_kcal: FoodArray | np.ndarray,
        population: CountArray | IntArray,
        hops: HopsArray | int,
    ) -> None:
        """Write beliefs at ``(slots[i], cells[i])`` (pairs must be distinct)."""
        self.year[slots, cells] = year
        self.food_kcal[slots, cells] = food_kcal
        self.population[slots, cells] = population
        self.hops[slots, cells] = hops


SPARSE_ENTRY_BYTES = BYTES_PER_CELL + 4  # cell id (int32) + the four fields
COMPACT_GARBAGE_FRACTION = 0.5  # compact when released capacity exceeds this share of the pool
COMPACT_MIN_ENTRIES = 4096


class SparseBeliefStore:
    """Beliefs as sorted per-unit rows of observed cells in shared numeric pools (PH4b).

    Same logical content and interface as :class:`DenseBeliefStore`: a cell missing from a
    row reads exactly as a never-observed dense entry. Expired entries (``year <= clock -
    memory_years`` of the unit's species) are semantically invisible
    (``tests/test_belief_expiry.py``) and are physically dropped whenever a row is
    rewritten anyway: a full row is pruned before it grows, copies and merges keep only
    current entries, and the pool is compacted (without expired entries) when released
    capacity exceeds half of it. Memory is therefore proportional to current beliefs,
    not to world cells or to every cell ever seen; no annual scan is needed: each row is
    pruned when it fills (amortized over the insertions that filled it) and compaction
    is amortized over the releases that created the garbage.

    Rows have no fixed maximum size: a full row doubles. All per-entry work is in
    compiled kernels (:mod:`madexplorer.population.belief_kernels`). ``view`` returns a
    read-only dense copy (compatibility and tests); writes go through ``scatter`` or
    ``assign``.
    """

    kind = "sparse"

    def __init__(self, n_cells: int, capacity: int = MIN_CAPACITY, pool: int = 0) -> None:
        self.n_cells = n_cells
        self.active = 0
        self.resizes = 0
        self.compactions = 0
        self.peak_resize_bytes = 0
        self.clock: int | None = None
        self.memory_by_code: IntArray | None = None
        self.row_start = np.zeros(capacity, dtype=np.int64)
        self.row_length = np.zeros(capacity, dtype=np.int64)
        self.row_capacity = np.zeros(capacity, dtype=np.int64)
        self.row_code = np.zeros(capacity, dtype=np.int64)
        self.claimed = np.zeros(capacity, dtype=bool)
        size = max(pool, capacity * 64)
        self.cell = np.zeros(size, dtype=np.int32)
        self.year = np.full(size, NEVER_OBSERVED, dtype=YEAR_DTYPE)
        self.food_kcal = np.zeros(size, dtype=FOOD_DTYPE)
        self.population = np.zeros(size, dtype=POPULATION_DTYPE)
        self.hops = np.zeros(size, dtype=HOPS_DTYPE)
        self.used = 0
        self.garbage = 0

    @classmethod
    def empty(cls, n_cells: int, capacity: int = MIN_CAPACITY) -> "SparseBeliefStore":
        """An empty store with ``capacity`` slots."""
        return cls(n_cells, capacity)

    # ------------------------------------------------------------------ sizes
    @property
    def capacity(self) -> int:
        """Addressable slots."""
        return int(self.row_start.size)

    @property
    def pool_size(self) -> int:
        """Allocated pool entries."""
        return int(self.cell.size)

    @property
    def nbytes(self) -> int:
        """Bytes of the pool arrays and the per-slot index."""
        pool = self.cell.nbytes + self.year.nbytes + self.food_kcal.nbytes
        pool += self.population.nbytes + self.hops.nbytes
        index = self.row_start.nbytes + self.row_length.nbytes + self.row_capacity.nbytes
        index += self.row_code.nbytes + self.claimed.nbytes
        return int(pool + index)

    @property
    def stored_entries(self) -> int:
        """Entries physically stored in claimed rows (current or not yet pruned)."""
        return int(self.row_length[self.claimed].sum())

    # ------------------------------------------------------------------ expiry
    def configure_expiry(self, memory_by_code: IntArray) -> None:
        """Memory horizon in years per species code (enables pruning)."""
        self.memory_by_code = np.asarray(memory_by_code, dtype=np.int64)

    def set_clock(self, year: int) -> None:
        """The current simulation year; entries with ``year <= clock - memory`` are dead.

        Only the simulation step advances the clock, so pruning can only lag behind the
        semantic expiry, never run ahead of it.
        """
        self.clock = year

    def _horizons(self, slots: IntArray) -> IntArray:
        from madexplorer.population.belief_kernels import NO_HORIZON

        if self.clock is None or self.memory_by_code is None:
            return np.full(slots.size, NO_HORIZON, dtype=np.int64)
        horizons: IntArray = self.clock - self.memory_by_code[self.row_code[slots]]
        return horizons

    def _horizon(self, slot: int) -> int:
        return int(self._horizons(np.array([slot], dtype=np.int64))[0])

    # ------------------------------------------------------------------ slots
    def _grow_slots(self, needed: int) -> None:
        new = max(needed, self.capacity + max(int(self.capacity * GROWTH_FRACTION), MIN_CAPACITY))
        for name in ("row_start", "row_length", "row_capacity", "row_code", "claimed"):
            old = getattr(self, name)
            grown = np.zeros(new, dtype=old.dtype)
            grown[: old.size] = old
            setattr(self, name, grown)
        self.resizes += 1

    def _reserve(self, entries: int) -> None:
        """Make room for ``entries`` more pool entries (compacting or growing)."""
        if self.used + entries <= self.pool_size:
            return
        if self.garbage > COMPACT_GARBAGE_FRACTION * self.pool_size:
            self.compact()
            if self.used + entries <= self.pool_size:
                return
        new = max(self.used + entries, int(self.pool_size * 1.5) + 1024)
        for name, fill in (
            ("cell", 0),
            ("year", NEVER_OBSERVED),
            ("food_kcal", 0),
            ("population", 0),
            ("hops", 0),
        ):
            old = getattr(self, name)
            grown = np.full(new, fill, dtype=old.dtype)
            grown[: self.used] = old[: self.used]
            setattr(self, name, grown)
        self.resizes += 1

    def claim(self, slot: int, species_code: int = 0) -> None:
        """Take ``slot`` for a registered unit, with an empty row."""
        if slot >= self.capacity:
            self._grow_slots(slot + 1)
        self.reset(slot)
        self.row_code[slot] = species_code
        self.claimed[slot] = True
        self.active += 1

    def release(self, slot: int) -> None:
        """Give ``slot`` back (its row capacity becomes garbage)."""
        self.reset(slot)
        self.claimed[slot] = False
        self.active -= 1

    def reset(self, slot: int) -> None:
        """Empty ``slot``'s row (never observed everywhere)."""
        self.garbage += int(self.row_capacity[slot])
        self.row_length[slot] = 0
        self.row_capacity[slot] = 0
        self.row_start[slot] = 0

    # ------------------------------------------------------------------ point access
    def gather(
        self, slots: IntArray, cells: IntArray
    ) -> tuple[YearArray, FoodArray, CountArray, HopsArray]:
        """Beliefs of ``(slots[i], cells[i])`` pairs (never observed where absent)."""
        n = int(np.size(slots))
        year = np.empty(n, dtype=YEAR_DTYPE)
        food = np.empty(n, dtype=FOOD_DTYPE)
        population = np.empty(n, dtype=POPULATION_DTYPE)
        hops = np.empty(n, dtype=HOPS_DTYPE)
        self._lookup(slots, cells, year, food, population, hops, 4)
        return year, food, population, hops

    def years(self, slots: IntArray, cells: IntArray) -> YearArray:
        """Observation years of ``(slots[i], cells[i])`` pairs."""
        n = int(np.size(slots))
        year = np.empty(n, dtype=YEAR_DTYPE)
        empty_f, empty_i, empty_h = (
            np.empty(0, dtype=FOOD_DTYPE),
            np.empty(0, dtype=POPULATION_DTYPE),
            np.empty(0, dtype=HOPS_DTYPE),
        )
        self._lookup(slots, cells, year, empty_f, empty_i, empty_h, 1)
        return year

    def years_and_hops(self, slots: IntArray, cells: IntArray) -> tuple[YearArray, HopsArray]:
        """Observation years and relay counts of ``(slots[i], cells[i])`` pairs."""
        n = int(np.size(slots))
        year = np.empty(n, dtype=YEAR_DTYPE)
        hops = np.empty(n, dtype=HOPS_DTYPE)
        empty_f, empty_i = np.empty(0, dtype=FOOD_DTYPE), np.empty(0, dtype=POPULATION_DTYPE)
        self._lookup(slots, cells, year, empty_f, empty_i, hops, 2)
        return year, hops

    def _lookup(
        self,
        slots: IntArray,
        cells: IntArray,
        year: np.ndarray,
        food: np.ndarray,
        population: np.ndarray,
        hops: np.ndarray,
        fields: int,
    ) -> None:
        from madexplorer.population.belief_kernels import lookup

        lookup(
            self.row_start,
            self.row_length,
            self.cell,
            self.year,
            self.food_kcal,
            self.population,
            self.hops,
            np.ascontiguousarray(slots, dtype=np.int64),
            np.ascontiguousarray(cells, dtype=np.int64),
            year,
            food,
            population,
            hops,
            fields,
        )

    def scatter(
        self,
        slots: IntArray,
        cells: IntArray,
        year: YearArray | int,
        food_kcal: FoodArray | np.ndarray,
        population: CountArray | IntArray,
        hops: HopsArray | int,
    ) -> None:
        """Write beliefs at ``(slots[i], cells[i])`` (pairs must be distinct)."""
        from madexplorer.population.belief_kernels import scatter

        slots = np.ascontiguousarray(slots, dtype=np.int64)
        n = slots.size
        if n == 0:
            return

        def column(values: object, dtype: type) -> np.ndarray:
            array = np.asarray(values)
            if array.ndim == 0:
                return np.full(n, array, dtype=dtype)
            return np.ascontiguousarray(array, dtype=dtype)

        args = (
            np.ascontiguousarray(cells, dtype=np.int64),
            column(year, YEAR_DTYPE),
            column(food_kcal, FOOD_DTYPE),
            column(population, POPULATION_DTYPE),
            column(hops, HOPS_DTYPE),
        )
        horizon = np.full(self.capacity, 0, dtype=np.int64)
        unique = np.unique(slots)
        horizon[unique] = self._horizons(unique)
        first = 0
        while True:
            first, self.used, released = scatter(
                self.row_start,
                self.row_length,
                self.row_capacity,
                horizon,
                self.cell,
                self.year,
                self.food_kcal,
                self.population,
                self.hops,
                self.used,
                slots,
                *args,
                first,
            )
            self.garbage += released
            if first >= n:
                return
            # The pool is full: make room for this row doubling (and some), then resume.
            need = 2 * int(self.row_length[slots[first]]) + 1024
            self._reserve(need)

    # ------------------------------------------------------------------ rows
    def copy_row(self, source: int, target: int) -> None:
        """``target`` becomes an independent copy of ``source``'s current entries."""
        from madexplorer.population.belief_kernels import MIN_ROW_CAPACITY, copy_row

        self.reset(target)
        self._reserve(max(int(self.row_length[source]), MIN_ROW_CAPACITY))
        self.used = copy_row(
            source,
            target,
            self._horizon(source),
            self.row_start,
            self.row_length,
            self.row_capacity,
            self.cell,
            self.year,
            self.food_kcal,
            self.population,
            self.hops,
            self.used,
        )

    def merge_row(self, source: int, target: int) -> None:
        """``target`` takes ``source``'s entry wherever it is better (current entries)."""
        from madexplorer.population.belief_kernels import MIN_ROW_CAPACITY, merge_rows

        self._reserve(max(int(self.row_length[source] + self.row_length[target]), MIN_ROW_CAPACITY))
        old_capacity = int(self.row_capacity[target])  # after a possible compaction
        self.used = merge_rows(
            source,
            target,
            self._horizon(target),
            self.row_start,
            self.row_length,
            self.row_capacity,
            self.cell,
            self.year,
            self.food_kcal,
            self.population,
            self.hops,
            self.used,
        )
        self.garbage += old_capacity

    def compact(self) -> None:
        """Rewrite every claimed row contiguously without expired entries (amortized)."""
        from madexplorer.population.belief_kernels import MIN_ROW_CAPACITY, compact

        slots = np.flatnonzero(self.claimed).astype(np.int64)
        lengths = self.row_length[slots]
        size = int(np.maximum(lengths + lengths // 4, MIN_ROW_CAPACITY).sum())
        size = max(size + size // 2, COMPACT_MIN_ENTRIES)
        new: dict[str, np.ndarray] = {
            "cell": np.zeros(size, dtype=np.int32),
            "year": np.full(size, NEVER_OBSERVED, dtype=YEAR_DTYPE),
            "food_kcal": np.zeros(size, dtype=FOOD_DTYPE),
            "population": np.zeros(size, dtype=POPULATION_DTYPE),
            "hops": np.zeros(size, dtype=HOPS_DTYPE),
        }
        horizon = np.zeros(self.capacity, dtype=np.int64)
        horizon[slots] = self._horizons(slots)
        self.used = compact(
            slots,
            horizon,
            self.row_start,
            self.row_length,
            self.row_capacity,
            self.cell,
            self.year,
            self.food_kcal,
            self.population,
            self.hops,
            new["cell"],
            new["year"],
            new["food_kcal"],
            new["population"],
            new["hops"],
        )
        for name, array in new.items():
            setattr(self, name, array)
        self.garbage = 0
        self.compactions += 1

    # ------------------------------------------------------------------ maps
    def entries(self, slot: int) -> tuple[IntArray, YearArray, FoodArray, CountArray, HopsArray]:
        """Every stored entry of ``slot``, by ascending cell (copies)."""
        start, length = int(self.row_start[slot]), int(self.row_length[slot])
        rows = slice(start, start + length)
        return (
            self.cell[rows].astype(np.int64),
            self.year[rows].copy(),
            self.food_kcal[rows].copy(),
            self.population[rows].copy(),
            self.hops[rows].copy(),
        )

    def detached(self, slot: int) -> BeliefMap:
        """A dense :class:`BeliefMap` copy of ``slot``."""
        beliefs = BeliefMap.empty(self.n_cells)
        cells, year, food, population, hops = self.entries(slot)
        beliefs.write(cells, year, food, population, hops)
        return beliefs

    def view(self, slot: int) -> BeliefMap:
        """A read-only dense copy of ``slot`` (writes must go through the store)."""
        beliefs = self.detached(slot)
        for array in (beliefs.year, beliefs.food_kcal, beliefs.population, beliefs.hops):
            array.flags.writeable = False
        return beliefs

    def assign(self, slot: int, beliefs: BeliefMap) -> None:
        """Overwrite ``slot`` with a map's observed entries."""
        self.reset(slot)
        if beliefs.n_cells == 0:
            return
        if beliefs.n_cells != self.n_cells:
            raise ValueError(f"belief map covers {beliefs.n_cells} cells, expected {self.n_cells}")
        cells = np.flatnonzero(beliefs.year != NEVER_OBSERVED)
        self.scatter(
            np.full(cells.size, slot, dtype=np.int64),
            cells,
            beliefs.year[cells],
            beliefs.food_kcal[cells],
            beliefs.population[cells],
            beliefs.hops[cells],
        )


BeliefStore = DenseBeliefStore | SparseBeliefStore
BACKENDS = ("dense", "sparse", "auto")
BACKEND_ENV = "MADEXPLORER_BELIEFS"  # inherited by spawned ensemble and benchmark workers


DEFAULT_BACKEND = "sparse"  # production default; dense stays the reference/debug backend


def requested_backend() -> str:
    """The backend requested for new simulators: ``$MADEXPLORER_BELIEFS`` or the default."""
    return os.environ.get(BACKEND_ENV, DEFAULT_BACKEND)


# ``auto`` (kept, not the default): dense for worlds up to 50 x 50, sparse above. PH4b/PH5
# measured sparse within CPU noise of dense even on 40 x 40 and 13-380x smaller, so sparse
# is the production default; dense is the reference backend (raw-byte oracle, expiry and
# backend differential tests, debugging).
AUTO_SPARSE_MIN_CELLS = 2500


def resolve_backend(name: str, n_cells: int) -> str:
    """``dense`` or ``sparse`` for a requested backend; ``auto`` decides from the world size
    only (static), never from simulation state."""
    if name not in BACKENDS:
        raise ValueError(f"unknown belief backend {name!r} (expected one of {BACKENDS})")
    if name == "auto":
        return "sparse" if n_cells >= AUTO_SPARSE_MIN_CELLS else "dense"
    return name


def make_belief_store(backend: str, n_cells: int) -> BeliefStore:
    """An empty store of the resolved backend."""
    if resolve_backend(backend, n_cells) == "sparse":
        return SparseBeliefStore.empty(n_cells)
    return DenseBeliefStore.empty(n_cells)
