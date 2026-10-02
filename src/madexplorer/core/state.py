"""Explicit mutable simulation state and per-step context (spec §28.2, §28.6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

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
from madexplorer.population.beliefs import BeliefStore
from madexplorer.population.store import PopulationStore, UnitRegistry
from madexplorer.population.table import UnitTable
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns
    from madexplorer.core.compiled import CompiledScenario
    from madexplorer.core.spatial import SpatialIndex
    from madexplorer.core.static import StaticContext
    from madexplorer.economy.foraging import ForageAccess

CapabilityMap = Mapping[Capability, float]


@dataclass(eq=False)
class SimulationState:
    """Everything that changes during a run.

    Population state has one owner, :class:`~madexplorer.population.store.PopulationStore`;
    ``units``, ``table`` and ``belief_store`` are read-only views of its parts.
    """

    year: int
    world: WorldGrid
    climate: ClimateYear
    ecology: EcologyState
    population: PopulationStore

    @property
    def units(self) -> UnitRegistry:
        """Units in stable insertion (processing) order; mutations bind or free their rows."""
        return self.population.units

    @property
    def table(self) -> UnitTable | None:
        """The authoritative unit table (``None`` in the object-authoritative reference)."""
        return self.population.table

    @property
    def belief_store(self) -> BeliefStore:
        """The belief store (any backend)."""
        return self.population.beliefs

    def _table_slots(self) -> IntArray | None:
        if self.table is not None:
            return self.units.slots()
        return None

    def cell_population(self) -> IntArray:
        """People per cell."""
        counts = np.zeros(self.world.n_cells, dtype=np.int64)
        slots = self._table_slots()
        if slots is not None:
            assert self.table is not None
            np.add.at(counts, self.table.cell[slots], self.table.population[slots])
            return counts
        for unit in self.units.values():
            counts[unit.cell] += unit.population
        return counts

    def total_population(self) -> int:
        """Total number of individuals."""
        slots = self._table_slots()
        if slots is not None:
            assert self.table is not None
            return int(self.table.population[slots].sum())
        return sum(unit.population for unit in self.units.values())

    def cell_fields_ha(self) -> FloatArray:
        """Cultivated hectares per cell (summed in unit order, as the per-unit loop)."""
        fields = np.zeros(self.world.n_cells)
        slots = self._table_slots()
        if slots is not None:
            assert self.table is not None
            np.add.at(fields, self.table.cell[slots], self.table.fields_ha[slots])
            return fields
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
    static: "StaticContext"
    trace_units: frozenset[str]
    knowledge: KnowledgeModel | None = None
    ledger: TickLedger = field(default_factory=TickLedger)
    # Immutable capability maps per technology set, shared across steps of a run.
    capability_cache: dict[frozenset[str], CapabilityMap] = field(default_factory=dict)
    compiled: "CompiledScenario | None" = None
    _crop_potential: FloatArray | None = None
    _spatial: "SpatialIndex | None" = None
    _columns: "UnitColumns | None" = None

    def spatial(self, state: "SimulationState") -> "SpatialIndex":
        """The shared cell -> unit index, built on first use in a phase.

        Valid until :meth:`invalidate_spatial`, which every apply that changes which units
        exist or where they are must call (migration, fission, fusion, extinction,
        coarsening).
        """
        index = self._spatial
        if index is None:
            from madexplorer.core.spatial import SpatialIndex

            units = tuple(state.units.values())
            table = state.table
            if table is not None:
                slots = state.units.slots()
                index = SpatialIndex.build(units, table.cell[slots], table.species_code[slots])
            else:
                index = SpatialIndex.build(units)
            self._spatial = index
        return index

    def invalidate_spatial(self) -> None:
        """Drop the spatial index (and column view) after a change of unit membership or
        location."""
        self._spatial = None
        self._columns = None

    def columns(self, state: "SimulationState") -> "UnitColumns":
        """Column access to the phase's units in processing order (see ``core.columns``).

        Table mode reads the authoritative unit table; object mode (the reference engine)
        reads unit attributes. Rebuilt after :meth:`invalidate_spatial`.
        """
        columns = self._columns
        if columns is None:
            from madexplorer.core.columns import ObjectColumns, TableColumns

            units = self.spatial(state).units
            table = state.table
            if table is not None:
                columns = TableColumns(units, state.units.slots(), table)
            else:
                compiled = self.compiled
                columns = ObjectColumns(
                    units,
                    compiled.species_index if compiled else {},
                    compiled.technologies if compiled else None,
                )
            self._columns = columns
        return columns

    @property
    def tables(self) -> Mapping[str, LifeTables]:
        """Life tables per species (static)."""
        return self.static.tables

    @property
    def movement(self) -> Mapping[str, MovementModel]:
        """Movement models per species (static; reachability cached lazily)."""
        return self.static.movement

    @property
    def forage(self) -> Mapping[str, "ForageAccess"]:
        """Static foraging access and return rates per species."""
        return self.static.forage

    @property
    def arable_ha(self) -> FloatArray:
        """Cultivable hectares per cell (static)."""
        return self.static.arable_ha

    def crop_potential(self, state: "SimulationState") -> FloatArray:
        """This year's potential crop yield per hectare, computed once per step.

        Soil and climate change only in the environment subsystems at the start of a step,
        so farming and field planning see the same values.
        """
        if self._crop_potential is None:
            from madexplorer.economy.agriculture import crop_potential_kcal_per_ha

            self._crop_potential = crop_potential_kcal_per_ha(
                state.world,
                state.climate,
                state.ecology.soil_nutrients,
                self.scenario.config.agriculture,
            )
        return self._crop_potential

    @property
    def mechanisms(self) -> MechanismsConfig:
        """Ablation switches."""
        return self.scenario.config.mechanisms

    def species(self, species_id: str) -> SpeciesProfile:
        """Species profile by id."""
        return self.scenario.species[species_id]

    def capabilities(self, unit: PopulationUnit) -> CapabilityMap:
        """Technology capabilities of a unit, honoring the storage/cultivation switches.

        Read-only and shared: one mapping per technology set for the whole run.
        """
        return self.capabilities_of(unit.technologies)

    def capabilities_of(self, technologies: frozenset[str]) -> CapabilityMap:
        """:meth:`capabilities` for a technology set."""
        cached = self.capability_cache.get(technologies)
        if cached is None:
            caps = (
                dict(self.knowledge.capabilities(technologies))
                if self.knowledge
                else default_capabilities()
            )
            if not self.mechanisms.cultivation:
                caps["crop_yield"] = 0.0
            if not self.mechanisms.storage:
                caps["storage_retention"] = 0.0
            cached = MappingProxyType(caps)
            self.capability_cache[technologies] = cached
        return cached
