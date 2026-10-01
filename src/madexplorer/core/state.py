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
from madexplorer.population.beliefs import BeliefStore, make_belief_store
from madexplorer.population.table import UnitTable
from madexplorer.population.unit import PopulationUnit, attach_unit, belief_slot, detach_unit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns
    from madexplorer.core.compiled import CompiledScenario, TechnologyTable
    from madexplorer.core.spatial import SpatialIndex
    from madexplorer.core.static import StaticContext
    from madexplorer.economy.foraging import ForageAccess

CapabilityMap = Mapping[Capability, float]


class UnitRegistry(dict[str, PopulationUnit]):
    """``state.units``: units in stable insertion order (the semantic processing order).

    Inserting a unit gives it a storage slot: its beliefs move into the belief store and,
    with a unit table (the production mode), its hot numeric fields into the table.
    Removing it copies that state back onto the object and frees the slot, which is reset
    before reuse. Reads are plain dict operations. Slots never define iteration order;
    :meth:`slots` gives the slots in insertion order.
    """

    def __init__(
        self,
        store: BeliefStore | None = None,
        units: Mapping[str, PopulationUnit] | None = None,
        table: UnitTable | None = None,
        species_index: Mapping[str, int] | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.table = table
        self.species_index = dict(species_index or {})
        self._free: list[int] = []
        self._next_slot = 0
        self._slots: IntArray | None = None
        for unit_id, unit in (units or {}).items():
            self[unit_id] = unit

    def _allocate(self) -> int:
        if self._free:
            return self._free.pop()
        slot = self._next_slot
        self._next_slot += 1
        return slot

    def _attach(self, unit: PopulationUnit) -> None:
        if self.store is None:
            return
        state = unit.__dict__
        if state.get("_belief_store") is self.store and state.get("_table") is self.table:
            return  # already ours (e.g. restored by deepcopy together with this registry)
        detach_unit(unit)  # from any other registry's stores
        code = self.species_index.get(unit.species_id, 0)
        attach_unit(unit, self._allocate(), self.store, self.table, code)

    def _detach(self, unit: PopulationUnit) -> None:
        slot = detach_unit(unit)
        if slot >= 0:
            self._free.append(slot)

    def claim_slot(self, species_code: int = 0) -> int:
        """A free slot with addressable table and belief rows, for a unit built in place
        (``population.lifecycle``); the unit is then inserted already bound to it."""
        assert self.store is not None
        slot = self._allocate()
        if self.table is not None:
            self.table.ensure(slot, 0, 0)
        self.store.claim(slot, species_code)
        return slot

    def discard(self, unit_id: str) -> PopulationUnit:
        """Remove a unit and free its rows *without* copying its state back onto the object.

        For units that leave the simulation for good (absorbed, extinct): the returned
        object keeps only its external fields (id, species, ties, ...); its table fields
        and beliefs are gone.
        """
        unit = super().pop(unit_id)
        self._slots = None
        state = unit.__dict__
        store = state.get("_belief_store")
        if store is not None:
            slot: int = state["_slot"]
            table = state.get("_table")
            if table is not None:
                table.reset(slot)
            store.release(slot)
            state["_table"], state["_belief_store"], state["_slot"] = None, None, -1
            self._free.append(slot)
        return unit

    def slots(self) -> IntArray:
        """Storage slots of the registered units, in insertion (processing) order."""
        cached = self._slots
        if cached is None:
            cached = np.array([belief_slot(u) for u in self.values()], dtype=np.int64)
            self._slots = cached
        return cached

    def __setitem__(self, unit_id: str, unit: PopulationUnit) -> None:
        previous = self.get(unit_id)
        if previous is not None and previous is not unit:
            self._detach(previous)
        self._attach(unit)
        self._slots = None
        super().__setitem__(unit_id, unit)

    def __delitem__(self, unit_id: str) -> None:
        unit = self[unit_id]
        super().__delitem__(unit_id)
        self._slots = None
        self._detach(unit)

    def pop(self, unit_id: str, *default: PopulationUnit) -> PopulationUnit:  # type: ignore[override]
        """Remove and return a unit (its state is copied back onto the object)."""
        if unit_id not in self:
            if default:
                return default[0]
            raise KeyError(unit_id)
        unit = super().pop(unit_id)
        self._slots = None
        self._detach(unit)
        return unit

    def popitem(self) -> tuple[str, PopulationUnit]:
        """Remove and return the last unit."""
        unit_id, unit = super().popitem()
        self._slots = None
        self._detach(unit)
        return unit_id, unit

    def clear(self) -> None:
        """Remove every unit."""
        for unit in list(self.values()):
            self._detach(unit)
        self._slots = None
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
    beliefs: BeliefStore | None = None
    belief_backend: str = "sparse"  # dense | sparse | auto (storage only; no semantics)
    # Production: hot unit state lives in a UnitTable. False keeps it on the unit objects
    # (the object-authoritative reference engine, used by differential tests).
    table_mode: bool = True
    technology_table: "TechnologyTable | None" = None
    species_index: Mapping[str, int] = field(default_factory=dict)
    table: UnitTable | None = None

    def __post_init__(self) -> None:
        if self.beliefs is None:
            self.beliefs = make_belief_store(self.belief_backend, self.world.n_cells)
        if self.table is None and self.table_mode:
            self.table = UnitTable(self.technology_table)
        self.units = self.units  # wrap in a registry bound to the stores

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "units" and self.__dict__.get("beliefs") is not None:
            store, table = self.__dict__["beliefs"], self.__dict__.get("table")
            bound = isinstance(value, UnitRegistry) and value.store is store
            if not bound:
                value = UnitRegistry(store, value, table, self.__dict__.get("species_index"))
        object.__setattr__(self, name, value)

    @property
    def belief_store(self) -> BeliefStore:
        """The dense belief store (always present after construction)."""
        store = self.beliefs
        assert store is not None
        return store

    def _table_slots(self) -> IntArray | None:
        units = self.units
        if self.table is not None and isinstance(units, UnitRegistry):
            return units.slots()
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
            registry = state.units
            if table is not None and isinstance(registry, UnitRegistry):
                slots = registry.slots()
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
                registry = state.units
                assert isinstance(registry, UnitRegistry)
                columns = TableColumns(units, registry.slots(), table)
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
