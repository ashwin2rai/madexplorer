"""The single owner of population state (performance layer; no model semantics).

:class:`PopulationStore` owns every representation of the population that must stay
consistent with every other:

- ``units``: the :class:`UnitRegistry`, unit identities in stable insertion order (the
  semantic processing order);
- ``table``: the authoritative :class:`~madexplorer.population.table.UnitTable` of hot
  numeric unit state (``None`` in the object-authoritative reference engine, which keeps
  that state on the unit objects for differential tests);
- ``beliefs``: the belief store (dense or sparse backend; storage only);
- ``strata``: the :class:`~madexplorer.population.strata.StrataTable` of socioeconomic
  strata (MVP 3), present exactly when ``table`` is (the reference engine keeps each unit's
  strata on the object), and the counter of opaque stratum ids;
- storage-slot allocation, shared by the tables and the belief store.

A unit belongs to at most one store: inserting a unit still bound to another store raises
(remove it there first; ownership never moves implicitly). Inserting a unit into ``units``
binds it to a slot: its beliefs move into the belief store and, with a table, its table
fields (``population.fields``) and strata into its table rows; its strata get fresh ids from
this store (ids are per-store observational handles). Removing it
copies that state back onto the object and frees the slot, which is reset before reuse;
:meth:`UnitRegistry.discard` frees it without copying (a unit leaving the simulation).
Reads are plain dict operations. Slots never define iteration order;
:meth:`UnitRegistry.slots` gives the slots in insertion order.
"""

import copy
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.beliefs import BeliefStore, make_belief_store
from madexplorer.population.strata import StrataTable
from madexplorer.population.table import UnitTable
from madexplorer.population.unit import PopulationUnit, attach_unit, belief_slot, detach_unit

if TYPE_CHECKING:
    from madexplorer.core.compiled import TechnologyTable


class PopulationStore:
    """Units, their table rows and belief rows, and the slots that tie them together."""

    def __init__(
        self,
        n_cells: int,
        *,
        belief_backend: str = "sparse",
        table: bool = True,
        technology_table: "TechnologyTable | None" = None,
        species_index: Mapping[str, int] | None = None,
    ) -> None:
        self.beliefs: BeliefStore = make_belief_store(belief_backend, n_cells)
        self.table: UnitTable | None = UnitTable(technology_table) if table else None
        self.strata: StrataTable | None = StrataTable() if table else None
        self._next_stratum_id = 0
        self.species_index = dict(species_index or {})
        self._free: list[int] = []
        self._next_slot = 0
        self.units = UnitRegistry(self)

    def _allocate(self) -> int:
        if self._free:
            return self._free.pop()
        slot = self._next_slot
        self._next_slot += 1
        return slot

    def new_stratum_ids(self, n: int) -> IntArray:
        """``n`` unused opaque stratum ids (never the unit id allocator; no randomness)."""
        ids = np.arange(self._next_stratum_id, self._next_stratum_id + n, dtype=np.int64)
        self._next_stratum_id += n
        return ids

    def claim_slot(self, species_code: int = 0) -> int:
        """A free slot with addressable table and belief rows, for a unit built in place
        (``population.lifecycle``); the unit is then inserted already bound to it."""
        slot = self._allocate()
        if self.table is not None:
            assert self.strata is not None
            self.table.ensure(slot, 0, 0)
            self.strata.ensure(slot)
        self.beliefs.claim(slot, species_code)
        return slot

    def check_insertable(self, unit: PopulationUnit) -> None:
        """Raise unless ``unit`` is detached or already bound to this store's rows.

        A unit belongs to at most one store: to move it, remove it from its store first.
        """
        state = unit.__dict__
        store = state.get("_belief_store")
        if store is not None and (
            store is not self.beliefs or state.get("_table") is not self.table
        ):
            raise ValueError(
                f"unit {unit.id} is already bound to another PopulationStore; remove it from "
                "that store before inserting it here"
            )

    def _bind(self, unit: PopulationUnit) -> None:
        self.check_insertable(unit)
        if unit.__dict__.get("_belief_store") is not None:
            return  # already ours (built in place, or restored by deepcopy with this store)
        code = self.species_index.get(unit.species_id, 0)
        unit.strata = unit.strata.with_ids(self.new_stratum_ids(len(unit.strata)))
        attach_unit(unit, self._allocate(), self.beliefs, self.table, code, self.strata)

    def _unbind(self, unit: PopulationUnit) -> None:
        slot = detach_unit(unit)
        if slot >= 0:
            self._free.append(slot)

    def _free_rows(self, unit: PopulationUnit) -> None:
        """Reset and free a unit's rows without copying its state back."""
        state = unit.__dict__
        if state.get("_belief_store") is None:
            return
        slot: int = state["_slot"]
        if self.table is not None:
            assert self.strata is not None
            self.table.reset(slot)
            self.strata.reset(slot)
        self.beliefs.release(slot)
        state["_table"], state["_belief_store"], state["_slot"] = None, None, -1
        state.pop("_strata", None)
        self._free.append(slot)


