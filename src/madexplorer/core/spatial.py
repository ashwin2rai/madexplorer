"""Shared cell -> unit index for one phase of a step (performance layer, not a model).

Several subsystems group co-located units. :class:`SpatialIndex` is built once from the
current units (a counting-sort style grouping, ``O(U + occupied cells)``) and reused by
every subsystem until an apply phase changes unit membership or location (migration,
fission, fusion, extinction, coarsening), which invalidates it through
:meth:`~madexplorer.core.state.StepContext.invalidate_spatial`.

Ordering reproduces :meth:`~madexplorer.core.state.SimulationState.units_by_cell`
exactly: cells in order of first appearance in unit order, and units in unit order within
a cell. Iteration order decides RNG assignment, ties and floating-point accumulation, so
exact seeded replay depends on it.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.unit import PopulationUnit


@dataclass(frozen=True, eq=False)
class SpatialIndex:
    """Units grouped by cell, plus integer row views for batched kernels."""

    units: tuple[PopulationUnit, ...]  # state order; a unit's row is its position here
    cell: IntArray  # (U,) cell of each row
    cells: IntArray  # occupied cells in first-appearance order
    order: IntArray  # rows grouped by ``cells``, unit order within a cell
    starts: IntArray  # (len(cells) + 1,): rows of cells[k] are order[starts[k]:starts[k+1]]
    by_cell: Mapping[int, list[PopulationUnit]]  # same content and order as units_by_cell()
    row_of: Mapping[str, int]  # unit id -> row
    species_code: IntArray | None = None  # (U,) compiled species codes (table mode)
    _pairs: dict[int, tuple[IntArray, IntArray]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        units: tuple[PopulationUnit, ...],
        cell: IntArray | None = None,
        species_code: IntArray | None = None,
    ) -> "SpatialIndex":
        """Index ``units`` (given in state order); cells and species codes may be given as
        arrays (from the unit table) instead of being read from the units."""
        if cell is None:
            cell = np.array([u.cell for u in units], dtype=np.int64)
        distinct, first, inverse = np.unique(cell, return_index=True, return_inverse=True)
        appearance = np.argsort(first, kind="stable")  # distinct cells in first-seen order
        rank = np.empty(distinct.size, dtype=np.int64)
        rank[appearance] = np.arange(distinct.size)
        order = np.argsort(rank[inverse], kind="stable")  # stable: unit order within a cell
        counts = np.bincount(rank[inverse], minlength=distinct.size)
        starts = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        cells = distinct[appearance]
        by_cell: dict[int, list[PopulationUnit]] = {}
        for k, c in enumerate(cells.tolist()):
            by_cell[c] = [units[r] for r in order[starts[k] : starts[k + 1]].tolist()]
        row_of = {u.id: i for i, u in enumerate(units)}
        return cls(units, cell, cells, order, starts, by_cell, row_of, species_code=species_code)

    def local_pairs(self, neighborhoods: IntArray) -> tuple[IntArray, IntArray]:
        """``(receiver, partner)`` rows of same-species units in the same or a neighboring
        cell (:func:`~madexplorer.mobility.exploration.candidate_encounters` order), built
        once per index and neighborhood table.

        Belief sharing draws encounters from these pairs and diffusion uses them as local
        contacts: the same semantic contact set, so one construction serves both while no
        membership or location change intervenes (which rebuilds the index).
        """
        key = id(neighborhoods)
        pairs = self._pairs.get(key)
        if pairs is None:
            from madexplorer.mobility.exploration import candidate_encounters

            pairs = candidate_encounters(
                self.units, neighborhoods, cell=self.cell, species_code=self.species_code
            )
            self._pairs[key] = pairs
        return pairs

    def rows_in(self, cell: int) -> list[PopulationUnit]:
        """Units in ``cell`` in unit order (empty if unoccupied)."""
        return self.by_cell.get(cell, [])
