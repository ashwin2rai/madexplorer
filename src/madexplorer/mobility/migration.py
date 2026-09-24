"""Residential migration from perceived, not omniscient, utility (spec §10.2, §30).

Each year a group compares the cell it is in with known cells reachable in one
relocation. Utility combines expected food per head (accounting for people
already there), water, movement cost, and staleness of information. Uncertainty
enters only through the group's noisy, aging beliefs (``mobility.exploration``):
the group picks the best-believed destination deterministically, then makes one
stochastic move/stay decision on its perceived advantage. There is no second,
per-candidate noise draw, so identical options do not make moving likelier just
because there are more of them (no best-of-many-noise bias).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import partial

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.groups import sigmoid
from madexplorer.population.unit import NEVER_OBSERVED, Observation, PopulationUnit
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
    version="2.0",
    rationale=(
        "The group moves to its best-believed destination with probability logistic in that "
        "destination's perceived utility advantage over staying, offset by inertia. Choice is "
        "argmax over beliefs (no per-candidate noise), so the move probability depends on the "
        "best option's advantage, not on how many options there are."
    ),
    source_type="heuristic",
    parameters=("decisiveness", "inertia"),
    expected_domain="annual probability in (0, 1)",
    known_limitations=(
        "Whole-group moves only; selective emigration arrives with distributional units. "
        "Noisy beliefs still carry a winner's-curse bias toward the best-looking cell."
    ),
)
def migration_probability(utility_gain: float, behavior: MigrationBehavior) -> float:
    """Annual probability of moving given the best alternative's utility gain."""
    return sigmoid(behavior.decisiveness * utility_gain - behavior.inertia)


def choose_destination(
    candidates: Sequence[int] | IntArray,
    scores: Sequence[float] | FloatArray,
    current: int,
    rng: np.random.Generator,
) -> int | None:
    """Best-scoring cell other than ``current``; exact ties are broken uniformly at random.

    Candidates must be in a deterministic order. Returns ``None`` without alternatives. The
    random draw happens only on an exact tie, which continuous beliefs make rare.
    """
    cells = np.asarray(candidates, dtype=np.int64)
    values = np.where(cells == current, -np.inf, np.asarray(scores, dtype=np.float64))
    if cells.size == 0 or not np.isfinite(values).any():
        return None
    best = np.flatnonzero(values == values.max())
    if best.size == 1:
        return int(cells[best[0]])
    return int(cells[best[int(rng.integers(best.size))]])


@dataclass(frozen=True)
class MoveCosts:
    """What a unit gives up or pays by moving, fixed for one year's decision."""

    reachable: Mapping[int, float]  # path cost (km) to each reachable cell
    need_kcal: float
    stores_cost: float  # utility lost by abandoning stores beyond carrying capacity
    fields_cost: float  # utility lost by abandoning fields
    farm_kcal: float  # expected crop output of the current fields


def destination_components(
    unit: PopulationUnit,
    cell: int,
    costs: MoveCosts,
    year: int,
    memory_years: int,
    behavior: MigrationBehavior,
) -> dict[str, float]:
    """Utility components of ``cell`` for ``unit``, including the cost of leaving."""
    obs = unit.beliefs[cell]
    staying = cell == unit.cell
    if staying and costs.farm_kcal > 0:
        obs = replace(obs, food_kcal=obs.food_kcal + costs.farm_kcal)
    components = cell_utility(
        obs,
        unit.population,
        costs.need_kcal,
        costs.reachable[cell],
        year - obs.year,
        memory_years,
        behavior,
    )
    components["abandoned_stores"] = 0.0 if staying else -costs.stores_cost
    components["abandoned_fields"] = 0.0 if staying else -costs.fields_cost
    return components