class UnitRegistry(dict[str, PopulationUnit]):
    """``state.units``: the store's units in stable insertion order (see module docstring).

    Every mutation binds or unbinds the unit's rows through the owning
    :class:`PopulationStore`.
    """

    def __init__(self, owner: PopulationStore) -> None:
        super().__init__()
        self.owner = owner
        self._slots: IntArray | None = None

    def __deepcopy__(self, memo: dict[int, Any]) -> "UnitRegistry":
        # Copied units stay bound to the copied owner's rows (same slots), so they are
        # inserted without rebinding; the owner may still be under construction here.
        copied = UnitRegistry.__new__(UnitRegistry)
        memo[id(self)] = copied
        copied.owner = copy.deepcopy(self.owner, memo)
        copied._slots = None
        dict.update(copied, {uid: copy.deepcopy(u, memo) for uid, u in self.items()})
        return copied

    def slots(self) -> IntArray:
        """Storage slots of the registered units, in insertion (processing) order."""
        cached = self._slots
        if cached is None:
            cached = np.array([belief_slot(u) for u in self.values()], dtype=np.int64)
            self._slots = cached
        return cached

    def discard(self, unit_id: str) -> PopulationUnit:
        """Remove a unit and free its rows *without* copying its state back onto the object.

        For units that leave the simulation for good (absorbed, extinct): the returned
        object keeps only its external fields (id, species, ties, ...); its table fields
        and beliefs are gone.
        """
        unit = super().pop(unit_id)
        self._slots = None
        self.owner._free_rows(unit)
        return unit

    def __setitem__(self, unit_id: str, unit: PopulationUnit) -> None:
        self.owner.check_insertable(unit)  # before anything is mutated
        previous = self.get(unit_id)
        if previous is not None and previous is not unit:
            self.owner._unbind(previous)
        self.owner._bind(unit)
        self._slots = None
        super().__setitem__(unit_id, unit)

    def __delitem__(self, unit_id: str) -> None:
        unit = self[unit_id]
        super().__delitem__(unit_id)
        self._slots = None
        self.owner._unbind(unit)

    def pop(self, unit_id: str, *default: PopulationUnit) -> PopulationUnit:  # type: ignore[override]
        """Remove and return a unit (its state is copied back onto the object)."""
        if unit_id not in self:
            if default:
                return default[0]
            raise KeyError(unit_id)
        unit = super().pop(unit_id)
        self._slots = None
        self.owner._unbind(unit)
        return unit

    def popitem(self) -> tuple[str, PopulationUnit]:
        """Remove and return the last unit."""
        unit_id, unit = super().popitem()
        self._slots = None
        self.owner._unbind(unit)
        return unit_id, unit

    def clear(self) -> None:
        """Remove every unit."""
        for unit in list(self.values()):
            self.owner._unbind(unit)
        self._slots = None
        super().clear()

    def update(self, *args: Any, **kwargs: PopulationUnit) -> None:
        """Insert units one by one (so each gets a slot), after checking that all can be."""
        units = dict(*args, **kwargs)
        for unit in units.values():
            self.owner.check_insertable(unit)
        for unit_id, unit in units.items():
            self[unit_id] = unit

    def setdefault(self, unit_id: str, unit: PopulationUnit) -> PopulationUnit:
        """Insert ``unit`` if ``unit_id`` is absent; return the registered unit."""
        if unit_id not in self:
            self[unit_id] = unit
        return self[unit_id]
