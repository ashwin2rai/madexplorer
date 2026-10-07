"""Socioeconomic strata of population units: passive representation (MVP 3 Stages 1-2).

A stratum is one component of a unit's socioeconomic mixture: a population weight
(``share``), entitlement/control shares over the unit's physical stocks (``field_claim`` of
``fields_ha``, ``store_claim`` of ``stores_kcal``) and an opaque ``stratum_id``. Each column
is a partition of unity over the unit's strata; physical stocks stay unit-level. Design:
``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md``.

Strata are passive: no simulation mechanism reads them and they draw no random numbers. A
founded unit has one neutral stratum; heterogeneity arises only by fusion inheritance
(:func:`fuse_strata`), which keeps predecessor positions as distinct components. After a
structural change, :func:`normalize_strata` makes the representation canonical: exact
duplicate positions become one component (:func:`compact_exact_strata`, lossless), and only
then, above the run's capacity ``max_strata``, :func:`coalesce_to_capacity` approximates
(numerical resolution, not social dynamics). Adaptive merging below capacity is deferred
(design §M2). A claim
on an empty physical stock is the population share (:func:`claims_on_empty_stocks`). Stratum
ids are observational handles allocated by the owning
:class:`~madexplorer.population.store.PopulationStore`; they never enter equations, ordering
or tie-breaking.

The composition rules are defined once, here, as functions on :class:`StrataBlock`; the
table and object engines both apply them (``population.lifecycle``,
``population.composition``).

Two storage forms:

- :class:`StrataTable` (production): padded ``[rows, max_strata]`` columns row-aligned with
  the unit table's slots, plus the active count per row; a free row holds no strata. The
  width ``max_strata`` is fixed per run (``strata.max_strata``; owned by the
  :class:`~madexplorer.population.store.PopulationStore`).
- :class:`StrataBlock` (a detached unit, and the object-authoritative reference engine):
  the same columns as 1-D arrays of the active strata.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.population.table import GROWTH_FRACTION, MIN_CAPACITY

# Default run capacity (strata.max_strata): a numerical socioeconomic-resolution limit, not a
# number of classes (16 since Stage 4B.1; agrees with StrataConfig). The active count per row
# is int8, so capacities stay <= MAX_STRATA_LIMIT.
DEFAULT_MAX_STRATA = 16
MAX_STRATA_LIMIT = 127
DUPLICATE_CHUNK_ROWS = 1024  # rows per chunk of the pairwise exact-duplicate check
UNASSIGNED = -1  # stratum id of a stratum not yet bound to a store
PARTITION_TOLERANCE = 1e-12  # |sum - 1| allowed for a partition-of-unity column


@dataclass(frozen=True)
class StratumField:
    """One stratum column: float64, a partition of unity over a unit's strata.

    ``neutral`` is its value for the single stratum of an undifferentiated unit; unused
    (padding) entries hold 0. ``stock`` names the unit-level physical stock a claim column
    divides (``None`` for the population share).
    """

    name: str
    meaning: str
    neutral: float = 1.0
    stock: str | None = None


STRATUM_FIELDS: tuple[StratumField, ...] = (
    StratumField("share", "represented population mass / unit population (mixture weight)"),
    StratumField(
        "field_claim", "entitlement/control share of the unit's fields_ha", stock="fields_ha"
    ),
    StratumField(
        "store_claim", "entitlement/control share of the unit's stores_kcal", stock="stores_kcal"
    ),
)
STRATUM_COLUMNS: tuple[str, ...] = tuple(f.name for f in STRATUM_FIELDS)
CLAIMS: dict[str, str] = {f.name: f.stock for f in STRATUM_FIELDS if f.stock is not None}


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

    def is_valid(self, max_strata: int | None = None) -> bool:
        """At least one stratum (at most ``max_strata`` when given), positive shares, every
        column a partition of unity, no exact duplicate positions."""
        upper = max_strata if max_strata is not None else len(self)
        if not 1 <= len(self) <= upper or (self.columns["share"] <= 0).any():
            return False
        return all(
            (values >= 0).all() and abs(float(values.sum()) - 1.0) <= PARTITION_TOLERANCE
            for values in self.columns.values()
        ) and not has_exact_duplicates(self)


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
    parameters=("max_strata",),
    expected_domain="1 <= strata per unit <= max_strata; each column sums to 1; shares > 0",
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


def validate_block(
    block: StrataBlock, max_strata: int, *, allow_over_capacity: bool = False
) -> None:
    """Raise ``ValueError`` unless ``block`` is a valid set of strata.

    Valid: 1..max_strata strata (more only with ``allow_over_capacity``), finite values,
    positive shares, nonnegative claims, every column summing to 1 within
    ``PARTITION_TOLERANCE``.
    """
    n = len(block)
    if n < 1 or (n > max_strata and not allow_over_capacity):
        raise ValueError(f"a unit needs 1..{max_strata} strata, got {n}")
    if set(block.columns) != set(STRATUM_COLUMNS):
        raise ValueError(f"strata columns must be exactly {STRATUM_COLUMNS}")
    for name, values in block.columns.items():
        if values.shape != (n,) or not np.isfinite(values).all():
            raise ValueError(f"{name}: expected {n} finite values")
        if (values < 0).any() or (name == "share" and (values <= 0).any()):
            raise ValueError(f"{name}: shares must be > 0 and claims >= 0")
        if abs(float(values.sum()) - 1.0) > PARTITION_TOLERANCE:
            raise ValueError(f"{name}: must sum to 1, got {float(values.sum())!r}")


def positions(block: StrataBlock) -> FloatArray:
    """Relative socioeconomic positions ``claim / share`` per stratum, ``(n, claims)``.

    1 is a proportional (equal per-capita) position.
    """
    share = block.columns["share"]
    return np.stack([block.columns[name] / share for name in CLAIMS], axis=1)


@model_rule(
    name="strata_fusion_inheritance",
    version="1.0",
    rationale=(
        "When units fuse, each predecessor stratum stays a distinct component and keeps its "
        "absolute position: population mass share * N, and for each claim the absolute "
        "control claim * predecessor stock (fields_ha, stores_kcal) taken before the stocks "
        "combine. Shares and claims are those absolutes normalized by the fused totals; a "
        "claim column whose fused stock is zero falls back to the population shares "
        "(claim_zero_stock). Physical stocks themselves combine by the unit rules; strata only "
        "describe control over them. A merger of groups with different resources per person "
        "therefore produces differentiated positions (a representation of existing "
        "differences, not a class distinction). Passive in MVP 3 Stage 2."
    ),
    source_type="theoretical",
    parameters=(),
    expected_domain="concatenated strata; shares > 0; each column sums to 1",
    known_limitations=(
        "Predecessors without people contribute no strata (their stocks pass to the others' "
        "claims); no blending of similar components (adaptive merging is MVP 3 Stage 4)."
    ),
)
def fuse_strata(parts: Sequence[tuple[StrataBlock, float, Sequence[float]]]) -> StrataBlock:
    """Strata of a fused unit, before capacity coalescence (ids preserved).

    ``parts`` are each predecessor's ``(strata, population, stocks)``, with ``stocks`` in
    :data:`CLAIMS` order, all read before the predecessors' state is combined.
    """
    kept = [(block, float(n), stocks) for block, n, stocks in parts if n > 0]
    if not kept:
        raise ValueError("fusion needs a predecessor with people")
    mass = np.concatenate([block.columns["share"] * n for block, n, _ in kept])
    share = mass / mass.sum()
    columns = {"share": share}
    for k, name in enumerate(CLAIMS):
        weight = np.concatenate([block.columns[name] * stocks[k] for block, _, stocks in kept])
        total = weight.sum()
        columns[name] = weight / total if total > 0 else share.copy()
    ids = np.concatenate([block.stratum_id for block, _, _ in kept])
    return StrataBlock(columns, ids)


@dataclass(frozen=True)
class Coalescence:
    """One capacity coalescence: two components replaced by their sum (observation only).

    Representation-error diagnostics of the merge, with ``w = s_i s_j / (s_i + s_j)``:
    ``field_error = w * (field position gap)^2``, ``store_error = w * (store position
    gap)^2`` and ``cost = w * (sum of both squared gaps)``, the combined error the pair was
    chosen by (equal to ``field_error + store_error`` up to rounding). Never read by the
    simulation.
    """

    merged_ids: tuple[int, int]
    new_id: int
    cost: float  # combined population-weighted squared position error introduced
    field_error: float = 0.0
    store_error: float = 0.0


@model_rule(
    name="strata_capacity_coalescence",
    version="1.0",
    rationale=(
        "Numerical-resolution rule, not social dynamics: while a unit has more than "
        "max_strata strata, the pair whose merger adds the least population-weighted squared "
        "position error, s_i s_j / (s_i + s_j) * |p_i - p_j|^2 with p = (field_claim, "
        "store_claim) / share, is replaced by one component with summed share and claims (its "
        "position is the population-weighted centroid; totals are conserved exactly) and a "
        "fresh id. Pairs are compared in a canonical order of their state values, so neither "
        "ids nor storage order choose the pair."
    ),
    source_type="theoretical",
    parameters=("max_strata",),
    expected_domain="at most max_strata strata; column totals unchanged",
    known_limitations=(
        "Greedy (one pair at a time); distance in the two Stage 2 positions with equal "
        "weights (mechanism-agnostic; design §M6, §N7). Only enforces capacity: components "
        "below max_strata are never merged here."
    ),
)
def coalesce_to_capacity(
    block: StrataBlock, new_ids: Callable[[int], IntArray], capacity: int
) -> tuple[StrataBlock, list[Coalescence]]:
    """Coalesce the cheapest pairs until at most ``capacity`` strata remain. Lifecycle code
    calls :func:`normalize_strata`, which compacts exact duplicates first.

    Vectorized form of :func:`coalesce_to_capacity_reference`, bit-identical to it: the
    same canonical pair order (state values; ties keep the first pair in that order), the
    same costs and the same sums. Squares go through ``pow`` (an exponent array: NumPy's
    scalar-exponent path would square by multiplication), like the reference's ``x ** 2``.
    """
    columns = {name: list(values.tolist()) for name, values in block.columns.items()}
    ids = block.stratum_id.tolist()
    records: list[Coalescence] = []
    while len(ids) > capacity:
        share, field, store = (np.array(columns[name]) for name in STRATUM_COLUMNS)
        order = np.lexsort((store, field, share))  # canonical: by state only (stable)
        s = share[order]
        a, b = np.triu_indices(len(ids), 1)  # pairs in the reference's nested-loop order
        s_a, s_b = s[a], s[b]
        two = np.full(a.size, 2.0)
        gaps = [
            np.power(values[order][a] / s_a - values[order][b] / s_b, two)
            for values in (field, store)
        ]
        weight = s_a * s_b / (s_a + s_b)
        costs = weight * (gaps[0] + gaps[1])
        best = int(np.argmin(costs))  # first minimum, as the reference's strict "<"
        i, j = int(order[a[best]]), int(order[b[best]])
        (new_id,) = new_ids(1).tolist()
        records.append(
            Coalescence(
                (ids[i], ids[j]),
                new_id,
                float(costs[best]),
                float(weight[best] * gaps[0][best]),
                float(weight[best] * gaps[1][best]),
            )
        )
        for values in columns.values():
            merged = values[i] + values[j]
            del values[max(i, j)], values[min(i, j)]
            values.append(merged)
        del ids[max(i, j)], ids[min(i, j)]
        ids.append(new_id)
    coalesced = StrataBlock(
        {name: np.array(values) for name, values in columns.items()},
        np.array(ids, dtype=np.int64),
    )
    return coalesced, records


def coalesce_to_capacity_reference(
    block: StrataBlock, new_ids: Callable[[int], IntArray], capacity: int
) -> tuple[StrataBlock, list[Coalescence]]:
    """Scalar reference of :func:`coalesce_to_capacity` (the Stage 2 implementation), kept
    as its differential oracle (tests only)."""
    columns = {name: list(values.tolist()) for name, values in block.columns.items()}
    ids = block.stratum_id.tolist()
    records: list[Coalescence] = []
    while len(ids) > capacity:
        state = list(zip(*(columns[name] for name in STRATUM_COLUMNS), strict=True))
        order = sorted(range(len(ids)), key=lambda k: state[k])  # canonical: by state only
        best: tuple[float, int, int] | None = None
        for a, i in enumerate(order):
            for j in order[a + 1 :]:
                si, sj = columns["share"][i], columns["share"][j]
                distance = sum(
                    (columns[name][i] / si - columns[name][j] / sj) ** 2 for name in CLAIMS
                )
                cost = si * sj / (si + sj) * distance
                if best is None or cost < best[0]:
                    best = (cost, i, j)
        assert best is not None
        cost, i, j = best
        si, sj = columns["share"][i], columns["share"][j]
        weight = si * sj / (si + sj)
        field_error, store_error = (
            weight * (columns[name][i] / si - columns[name][j] / sj) ** 2 for name in CLAIMS
        )
        (new_id,) = new_ids(1).tolist()
        records.append(Coalescence((ids[i], ids[j]), new_id, cost, field_error, store_error))
        for values in columns.values():
            merged = values[i] + values[j]
            del values[max(i, j)], values[min(i, j)]
            values.append(merged)
        del ids[max(i, j)], ids[min(i, j)]
        ids.append(new_id)
    coalesced = StrataBlock(
        {name: np.array(values) for name, values in columns.items()},
        np.array(ids, dtype=np.int64),
    )
    return coalesced, records


@dataclass(frozen=True)
class Compaction:
    """Exact duplicates replaced by one component (observation only)."""

    merged_ids: tuple[int, ...]
    new_id: int
    position: tuple[float, ...]  # the shared (field, store) position


@model_rule(
    name="strata_exact_compaction",
    version="1.0",
    rationale=(
        "Representation identity rule, not a social mechanism: strata encode socioeconomic "
        "positions, not lineages, so components of one unit whose positions (claim / share "
        "for every claim) are exactly equal in floating point carry no additional modeled "
        "information. They are replaced by one component with summed share and claims "
        "(same position, totals conserved) and a fresh id. Lossless; applied before capacity "
        "coalescence so that no approximation is spent on redundant components. No "
        "tolerance: nearly equal positions stay separate (adaptive merging is MVP 3 Stage 4)."
    ),
    source_type="theoretical",
    parameters=(),
    expected_domain="at most one component per exact position in a unit",
    known_limitations=(
        "Mathematically equal positions with different arithmetic histories can differ in the "
        "last bits and are then not compacted; a merged component's recomputed position can "
        "itself shift by a last bit (passes repeat until no exact duplicate remains)."
    ),
)
def compact_exact_strata(
    block: StrataBlock, new_ids: Callable[[int], IntArray]
) -> tuple[StrataBlock, list[Compaction]]:
    """Merge components with exactly equal positions until none remain (the same block if
    there are none).

    A merged component's position, recomputed from summed claims and shares, can differ from
    its members' in the last bit and then coincide exactly with another component, so passes
    repeat; each pass removes at least one component.
    """
    records: list[Compaction] = []
    while True:
        block, found = _compact_once(block, new_ids)
        if not found:
            return block, records
        records += found


def _compact_once(
    block: StrataBlock, new_ids: Callable[[int], IntArray]
) -> tuple[StrataBlock, list[Compaction]]:
    """One pass: groups keep the storage order of their first member; each group is summed
    in an order sorted by state values, so storage order and ids cannot change the result."""
    if len(block) == 1:
        return block, []
    keys = [tuple(row) for row in positions(block).tolist()]
    groups: dict[tuple[float, ...], list[int]] = {}
    for k, key in enumerate(keys):
        groups.setdefault(key, []).append(k)
    if len(groups) == len(block):
        return block, []
    columns: dict[str, list[float]] = {name: [] for name in STRATUM_COLUMNS}
    ids: list[int] = []
    records: list[Compaction] = []
    for key, members in groups.items():
        if len(members) == 1:
            (k,) = members
            for name in STRATUM_COLUMNS:
                columns[name].append(float(block.columns[name][k]))
            ids.append(int(block.stratum_id[k]))
            continue
        members = sorted(
            members, key=lambda k: tuple(float(block.columns[n][k]) for n in STRATUM_COLUMNS)
        )
        for name in STRATUM_COLUMNS:
            total = 0.0
            for k in members:
                total += float(block.columns[name][k])
            columns[name].append(total)
        (new_id,) = new_ids(1).tolist()
        ids.append(new_id)
        records.append(Compaction(tuple(int(block.stratum_id[k]) for k in members), new_id, key))
    compacted = StrataBlock(
        {name: np.array(values) for name, values in columns.items()},
        np.array(ids, dtype=np.int64),
    )
    return compacted, records


def normalize_strata(
    block: StrataBlock, new_ids: Callable[[int], IntArray], max_strata: int
) -> tuple[StrataBlock, list[Compaction | Coalescence]]:
    """The canonical strata of a unit after a structural change: exact compaction first
    (lossless), then, only while more than ``max_strata`` remain, one capacity coalescence
    at a time, each followed by exact compaction (a merged position may equal another's)."""
    block, compactions = compact_exact_strata(block, new_ids)
    records: list[Compaction | Coalescence] = list(compactions)
    while len(block) > max_strata:
        block, coalesced = coalesce_to_capacity(block, new_ids, capacity=len(block) - 1)
        block, compactions = compact_exact_strata(block, new_ids)
        records += [*coalesced, *compactions]
    return block, records


def has_exact_duplicates(block: StrataBlock) -> bool:
    """Whether two components share an exactly equal position."""
    keys = [tuple(row) for row in positions(block).tolist()]
    return len(set(keys)) < len(keys)


@model_rule(
    name="claim_zero_stock",
    version="1.0",
    rationale=(
        "A claim on a physical stock that does not exist carries no position: when a unit's "
        "fields_ha (stores_kcal) is zero, every stratum's field (store) claim equals its "
        "population share. While a stock stays positive, its claim fractions persist "
        "unchanged as its size changes (passive carry-forward until a mechanism allocates "
        "new stock, MVP 3 Stage 3). The representation therefore never invents inequality."
    ),
    source_type="theoretical",
    parameters=(),
    expected_domain="claim = share wherever the stock is zero",
    known_limitations="Applied after each subsystem's apply, the granularity of stock changes.",
)
def claims_on_empty_stocks(block: StrataBlock, stocks: Sequence[float]) -> StrataBlock:
    """``block`` with each claim on a zero stock (``stocks`` in :data:`CLAIMS` order) reset to
    the population shares; the same block if nothing changes."""
    empty = [name for name, stock in zip(CLAIMS, stocks, strict=True) if stock == 0]
    if len(block) == 1 or not empty:
        return block
    columns = {name: values.copy() for name, values in block.columns.items()}
    for name in empty:
        columns[name] = columns["share"].copy()
    return StrataBlock(columns, block.stratum_id.copy())


class StrataTable:
    """Strata of registered units: ``[capacity, max_strata]`` columns row-aligned with unit
    slots.

    Row ``r`` belongs to the unit in slot ``r``; its active strata are columns
    ``0 .. n_strata[r] - 1`` (compacted). A reset row has ``n_strata == 0``, zero columns and
    unassigned ids, so nothing can leak into a unit that later reuses the slot. The width
    ``max_strata`` is fixed for the table's life (one run).
    """

    def __init__(self, max_strata: int = DEFAULT_MAX_STRATA) -> None:
        if not 1 <= max_strata <= MAX_STRATA_LIMIT:
            raise ValueError(f"max_strata must be in 1..{MAX_STRATA_LIMIT}, got {max_strata}")
        self.max_strata = max_strata
        self.capacity = 0
        self.columns: dict[str, FloatArray] = {
            name: np.zeros((0, max_strata)) for name in STRATUM_COLUMNS
        }
        self.stratum_id: IntArray = np.full((0, max_strata), UNASSIGNED, dtype=np.int64)
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
        if not 1 <= n <= self.max_strata:
            raise ValueError(f"a unit needs 1..{self.max_strata} strata, got {n}")
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

    def reset_empty_claims(self, slots: IntArray, stocks: dict[str, FloatArray]) -> IntArray:
        """:func:`claims_on_empty_stocks` for the rows ``slots``; ``stocks`` maps each claim
        column to the rows' physical stock (single-stratum rows are always neutral). Returns
        the rows that changed, in the order of ``slots``."""
        differentiated = self.n_strata[slots] > 1
        changed = np.zeros(slots.size, dtype=bool)
        if not differentiated.any():
            return slots[changed]
        for name, stock in stocks.items():
            candidates = np.flatnonzero(differentiated & (stock == 0))
            if candidates.size == 0:
                continue
            rows = slots[candidates]
            share = self.columns["share"][rows]
            moved = (self.columns[name][rows] != share).any(axis=1)  # only actual changes
            if moved.any():
                self.columns[name][rows[moved]] = share[moved]
                changed[candidates[moved]] = True
        return slots[changed]

    def check(self, slots: IntArray) -> BoolArray:
        """Per slot: 1..max_strata strata with assigned ids, positive shares, zero padding,
        every column a partition of unity, and no exact duplicate positions. Rows are
        checked in chunks, so temporaries stay bounded."""
        ok = np.empty(slots.size, dtype=bool)
        for start in range(0, slots.size, DUPLICATE_CHUNK_ROWS):
            chunk = slots[start : start + DUPLICATE_CHUNK_ROWS]
            ok[start : start + chunk.size] = self._check_rows(chunk)
        ok &= ~self.duplicate_rows(slots)  # no two components at exactly the same position
        return ok

    def _check_rows(self, slots: IntArray) -> BoolArray:
        n = self.n_strata[slots].astype(np.int64)
        active = np.arange(self.max_strata)[None, :] < n[:, None]
        ids = self.stratum_id[slots]
        ok: BoolArray = (n >= 1) & (n <= self.max_strata)
        ok &= np.where(active, ids != UNASSIGNED, ids == UNASSIGNED).all(axis=1)
        ok &= np.where(active, self.columns["share"][slots] > 0, True).all(axis=1)
        for values in self.columns.values():
            rows = values[slots]
            ok &= np.where(active, rows >= 0, rows == 0).all(axis=1)
            ok &= np.abs(rows.sum(axis=1) - 1.0) <= PARTITION_TOLERANCE
        return ok

    def duplicate_rows(self, slots: IntArray) -> BoolArray:
        """Per slot: whether two active strata sit at exactly the same position.

        Exact (no tolerance) pairwise comparison, only for rows with at least two strata, in
        chunks of ``DUPLICATE_CHUNK_ROWS`` rows and only over the chunk's largest active
        count ``k``: temporaries are ``[chunk, k, k]``, bounded independently of the number
        of units and of ``max_strata``.
        """
        duplicated = np.zeros(slots.size, dtype=bool)
        multi = np.flatnonzero(self.n_strata[slots] > 1)
        for start in range(0, multi.size, DUPLICATE_CHUNK_ROWS):
            where = multi[start : start + DUPLICATE_CHUNK_ROWS]
            rows = slots[where]
            n = self.n_strata[rows].astype(np.int64)
            k = int(n.max())
            active = np.arange(k)[None, :] < n[:, None]
            share = np.where(active, self.columns["share"][rows, :k], 1.0)
            same = active[:, :, None] & active[:, None, :] & ~np.eye(k, dtype=bool)[None]
            for name in CLAIMS:
                position = self.columns[name][rows, :k] / share
                same &= position[:, :, None] == position[:, None, :]
            duplicated[where] = same.any(axis=(1, 2))
        return duplicated
