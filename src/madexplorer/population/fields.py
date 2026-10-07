"""What state a population unit has: one declaration per field.

Every field of :class:`~madexplorer.population.unit.PopulationUnit` is declared once in
:data:`UNIT_FIELDS` with

- where it lives while the unit is registered (:class:`Storage`): a unit-table column or
  matrix, the belief store, or the unit object itself (irregular state);
- how it combines when two units merge and divides when one splits: the common
  :class:`Composition` classes (extensive, intensive), or a field-specific rule that
  :mod:`~madexplorer.population.composition` and :mod:`~madexplorer.population.lifecycle`
  implement explicitly.

The unit table's columns, the unit's row descriptors, the merge/split documentation
(``FIELD_RULES``) and the extensive/intensive field groups are all derived from this table,
so a new field (MVP 3: wealth, health, ...) cannot be added without declaring its storage
and its composition semantics. The test suite checks the declarations against the
dataclass. The domain object itself stays a hand-written dataclass.
"""

from dataclasses import dataclass
from enum import Enum


class Storage(Enum):
    """Where a registered unit's field lives."""

    FLOAT = "float"  # unit-table scalar column (float64)
    INT = "int"  # unit-table scalar column (int64)
    BOOL = "bool"  # unit-table scalar column
    COHORT = "cohort"  # unit-table age matrix with an exact population count
    KNOWLEDGE = "knowledge"  # unit-table domain matrix
    TECHNOLOGIES = "technologies"  # unit-table set column plus compiled bitmask
    BELIEFS = "beliefs"  # belief-store row
    STRATA = "strata"  # strata-table row: [U,S] state with its own schema (population.strata)
    OBJECT = "object"  # on the unit object (irregular: ids, maps, histories, ties)


SCALAR_STORAGE = (Storage.FLOAT, Storage.INT, Storage.BOOL)
TABLE_STORAGE = (*SCALAR_STORAGE, Storage.COHORT, Storage.KNOWLEDGE, Storage.TECHNOLOGIES)


class Composition(Enum):
    """Shared merge/split semantics (``SPECIFIC``: a rule of the field's own)."""

    EXTENSIVE = "extensive"  # merge: sum; split: proportional to people (conserved)
    INTENSIVE = "intensive"  # merge: population-weighted mean; split: copy
    SPECIFIC = "specific"


_SHARED_RULES = {
    Composition.EXTENSIVE: ("sum", "proportional to people"),
    Composition.INTENSIVE: ("population-weighted mean", "copy"),
}


@dataclass(frozen=True)
class UnitField:
    """One unit field: its storage and its merge and split rules."""

    name: str
    storage: Storage
    composition: Composition = Composition.SPECIFIC
    merge: str = ""  # field-specific rules only (shared ones are named by the composition)
    split: str = ""

    def __post_init__(self) -> None:
        shared = self.composition is not Composition.SPECIFIC
        if shared == bool(self.merge or self.split):
            raise ValueError(f"{self.name}: give merge/split rules exactly when specific")
        if shared and self.storage is not Storage.FLOAT:
            raise ValueError(f"{self.name}: shared compositions apply to float columns")

    @property
    def rules(self) -> tuple[str, str]:
        """``(merge rule, split rule)`` as documentation."""
        return _SHARED_RULES.get(self.composition, (self.merge, self.split))


def _extensive(name: str) -> UnitField:
    return UnitField(name, Storage.FLOAT, Composition.EXTENSIVE)


def _intensive(name: str) -> UnitField:
    return UnitField(name, Storage.FLOAT, Composition.INTENSIVE)


