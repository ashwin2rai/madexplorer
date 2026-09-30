"""Explicit mutable simulation state and per-step context (spec §28.2, §28.6)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

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
from madexplorer.population.beliefs import DenseBeliefStore
from madexplorer.population.unit import PopulationUnit, attach_beliefs, detach_beliefs
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid

if TYPE_CHECKING:
    from madexplorer.core.compiled import CompiledScenario
    from madexplorer.core.spatial import SpatialIndex
    from madexplorer.core.static import StaticContext
    from madexplorer.economy.foraging import ForageAccess

CapabilityMap = Mapping[Capability, float]


class UnitRegistry(dict[str, PopulationUnit]):
    """``state.units``: units in stable insertion order (the semantic processing order),
    whose beliefs live in the state's belief store while they are registered.

    Inserting a unit allocates a store slot for its beliefs; removing one copies its
    beliefs back out and frees the slot. Reads are plain dict operations. Slots are
    storage only and never define iteration order.
    """

    def __init__(
        self,
        store: DenseBeliefStore | None = None,
        units: Mapping[str, PopulationUnit] | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        for unit_id, unit in (units or {}).items():
            self[unit_id] = unit

    def __setitem__(self, unit_id: str, unit: PopulationUnit) -> None:
        previous = self.get(unit_id)
        if previous is not None and previous is not unit:
            detach_beliefs(previous)
        if self.store is not None:
            attach_beliefs(unit, self.store)
        super().__setitem__(unit_id, unit)

    def __delitem__(self, unit_id: str) -> None:
        unit = self[unit_id]
        super().__delitem__(unit_id)
        detach_beliefs(unit)

    def pop(self, unit_id: str, *default: PopulationUnit) -> PopulationUnit:  # type: ignore[override]
        """Remove and return a unit (its beliefs are detached)."""
        if unit_id not in self:
            if default:
                return default[0]
            raise KeyError(unit_id)
        unit = super().pop(unit_id)
        detach_beliefs(unit)
        return unit

    def popitem(self) -> tuple[str, PopulationUnit]:
        """Remove and return the last unit (its beliefs are detached)."""
        unit_id, unit = super().popitem()
        detach_beliefs(unit)
        return unit_id, unit

    def clear(self) -> None:
        """Remove every unit (beliefs detached)."""
        for unit in self.values():
            detach_beliefs(unit)
        super().clear()

    def update(self, *args: Any, **kwargs: PopulationUnit) -> None:
        """Insert units one by one (so each gets a slot)."""
        for unit_id, unit in dict(*args, **kwargs).items():
            self[unit_id] = unit

    def setdefault(self, unit_id: str, unit: PopulationUnit) -> PopulationUnit:
        """Insert ``unit`` if ``unit_id`` is absent; return the registered unit."""
        if unit_id not in self:
            self[unit_id] = unit
        return self[unit_id]


@dataclass(eq=False)
class SimulationState:
    """Everything that changes during a run. Units are kept in stable insertion order."""

    year: int
    world: WorldGrid
    climate: ClimateYear
    ecology: EcologyState
    units: dict[str, PopulationUnit]
    beliefs: DenseBeliefStore | None = None

    def __post_init__(self) -> None:
        if self.beliefs is None:
            self.beliefs = DenseBeliefStore.empty(self.world.n_cells)
        self.units = self.units  # wrap in a registry bound to the store

    def __setattr__(self, name: str, value: Any) -> None:
        store = self.__dict__.get("beliefs")
        bound = isinstance(value, UnitRegistry) and value.store is store
        if name == "units" and store is not None and not bound:
            value = UnitRegistry(store, value)
        object.__setattr__(self, name, value)

    @property
    def belief_store(self) -> DenseBeliefStore:
        """The dense belief store (always present after construction)."""
        store = self.beliefs
        assert store is not None
        return store

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
    static: "StaticContext"
    trace_units: frozenset[str]
    knowledge: KnowledgeModel | None = None
    ledger: TickLedger = field(default_factory=TickLedger)
    # Immutable capability maps per technology set, shared across steps of a run.
    capability_cache: dict[frozenset[str], CapabilityMap] = field(default_factory=dict)
    compiled: "CompiledScenario | None" = None
    _crop_potential: FloatArray | None = None
    _spatial: "SpatialIndex | None" = None

    def spatial(self, state: "SimulationState") -> "SpatialIndex":
        """The shared cell -> unit index, built on first use in a phase.

        Valid until :meth:`invalidate_spatial`, which every apply that changes which units
        exist or where they are must call (migration, fission, fusion, extinction,
        coarsening).
        """
        index = self._spatial
        if index is None:
            from madexplorer.core.spatial import SpatialIndex

            index = SpatialIndex.build(tuple(state.units.values()))
            self._spatial = index
        return index

    def invalidate_spatial(self) -> None:
        """Drop the spatial index after a change of unit membership or location."""
        self._spatial = None

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
        cached = self.capability_cache.get(unit.technologies)
        if cached is None:
            caps = (
                dict(self.knowledge.capabilities(unit.technologies))
                if self.knowledge
                else default_capabilities()
            )
            if not self.mechanisms.cultivation:
                caps["crop_yield"] = 0.0
            if not self.mechanisms.storage:
                caps["storage_retention"] = 0.0
            cached = MappingProxyType(caps)
            self.capability_cache[unit.technologies] = cached
        return cached
