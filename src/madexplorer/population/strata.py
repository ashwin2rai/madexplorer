"""Socioeconomic strata of population units: representation only (MVP 3 Stage 1).

A stratum is one component of a unit's socioeconomic mixture: a population weight
(``share``), entitlement/control shares over the unit's physical stocks (``field_claim`` of
``fields_ha``, ``store_claim`` of ``stores_kcal``) and an opaque ``stratum_id``. Each column
is a partition of unity over the unit's strata; physical stocks stay unit-level. Design:
``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md``.

Stage 1 is a passive numerical representation: every unit has exactly one neutral stratum,
no mechanism reads strata, and they draw no random numbers. Stratum ids are observational
handles, allocated by the owning :class:`~madexplorer.population.store.PopulationStore`
when a unit is bound to it; they never enter equations, ordering or tie-breaking.

Two storage forms:

- :class:`StrataTable` (production): padded ``[capacity, S_MAX]`` columns row-aligned with
  the unit table's slots, plus the active count per row; a free row holds no strata.
- :class:`StrataBlock` (a detached unit, and the object-authoritative reference engine):
  the same columns as 1-D arrays of the active strata.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.population.table import GROWTH_FRACTION, MIN_CAPACITY

S_MAX = 8  # numerical socioeconomic-resolution limit, not a number of classes
UNASSIGNED = -1  # stratum id of a stratum not yet bound to a store
PARTITION_TOLERANCE = 1e-12  # |sum - 1| allowed for a partition-of-unity column


@dataclass(frozen=True)
class StratumField:
    """One stratum column: float64, a partition of unity over a unit's strata.

    ``neutral`` is its value for the single stratum of an undifferentiated unit; unused
    (padding) entries hold 0.
    """

    name: str
    meaning: str
    neutral: float = 1.0


STRATUM_FIELDS: tuple[StratumField, ...] = (
    StratumField("share", "represented population mass / unit population (mixture weight)"),
    StratumField("field_claim", "entitlement/control share of the unit's fields_ha"),
    StratumField("store_claim", "entitlement/control share of the unit's stores_kcal"),
)
STRATUM_COLUMNS: tuple[str, ...] = tuple(f.name for f in STRATUM_FIELDS)


@dataclass(eq=False)
class StrataBlock:
    """A unit's active strata as 1-D arrays (one entry per stratum)."""

    columns: dict[str, FloatArray]
    stratum_id: IntArray

    @classmethod
    def neutral(cls) -> "StrataBlock":
        """One undifferentiated stratum (id unassigned until the unit is bound)."""
        return neutral_strata()

    def __len__(self) -> int:
        return int(self.stratum_id.size)

    def unassigned_copy(self) -> "StrataBlock":
        """The same strata as new components (fission): ids are assigned on binding."""
        return StrataBlock(
            {name: values.copy() for name, values in self.columns.items()},
            np.full(len(self), UNASSIGNED, dtype=np.int64),
        )

    def with_ids(self, ids: IntArray) -> "StrataBlock":
        """These strata with the given ids."""
        return StrataBlock({k: v.copy() for k, v in self.columns.items()}, ids.copy())

    def is_neutral(self) -> bool:
        """Exactly one stratum holding the neutral values."""
        return len(self) == 1 and all(
            float(self.columns[f.name][0]) == f.neutral for f in STRATUM_FIELDS
        )

    def is_valid(self) -> bool:
        """At least one stratum, positive shares, every column a partition of unity."""
        if not 1 <= len(self) <= S_MAX or (self.columns["share"] <= 0).any():
            return False
        return all(
            (values >= 0).all() and abs(float(values.sum()) - 1.0) <= PARTITION_TOLERANCE
            for values in self.columns.values()
        )


@model_rule(
    name="stratum_composition",
    version="1.0",
    rationale=(
        "Representation, not a claim that societies are homogeneous: a unit's socioeconomic "
        "state is approximated by a small mixture of strata, each with a population share and "
        "entitlement/control shares over the unit's physical stocks. All strata share the "
        "unit's age-sex structure (P(age, sex, stratum) = P(age, sex) * share), so births and "
        "deaths do not change shares. A unit without socioeconomic history has one neutral "
        "stratum (share = field_claim = store_claim = 1), which no mechanism reads in MVP 3 "
        "Stage 1."
    ),
    source_type="theoretical",
    parameters=("S_MAX",),
    expected_domain="1 <= strata per unit <= S_MAX; each column sums to 1; shares > 0",
    known_limitations=(
        "No correlation between socioeconomic position and age or sex; no stratum-specific "
        "vital rates. Stage 1 strata are passive."
    ),
)
def neutral_strata() -> StrataBlock:
    """The strata of a unit without socioeconomic history: one neutral component."""
    return StrataBlock(
        {f.name: np.array([f.neutral]) for f in STRATUM_FIELDS},
        np.array([UNASSIGNED], dtype=np.int64),
    )


