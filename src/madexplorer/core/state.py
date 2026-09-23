"""Explicit mutable simulation state and per-step context (spec §28.2, §28.6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import MechanismsConfig
from madexplorer.core.events import EventLog
from madexplorer.core.ids import IdAllocator
from madexplorer.core.rng import RngManager
from madexplorer.core.types import IntArray
from madexplorer.ecology.resources import EcologyState
from madexplorer.mobility.movement import MovementModel
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid


@dataclass(eq=False)
class SimulationState:
    """Everything that changes during a run. Units are kept in stable insertion order."""

    year: int
    world: WorldGrid
    climate: ClimateYear
    ecology: EcologyState
    units: dict[str, PopulationUnit]

    def cell_population(self) -> IntArray:
        """People per cell."""
        counts = np.zeros(self.world.n_cells, dtype=np.int64)
        for unit in self.units.values():
            counts[unit.cell] += unit.population
        return counts

    def total_population(self) -> int:
        """Total number of individuals."""
        return sum(unit.population for unit in self.units.values())

    def units_by_cell(self) -> dict[int, list[PopulationUnit]]:
        """Co-located units, in stable order."""
        grouped: dict[int, list[PopulationUnit]] = {}
        for unit in self.units.values():
            grouped.setdefault(unit.cell, []).append(unit)
        return grouped


@dataclass
class TickLedger:
    """Flows recorded during one step, used for metrics and conservation checks."""

    births: int = 0
    deaths: int = 0
    migrations: int = 0
    fissions: int = 0
    fusions: int = 0
    extinctions: int = 0
    harvest_kcal: float = 0.0
    need_kcal: float = 0.0


@dataclass(eq=False)
class StepContext:
    """Injected dependencies for one simulation step."""

    year: int
    scenario: Scenario
    rng: RngManager
    ids: IdAllocator
    events: EventLog
    tables: Mapping[str, LifeTables]
    movement: Mapping[str, MovementModel]
    trace_units: frozenset[str]
    ledger: TickLedger = field(default_factory=TickLedger)

    @property
    def mechanisms(self) -> MechanismsConfig:
        """Ablation switches."""
        return self.scenario.config.mechanisms

    def species(self, species_id: str) -> SpeciesProfile:
        """Species profile by id."""
        return self.scenario.species[species_id]
