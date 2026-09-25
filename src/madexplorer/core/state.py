"""Explicit mutable simulation state and per-step context (spec §28.2, §28.6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import MechanismsConfig
from madexplorer.core.events import EventLog
from madexplorer.core.ids import IdAllocator
from madexplorer.core.rng import RngManager
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.ecology.resources import EcologyState
from madexplorer.knowledge.system import Capability, KnowledgeModel, default_capabilities
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

    def cell_fields_ha(self) -> FloatArray:
        """Cultivated hectares per cell."""
        fields = np.zeros(self.world.n_cells)
        for unit in self.units.values():
            fields[unit.cell] += unit.fields_ha
        return fields

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
    farm_harvest_kcal: float = 0.0
    spoilage_kcal: float = 0.0
    abandoned_stores_kcal: float = 0.0
    trade_volume_kcal: float = 0.0
    transport_loss_kcal: float = 0.0
    inventions: int = 0
    adoptions: int = 0
    technology_losses: int = 0
    resolution_merges: int = 0
    crowding_deaths_expected: float = 0.0  # deaths attributable to crowding (expected value)
    migration_decisions: int = 0  # units that compared staying with a destination
    food_saturated_decisions: int = 0  # of those, with a flat food utility at home


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
    knowledge: KnowledgeModel | None = None
    ledger: TickLedger = field(default_factory=TickLedger)

    @property
    def mechanisms(self) -> MechanismsConfig:
        """Ablation switches."""
        return self.scenario.config.mechanisms

    def species(self, species_id: str) -> SpeciesProfile:
        """Species profile by id."""
        return self.scenario.species[species_id]

    def capabilities(self, unit: PopulationUnit) -> dict[Capability, float]:
        """Technology capabilities of a unit, honoring the storage/cultivation switches."""
        caps = (
            dict(self.knowledge.capabilities(unit.technologies))
            if self.knowledge
            else default_capabilities()
        )
        if not self.mechanisms.cultivation:
            caps["crop_yield"] = 0.0
        if not self.mechanisms.storage:
            caps["storage_retention"] = 0.0
        return caps
