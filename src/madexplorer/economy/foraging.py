"""Foraging with diminishing returns and within-cell competition (spec §4.4, §9.1).

Harvest from a resource with accessible stock ``A`` and initial return rate
``r`` (kcal per effective labor hour) under effort ``E`` is
``A * (1 - exp(-r * E / A))``: early hours are productive, later hours deplete
the patch. Groups in the same cell share one pool, so crowding lowers returns.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.profile import Foraging
from madexplorer.world.grid import WorldGrid


@model_rule(
    name="forage_accessibility",
    version="1.0",
    rationale=(
        "Dense canopy hides part of the edible plant stock; vegetation lengthens game search "
        "time, lowering the return rate rather than the stock."
    ),
    source_type="heuristic",
    parameters=(
        "plant_canopy_access_penalty",
        "game_search_vegetation_penalty",
        "plant_return_kcal_per_hour",
        "game_return_kcal_per_hour",
    ),
    expected_domain="access fractions in [0, 1]; return rates >= 0",
    known_limitations="Two aggregate resources; no seasonality or storage.",
)
def access_and_returns(
    world: WorldGrid, foraging: Foraging
) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """Per-cell ``(plant_access, game_access, plant_return, game_return)``."""
    veg = world.vegetation_density
    plant_access = np.clip(1.0 - foraging.plant_canopy_access_penalty * veg, 0.0, 1.0)
    game_access = np.ones_like(veg)
    plant_return = np.full_like(veg, foraging.plant_return_kcal_per_hour)
    game_return = foraging.game_return_kcal_per_hour * np.clip(
        1.0 - foraging.game_search_vegetation_penalty * veg, 0.0, 1.0
    )
    return plant_access, game_access, plant_return, game_return


def accessible_food_kcal(state: SimulationState, foraging: Foraging) -> FloatArray:
    """Accessible wild food per cell for a species (what foragers can perceive and take)."""
    plant_access, game_access, _, _ = access_and_returns(state.world, foraging)
    food: FloatArray = (
        state.ecology.plant_stock_kcal * plant_access + state.ecology.game_stock_kcal * game_access
    )
    return food


def _harvest(
    accessible: tuple[float, float], rates: tuple[float, float], effort_hours: float
) -> tuple[float, float]:
    """Harvest per resource when ``effort_hours`` are split by expected yield ``r * A``.

    Scalar arithmetic on purpose: this is the innermost loop of the step.
    """
    (a_p, a_g), (r_p, r_g) = accessible, rates
    w_p, w_g = r_p * a_p, r_g * a_g
    total = w_p + w_g
    if total <= 0 or effort_hours <= 0:
        return 0.0, 0.0
    h_p = a_p * -math.expm1(-r_p * effort_hours * w_p / total / a_p) if a_p > 0 else 0.0
    h_g = a_g * -math.expm1(-r_g * effort_hours * w_g / total / a_g) if a_g > 0 else 0.0
    return h_p, h_g


@model_rule(
    name="satisficing_group_foraging",
    version="1.0",
    rationale=(
        "Co-located groups apply the same fraction of their labor, just enough to meet their "
        "combined requirement plus a surplus target; harvest is shared by effective effort "
        "(labor x local familiarity)."
    ),
    source_type="heuristic",
    parameters=("surplus_target", "foraging_hours_per_day", "familiarity_learning_rate"),
    expected_domain="harvest <= accessible stock; effort <= labor supply",
    known_limitations="Different species in one cell forage sequentially, not jointly.",
)
def cell_harvest(
    accessible: FloatArray,
    rates: FloatArray,
    labor_hours: FloatArray,
    familiarity: FloatArray,
    target_kcal: float,
) -> tuple[FloatArray, FloatArray]:
    """Return ``(per-unit harvest, per-resource removal)`` for groups sharing a cell."""
    effective = labor_hours * familiarity
    capacity = float(effective.sum())
    if capacity <= 0:
        return np.zeros_like(labor_hours), np.zeros(2)
    stock = (float(accessible[0]), float(accessible[1]))
    returns = (float(rates[0]), float(rates[1]))
    fraction = 1.0
    if sum(_harvest(stock, returns, capacity)) > target_kcal:
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if sum(_harvest(stock, returns, capacity * mid)) >= target_kcal:
                hi = mid
            else:
                lo = mid
        fraction = hi
    removal = np.array(_harvest(stock, returns, capacity * fraction))
    shares: FloatArray = removal.sum() * effective / capacity
    return shares, removal


@dataclass(frozen=True)
class CellHarvest:
    """Harvest outcome for one species group in one cell."""

    cell: int
    unit_ids: tuple[str, ...]
    unit_harvest_kcal: tuple[float, ...]
    plant_removed_kcal: float
    game_removed_kcal: float
    learning_rate: float
    initial_familiarity: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Deplete stocks, credit harvests, and grow local familiarity (learning by doing)."""
        eco = state.ecology
        eco.plant_stock_kcal[self.cell] = max(
            eco.plant_stock_kcal[self.cell] - self.plant_removed_kcal, 0.0
        )
        eco.game_stock_kcal[self.cell] = max(
            eco.game_stock_kcal[self.cell] - self.game_removed_kcal, 0.0
        )
        for unit_id, harvest in zip(self.unit_ids, self.unit_harvest_kcal, strict=True):
            unit = state.units[unit_id]
            unit.harvest_kcal = harvest
            known = unit.familiarity.get(self.cell, self.initial_familiarity)
            unit.familiarity[self.cell] = known + self.learning_rate * (1.0 - known)
            ctx.ledger.harvest_kcal += harvest