# In PopulationUnit's field order (checked by the test suite).
UNIT_FIELDS: tuple[UnitField, ...] = (
    UnitField("id", Storage.OBJECT, merge="keep target", split="new id"),
    UnitField("species_id", Storage.OBJECT, merge="must match", split="copy"),
    UnitField("cell", Storage.INT, merge="must match", split="copy"),
    UnitField(
        "females", Storage.COHORT, merge="vector sum", split="binomial draw per cohort (given)"
    ),
    UnitField(
        "males", Storage.COHORT, merge="vector sum", split="binomial draw per cohort (given)"
    ),
    UnitField(
        "reserve_kcal_per_capita",
        Storage.FLOAT,
        merge="conserve total",
        split="copy per-capita value (conserves total)",
    ),
    UnitField("founded_year", Storage.INT, merge="keep target", split="split year"),
    UnitField("parent_id", Storage.OBJECT, merge="keep target", split="parent id"),
    _extensive("energy_debt_kcal"),
    _extensive("harvest_kcal"),
    _intensive("food_ratio"),
    _intensive("energy_deficit"),
    UnitField(
        "beliefs",
        Storage.BELIEFS,
        merge="freshest observation per cell (fewer relays on ties)",
        split="copy",
    ),
    _intensive("food_log_prior"),
    _intensive("food_log_signal_var"),
    UnitField("report_cells", Storage.OBJECT, merge="union", split="copy"),
    UnitField("recent_residence", Storage.OBJECT, merge="latest year per cell", split="copy"),
    UnitField(
        "familiarity",
        Storage.OBJECT,
        merge="population-weighted mean of values decayed to the merge year (max per cell "
        "when familiarity_decay is off)",
        split="copy of the values decayed to the split year",
    ),
    UnitField(
        "groups",
        Storage.INT,
        merge="sum (aggregation) / keep target (fusion)",
        split="one group leaves a multi-group unit",
    ),
    UnitField("knowledge", Storage.KNOWLEDGE, merge="population-weighted mean", split="copy"),
    UnitField("technologies", Storage.TECHNOLOGIES, merge="union", split="copy"),
    _extensive("stores_kcal"),
    _extensive("fields_ha"),
    UnitField("ever_cultivated", Storage.BOOL, merge="or", split="copy"),
    _extensive("labor_debt_hours"),
    _extensive("farm_harvest_kcal"),
    _extensive("farm_hours"),
    _extensive("forage_harvest_kcal"),
    _extensive("forage_hours"),
    _intensive("forage_marginal_kcal_per_hour"),
    _intensive("forage_plant_share"),
    UnitField(
        "crop_yield_kcal_per_ha",
        Storage.FLOAT,
        merge="keep target (same cell and technology)",
        split="copy",
    ),
    _extensive("clearing_hours"),
    _extensive("stored_kcal"),
    UnitField("residence_years", Storage.INT, merge="keep target (the larger unit)", split="copy"),
    UnitField(
        "move_hazard",
        Storage.FLOAT,
        merge="population-weighted mean of known values (NaN if neither known)",
        split="copy",
    ),
    UnitField(
        "harvest_history",
        Storage.OBJECT,
        merge="population-weighted mean of aligned recent years",
        split="copy",
    ),
    UnitField(
        "trade_ties",
        Storage.OBJECT,
        merge="additive union, rewired network",
        split="stay with the parent (daughter unconnected)",
    ),
    UnitField(
        "strata",
        Storage.STRATA,
        merge="target's strata (MVP 3 Stage 1: both units hold one neutral stratum; "
        "differentiated fusion inheritance is Stage 2)",
        split="copy of the parent's strata as new components (fresh stratum ids)",
    ),
)


def names(
    *, storage: Storage | None = None, composition: Composition | None = None
) -> tuple[str, ...]:
    """Field names with the given storage and/or composition, in declaration order."""
    return tuple(
        f.name
        for f in UNIT_FIELDS
        if (storage is None or f.storage is storage)
        and (composition is None or f.composition is composition)
    )


FLOAT_FIELDS = names(storage=Storage.FLOAT)
INT_FIELDS = names(storage=Storage.INT)
BOOL_FIELDS = names(storage=Storage.BOOL)
TABLE_FIELDS = tuple(f.name for f in UNIT_FIELDS if f.storage in TABLE_STORAGE)
OBJECT_FIELDS = names(storage=Storage.OBJECT)  # always on the unit object
EXTENSIVE_FIELDS = names(composition=Composition.EXTENSIVE)
INTENSIVE_FIELDS = names(composition=Composition.INTENSIVE)
FIELD_RULES: dict[str, tuple[str, str]] = {f.name: f.rules for f in UNIT_FIELDS}
