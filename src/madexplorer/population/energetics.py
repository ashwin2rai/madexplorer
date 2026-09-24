"""Energy balance: requirement, reserves, and nutritional deficit (spec §5.4, §8.2)."""

from collections.abc import Sequence
from dataclasses import dataclass

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
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


@dataclass(frozen=True)
class EnergyUpdate:
    """New nutritional and storage state of one unit."""

    unit_id: str
    need_kcal: float
    balance: EnergyBalance
    storage_retention: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the unit's energy state; stores spoil at the end of the year."""
        unit = state.units[self.unit_id]
        n = unit.population
        b = self.balance
        unit.food_ratio = b.food_ratio
        unit.energy_deficit = b.deficit
        unit.reserve_kcal_per_capita = b.reserve_kcal / n
        retained = b.stores_kcal * self.storage_retention
        ctx.ledger.spoilage_kcal += b.spoiled_kcal + (b.stores_kcal - retained)
        unit.stores_kcal = retained
        unit.stored_kcal = b.stored_kcal
        unit.energy_debt_kcal = 0.0
        unit.residence_years += 1
        unit.harvest_history.append(unit.harvest_kcal / n)
        ctx.ledger.need_kcal += self.need_kcal


class EnergeticsSubsystem:
    """Balances each unit's harvest against its requirement."""

    name = "energetics"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[EnergyUpdate]:
        """Compute energy balance for every unit."""
        updates: list[EnergyUpdate] = []
        for unit in state.units.values():
            profile = ctx.species(unit.species_id)
            n = unit.population
            if n == 0:
                continue
            temperature = float(state.climate.temperature_c[unit.cell])
            need = annual_need_kcal(unit, profile, ctx.tables[unit.species_id], temperature)
            cap = n * profile.metabolism.reserve_days_max * profile.metabolism.adult_daily_kcal
            retention = ctx.capabilities(unit)["storage_retention"]
            balance = energy_balance(
                need,
                unit.harvest_kcal,
                unit.total_reserve_kcal,
                cap,
                unit.stores_kcal,
                retention > 0,
            )
            updates.append(EnergyUpdate(unit.id, need, balance, retention))
        return updates
