"""Energy balance: requirement, reserves, and nutritional deficit (spec §5.4, §8.2)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray
from madexplorer.population.strata_accounting import FoodAccounts
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import Metabolism, SpeciesProfile

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns


@model_rule(
    name="thermoregulation_cost",
    version="1.0",
    rationale=(
        "Energy requirement rises linearly with temperature outside the species comfort range."
    ),
    source_type="heuristic",
    parameters=("comfort_temp_low_c", "comfort_temp_high_c", "cold_cost_per_c", "heat_cost_per_c"),
    expected_domain="multiplier >= 1",
    known_limitations="Annual mean temperature only; clothing and shelter technology not modeled.",
)
def thermoregulation_multiplier(metabolism: Metabolism, temperature_c: float) -> float:
    """Multiplier on energy requirement from ambient temperature."""
    cold = max(0.0, metabolism.comfort_temp_low_c - temperature_c) * metabolism.cold_cost_per_c
    heat = max(0.0, temperature_c - metabolism.comfort_temp_high_c) * metabolism.heat_cost_per_c
    return 1.0 + cold + heat


def annual_need_kcal(
    unit: PopulationUnit, profile: SpeciesProfile, tables: LifeTables, temperature_c: float
) -> float:
    """Energy the unit requires this year, including carried-over energy debt."""
    adult_equivalents = unit.weighted_count(tables.need_fraction)
    daily = profile.metabolism.adult_daily_kcal
    need = (
        adult_equivalents
        * daily
        * 365.0
        * thermoregulation_multiplier(profile.metabolism, temperature_c)
    )
    return need + unit.energy_debt_kcal


def annual_need_columns(
    cols: "UnitColumns", state: SimulationState, ctx: StepContext
) -> FloatArray:
    """:func:`annual_need_kcal` for the rows of ``cols`` (same operations, bit-identical)."""
    compiled = ctx.compiled
    assert compiled is not None
    species = cols.species()
    adults = cols.weighted(
        {k: ctx.tables[sid].need_fraction for k, sid in enumerate(compiled.species_ids)}
    )
    temperature = state.climate.temperature_c[cols.get("cell")].astype(np.float64)
    p = compiled.parameter
    cold = (
        np.maximum(0.0, p("metabolism.comfort_temp_low_c")[species] - temperature)
        * p("metabolism.cold_cost_per_c")[species]
    )
    heat = (
        np.maximum(0.0, temperature - p("metabolism.comfort_temp_high_c")[species])
        * p("metabolism.heat_cost_per_c")[species]
    )
    need: FloatArray = adults * p("metabolism.adult_daily_kcal")[species] * 365.0 * (
        1.0 + cold + heat
    ) + cols.get("energy_debt_kcal")
    return need


def annual_need_batch(
    units: Sequence[PopulationUnit], state: SimulationState, ctx: StepContext
) -> FloatArray:
    """:func:`annual_need_columns` for given unit objects (reference and tests)."""
    from madexplorer.core.columns import ObjectColumns

    compiled = ctx.compiled
    assert compiled is not None
    cols = ObjectColumns(units, compiled.species_index, compiled.technologies)
    return annual_need_columns(cols, state, ctx)


@dataclass(frozen=True)
class EnergyBalance:
    """Outcome of one year's energy accounting for a group."""

    food_ratio: float  # harvest / requirement
    deficit: float  # unmet share of requirement after drawing on stores and reserves
    reserve_kcal: float  # body reserve after the year
    stores_kcal: float  # food stores after the year, before spoilage
    stored_kcal: float  # surplus put into storage this year
    spoiled_kcal: float  # surplus that could be neither eaten, stored, nor kept as body reserve


