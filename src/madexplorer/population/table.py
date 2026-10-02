"""Authoritative slot-aligned numeric unit state (performance layer; no model semantics).

:class:`UnitTable` holds the frequently used mutable state of every registered unit as
columns indexed by storage slot: scalar fields, age-by-sex cohort matrices with an
exactly maintained population count, the knowledge matrix, and technology sets (names,
plus bitmasks from the compiled technology table). The belief store uses the same slot.

``PopulationUnit`` stays the domain view: while a unit is registered, its table fields are
descriptors that read and write its row (no copy lives on the object); a detached unit
(test fixture, a daughter before insertion) keeps plain attribute values. Hot subsystems
read and write whole columns for the ordered active slots instead of touching objects.
Irregular external state (familiarity, residence records, report cells, trade ties,
harvest history) stays on the unit object. Which field lives where is declared once in
:mod:`madexplorer.population.fields`.

Slots are storage only: the processing order is the unit registry's insertion order,
exposed as an ordered slot array. A released row is reset to defaults so nothing leaks
into a later unit.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.population.fields import BOOL_FIELDS, FLOAT_FIELDS, INT_FIELDS

if TYPE_CHECKING:
    from madexplorer.core.compiled import TechnologyTable

GROWTH_FRACTION = 0.25
MIN_CAPACITY = 64


@dataclass(eq=False)
class UnitTable:
    """Slot-aligned columns of registered units (see module docstring)."""

    technology_table: "TechnologyTable | None" = None
    capacity: int = 0
    columns: dict[str, np.ndarray] = field(default_factory=dict)
    females: IntArray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int64))
    males: IntArray = field(default_factory=lambda: np.zeros((0, 0), dtype=np.int64))
    n_ages: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    population: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    knowledge: FloatArray = field(default_factory=lambda: np.zeros((0, 0)))
    technologies: np.ndarray = field(default_factory=lambda: np.empty(0, dtype=object))
    technology_mask: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    species_code: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    resizes: int = 0

    def __post_init__(self) -> None:
        if not self.columns:
            for name in FLOAT_FIELDS:
                self.columns[name] = np.zeros(self.capacity)
            for name in INT_FIELDS:
                self.columns[name] = np.zeros(self.capacity, dtype=np.int64)
            for name in BOOL_FIELDS:
                self.columns[name] = np.zeros(self.capacity, dtype=bool)

    def __getattr__(self, name: str) -> np.ndarray:
        # Scalar columns as attributes (table.food_ratio, table.cell, ...).
        columns = self.__dict__.get("columns")
        if columns is not None and name in columns:
            array: np.ndarray = columns[name]
            return array
        raise AttributeError(name)

    # ------------------------------------------------------------------ capacity
    def ensure(self, slot: int, n_ages: int, n_domains: int) -> None:
        """Make ``slot`` addressable and the matrices wide enough."""
        if slot >= self.capacity:
            new = max(
                slot + 1, self.capacity + max(int(self.capacity * GROWTH_FRACTION), MIN_CAPACITY)
            )
            self._resize_rows(new)
        if n_ages > self.females.shape[1]:
            self._widen("females", n_ages)
            self._widen("males", n_ages)
        if n_domains > self.knowledge.shape[1]:
            self._widen("knowledge", n_domains)

    def _resize_rows(self, new: int) -> None:
        old = self.capacity

        def grow(array: np.ndarray) -> np.ndarray:
            grown = np.zeros((new, *array.shape[1:]), dtype=array.dtype)
            grown[:old] = array[:old]
            return grown

        for name in list(self.columns):
            self.columns[name] = grow(self.columns[name])
        for name in ("females", "males", "n_ages", "population", "knowledge"):
            setattr(self, name, grow(getattr(self, name)))
        technologies = np.empty(new, dtype=object)
        technologies[:old] = self.technologies[:old]
        technologies[old:] = frozenset()
        self.technologies = technologies
        self.technology_mask = grow(self.technology_mask)
        self.species_code = grow(self.species_code)
        self.capacity = new
        self.resizes += 1

    def _widen(self, name: str, width: int) -> None:
        array = getattr(self, name)
        wider = np.zeros((array.shape[0], width), dtype=array.dtype)
        wider[:, : array.shape[1]] = array
        setattr(self, name, wider)

    @property
    def nbytes(self) -> int:
        """Bytes of all numeric columns and matrices (object column excluded)."""
        total = sum(a.nbytes for a in self.columns.values())
        for name in ("females", "males", "n_ages", "population", "knowledge"):
            total += getattr(self, name).nbytes
        return int(total + self.technology_mask.nbytes + self.species_code.nbytes)

    # ------------------------------------------------------------------ rows
    def reset(self, slot: int) -> None:
        """Default values for a fresh or released row."""
        for array in self.columns.values():
            array[slot] = 0
        self.females[slot] = 0
        self.males[slot] = 0
        self.n_ages[slot] = 0
        self.population[slot] = 0
        self.knowledge[slot] = 0.0
        self.technologies[slot] = frozenset()
        self.technology_mask[slot] = 0
        self.species_code[slot] = 0

    def copy_row(self, source: int, target: int) -> None:
        """``target`` becomes a copy of ``source`` (every column; both slots addressable)."""
        for array in self.columns.values():
            array[target] = array[source]
        for name in ("females", "males", "n_ages", "population", "knowledge"):
            array = getattr(self, name)
            array[target] = array[source]
        self.technologies[target] = self.technologies[source]
        self.technology_mask[target] = self.technology_mask[source]
        self.species_code[target] = self.species_code[source]

    def load(self, slot: int, values: dict[str, Any], species_code: int) -> None:
        """Write a unit's table fields (from its detached attributes) into ``slot``."""
        females, males = values["females"], values["males"]
        knowledge = values["knowledge"]
        self.ensure(slot, females.size, knowledge.size)
        self.reset(slot)
        for name in FLOAT_FIELDS + INT_FIELDS + BOOL_FIELDS:
            self.columns[name][slot] = values[name]
        self.set_cohorts(slot, females, males)
        self.knowledge[slot, : knowledge.size] = knowledge
        self.set_technologies(slot, values["technologies"])
        self.species_code[slot] = species_code

    def unload(self, slot: int) -> dict[str, Any]:
        """A unit's table fields as detached attribute values (copies)."""
        values: dict[str, Any] = {}
        for name in FLOAT_FIELDS:
            values[name] = float(self.columns[name][slot])
        for name in INT_FIELDS:
            values[name] = int(self.columns[name][slot])
        for name in BOOL_FIELDS:
            values[name] = bool(self.columns[name][slot])
        values["females"], values["males"] = self.cohorts(slot)
        values["knowledge"] = self.knowledge_row(slot)
        values["technologies"] = self.technologies[slot]
        return values

    def cohorts(self, slot: int) -> tuple[IntArray, IntArray]:
        """Copies of a unit's female and male cohort vectors."""
        n = int(self.n_ages[slot])
        return self.females[slot, :n].copy(), self.males[slot, :n].copy()

    def set_cohorts(self, slot: int, females: IntArray, males: IntArray) -> None:
        """Replace a unit's cohorts and its population count (exact integer sums)."""
        n = females.size
        self.n_ages[slot] = n
        self.females[slot, :n] = females
        self.females[slot, n:] = 0
        self.males[slot, :n] = males
        self.males[slot, n:] = 0
        self.population[slot] = int(females.sum() + males.sum())

    def set_females(self, slot: int, females: IntArray) -> None:
        """Replace the female cohort only (population recomputed)."""
        n = females.size
        self.n_ages[slot] = n
        self.females[slot, :n] = females
        self.population[slot] = int(females.sum() + self.males[slot, :n].sum())

    def set_males(self, slot: int, males: IntArray) -> None:
        """Replace the male cohort only (population recomputed)."""
        n = males.size
        self.n_ages[slot] = n
        self.males[slot, :n] = males
        self.population[slot] = int(self.females[slot, :n].sum() + males.sum())

    def knowledge_row(self, slot: int) -> FloatArray:
        """A copy of a unit's knowledge vector."""
        row: FloatArray = self.knowledge[slot].copy()
        return row

    def set_technologies(self, slot: int, technologies: frozenset[str]) -> None:
        """Replace a unit's technology set (names and, if compiled, the bitmask)."""
        self.technologies[slot] = technologies
        table = self.technology_table
        self.technology_mask[slot] = table.mask(technologies) if table is not None else 0

    def check_population(self, slots: IntArray) -> BoolArray:
        """Whether the cached population equals the cohort sums (invariant)."""
        totals = self.females[slots].sum(axis=1) + self.males[slots].sum(axis=1)
        ok: BoolArray = totals == self.population[slots]
        return ok