def candidate_utilities(
    food_kcal: FloatArray,
    water_access: FloatArray,
    others: FloatArray,
    age_years: FloatArray,
    path_cost_km: FloatArray,
    staying: BoolArray,
    population: FloatArray,
    need_kcal: FloatArray,
    farm_kcal: FloatArray,
    stores_cost: FloatArray,
    fields_cost: FloatArray,
    memory_years: FloatArray,
    weights: FloatArray,
) -> FloatArray:
    """:func:`cell_utility` plus leaving costs for many candidates at once (numpy).

    Every argument is one value per candidate (per-unit values repeated); ``weights`` has
    columns food, water, movement, movement reference km, uncertainty, food-ratio cap.
    Matches the scalar rule up to floating-point rounding.
    """
    food = np.where(staying & (farm_kcal > 0), food_kcal + farm_kcal, food_kcal)
    per_head = population + others
    ratio = food / np.maximum(need_kcal * per_head / np.maximum(population, 1.0), 1.0)
    ratio = np.minimum(np.maximum(ratio, 0.05), weights[:, 5])
    utility: FloatArray = (
        weights[:, 0] * np.log(ratio)
        + weights[:, 1] * water_access
        - weights[:, 2] * path_cost_km / weights[:, 3]
        - weights[:, 4] * age_years / memory_years
        - np.where(staying, 0.0, stores_cost)
        - np.where(staying, 0.0, fields_cost)
    )
    return utility


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


@dataclass(frozen=True)
class MigrationDecision:
    """A unit's best-believed destination and its annual probability of moving there."""

    destination: int
    hazard: float
    candidates: int  # reachable cells with a belief, including the current one
    carry_kcal: float


@dataclass(frozen=True)
class _Prepared:
    """One unit's inputs to this year's migration choice."""

    unit: PopulationUnit
    candidates: IntArray  # reachable believed cells, ascending (includes the current cell)
    path_costs: FloatArray
    costs: MoveCosts
    carry_kcal: float
    behavior: MigrationBehavior
    memory_years: int