@model_rule(
    name="pooled_energy_balance",
    version="1.1",
    rationale=(
        "Food is shared within the group (forager pooling). Harvest covers requirement first; "
        "shortfalls draw on food stores, then body reserves. Surplus refills body reserves up to "
        "a physiological cap and then goes to storage if the group can store; otherwise it spoils. "
        "Any remaining shortfall is the energy deficit that drives starvation mortality."
    ),
    source_type="heuristic",
    parameters=("reserve_days_max",),
    expected_domain="deficit in [0, 1]; reserve in [0, cap]; stores >= 0",
    known_limitations="Equal sharing assumed; unequal intra-group access arrives with MVP 3.",
)
def energy_balance(
    need_kcal: float,
    harvest_kcal: float,
    reserve_kcal: float,
    reserve_cap_kcal: float,
    stores_kcal: float = 0.0,
    can_store: bool = False,
) -> EnergyBalance:
    """Account for one year of intake, requirement, reserves, and storage."""
    food_ratio = harvest_kcal / need_kcal if need_kcal > 0 else 1.0
    if harvest_kcal >= need_kcal:
        surplus = harvest_kcal - need_kcal
        to_reserve = min(surplus, max(reserve_cap_kcal - reserve_kcal, 0.0))
        leftover = surplus - to_reserve
        stored = leftover if can_store else 0.0
        return EnergyBalance(
            food_ratio,
            0.0,
            reserve_kcal + to_reserve,
            stores_kcal + stored,
            stored,
            leftover - stored,
        )
    shortfall = need_kcal - harvest_kcal
    from_stores = min(shortfall, stores_kcal)
    shortfall -= from_stores
    from_reserve = min(shortfall, reserve_kcal)
    shortfall -= from_reserve
    return EnergyBalance(
        food_ratio,
        shortfall / need_kcal,
        reserve_kcal - from_reserve,
        stores_kcal - from_stores,
        0.0,
        0.0,
    )


def energy_balance_batch(
    need_kcal: FloatArray,
    harvest_kcal: FloatArray,
    reserve_kcal: FloatArray,
    reserve_cap_kcal: FloatArray,
    stores_kcal: FloatArray,
    can_store: BoolArray,
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray, FloatArray, FloatArray]:
    """:func:`energy_balance` for many units at once, elementwise and bit-identical.

    Returns ``(food_ratio, deficit, reserve, stores, stored, spoiled)`` arrays. Both
    branches use the scalar rule's operations in the same order (differential test).
    """
    food_ratio = np.divide(
        harvest_kcal, need_kcal, out=np.ones_like(need_kcal), where=need_kcal > 0
    )
    fed = harvest_kcal >= need_kcal
    # Surplus branch.
    surplus = harvest_kcal - need_kcal
    to_reserve = np.minimum(surplus, np.maximum(reserve_cap_kcal - reserve_kcal, 0.0))
    leftover = surplus - to_reserve
    stored = np.where(can_store, leftover, 0.0)
    # Shortfall branch.
    shortfall = need_kcal - harvest_kcal
    from_stores = np.minimum(shortfall, stores_kcal)
    shortfall = shortfall - from_stores
    from_reserve = np.minimum(shortfall, reserve_kcal)
    shortfall = shortfall - from_reserve
    unmet = np.divide(shortfall, need_kcal, out=np.zeros_like(need_kcal), where=~fed)
    return (
        food_ratio,
        np.where(fed, 0.0, unmet),
        np.where(fed, reserve_kcal + to_reserve, reserve_kcal - from_reserve),
        np.where(fed, stores_kcal + stored, stores_kcal - from_stores),
        np.where(fed, stored, 0.0),
        np.where(fed, leftover - stored, 0.0),
    )


@dataclass(frozen=True)
class EnergyUpdate:
    """New nutritional and storage state of one unit (reference form of :class:`EnergyUpdates`)."""

    unit_id: str
    need_kcal: float
    balance: EnergyBalance
    storage_retention: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the unit's energy state; stores spoil at the end of the year."""
        b = self.balance
        _commit_energy(
            state.units[self.unit_id],
            ctx,
            self.need_kcal,
            b.food_ratio,
            b.deficit,
            b.reserve_kcal,
            b.stores_kcal,
            b.stored_kcal,
            b.spoiled_kcal,
            self.storage_retention,
        )


def _commit_energy(
    unit: PopulationUnit,
    ctx: StepContext,
    need_kcal: float,
    food_ratio: float,
    deficit: float,
    reserve_kcal: float,
    stores_kcal: float,
    stored_kcal: float,
    spoiled_kcal: float,
    retention: float,
) -> None:
    n = unit.population
    unit.food_ratio = food_ratio
    unit.energy_deficit = deficit
    unit.reserve_kcal_per_capita = reserve_kcal / n
    retained = stores_kcal * retention
    ctx.ledger.spoilage_kcal += spoiled_kcal + (stores_kcal - retained)
    unit.stores_kcal = retained
    unit.stored_kcal = stored_kcal
    unit.energy_debt_kcal = 0.0
    unit.residence_years += 1
    unit.harvest_history.append(unit.harvest_kcal / n)
    ctx.ledger.need_kcal += need_kcal


