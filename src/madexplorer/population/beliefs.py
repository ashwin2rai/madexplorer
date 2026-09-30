"""Belief storage backends (performance layer; belief semantics live in ``unit.BeliefMap``).

Every unit's beliefs about every cell (observation year, perceived food, perceived
population, relay count) were four small arrays owned by the unit. :class:`DenseBeliefStore`
keeps the same fields, dtypes and sentinel as four global ``(capacity, cells)`` matrices,
one row per *storage slot*, so hot subsystems gather and scatter beliefs for all units in
one indexing operation instead of visiting thousands of separate arrays.

Slots are storage only. Processing order stays the unit registry's insertion order
(``state.units``); a slot is allocated when a unit enters the registry and released when
it leaves, and a reused slot is reset to "never observed" so no stale belief can leak into
a later unit. Units outside a registry (test fixtures, a daughter before insertion) keep a
detached :class:`~madexplorer.population.unit.BeliefMap`.

The interface (``gather``/``scatter``/``assign``/``copy_row``/``view``) is what a later
sparse backend must provide; see objective/status.md (PH3a).
"""

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
    free: list[int]
    resizes: int = 0
    peak_resize_bytes: int = 0  # largest transient old + new footprint of a copying resize

    @classmethod
    def empty(cls, n_cells: int, capacity: int = MIN_CAPACITY) -> "DenseBeliefStore":
        """A store with ``capacity`` free slots, all never observed."""
        store = cls(
            n_cells,
            np.full((capacity, n_cells), NEVER_OBSERVED, dtype=YEAR_DTYPE),
            np.zeros((capacity, n_cells), dtype=FOOD_DTYPE),
            np.zeros((capacity, n_cells), dtype=POPULATION_DTYPE),
            np.zeros((capacity, n_cells), dtype=HOPS_DTYPE),
            list(range(capacity - 1, -1, -1)),  # pop() hands out low slots first
        )
        return store

    @property
    def capacity(self) -> int:
        """Allocated rows."""
        return int(self.year.shape[0])

    @property
    def active(self) -> int:
        """Rows in use."""
        return self.capacity - len(self.free)

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
        self.free.extend(range(new - 1, old - 1, -1))
        self.resizes += 1

    def allocate(self) -> int:
        """A free slot, reset to never observed."""
        if not self.free:
            self._grow()
        slot = self.free.pop()
        self.reset(slot)
        return slot

    def release(self, slot: int) -> None:
        """Return a slot (its row is cleared so nothing leaks into a later unit)."""
        self.reset(slot)
        self.free.append(slot)

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
