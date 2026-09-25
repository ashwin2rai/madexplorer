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


@dataclass(frozen=True, eq=False)
class ForageAccess:
    """Static per-cell foraging access and return rates for one species."""

    plant_access: FloatArray
    game_access: FloatArray
    plant_return: FloatArray
    game_return: FloatArray

    def as_tuple(self) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        """``(plant_access, game_access, plant_return, game_return)``."""
        return self.plant_access, self.game_access, self.plant_return, self.game_return


def accessible_food_kcal(state: SimulationState, access: ForageAccess) -> FloatArray:
    """Accessible wild food per cell for a species (what foragers can perceive and take)."""
    food: FloatArray = (
        state.ecology.plant_stock_kcal * access.plant_access
        + state.ecology.game_stock_kcal * access.game_access
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


def _marginal_return(
    accessible: tuple[float, float], rates: tuple[float, float], effort_hours: float
) -> float:
    """Derivative of total harvest with respect to effective effort at ``effort_hours``."""
    (a_p, a_g), (r_p, r_g) = accessible, rates
    w_p, w_g = r_p * a_p, r_g * a_g
    total = w_p + w_g
    if total <= 0:
        return 0.0
    marginal = 0.0
    for a, r, w in ((a_p, r_p, w_p), (a_g, r_g, w_g)):
        if a > 0:
            share = w / total
            marginal += r * share * math.exp(-r * share * effort_hours / a)
    return marginal


SOLVER_TOLERANCE = 1e-12  # relative harvest error |H(E) - target| / target at convergence
SOLVER_MAX_NEWTON = 50


def _effort_fraction(
    stock: tuple[float, float], returns: tuple[float, float], capacity: float, target: float
) -> float:
    """Fraction of labor whose harvest meets ``target`` (harvest at full labor exceeds it).

    Newton's method on effort, started at zero effort: harvest is increasing and concave in
    effort, so the iterates rise monotonically to the root without overshooting and never
    visit the flat, depleted region beyond it; typically ~5 steps reach the tolerance.
    Numerical approximation of the exact root, as precise as the 40-step bisection it
    replaces (differences <= ~2e-12 relative on recorded run inputs; objective/status.md
    P4). Falls back to that bisection if Newton has not converged.
    """
    effort = 0.0
    for _ in range(SOLVER_MAX_NEWTON):
        gap = sum(_harvest(stock, returns, effort)) - target
        if abs(gap) <= SOLVER_TOLERANCE * target:
            return effort / capacity
        slope = _marginal_return(stock, returns, effort)
        if slope <= 0:
            break
        effort = min(max(effort - gap / slope, 0.0), capacity)
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if sum(_harvest(stock, returns, capacity * mid)) >= target:
            hi = mid
        else:
            lo = mid
    return hi


@dataclass(frozen=True)
class CellForagingOutcome:
    """Result of groups foraging one shared pool."""

    shares: FloatArray  # per-unit harvest, kcal
    removal: FloatArray  # per-resource removal (plant, game), kcal
    effort_fraction: float  # share of labor actually applied
    marginal_kcal_per_effective_hour: float


@model_rule(
    name="satisficing_group_foraging",
    version="1.2",
    rationale=(
        "Co-located groups apply the same fraction of their labor, just enough to meet their "
        "combined requirement (net of crops) plus a surplus target; harvest is shared by effective "
        "effort (labor x local familiarity x ecological knowledge efficiency)."
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
    efficiency: FloatArray,
    target_kcal: float,
) -> CellForagingOutcome:
    """Forage a shared pool; ``efficiency`` converts labor hours into effective hours."""
    effective = labor_hours * efficiency
    capacity = float(effective.sum())
    stock = (float(accessible[0]), float(accessible[1]))
    returns = (float(rates[0]), float(rates[1]))
    if capacity <= 0:
        return CellForagingOutcome(
            np.zeros_like(labor_hours), np.zeros(2), 0.0, _marginal_return(stock, returns, 0.0)
        )
    fraction = 1.0
    if sum(_harvest(stock, returns, capacity)) > target_kcal:
        fraction = _effort_fraction(stock, returns, capacity, target_kcal)
    removal = np.array(_harvest(stock, returns, capacity * fraction))
    shares: FloatArray = removal.sum() * effective / capacity
    marginal = _marginal_return(stock, returns, capacity * fraction)
    return CellForagingOutcome(shares, removal, fraction, marginal)


@dataclass(frozen=True)
class CellHarvest:
    """Foraging outcome for one species group in one cell."""

    cell: int
    unit_ids: tuple[str, ...]
    unit_harvest_kcal: tuple[float, ...]
    unit_hours: tuple[float, ...]
    unit_marginal_kcal_per_hour: tuple[float, ...]
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
        removed = self.plant_removed_kcal + self.game_removed_kcal
        plant_share = self.plant_removed_kcal / removed if removed > 0 else 0.0
        for unit_id, harvest, hours, marginal in zip(
            self.unit_ids,
            self.unit_harvest_kcal,
            self.unit_hours,
            self.unit_marginal_kcal_per_hour,
            strict=True,
        ):
            unit = state.units[unit_id]
            unit.forage_harvest_kcal = harvest
            unit.forage_hours = hours
            unit.forage_marginal_kcal_per_hour = marginal
            unit.forage_plant_share = plant_share
            unit.harvest_kcal = unit.farm_harvest_kcal + harvest
            unit.labor_debt_hours = 0.0
            known = unit.familiarity.get(self.cell, self.initial_familiarity)
            unit.familiarity[self.cell] = known + self.learning_rate * (1.0 - known)
            ctx.ledger.harvest_kcal += unit.harvest_kcal


class ForagingSubsystem:
    """Every group forages in its current cell with the labor left after field work."""

    name = "foraging"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[CellHarvest]:
        """Compute harvests; groups of different species in one cell forage in id order."""
        proposals: list[CellHarvest] = []
        access = {sid: forage.as_tuple() for sid, forage in ctx.forage.items()}
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
                        max(
                            u.weighted_count(tables.labor) * hours_per_year
                            - u.labor_debt_hours
                            - u.farm_hours,
                            0.0,
                        )
                        for u in group
                    ]
                )
                efficiency = np.array(
                    [
                        u.familiarity.get(cell, profile.cognition.initial_familiarity)
                        * (
                            ctx.knowledge.efficiency(u.knowledge, "ecology")
                            if ctx.knowledge
                            else 1.0
                        )
                        for u in group
                    ]
                )
                temperature = float(state.climate.temperature_c[cell])
                target = sum(
                    max(
                        annual_need_kcal(u, profile, tables, temperature)
                        * (1.0 + profile.foraging.surplus_target)
                        - u.farm_harvest_kcal,
                        0.0,
                    )
                    for u in group
                )
                outcome = cell_harvest(accessible, rates, labor, efficiency, target)
                plant_left[cell] -= outcome.removal[0]
                game_left[cell] -= outcome.removal[1]
                proposals.append(
                    CellHarvest(
                        cell=cell,
                        unit_ids=tuple(u.id for u in group),
                        unit_harvest_kcal=tuple(float(x) for x in outcome.shares),
                        unit_hours=tuple(float(x) * outcome.effort_fraction for x in labor),
                        unit_marginal_kcal_per_hour=tuple(
                            outcome.marginal_kcal_per_effective_hour * float(e) for e in efficiency
                        ),
                        plant_removed_kcal=float(outcome.removal[0]),
                        game_removed_kcal=float(outcome.removal[1]),
                        learning_rate=profile.cognition.familiarity_learning_rate,
                        initial_familiarity=profile.cognition.initial_familiarity,
                    )
                )
        return proposals