@dataclass(frozen=True, eq=False)
class EnergyUpdates:
    """Energy state of many units, committed as columns (one proposal per step).

    Equivalent to one :class:`EnergyUpdate` per row in row order: ledger totals are
    accumulated sequentially in that order.
    """

    cols: "UnitColumns"
    need_kcal: FloatArray
    food_ratio: FloatArray
    deficit: FloatArray
    reserve_kcal: FloatArray
    stores_kcal: FloatArray
    stored_kcal: FloatArray
    spoiled_kcal: FloatArray
    retention: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit every row's energy state; stores spoil at the end of the year."""
        cols = self.cols
        n = cols.population()
        opening = cols.get("stores_kcal")  # after trade: K0
        cols.set("food_ratio", self.food_ratio)
        cols.set("energy_deficit", self.deficit)
        cols.set("reserve_kcal_per_capita", self.reserve_kcal / n)
        retained = self.stores_kcal * self.retention
        ledger = ctx.ledger
        total = ledger.spoilage_kcal
        for spoiled in (self.spoiled_kcal + (self.stores_kcal - retained)).tolist():
            total += spoiled
        ledger.spoilage_kcal = total
        cols.set("stores_kcal", retained)
        cols.set("stored_kcal", self.stored_kcal)
        cols.set("energy_debt_kcal", 0.0)
        cols.set("residence_years", cols.get("residence_years") + 1)
        # Gross store flows for strata accounting (recorded only; nothing above reads them).
        ctx.food_accounts = FoodAccounts(
            cols.units,
            opening,
            self.stored_kcal,
            np.maximum(opening + self.stored_kcal - self.stores_kcal, 0.0),
            retained,
        )
        per_capita = (cols.get("harvest_kcal") / n).tolist()
        for unit, value in zip(cols.units, per_capita, strict=True):
            unit.harvest_history.append(value)
        total = ledger.need_kcal
        for need in self.need_kcal.tolist():
            total += need
        ledger.need_kcal = total


class EnergeticsSubsystem:
    """Balances each unit's harvest against its requirement."""

    name = "energetics"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[EnergyUpdates]:
        """Compute energy balance for every unit, as one batched proposal."""
        everyone = ctx.columns(state)
        populated = np.flatnonzero(everyone.population() > 0)
        if populated.size == 0:
            return []
        cols = everyone.subset(populated) if populated.size < len(everyone) else everyone
        compiled = ctx.compiled
        assert compiled is not None
        species = cols.species()
        people = cols.population()
        need = annual_need_columns(cols, state, ctx)
        p = compiled.parameter
        daily = p("metabolism.adult_daily_kcal")[species]
        cap = people.astype(np.float64) * p("metabolism.reserve_days_max")[species] * daily
        reserve = cols.get("reserve_kcal_per_capita") * people
        retention = capability_column(cols, ctx, "storage_retention")
        outcome = energy_balance_batch(
            need,
            cols.get("harvest_kcal"),
            reserve,  # type: ignore[arg-type]
            cap,
            cols.get("stores_kcal"),
            retention > 0,
        )
        return [EnergyUpdates(cols, need, *outcome, retention)]


def capability_column(cols: "UnitColumns", ctx: StepContext, name: str) -> FloatArray:
    """One capability for every row, from each distinct technology set's cached capability
    map (the values ``ctx.capabilities(unit)[name]`` returns).

    With compiled technologies the distinct sets are found from the table's bitmasks (a
    bitmask identifies its set exactly: every technology has one bit), so only one
    capability lookup per distinct set remains in Python.
    """
    if ctx.compiled is not None and ctx.compiled.technologies is not None:
        masks = cols.technology_masks()
        _, first, inverse = np.unique(masks, return_index=True, return_inverse=True)
        sets = cols.technologies()
        distinct_values = np.array(
            [ctx.capabilities_of(sets[i])[name] for i in first.tolist()],  # type: ignore[index]
            dtype=np.float64,
        )
        column: FloatArray = distinct_values[inverse]
        return column
    sets = cols.technologies()
    distinct: dict[frozenset[str], float] = {}
    values = np.empty(len(sets))
    for i, techs in enumerate(sets):
        value = distinct.get(techs)
        if value is None:
            value = ctx.capabilities_of(techs)[name]  # type: ignore[index]
            distinct[techs] = value
        values[i] = value
    return values
