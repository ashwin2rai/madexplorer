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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.mobility.exploration import report_confidence
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.groups import sigmoid
from madexplorer.population.unit import Observation, PopulationUnit
from madexplorer.species.profile import MigrationBehavior

FOOD_RATIO_FLOOR = 0.05  # numerical guard: log of an empty cell
FOOD_RATIO_CEILING = 1000.0  # numerical guard for the unbounded forms (1,000 years of need)
# Diagnostic: a decision is food-saturated when the home cell has at least a year of stock per
# head and the food utility's slope dU/d ln R there is below 10% of the plain log's.
SATURATED_SLOPE = 0.1


def food_ratio(
    food_kcal: FloatArray, others: FloatArray, population: FloatArray, need_kcal: FloatArray
) -> FloatArray:
    """Perceived food stock per prospective head, in years of the group's per-capita need."""
    per_head = population + others
    ratio: FloatArray = food_kcal / np.maximum(
        need_kcal * per_head / np.maximum(population, 1.0), 1.0
    )
    return ratio


@model_rule(
    name="food_utility",
    version="2.0",
    rationale=(
        "Value of a cell's food stock R (years of need per prospective head), with diminishing "
        "returns. Forms: capped_log = ln(min(R, cap)) (flat above the cap; the original rule); "
        "log1p = ln(1 + R) (each further year of stock is worth less, marginal value per kcal "
        "1/(1+R), never flat); saturating = R/(R + k) (bounded: value above sufficiency falls "
        "off sharply); log = ln R (diagnostic, no diminishing returns beyond the log). Guards "
        "clamp R to [0.05, 1000] (cap for capped_log)."
    ),
    source_type="heuristic",
    parameters=("food_utility", "food_ratio_cap", "food_half_saturation_years"),
    expected_domain="monotone non-decreasing in R; multiplied by food_weight",
    known_limitations=(
        "Standing stock, not expected sustained yield: regrowth and depletion by the group are "
        "not projected."
    ),
)
def food_utility(ratio: FloatArray, behavior: MigrationBehavior) -> FloatArray:
    """Unweighted food utility of stock ratios under the species' chosen form."""
    form = behavior.food_utility
    if form == "capped_log":
        values = np.log(np.minimum(np.maximum(ratio, FOOD_RATIO_FLOOR), behavior.food_ratio_cap))
    else:
        r = np.minimum(np.maximum(ratio, FOOD_RATIO_FLOOR), FOOD_RATIO_CEILING)
        if form == "log1p":
            values = np.log1p(r)
        elif form == "saturating":
            values = r / (r + behavior.food_half_saturation_years)
        else:
            values = np.log(r)
    result: FloatArray = np.asarray(values, dtype=np.float64)
    return result


def food_utility_slope(ratio: FloatArray, behavior: MigrationBehavior) -> FloatArray:
    """``dU/d ln R`` of :func:`food_utility` (1 for the plain log): food sensitivity."""
    form = behavior.food_utility
    if form == "capped_log":
        within = (ratio >= FOOD_RATIO_FLOOR) & (ratio < behavior.food_ratio_cap)
        slope = np.where(within, 1.0, 0.0)
    elif form == "log1p":
        slope = ratio / (1.0 + ratio)
    elif form == "saturating":
        k = behavior.food_half_saturation_years
        slope = ratio * k / (ratio + k) ** 2
    else:
        slope = np.ones_like(ratio)
    result: FloatArray = np.asarray(slope, dtype=np.float64)
    return result


