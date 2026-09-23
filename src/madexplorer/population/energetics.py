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
    adult_equivalents = float(((unit.females + unit.males) * tables.need_fraction).sum())
    daily = profile.metabolism.adult_daily_kcal
    need = (
        adult_equivalents
        * daily
        * 365.0
        * thermoregulation_multiplier(profile.metabolism, temperature_c)
    )
    return need + unit.energy_debt_kcal


@model_rule(
    name="pooled_energy_balance",
    version="1.0",
    rationale=(
        "Food is shared within the group (forager pooling). Intake plus reserves covers "
        "requirement first; any surplus refills reserves up to a physiological cap and the rest "
        "spoils; any shortfall is the energy deficit that drives starvation mortality."
    ),
    source_type="heuristic",
    parameters=("reserve_days_max",),
    expected_domain="deficit in [0, 1]; reserve in [0, cap]",
    known_limitations="Equal sharing assumed; unequal intra-group access arrives with MVP 3.",
)
def energy_balance(
    need_kcal: float, harvest_kcal: float, reserve_kcal: float, reserve_cap_kcal: float
) -> tuple[float, float, float]:
    """Return ``(food_ratio, deficit_fraction, new_reserve_kcal)``."""
    if need_kcal <= 0:
        return 1.0, 0.0, min(reserve_kcal + harvest_kcal, reserve_cap_kcal)
    available = harvest_kcal + reserve_kcal
    food_ratio = harvest_kcal / need_kcal
    if available >= need_kcal:
        return food_ratio, 0.0, min(available - need_kcal, reserve_cap_kcal)
    return food_ratio, (need_kcal - available) / need_kcal, 0.0


@dataclass(frozen=True)
class EnergyUpdate:
    """New nutritional state of one unit."""

    unit_id: str
    need_kcal: float
    food_ratio: float
    deficit: float
    reserve_kcal_per_capita: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the unit's energy state."""
        unit = state.units[self.unit_id]
        unit.food_ratio = self.food_ratio
        unit.energy_deficit = self.deficit
        unit.reserve_kcal_per_capita = self.reserve_kcal_per_capita
        unit.energy_debt_kcal = 0.0
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
            ratio, deficit, reserve = energy_balance(
                need, unit.harvest_kcal, unit.total_reserve_kcal, cap
            )
            updates.append(EnergyUpdate(unit.id, need, ratio, deficit, reserve / n))
        return updates
