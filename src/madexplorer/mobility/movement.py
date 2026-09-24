"""Species-specific movement costs (spec §4.3).

There is no biome penalty: slope, vegetation, and water each add separate
friction whose magnitude depends on species locomotion.
"""

import math

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.species.profile import Movement
from madexplorer.world.grid import NeighborGraph, WorldGrid


@model_rule(
    name="cell_movement_friction",
    version="1.0",
    rationale=(
        "Movement cost multiplier = terrain friction (slope) x vegetation friction; water is "
        "impassable to walkers, costly to swimmers, and ordinary to fliers. Flight scales "
        "terrain and vegetation effects by flight_terrain_factor."
    ),
    source_type="heuristic",
    parameters=(
        "slope_friction_coefficient",
        "vegetation_friction_coefficient",
        "water_friction",
        "flight_terrain_factor",
    ),
    expected_domain=">= 1, or inf for impassable cells",
    known_limitations="No weather friction, trails/roads, or mobility technology in MVP 1.",
)
def cell_friction(world: WorldGrid, movement: Movement) -> FloatArray:
    """Dimensionless friction per cell; effective km = distance_km * friction."""
    terrain_scale = movement.flight_terrain_factor if movement.can_fly else 1.0
    terrain = 1.0 + movement.slope_friction_coefficient * terrain_scale * world.slope
    vegetation = (
        1.0 + movement.vegetation_friction_coefficient * terrain_scale * world.vegetation_density
    )
    friction = terrain * vegetation
    if movement.can_fly:
        water_friction = 1.0
    elif movement.can_swim:
        water_friction = movement.water_friction
    else:
        water_friction = math.inf
    result: FloatArray = np.where(world.is_water, water_friction, friction)
    return result


class MovementModel:
    """Friction field and cached reachability for one species on a static world."""

    def __init__(self, world: WorldGrid, movement: Movement) -> None:
        self.movement = movement
        self.friction = cell_friction(world, movement)
        self._friction_list: list[float] = self.friction.tolist()
        self._graph: NeighborGraph = world.graph()
        self._reachable: dict[int, dict[int, float]] = {}
        self._reachable_arrays: dict[int, tuple[IntArray, FloatArray]] = {}

    def reachable(self, origin: int) -> dict[int, float]:
        """Cells reachable in one annual relocation, with effective path cost in km.

        Cached per origin: the world (and thus friction) is static in MVP 1.
        """
        costs = self._reachable.get(origin)
        if costs is None:
            costs = self._graph.shortest_costs(
                [origin], self._friction_list, self.movement.annual_relocation_range_km
            )
            self._reachable[origin] = costs
        return costs

    def reachable_arrays(self, origin: int) -> tuple[IntArray, FloatArray]:
        """``reachable(origin)`` as ascending cell ids and aligned path costs (cached)."""
        arrays = self._reachable_arrays.get(origin)
        if arrays is None:
            costs = self.reachable(origin)
            cells = sorted(costs)
            arrays = (
                np.array(cells, dtype=np.int64),
                np.array([costs[c] for c in cells], dtype=np.float64),
            )
            self._reachable_arrays[origin] = arrays
        return arrays