@model_rule(
    name="perceived_cell_utility",
    version="2.0",
    rationale=(
        "Utility = w_food*food_utility(perceived food per head relative to need) + "
        "w_water*water - w_move*path_cost/reference - w_uncertainty*information_age/memory."
    ),
    source_type="heuristic",
    parameters=(
        "food_weight",
        "water_weight",
        "movement_cost_weight",
        "movement_reference_km",
        "uncertainty_weight",
    ),
    expected_domain="real-valued score; only differences matter",
    known_limitations="No security, trade, disease, or extraction terms until later MVPs.",
)
def cell_utility(
    observation: Observation,
    water_access: float,
    population: int,
    need_kcal: float,
    path_cost_km: float,
    information_age_years: int,
    memory_years: int,
    behavior: MigrationBehavior,
) -> dict[str, float]:
    """Utility components of settling in a cell (noise excluded).

    ``water_access`` is the cell's static, exactly known water access (read from the world
    once the cell is known), not part of the belief.
    """
    ratio = food_ratio(
        np.array([observation.food_kcal]),
        np.array([float(observation.population)]),
        np.array([float(population)]),
        np.array([need_kcal]),
    )
    return {
        "expected_food": behavior.food_weight * float(food_utility(ratio, behavior)[0]),
        "water_access": behavior.water_weight * water_access,
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


@model_rule(
    name="direct_observation_confidence",
    version="1.0",
    rationale=(
        "Precision weighting of one noisy direct observation: q = tau^2 / (tau^2 + sigma^2), "
        "with sigma^2 the (log) observation-noise variance and tau^2 the estimated true "
        "between-cell variance of the group's surroundings (food_prior). Where cells really "
        "differ much more than the noise, observations are trusted; where apparent differences "
        "are mostly noise, they are discounted. Switchable (mechanisms."
        "direct_observation_shrinkage); off means direct observations are taken at face value."
    ),
    source_type="theoretical",
    parameters=("observation_noise_sigma",),
    expected_domain="confidence in [0, 1]",
    known_limitations="tau^2 comes from one year's neighborhood and is itself noisy.",
)
def direct_confidence(signal_var: float, noise_sigma: float, enabled: bool) -> float:
    """Confidence in a single direct observation (1 when shrinkage is off or noise is 0)."""
    noise_var = noise_sigma**2
    if not enabled or noise_var == 0:
        return 1.0
    return signal_var / (signal_var + noise_var)


@model_rule(
    name="belief_shrinkage",
    version="2.0",
    rationale=(
        "A food belief held with confidence q is used as exp(q*ln(belief) + (1-q)*log_prior): "
        "shrinkage toward the group's log-space prior (noise is multiplicative). Confidence is "
        "the direct-observation confidence times transmission_confidence_decay per relay, so "
        "hearsay about exceptional places counts but cannot dominate a choice among uncertain "
        "options (limits the winner's curse). A belief with q = 1 is used unchanged."
    ),
    source_type="heuristic",
    parameters=("transmission_confidence_decay", "observation_noise_sigma"),
    expected_domain="effective food estimate between the prior and the belief (geometrically)",
    known_limitations=(
        "Prior from this year's perception only; staleness is handled by the separate "
        "uncertainty term, not by confidence."
    ),
)
def shrunk_food_kcal(
    food_kcal: FloatArray | float, confidence: FloatArray | float, log_prior: FloatArray | float
) -> FloatArray:
    """Effective food belief: confidence-weighted log-space mix of the belief and the prior."""
    food = np.asarray(food_kcal, dtype=np.float64)
    q = np.asarray(confidence, dtype=np.float64)
    with np.errstate(invalid="ignore"):
        mixed = np.exp(q * np.log(np.maximum(food, 1.0)) + (1.0 - q) * np.asarray(log_prior))
    shrunk: FloatArray = np.where(q >= 1.0, food, mixed)
    return shrunk


def attention_set(
    candidates: IntArray, path_costs: FloatArray, current: int, cap: int | None
) -> IntArray:
    """Indices of the candidates a group considers: all, or the current cell plus the nearest.

    The cap is utility-blind (path cost, then cell id), so it cannot re-create a best-of-many
    selection. ``None`` keeps every reachable known cell. Indices are returned ascending.
    """
    if cap is None or candidates.size <= cap:
        return np.arange(candidates.size)
    others = np.flatnonzero(candidates != current)
    nearest = others[np.lexsort((candidates[others], path_costs[others]))[: cap - 1]]
    keep: IntArray = np.sort(np.concatenate([np.flatnonzero(candidates == current), nearest]))
    return keep


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
    water_access: float,
    confidence_decay: float,
    direct_confidence: float,
) -> dict[str, float]:
    """Utility components of ``cell`` for ``unit``, including the cost of leaving."""
    obs = unit.beliefs[cell]
    relay = float(report_confidence(np.array([obs.hops]), confidence_decay)[0])
    food = float(shrunk_food_kcal(obs.food_kcal, direct_confidence * relay, unit.food_log_prior))
    obs = replace(obs, food_kcal=food)
    staying = cell == unit.cell
    if staying and costs.farm_kcal > 0:
        obs = replace(obs, food_kcal=obs.food_kcal + costs.farm_kcal)
    components = cell_utility(
        obs,
        water_access,
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
    food_term: FloatArray,
    water_access: FloatArray,
    age_years: FloatArray,
    path_cost_km: FloatArray,
    staying: BoolArray,
    stores_cost: FloatArray,
    fields_cost: FloatArray,
    memory_years: FloatArray,
    weights: FloatArray,
) -> FloatArray:
    """:func:`cell_utility` plus leaving costs for many candidates at once (numpy).

    Every argument is one value per candidate (per-unit values repeated); ``food_term`` is
    ``food_weight * food_utility``; ``weights`` has columns food, water, movement, movement
    reference km, uncertainty. Matches the scalar rule up to floating-point rounding.
    """
    utility: FloatArray = (
        food_term
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
    confidence_decay: float
    direct_confidence: float


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
        known = beliefs.current(cells, state.year, profile.cognition.memory_years)
        candidates, path_costs = cells[known], path_costs[known]
        if not (candidates == unit.cell).any():
            return None  # cannot evaluate staying without a current observation
        considered = attention_set(
            candidates, path_costs, unit.cell, behavior.max_considered_destinations
        )
        candidates, path_costs = candidates[considered], path_costs[considered]
        farm_kcal = unit.fields_ha * unit.crop_yield_kcal_per_ha
        carry = n * profile.movement.carry_kcal_per_capita
        abandoned = max(unit.stores_kcal - carry, 0.0)
        stores_cost = behavior.abandoned_stores_weight * abandoned / need if need > 0 else 0.0
        fields_cost = behavior.abandoned_fields_weight * farm_kcal / need if need > 0 else 0.0
        costs = MoveCosts(movement.reachable(unit.cell), need, stores_cost, fields_cost, farm_kcal)
        return _Prepared(
            unit,
            candidates,
            path_costs,
            costs,
            carry,
            behavior,
            profile.cognition.memory_years,
            profile.social_information.transmission_confidence_decay,
            direct_confidence(
                unit.food_log_signal_var,
                profile.cognition.observation_noise_sigma,
                ctx.mechanisms.direct_observation_shrinkage,
            ),
        )

    @staticmethod
    def _scores(
        prepared: Sequence[_Prepared], year: int, water_access: FloatArray
    ) -> list[tuple[FloatArray, FloatArray]]:
        """Utilities and food ratios of every candidate of every prepared unit, in one pass."""
        if not prepared:
            return []
        counts = np.array([p.candidates.size for p in prepared])
        cells = np.concatenate([p.candidates for p in prepared])
        owner = np.repeat(np.arange(len(prepared)), counts)

        def gather(field: str) -> np.ndarray:
            return np.concatenate([getattr(p.unit.beliefs, field)[p.candidates] for p in prepared])

        others, observed = gather("population"), gather("year")

        def per_unit(values: list[float]) -> FloatArray:
            array: FloatArray = np.asarray(values, dtype=np.float64)[owner]
            return array

        confidence = per_unit([p.direct_confidence for p in prepared]) * np.power(
            per_unit([p.confidence_decay for p in prepared]), gather("hops").astype(np.float64)
        )
        food = shrunk_food_kcal(
            gather("food_kcal").astype(np.float64),
            confidence,
            per_unit([p.unit.food_log_prior for p in prepared]),
        )
        water = water_access[cells]
        staying = cells == per_unit([p.unit.cell for p in prepared])
        farm = per_unit([p.costs.farm_kcal for p in prepared])
        food = np.where(staying & (farm > 0), food + farm, food)
        ratio = food_ratio(
            food,
            others.astype(np.float64),
            per_unit([p.unit.population for p in prepared]),
            per_unit([p.costs.need_kcal for p in prepared]),
        )
        food_term = np.empty_like(ratio)
        behaviors = {id(p.behavior): p.behavior for p in prepared}
        behavior_of = np.array([id(p.behavior) for p in prepared])[owner]
        for key, behavior in behaviors.items():
            rows = behavior_of == key
            food_term[rows] = behavior.food_weight * food_utility(ratio[rows], behavior)
        weights = np.array(
            [
                (
                    p.behavior.food_weight,
                    p.behavior.water_weight,
                    p.behavior.movement_cost_weight,
                    p.behavior.movement_reference_km,
                    p.behavior.uncertainty_weight,
                )
                for p in prepared
            ]
        )[owner]
        scores = candidate_utilities(
            food_term,
            water,
            (year - observed).astype(np.float64),
            np.concatenate([p.path_costs for p in prepared]),
            staying,
            per_unit([p.costs.stores_cost for p in prepared]),
            per_unit([p.costs.fields_cost for p in prepared]),
            per_unit([p.memory_years for p in prepared]),
            weights,
        )
        split = np.cumsum(counts)[:-1]
        return list(zip(np.split(scores, split), np.split(ratio, split), strict=True))

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

            def components(cell: int) -> dict[str, float]:
                return destination_components(
                    unit,
                    cell,
                    prepared.costs,
                    state.year,
                    prepared.memory_years,
                    prepared.behavior,
                    float(state.world.water_access[cell]),
                    prepared.confidence_decay,
                    prepared.direct_confidence,
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
        ((scores, _),) = self._scores([prepared], state.year, state.world.water_access)
        return self._finish(prepared, scores, state, ctx, rng)

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Relocation]:
        """Decide which units move where this year (scores for all units computed at once)."""
        rng = ctx.rng.stream(Streams.MIGRATION)
        prepared = [p for u in state.units.values() if (p := self._prepare(u, state, ctx))]
        proposals: list[Relocation] = []
        home_ratios: dict[int, list[float]] = {}
        behaviors: dict[int, MigrationBehavior] = {}
        for item, (scores, ratios) in zip(
            prepared, self._scores(prepared, state.year, state.world.water_access), strict=True
        ):
            unit = item.unit
            decision = self._finish(item, scores, state, ctx, rng)
            if decision is not None:
                key = id(item.behavior)
                behaviors[key] = item.behavior
                home_ratios.setdefault(key, []).append(
                    float(ratios[item.candidates == unit.cell][0])
                )
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
        for key, values in home_ratios.items():
            ratio = np.asarray(values)
            flat = (food_utility_slope(ratio, behaviors[key]) < SATURATED_SLOPE) & (ratio > 1.0)
            ctx.ledger.migration_decisions += ratio.size
            ctx.ledger.food_saturated_decisions += int(flat.sum())
        return proposals