class StrataTable:
    """Strata of registered units: ``[capacity, S_MAX]`` columns row-aligned with unit slots.

    Row ``r`` belongs to the unit in slot ``r``; its active strata are columns
    ``0 .. n_strata[r] - 1`` (compacted). A reset row has ``n_strata == 0``, zero columns and
    unassigned ids, so nothing can leak into a unit that later reuses the slot.
    """

    def __init__(self) -> None:
        self.capacity = 0
        self.columns: dict[str, FloatArray] = {
            name: np.zeros((0, S_MAX)) for name in STRATUM_COLUMNS
        }
        self.stratum_id: IntArray = np.full((0, S_MAX), UNASSIGNED, dtype=np.int64)
        self.n_strata = np.zeros(0, dtype=np.int8)

    def ensure(self, slot: int) -> None:
        """Make row ``slot`` addressable (new rows hold no strata); grows like the unit table."""
        if slot < self.capacity:
            return
        old = self.capacity
        capacity = max(slot + 1, old + max(int(old * GROWTH_FRACTION), MIN_CAPACITY))

        def grow(array: Any, fill: float) -> Any:
            grown = np.full((capacity, *array.shape[1:]), fill, dtype=array.dtype)
            grown[:old] = array[:old]
            return grown

        for name in STRATUM_COLUMNS:
            self.columns[name] = grow(self.columns[name], 0.0)
        self.stratum_id = grow(self.stratum_id, UNASSIGNED)
        self.n_strata = grow(self.n_strata, 0)
        self.capacity = capacity

    @property
    def nbytes(self) -> int:
        """Bytes of all strata arrays."""
        total = sum(a.nbytes for a in self.columns.values())
        return int(total + self.stratum_id.nbytes + self.n_strata.nbytes)

    def reset(self, slot: int) -> None:
        """No strata in ``slot`` (a released or fresh row)."""
        for values in self.columns.values():
            values[slot] = 0.0
        self.stratum_id[slot] = UNASSIGNED
        self.n_strata[slot] = 0

    def load(self, slot: int, block: StrataBlock) -> None:
        """Write a unit's strata (ids included) into ``slot``."""
        n = len(block)
        if not 1 <= n <= S_MAX:
            raise ValueError(f"a unit needs 1..{S_MAX} strata, got {n}")
        self.ensure(slot)
        self.reset(slot)
        for name in STRATUM_COLUMNS:
            self.columns[name][slot, :n] = block.columns[name]
        self.stratum_id[slot, :n] = block.stratum_id
        self.n_strata[slot] = n

    def unload(self, slot: int) -> StrataBlock:
        """A copy of the strata in ``slot`` as a detached block."""
        n = int(self.n_strata[slot])
        return StrataBlock(
            {name: self.columns[name][slot, :n].copy() for name in STRATUM_COLUMNS},
            self.stratum_id[slot, :n].copy(),
        )

    def copy_row(self, source: int, target: int, ids: IntArray) -> None:
        """``target`` gets ``source``'s strata as new components with ``ids`` (fission)."""
        n = int(self.n_strata[source])
        if ids.size != n:
            raise ValueError("one new id per copied stratum")
        self.ensure(target)
        self.reset(target)
        for values in self.columns.values():
            values[target, :n] = values[source, :n]
        self.stratum_id[target, :n] = ids
        self.n_strata[target] = n

    def is_neutral(self, slot: int) -> bool:
        """Exactly one stratum holding the neutral values."""
        return int(self.n_strata[slot]) == 1 and all(
            float(self.columns[f.name][slot, 0]) == f.neutral for f in STRATUM_FIELDS
        )

    def check(self, slots: IntArray) -> BoolArray:
        """Per slot: 1..S_MAX strata with assigned ids, positive shares, zero padding, and
        every column a partition of unity."""
        n = self.n_strata[slots].astype(np.int64)
        active = np.arange(S_MAX)[None, :] < n[:, None]
        ids = self.stratum_id[slots]
        ok: BoolArray = (n >= 1) & (n <= S_MAX)
        ok &= np.where(active, ids != UNASSIGNED, ids == UNASSIGNED).all(axis=1)
        ok &= np.where(active, self.columns["share"][slots] > 0, True).all(axis=1)
        for values in self.columns.values():
            rows = values[slots]
            ok &= np.where(active, rows >= 0, rows == 0).all(axis=1)
            ok &= np.abs(rows.sum(axis=1) - 1.0) <= PARTITION_TOLERANCE
        return ok