class MigrationSubsystem:
    """Evaluates relocation decisions for all units."""

    name = "migration"

    def _prepare(
        self, unit: PopulationUnit, state: SimulationState, ctx: StepContext
    ) -> _Prepared | None:
        n = unit.population
        beliefs = unit.beliefs
        if n == 0 or beliefs.n_cells == 0:
            return None
        profile = ctx.species(unit.species_id)
        behavior = profile.migration
        temperature = float(state.climate.temperature_c[unit.cell])
        need = (
            annual_need_kcal(unit, profile, ctx.tables[unit.species_id], temperature)
            - unit.energy_debt_kcal
        )
        movement = ctx.movement[unit.species_id]
        cells, path_costs = movement.reachable_arrays(unit.cell)
        known = beliefs.year[cells] != NEVER_OBSERVED
        candidates = cells[known]
        if not (candidates == unit.cell).any():
            return None  # cannot evaluate staying without a current observation
        farm_kcal = unit.fields_ha * unit.crop_yield_kcal_per_ha
        carry = n * profile.movement.carry_kcal_per_capita
        abandoned = max(unit.stores_kcal - carry, 0.0)
        stores_cost = behavior.abandoned_stores_weight * abandoned / need if need > 0 else 0.0
        fields_cost = behavior.abandoned_fields_weight * farm_kcal / need if need > 0 else 0.0
        costs = MoveCosts(movement.reachable(unit.cell), need, stores_cost, fields_cost, farm_kcal)
        return _Prepared(
            unit,
            candidates,
            path_costs[known],
            costs,
            carry,
            behavior,
            profile.cognition.memory_years,
        )

    @staticmethod
    def _scores(prepared: Sequence[_Prepared], year: int) -> list[FloatArray]:
        """Utilities of every candidate of every prepared unit, in one vectorized pass."""
        if not prepared:
            return []
        counts = np.array([p.candidates.size for p in prepared])
        cells = np.concatenate([p.candidates for p in prepared])
        owner = np.repeat(np.arange(len(prepared)), counts)

        def gather(field: str) -> np.ndarray:
            return np.concatenate([getattr(p.unit.beliefs, field)[p.candidates] for p in prepared])

        food, water = gather("food_kcal"), gather("water_access")
        others, observed = gather("population"), gather("year")

        def per_unit(values: list[float]) -> FloatArray:
            array: FloatArray = np.asarray(values, dtype=np.float64)[owner]
            return array

        weights = np.array(
            [
                (
                    p.behavior.food_weight,
                    p.behavior.water_weight,
                    p.behavior.movement_cost_weight,
                    p.behavior.movement_reference_km,
                    p.behavior.uncertainty_weight,
                    p.behavior.food_ratio_cap,
                )
                for p in prepared
            ]
        )[owner]
        scores = candidate_utilities(
            food,
            water,
            others.astype(np.float64),
            (year - observed).astype(np.float64),
            np.concatenate([p.path_costs for p in prepared]),
            cells == per_unit([p.unit.cell for p in prepared]),
            per_unit([p.unit.population for p in prepared]),
            per_unit([p.costs.need_kcal for p in prepared]),
            per_unit([p.costs.farm_kcal for p in prepared]),
            per_unit([p.costs.stores_cost for p in prepared]),
            per_unit([p.costs.fields_cost for p in prepared]),
            per_unit([p.memory_years for p in prepared]),
            weights,
        )
        return np.split(scores, np.cumsum(counts)[:-1])

    def _finish(
        self,
        prepared: _Prepared,
        scores: FloatArray,
        state: SimulationState,
        ctx: StepContext,
        rng: np.random.Generator,
    ) -> MigrationDecision | None:
        unit = prepared.unit
        best = choose_destination(prepared.candidates, scores, unit.cell, rng)
        if best is None:
            return None
        position = {int(c): i for i, c in enumerate(prepared.candidates.tolist())}
        gain = float(scores[position[best]] - scores[position[unit.cell]])
        hazard = migration_probability(gain, prepared.behavior)
        if unit.id in ctx.trace_units:
            components = partial(
                destination_components,
                unit,
                costs=prepared.costs,
                year=state.year,
                memory_years=prepared.memory_years,
                behavior=prepared.behavior,
            )
            ctx.events.emit(
                state.year,
                "trace_migration",
                unit_id=unit.id,
                current_cell=list(state.world.coords(unit.cell)),
                best_cell=list(state.world.coords(best)),
                candidates=int(prepared.candidates.size),
                current={k: round(v, 3) for k, v in components(unit.cell).items()},
                best={k: round(v, 3) for k, v in components(best).items()},
                final_hazard=round(hazard, 4),
            )
        return MigrationDecision(best, hazard, int(prepared.candidates.size), prepared.carry_kcal)

    def decide(
        self,
        unit: PopulationUnit,
        state: SimulationState,
        ctx: StepContext,
        rng: np.random.Generator,
    ) -> MigrationDecision | None:
        """Best-believed destination and move hazard, or ``None`` if staying is the only option."""
        prepared = self._prepare(unit, state, ctx)
        if prepared is None:
            return None
        (scores,) = self._scores([prepared], state.year)
        return self._finish(prepared, scores, state, ctx, rng)

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Relocation]:
        """Decide which units move where this year (scores for all units computed at once)."""
        rng = ctx.rng.stream(Streams.MIGRATION)
        prepared = [p for u in state.units.values() if (p := self._prepare(u, state, ctx))]
        proposals: list[Relocation] = []
        for item, scores in zip(prepared, self._scores(prepared, state.year), strict=True):
            unit = item.unit
            decision = self._finish(item, scores, state, ctx, rng)
            if decision is None or rng.random() >= decision.hazard:
                continue
            cost = item.costs.reachable[decision.destination]
            travel = unit.population * ctx.species(unit.species_id).movement.travel_kcal_per_km
            proposals.append(
                Relocation(
                    unit.id,
                    unit.cell,
                    decision.destination,
                    cost,
                    travel * cost,
                    decision.hazard,
                    decision.carry_kcal,
                )
            )
        return proposals
