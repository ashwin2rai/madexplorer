"""Immutable scenario context computed once per world and species set (spec §27).

Everything here depends only on the static parts of a scenario (world generation,
ecology, agriculture and species parameters), not on the run seed or horizon, so
one context can serve every seed of an ensemble in a worker process. Nothing in it
is mutated by a run, except lazily filled caches (reachability) whose values are
deterministic functions of the static inputs.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.economy.agriculture import arable_hectares
from madexplorer.economy.foraging import ForageAccess, access_and_returns
from madexplorer.mobility.movement import MovementModel
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import Cognition
from madexplorer.world.generation import generate_world
from madexplorer.world.grid import WorldGrid


@dataclass(frozen=True, eq=False)
class StaticContext:
    """World, species tables and topology-derived constants shared by runs of one scenario."""

    key: str
    world: WorldGrid
    tables: Mapping[str, LifeTables]
    movement: Mapping[str, MovementModel]
    forage: Mapping[str, ForageAccess]
    arable_ha: FloatArray
    # Lazily filled: land cells perceived from (species, cell); a function of static inputs.
    _perceived: dict[tuple[str, int], IntArray] = field(default_factory=dict)
    _neighborhoods: dict[int, IntArray] = field(default_factory=dict)

    def neighborhood_table(self, radius_cells: int) -> IntArray:
        """Row ``c``: the cells within ``radius_cells`` of ``c`` in ascending id order, padded
        with -1 (the order of :meth:`WorldGrid.cells_within`; cached)."""
        table = self._neighborhoods.get(radius_cells)
        if table is None:
            width = (2 * radius_cells + 1) ** 2
            table = np.full((self.world.n_cells, width), -1, dtype=np.int64)
            for cell in range(self.world.n_cells):
                cells = self.world.cells_within(cell, radius_cells)
                table[cell, : len(cells)] = cells
            self._neighborhoods[radius_cells] = table
        return table

    def perceived_cells(self, species_id: str, cell: int, cognition: Cognition) -> IntArray:
        """Land cells a group of ``species_id`` in ``cell`` observes (ascending; cached)."""
        key = (species_id, cell)
        cells = self._perceived.get(key)
        if cells is None:
            from madexplorer.mobility.exploration import perception_radius_cells

            radius = perception_radius_cells(
                cognition, float(self.world.vegetation_density[cell]), self.world.cell_size_km
            )
            cells = self.world.land_cells_within(cell, radius)
            self._perceived[key] = cells
        return cells

    @classmethod
    def build(cls, scenario: Scenario) -> "StaticContext":
        """Compute the context for a scenario (world generation included)."""
        config = scenario.config
        world = generate_world(config.world, config.ecology)
        return cls(
            key=static_key(scenario),
            world=world,
            tables={sid: LifeTables.build(p) for sid, p in scenario.species.items()},
            movement={sid: MovementModel(world, p.movement) for sid, p in scenario.species.items()},
            forage={
                sid: ForageAccess(*access_and_returns(world, p.foraging))
                for sid, p in scenario.species.items()
            },
            arable_ha=arable_hectares(world, config.agriculture),
        )


def static_key(scenario: Scenario) -> str:
    """Hash of the scenario parts a :class:`StaticContext` depends on (not seed or horizon)."""
    config = scenario.config
    payload = {
        "world": config.world.model_dump(mode="json"),
        "ecology": config.ecology.model_dump(mode="json"),
        "agriculture": config.agriculture.model_dump(mode="json"),
        "species": {sid: p.model_dump(mode="json") for sid, p in sorted(scenario.species.items())},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


_CACHE: dict[str, StaticContext] = {}
_CACHE_SIZE = 2


def shared_static_context(scenario: Scenario) -> StaticContext:
    """The process-wide context for ``scenario``, built on first use (ensemble workers).

    Keeps the most recent few contexts so a worker running many seeds of one scenario
    builds the world, life tables and reachability caches only once.
    """
    key = static_key(scenario)
    context = _CACHE.get(key)
    if context is None:
        context = StaticContext.build(scenario)
        if len(_CACHE) >= _CACHE_SIZE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = context
    return context
