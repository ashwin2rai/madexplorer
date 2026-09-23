"""Grid world state and neighborhood graph (spec §4.1).

Cells are addressed by a flat integer id ``y * width + x``. Every per-cell
field is a flat ``(n_cells,)`` array so subsystems never depend on grid shape;
a later mesh implementation only needs to provide the same neighbor tables.
"""

import heapq
import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from madexplorer.core.types import BoolArray, FloatArray, IntArray

# 8-connected neighborhood offsets (dx, dy).
NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)


def build_neighbor_table(
    width: int, height: int, cell_size_km: float
) -> tuple[IntArray, FloatArray]:
    """Return ``(index, distance_km)`` arrays of shape ``(n_cells, 8)``; missing entries are -1."""
    n = width * height
    index = np.full((n, len(NEIGHBOR_OFFSETS)), -1, dtype=np.int64)
    distance = np.full((n, len(NEIGHBOR_OFFSETS)), np.inf)
    ys, xs = np.divmod(np.arange(n), width)
    for k, (dx, dy) in enumerate(NEIGHBOR_OFFSETS):
        nx, ny = xs + dx, ys + dy
        valid = (nx >= 0) & (nx < width) & (ny >= 0) & (ny < height)
        index[valid, k] = ny[valid] * width + nx[valid]
        distance[valid, k] = cell_size_km * math.hypot(dx, dy)
    return index, distance


class NeighborGraph:
    """Python-list view of the neighbor table for fast scalar graph traversal."""

    def __init__(self, index: IntArray, distance_km: FloatArray) -> None:
        self.index: list[list[int]] = index.tolist()
        self.distance_km: list[list[float]] = distance_km.tolist()

    def shortest_costs(
        self, sources: Iterable[int], friction: list[float], max_cost: float = math.inf
    ) -> dict[int, float]:
        """Dijkstra over friction-weighted edges; edge cost = distance * mean endpoint friction.

        Cells with infinite friction are impassable. Returns costs for all cells
        reachable within ``max_cost``.
        """
        costs: dict[int, float] = {}
        heap = [(0.0, s) for s in sources]
        heapq.heapify(heap)
        while heap:
            cost, cell = heapq.heappop(heap)
            if cell in costs:
                continue
            costs[cell] = cost
            f_here = friction[cell]
            for neighbor, step_km in zip(self.index[cell], self.distance_km[cell], strict=True):
                if neighbor < 0 or neighbor in costs:
                    continue
                f_next = friction[neighbor]
                if math.isinf(f_next):
                    continue
                new_cost = cost + step_km * 0.5 * (f_here + f_next)
                if new_cost <= max_cost:
                    heapq.heappush(heap, (new_cost, neighbor))
        return costs


@dataclass(frozen=True, eq=False)
class WorldGrid:
    """Static physical properties of the world. All fields are flat ``(n_cells,)`` arrays."""

    width: int
    height: int
    cell_size_km: float
    elevation_m: FloatArray
    slope: FloatArray  # rise over run, dimensionless
    is_water: BoolArray
    flow_accumulation: FloatArray  # upstream land cells draining through each cell
    is_river: BoolArray
    distance_to_ocean_km: FloatArray
    water_access: FloatArray  # freshwater availability index in [0, 1]
    latitude_deg: FloatArray
    base_temperature_c: FloatArray
    base_rainfall_mm: FloatArray
    soil_fertility: FloatArray  # multiplier on productivity
    base_npp_g_m2: FloatArray  # net primary productivity under base climate, g dry matter/m2/yr
    vegetation_density: FloatArray  # in [0, 1]
    neighbor_index: IntArray
    neighbor_distance_km: FloatArray

    @property
    def n_cells(self) -> int:
        """Number of cells."""
        return self.width * self.height

    @property
    def cell_area_km2(self) -> float:
        """Area of one cell."""
        return self.cell_size_km**2

    def cell_id(self, x: int, y: int) -> int:
        """Flat id of grid coordinate ``(x, y)``."""
        return y * self.width + x

    def coords(self, cell: int) -> tuple[int, int]:
        """Grid coordinate ``(x, y)`` of a flat cell id."""
        y, x = divmod(cell, self.width)
        return x, y

    def as_grid(self, field: FloatArray | IntArray | BoolArray) -> np.ndarray:
        """Reshape a flat field to ``(height, width)`` for display or export."""
        return field.reshape(self.height, self.width)

    def graph(self) -> NeighborGraph:
        """Neighbor graph for scalar traversal."""
        return NeighborGraph(self.neighbor_index, self.neighbor_distance_km)

    def cells_within(self, cell: int, radius_cells: int) -> list[int]:
        """Cells within Chebyshev distance ``radius_cells`` of ``cell`` (including it)."""
        x0, y0 = self.coords(cell)
        xs = range(max(0, x0 - radius_cells), min(self.width, x0 + radius_cells + 1))
        ys = range(max(0, y0 - radius_cells), min(self.height, y0 + radius_cells + 1))
        return [y * self.width + x for y in ys for x in xs]
