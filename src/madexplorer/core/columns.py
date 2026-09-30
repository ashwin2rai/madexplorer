"""Coarse column access to the units of one phase (performance layer, no model semantics).

Subsystems obtain whole columns for the units of a phase, in processing order, compute
on arrays, and write whole columns back. Two backends implement the same interface:

- :class:`TableColumns` (production): fancy indexing on the authoritative
  :class:`~madexplorer.population.table.UnitTable` with the ordered slot array;
- :class:`ObjectColumns` (reference): gathers from and writes to ``PopulationUnit``
  attributes, the object-authoritative engine that differential tests compare against.

Accessors work on whole columns, never on single scalars, so backend dispatch happens
once per field per subsystem. Rows are the units of the phase in registry order; a
``subset`` keeps that order.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.types import FloatArray, IntArray
from madexplorer.population.unit import PopulationUnit

if TYPE_CHECKING:
    from madexplorer.core.compiled import TechnologyTable
    from madexplorer.population.table import UnitTable


class TableColumns:
    """Columns of the phase's units read from and written to the unit table."""

    def __init__(
        self, units: Sequence[PopulationUnit], slots: IntArray, table: "UnitTable"
    ) -> None:
        self.units = tuple(units)
        self.slots = slots
        self.table = table

    def __len__(self) -> int:
        return len(self.units)

    def subset(self, rows: IntArray) -> "TableColumns":
        """The same columns for ``rows`` (positions, in order)."""
        return TableColumns([self.units[i] for i in rows.tolist()], self.slots[rows], self.table)

    def get(self, name: str) -> np.ndarray:
        """A copy of a scalar column for the rows."""
        values: np.ndarray = self.table.columns[name][self.slots]
        return values

    def set(self, name: str, values: np.ndarray | float) -> None:
        """Write a scalar column for the rows."""
        self.table.columns[name][self.slots] = values

    def set_rows(self, name: str, rows: IntArray, values: np.ndarray | float) -> None:
        """Write a scalar column for the given row positions."""
        self.table.columns[name][self.slots[rows]] = values

    def population(self) -> IntArray:
        """Exact head counts."""
        counts: IntArray = self.table.population[self.slots]
        return counts

    def species(self) -> IntArray:
        """Species codes (compiled species index)."""
        codes: IntArray = self.table.species_code[self.slots]
        return codes

    def cohorts(self, n_ages: int) -> tuple[IntArray, IntArray]:
        """``(females, males)`` matrices of the first ``n_ages`` age classes."""
        return (
            self.table.females[self.slots, :n_ages],
            self.table.males[self.slots, :n_ages],
        )

    def set_cohorts(self, females: IntArray, males: IntArray) -> None:
        """Replace every row's cohorts (``(rows, ages)``) and exact population counts."""
        n = females.shape[1]
        table, slots = self.table, self.slots
        table.females[slots, :n] = females
        table.males[slots, :n] = males
        table.females[slots, n:] = 0
        table.males[slots, n:] = 0
        table.n_ages[slots] = n
        table.population[slots] = females.sum(axis=1) + males.sum(axis=1)

    def weighted(self, weights: Mapping[int, FloatArray]) -> FloatArray:
        """``sum((females + males) * w)`` per row, with ``w`` chosen by species code.

        Row reductions over the contiguous age axis use numpy's pairwise sum exactly as the
        per-unit ``weighted_count`` did (differential test).
        """
        codes = self.species()
        out = np.zeros(len(self.units))
        for code, w in weights.items():
            rows = np.flatnonzero(codes == code)
            if rows.size == 0:
                continue
            n = w.size
            slots = self.slots[rows]
            both = self.table.females[slots, :n] + self.table.males[slots, :n]
            out[rows] = (both * w[None, :]).sum(axis=1)
        return out

    def knowledge(self) -> FloatArray:
        """``(rows, domains)`` knowledge matrix."""
        matrix: FloatArray = self.table.knowledge[self.slots]
        return matrix

    def set_knowledge(self, values: FloatArray) -> None:
        """Replace every row's knowledge vector."""
        self.table.knowledge[self.slots, : values.shape[1]] = values

    def technology_masks(self) -> IntArray:
        """Technology bitmasks."""
        masks: IntArray = self.table.technology_mask[self.slots]
        return masks

    def technologies(self) -> list[frozenset[str]]:
        """Technology sets (names)."""
        values: list[frozenset[str]] = self.table.technologies[self.slots].tolist()
        return values


