"""Residential migration from perceived, not omniscient, utility (spec §10.2, §30).

Each year a group compares the cell it is in with known cells reachable in one
relocation. Utility combines expected food per head (accounting for people
already there), water, movement cost, and staleness of information, plus
perception noise. The probability of moving rises with the utility gain.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.groups import sigmoid
from madexplorer.population.unit import Observation
from madexplorer.species.profile import MigrationBehavior


@model_rule(
    name="perceived_cell_utility",
    version="1.0",
    rationale=(
        "Utility = w_food*log(perceived food per head relative to need, capped) + w_water*water "
        "- w_move*path_cost/reference - w_uncertainty*information_age/memory. Log food captures "
        "diminishing marginal value of abundance."
    ),
    source_type="heuristic",
    parameters=(
        "food_weight",
        "water_weight",
        "movement_cost_weight",
        "movement_reference_km",
        "uncertainty_weight",
        "food_ratio_cap",
    ),
    expected_domain="real-valued score; only differences matter",
    known_limitations="No security, trade, disease, or extraction terms until later MVPs.",
)
def cell_utility(
    observation: Observation,
    population: int,
    need_kcal: float,
    path_cost_km: float,
    information_age_years: int,
    memory_years: int,
    behavior: MigrationBehavior,
) -> dict[str, float]:
    """Utility components of settling in a cell (noise excluded)."""
    per_head = population + observation.population
    ratio = observation.food_kcal / max(need_kcal * per_head / max(population, 1), 1.0)
    ratio = min(max(ratio, 0.05), behavior.food_ratio_cap)
    return {
        "expected_food": behavior.food_weight * math.log(ratio),
        "water_access": behavior.water_weight * observation.water_access,
        "movement_cost": -behavior.movement_cost_weight
        * path_cost_km
        / behavior.movement_reference_km,
        "uncertainty": -behavior.uncertainty_weight * information_age_years / memory_years,
    }


@model_rule(
    name="migration_hazard",
    version="1.0",
    rationale=(
        "Probability of relocating is logistic in the perceived utility gain, offset by inertia."
    ),
    source_type="heuristic",
    parameters=("decisiveness", "inertia", "perception_noise"),
    expected_domain="annual probability in (0, 1)",
    known_limitations=(
        "Whole-group moves only; selective emigration arrives with distributional units."
    ),
)
def migration_probability(utility_gain: float, behavior: MigrationBehavior) -> float:
    """Annual probability of moving given the best alternative's utility gain."""
    return sigmoid(behavior.decisiveness * utility_gain - behavior.inertia)


@dataclass(frozen=True)
class Relocation:
    """Move a unit to a new cell, paying the travel energy cost."""

    unit_id: str
    origin: int
    destination: int
    path_cost_km: float
    travel_kcal: float
    hazard: float
    carry_kcal: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Relocate the unit: pay travel energy, carry what stores it can, abandon fields."""
        unit = state.units[self.unit_id]
        unit.cell = self.destination
        unit.energy_debt_kcal += self.travel_kcal
        abandoned = max(unit.stores_kcal - self.carry_kcal, 0.0)
        unit.stores_kcal -= abandoned
        ctx.ledger.abandoned_stores_kcal += abandoned
        unit.fields_ha = 0.0
        unit.residence_years = 0
        ctx.ledger.migrations += 1
        if ctx.scenario.config.output.log_migrations:
            ctx.events.emit(
                state.year,
                "migration",
                unit_id=unit.id,
                population=unit.population,
                origin=list(state.world.coords(self.origin)),
                destination=list(state.world.coords(self.destination)),
                path_cost_km=round(self.path_cost_km, 2),
                hazard=round(self.hazard, 4),
            )


class MigrationSubsystem:
    """Evaluates relocation decisions for all units."""

    name = "migration"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Relocation]:
        """Decide which units move where this year."""
        rng = ctx.rng.stream(Streams.MIGRATION)
        proposals: list[Relocation] = []
        for unit in state.units.values():
            n = unit.population
            if n == 0:
                continue
            profile = ctx.species(unit.species_id)
            behavior, memory = profile.migration, profile.cognition.memory_years
            temperature = float(state.climate.temperature_c[unit.cell])
            need = (
                annual_need_kcal(unit, profile, ctx.tables[unit.species_id], temperature)
                - unit.energy_debt_kcal
            )
            reachable = ctx.movement[unit.species_id].reachable(unit.cell)
            candidates = sorted(c for c in unit.beliefs if c in reachable)
            if unit.cell not in candidates:
                continue  # cannot evaluate staying without a current observation
            noise = (
                rng.gumbel(0.0, behavior.perception_noise, len(candidates))
                if behavior.perception_noise > 0
                else np.zeros(len(candidates))
            )
            farm_kcal = unit.fields_ha * unit.crop_yield_kcal_per_ha
            carry = n * profile.movement.carry_kcal_per_capita
            abandoned = max(unit.stores_kcal - carry, 0.0)
            stores_cost = behavior.abandoned_stores_weight * abandoned / need if need > 0 else 0.0
            fields_cost = behavior.abandoned_fields_weight * farm_kcal / need if need > 0 else 0.0
            scores: dict[int, tuple[float, dict[str, float]]] = {}
            for cell, eps in zip(candidates, noise, strict=True):
                obs = unit.beliefs[cell]
                if cell == unit.cell and farm_kcal > 0:
                    obs = replace(obs, food_kcal=obs.food_kcal + farm_kcal)
                components = cell_utility(
                    obs, n, need, reachable[cell], state.year - obs.year, memory, behavior
                )
                components["abandoned_stores"] = 0.0 if cell == unit.cell else -stores_cost
                components["abandoned_fields"] = 0.0 if cell == unit.cell else -fields_cost
                components["perception_noise"] = float(eps)
                scores[cell] = (sum(components.values()), components)
            stay_score, stay_components = scores[unit.cell]
            alternatives = [c for c in candidates if c != unit.cell]
            if not alternatives:
                continue
            best = max(alternatives, key=lambda c: scores[c][0])
            best_score, best_components = scores[best]
            hazard = migration_probability(best_score - stay_score, behavior)
            if unit.id in ctx.trace_units:
                ctx.events.emit(
                    state.year,
                    "trace_migration",
                    unit_id=unit.id,
                    current_cell=list(state.world.coords(unit.cell)),
                    best_cell=list(state.world.coords(best)),
                    current={k: round(v, 3) for k, v in stay_components.items()},
                    best={k: round(v, 3) for k, v in best_components.items()},
                    final_hazard=round(hazard, 4),
                )
            if rng.random() < hazard:
                cost = reachable[best]
                proposals.append(
                    Relocation(
                        unit.id,
                        unit.cell,
                        best,
                        cost,
                        n * profile.movement.travel_kcal_per_km * cost,
                        hazard,
                        carry,
                    )
                )
        return proposals