class ForagingSubsystem:
    """Every group forages in its current cell."""

    name = "foraging"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[CellHarvest]:
        """Compute harvests; groups of different species in one cell forage in id order."""
        proposals: list[CellHarvest] = []
        access = {
            sid: access_and_returns(state.world, profile.foraging)
            for sid, profile in ctx.scenario.species.items()
        }
        plant_left = state.ecology.plant_stock_kcal.copy()
        game_left = state.ecology.game_stock_kcal.copy()
        for cell, units in state.units_by_cell().items():
            by_species: dict[str, list[PopulationUnit]] = {}
            for unit in units:
                by_species.setdefault(unit.species_id, []).append(unit)
            for species_id in sorted(by_species):
                group = by_species[species_id]
                profile = ctx.species(species_id)
                tables = ctx.tables[species_id]
                plant_access, game_access, plant_return, game_return = access[species_id]
                accessible = np.array(
                    [plant_left[cell] * plant_access[cell], game_left[cell] * game_access[cell]]
                )
                rates = np.array([plant_return[cell], game_return[cell]])
                hours_per_year = profile.foraging.foraging_hours_per_day * 365.0
                labor = np.array(
                    [
                        float(((u.females + u.males) * tables.labor).sum()) * hours_per_year
                        for u in group
                    ]
                )
                familiarity = np.array(
                    [u.familiarity.get(cell, profile.cognition.initial_familiarity) for u in group]
                )
                temperature = float(state.climate.temperature_c[cell])
                target = sum(annual_need_kcal(u, profile, tables, temperature) for u in group) * (
                    1.0 + profile.foraging.surplus_target
                )
                shares, removal = cell_harvest(accessible, rates, labor, familiarity, target)
                plant_left[cell] -= removal[0]
                game_left[cell] -= removal[1]
                proposals.append(
                    CellHarvest(
                        cell=cell,
                        unit_ids=tuple(u.id for u in group),
                        unit_harvest_kcal=tuple(float(x) for x in shares),
                        plant_removed_kcal=float(removal[0]),
                        game_removed_kcal=float(removal[1]),
                        learning_rate=profile.cognition.familiarity_learning_rate,
                        initial_familiarity=profile.cognition.initial_familiarity,
                    )
                )
        return proposals