class ObjectColumns:
    """The same interface over ``PopulationUnit`` attributes (reference engine)."""

    def __init__(
        self,
        units: Sequence[PopulationUnit],
        species_index: Mapping[str, int],
        technology_table: "TechnologyTable | None",
    ) -> None:
        self.units = tuple(units)
        self.slots = np.array([u.__dict__.get("_slot", -1) for u in self.units], dtype=np.int64)
        self.species_index = species_index
        self.technology_table = technology_table

    def __len__(self) -> int:
        return len(self.units)

    def subset(self, rows: IntArray) -> "ObjectColumns":
        """The same columns for ``rows`` (positions, in order)."""
        return ObjectColumns(
            [self.units[i] for i in rows.tolist()], self.species_index, self.technology_table
        )

    def get(self, name: str) -> np.ndarray:
        """A scalar column gathered from the objects."""
        return np.array([getattr(u, name) for u in self.units])

    def set(self, name: str, values: np.ndarray | float) -> None:
        """Write a scalar column onto the objects (Python scalars)."""
        items = values.tolist() if isinstance(values, np.ndarray) else [values] * len(self.units)
        for unit, value in zip(self.units, items, strict=True):
            setattr(unit, name, value)

    def set_rows(self, name: str, rows: IntArray, values: np.ndarray | float) -> None:
        """Write a scalar column for the given row positions."""
        items = values.tolist() if isinstance(values, np.ndarray) else [values] * rows.size
        for r, value in zip(rows.tolist(), items, strict=True):
            setattr(self.units[r], name, value)

    def population(self) -> IntArray:
        """Exact head counts."""
        return np.array([u.population for u in self.units], dtype=np.int64)

    def species(self) -> IntArray:
        """Species codes (compiled species index)."""
        index = self.species_index
        return np.array([index[u.species_id] for u in self.units], dtype=np.int64)

    def cohorts(self, n_ages: int) -> tuple[IntArray, IntArray]:
        """``(females, males)`` matrices."""
        return (
            np.stack([u.females[:n_ages] for u in self.units]),
            np.stack([u.males[:n_ages] for u in self.units]),
        )

    def set_cohorts(self, females: IntArray, males: IntArray) -> None:
        """Replace every row's cohorts (each unit gets its own row copies)."""
        for i, unit in enumerate(self.units):
            unit.females, unit.males = females[i].copy(), males[i].copy()

    def weighted(self, weights: Mapping[int, FloatArray]) -> FloatArray:
        """Per-unit ``weighted_count`` with ``w`` chosen by species code."""
        codes = self.species().tolist()
        return np.array(
            [u.weighted_count(weights[c]) for u, c in zip(self.units, codes, strict=True)],
            dtype=np.float64,
        )

    def knowledge(self) -> FloatArray:
        """``(rows, domains)`` knowledge matrix."""
        if not self.units:
            return np.zeros((0, 0))
        return np.stack([u.knowledge for u in self.units])

    def set_knowledge(self, values: FloatArray) -> None:
        """Replace every row's knowledge vector (row copies)."""
        for unit, row in zip(self.units, values, strict=True):
            unit.knowledge = row.copy()

    def technology_masks(self) -> IntArray:
        """Technology bitmasks from the compiled technology table."""
        table = self.technology_table
        if table is None:
            return np.zeros(len(self.units), dtype=np.int64)
        return table.masks([u.technologies for u in self.units])

    def technologies(self) -> list[frozenset[str]]:
        """Technology sets (names)."""
        return [u.technologies for u in self.units]


UnitColumns = TableColumns | ObjectColumns
