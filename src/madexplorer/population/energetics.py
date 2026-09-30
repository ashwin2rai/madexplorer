"""Energy balance: requirement, reserves, and nutritional deficit (spec §5.4, §8.2)."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import Metabolism, SpeciesProfile


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


def annual_need_batch(
    units: Sequence[PopulationUnit], state: SimulationState, ctx: StepContext
) -> FloatArray:
    """:func:`annual_need_kcal` for many units at once (same operations, bit-identical)."""
    compiled = ctx.compiled
    assert compiled is not None
    len(units)
    species = compiled.species_of([u.species_id for u in units])
    adults = np.array(
        [u.weighted_count(ctx.tables[u.species_id].need_fraction) for u in units], dtype=np.float64
    )
    cells = np.array([u.cell for u in units], dtype=np.int64)
    temperature = state.climate.temperature_c[cells].astype(np.float64)
    p = compiled.parameter
    cold = (
        np.maximum(0.0, p("metabolism.comfort_temp_low_c")[species] - temperature)
        * p("metabolism.cold_cost_per_c")[species]
    )
    heat = (
        np.maximum(0.0, temperature - p("metabolism.comfort_temp_high_c")[species])
        * p("metabolism.heat_cost_per_c")[species]
    )
    debt = np.array([u.energy_debt_kcal for u in units], dtype=np.float64)
    need: FloatArray = (
        adults * p("metabolism.adult_daily_kcal")[species] * 365.0 * (1.0 + cold + heat) + debt
    )
    return need


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
    """Energy state of many units, committed in unit order (one proposal per step)."""

    units: tuple[PopulationUnit, ...]
    need_kcal: FloatArray
    food_ratio: FloatArray
    deficit: FloatArray
    reserve_kcal: FloatArray
    stores_kcal: FloatArray
    stored_kcal: FloatArray
    spoiled_kcal: FloatArray
    retention: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit every unit's energy state, in the order the per-unit updates used."""
        for unit, *values in zip(
            self.units,
            self.need_kcal.tolist(),
            self.food_ratio.tolist(),
            self.deficit.tolist(),
            self.reserve_kcal.tolist(),
            self.stores_kcal.tolist(),
            self.stored_kcal.tolist(),
            self.spoiled_kcal.tolist(),
            self.retention.tolist(),
            strict=True,
        ):
            _commit_energy(unit, ctx, *values)


class EnergeticsSubsystem:
    """Balances each unit's harvest against its requirement."""

    name = "energetics"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[EnergyUpdates]:
        """Compute energy balance for every unit, as one batched proposal."""
        units = tuple(u for u in state.units.values() if u.population > 0)
        if not units:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        len(units)
        species = compiled.species_of([u.species_id for u in units])
        people = np.array([u.population for u in units], dtype=np.float64)
        need = annual_need_batch(units, state, ctx)
        p = compiled.parameter
        daily = p("metabolism.adult_daily_kcal")[species]
        cap = people * p("metabolism.reserve_days_max")[species] * daily
        reserve = np.array([u.reserve_kcal_per_capita for u in units], dtype=np.float64) * np.array(
            [u.population for u in units], dtype=np.int64
        )
        retention = np.array(
            [ctx.capabilities(u)["storage_retention"] for u in units], dtype=np.float64
        )
        harvest = np.array([u.harvest_kcal for u in units], dtype=np.float64)
        stores = np.array([u.stores_kcal for u in units], dtype=np.float64)
        outcome = energy_balance_batch(need, harvest, reserve, cap, stores, retention > 0)
        return [EnergyUpdates(units, need, *outcome, retention)]
