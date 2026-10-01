"""Foraging with diminishing returns and within-cell competition (spec §4.4, §9.1).

Harvest from a resource with accessible stock ``A`` and initial return rate
``r`` (kcal per effective labor hour) under effort ``E`` is
``A * (1 - exp(-r * E / A))``: early hours are productive, later hours deplete
the patch. Groups in the same cell share one pool, so crowding lowers returns.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.population.energetics import annual_need_columns
from madexplorer.population.familiarity import FamiliarityRule, familiarity_rule
from madexplorer.species.profile import Foraging
from madexplorer.world.grid import WorldGrid

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns
    from madexplorer.core.spatial import SpatialIndex


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


def single_unit_harvest(
    stock: tuple[float, float],
    returns: tuple[float, float],
    labor_hours: float,
    efficiency: float,
    target_kcal: float,
) -> tuple[float, float, float, float, float]:
    """:func:`cell_harvest` for a cell with one group, in Python floats (bit-identical).

    Returns ``(share, plant_removed, game_removed, effort_fraction, marginal)``. With one
    group numpy's sums reduce to the element itself (effort) and ``a + b`` (removal), so
    scalar arithmetic reproduces the array path exactly (differential test).
    """
    effective = labor_hours * efficiency
    capacity = effective
    if capacity <= 0:
        return 0.0, 0.0, 0.0, 0.0, _marginal_return(stock, returns, 0.0)
    fraction = 1.0
    if sum(_harvest(stock, returns, capacity)) > target_kcal:
        fraction = _effort_fraction(stock, returns, capacity, target_kcal)
    plant, game = _harvest(stock, returns, capacity * fraction)
    share = (plant + game) * effective / capacity
    return share, plant, game, fraction, _marginal_return(stock, returns, capacity * fraction)


@dataclass(frozen=True, eq=False)
class CellHarvests:
    """Foraging outcomes of every (cell, species) group, packed; applied in group order.

    Equivalent to one :class:`CellHarvest` per group, applied in that order: stocks per
    group, then each member's columns; the ledger total is accumulated in member order.
    """

    cols: "UnitColumns"
    cells: tuple[int, ...]
    bounds: tuple[int, ...]  # (groups + 1,) positions in ``rows`` of each group's members
    rows: IntArray  # row positions in cols, grouped
    harvest_kcal: FloatArray
    hours: FloatArray
    marginal_kcal_per_hour: FloatArray
    plant_removed_kcal: tuple[float, ...]
    game_removed_kcal: tuple[float, ...]
    learning_rate: tuple[float, ...]
    familiarity: tuple[FamiliarityRule, ...]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Deplete stocks, credit harvests, and grow local familiarity (learning by doing)."""
        eco = state.ecology
        plant_stock, game_stock = eco.plant_stock_kcal, eco.game_stock_kcal
        year = state.year
        bounds = self.bounds
        cols, rows = self.cols, self.rows
        plant_share = np.empty(rows.size)
        units = cols.units
        rows_list = rows.tolist()
        for k, cell in enumerate(self.cells):
            plant_removed, game_removed = self.plant_removed_kcal[k], self.game_removed_kcal[k]
            plant_stock[cell] = max(plant_stock[cell] - plant_removed, 0.0)
            game_stock[cell] = max(game_stock[cell] - game_removed, 0.0)
            removed = plant_removed + game_removed
            plant_share[bounds[k] : bounds[k + 1]] = plant_removed / removed if removed > 0 else 0.0
            rate, rule = self.learning_rate[k], self.familiarity[k]
            for r in rows_list[bounds[k] : bounds[k + 1]]:
                units[r].familiarity.practice(cell, year, rate, rule)
        harvest = cols.get("farm_harvest_kcal")[rows] + self.harvest_kcal
        cols.set_rows("forage_harvest_kcal", rows, self.harvest_kcal)
        cols.set_rows("forage_hours", rows, self.hours)
        cols.set_rows("forage_marginal_kcal_per_hour", rows, self.marginal_kcal_per_hour)
        cols.set_rows("forage_plant_share", rows, plant_share)
        cols.set_rows("harvest_kcal", rows, harvest)
        cols.set_rows("labor_debt_hours", rows, 0.0)
        ledger = ctx.ledger
        total = ledger.harvest_kcal
        for value in harvest.tolist():
            total += value
        ledger.harvest_kcal = total


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
    familiarity: FamiliarityRule

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
            unit.familiarity.practice(self.cell, state.year, self.learning_rate, self.familiarity)
            ctx.ledger.harvest_kcal += unit.harvest_kcal


_AccessMatrices = tuple[FloatArray, FloatArray, FloatArray, FloatArray]


@dataclass(frozen=True, eq=False)
class _ForageInputs:
    """Per-unit foraging inputs of one step, computed once in batched form."""

    index: "SpatialIndex"
    cols: "UnitColumns"
    species: IntArray
    labor: FloatArray
    efficiency: FloatArray
    target_share: FloatArray
    rules: dict[str, FamiliarityRule]


class ForagingSubsystem:
    """Every group forages in its current cell with the labor left after field work."""

    name = "foraging"

    def __init__(self) -> None:
        self._access: tuple[object, _AccessMatrices] | None = None

    def _inputs(self, state: SimulationState, ctx: StepContext) -> _ForageInputs | None:
        index = ctx.spatial(state)
        cols = ctx.columns(state)
        units = cols.units
        if not units:
            return None
        compiled = ctx.compiled
        assert compiled is not None
        year = state.year
        species = cols.species()
        p = compiled.parameter
        hours_per_year = p("foraging.foraging_hours_per_day")[species] * 365.0
        capacity = cols.weighted(
            {k: ctx.tables[sid].labor for k, sid in enumerate(compiled.species_ids)}
        )
        debt = cols.get("labor_debt_hours")
        farm_hours = cols.get("farm_hours")
        labor = np.maximum(capacity * hours_per_year - debt - farm_hours, 0.0)
        rules = {
            sid: familiarity_rule(profile, ctx.mechanisms)
            for sid, profile in ctx.scenario.species.items()
        }
        cells_list = cols.get("cell").tolist()
        familiarity = np.array(
            [
                u.familiarity.effective(c, year, rules[u.species_id])
                for u, c in zip(units, cells_list, strict=True)
            ],
            dtype=np.float64,
        )
        knowledge = ctx.knowledge
        if knowledge is not None and "ecology" in knowledge.index:
            domain = knowledge.index["ecology"]
            level = cols.knowledge()[:, domain].astype(np.float64)
            efficiency = familiarity * (level / (level + float(knowledge.half_efficiency[domain])))
        else:
            efficiency = familiarity * 1.0
        farm_harvest = cols.get("farm_harvest_kcal")
        need = annual_need_columns(cols, state, ctx)
        target_share = np.maximum(
            need * (1.0 + p("foraging.surplus_target")[species]) - farm_harvest, 0.0
        )
        return _ForageInputs(index, cols, species, labor, efficiency, target_share, rules)

    def _access_matrices(self, ctx: StepContext) -> "_AccessMatrices":
        """``(plant_access, game_access, plant_return, game_return)`` as (species, cells)
        matrices in compiled species order (static; cached per run)."""
        cached = self._access
        if cached is None or cached[0] is not ctx.static:
            assert ctx.compiled is not None
            tuples = [ctx.forage[sid].as_tuple() for sid in ctx.compiled.species_ids]
            plant_access, game_access, plant_return, game_return = (
                np.ascontiguousarray(np.stack([t[k] for t in tuples]), dtype=np.float64)
                for k in range(4)
            )
            matrices = (plant_access, game_access, plant_return, game_return)
            cached = (ctx.static, matrices)
            self._access = cached
        return cached[1]

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[CellHarvests]:
        """Compute harvests; groups of different species in one cell forage in id order.

        Per-unit inputs are batched (:meth:`_inputs`); every (cell, species) group's pool is
        then solved by one compiled call (:func:`~madexplorer.economy.foraging_kernel.
        forage_groups`) in the order of the spatial index, bit-identical to
        :meth:`_evaluate_reference`.
        """
        from madexplorer.economy.foraging_kernel import forage_groups

        inputs = self._inputs(state, ctx)
        if inputs is None:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        index, cols = inputs.index, inputs.cols
        order, starts = index.order, index.starts
        if len(compiled.species_ids) == 1:
            rows = order
            bounds = starts
            group_cell = index.cells
            group_code = np.zeros(group_cell.size, dtype=np.int64)
        else:  # within a cell, species groups by code, members in index order
            cell_of = np.repeat(np.arange(index.cells.size), np.diff(starts))
            codes = inputs.species[order]
            perm = np.lexsort((np.arange(order.size), codes, cell_of))
            rows, cell_of, codes = order[perm], cell_of[perm], codes[perm]
            first = np.r_[True, (cell_of[1:] != cell_of[:-1]) | (codes[1:] != codes[:-1])]
            heads = np.flatnonzero(first)
            bounds = np.r_[heads, rows.size]
            group_cell = index.cells[cell_of[heads]]
            group_code = codes[heads]
        rows = np.ascontiguousarray(rows, dtype=np.int64)
        bounds = np.ascontiguousarray(bounds, dtype=np.int64)
        group_cell = np.ascontiguousarray(group_cell, dtype=np.int64)
        group_code = np.ascontiguousarray(group_code, dtype=np.int64)
        n_groups = group_cell.size
        plant_left = state.ecology.plant_stock_kcal.astype(np.float64, copy=True)
        game_left = state.ecology.game_stock_kcal.astype(np.float64, copy=True)
        harvests = np.empty(rows.size)
        hours = np.empty(rows.size)
        marginals = np.empty(rows.size)
        plant_removed = np.empty(n_groups)
        game_removed = np.empty(n_groups)
        largest = int(np.diff(bounds).max()) if n_groups else 0
        forage_groups(
            rows,
            bounds,
            group_cell,
            group_code,
            np.ascontiguousarray(inputs.labor, dtype=np.float64),
            np.ascontiguousarray(inputs.efficiency, dtype=np.float64),
            np.ascontiguousarray(inputs.target_share, dtype=np.float64),
            plant_left,
            game_left,
            *self._access_matrices(ctx),
            harvests,
            hours,
            marginals,
            plant_removed,
            game_removed,
            np.empty(largest),
            np.empty(largest),
        )
        rates = [
            ctx.species(sid).cognition.familiarity_learning_rate for sid in compiled.species_ids
        ]
        rules = [inputs.rules[sid] for sid in compiled.species_ids]
        code_list = group_code.tolist()
        return [
            CellHarvests(
                cols,
                tuple(group_cell.tolist()),
                tuple(bounds.tolist()),
                rows,
                harvests,
                hours,
                marginals,
                tuple(plant_removed.tolist()),
                tuple(game_removed.tolist()),
                tuple(rates[c] for c in code_list),
                tuple(rules[c] for c in code_list),
            )
        ]

    def _evaluate_reference(
        self, state: SimulationState, ctx: StepContext
    ) -> Sequence[CellHarvests]:
        """The PH3b Python path (reference for the compiled kernel; differential tests).

        Per-unit inputs (labor, efficiency, target share) are computed for all units in one
        batched pass; each cell's shared pool is then solved as before, in the order of
        the spatial index (cells in first-appearance order, units in unit order).
        """
        inputs = self._inputs(state, ctx)
        if inputs is None:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        index, cols, species = inputs.index, inputs.cols, inputs.species
        labor, efficiency, rules = inputs.labor, inputs.efficiency, inputs.rules
        target_share = inputs.target_share.tolist()
        access = {sid: forage.as_tuple() for sid, forage in ctx.forage.items()}
        plant_left = state.ecology.plant_stock_kcal.copy()
        game_left = state.ecology.game_stock_kcal.copy()
        labor_list, efficiency_list = labor.tolist(), efficiency.tolist()
        single_species = len(compiled.species_ids) == 1
        group_cells: list[int] = []
        bounds = [0]
        order_rows: list[int] = []
        harvests: list[float] = []
        hours: list[float] = []
        marginals: list[float] = []
        plant_removed: list[float] = []
        game_removed: list[float] = []
        rates: list[float] = []
        rules_used: list[FamiliarityRule] = []
        order, starts = index.order, index.starts
        for k, cell in enumerate(index.cells.tolist()):
            rows = order[starts[k] : starts[k + 1]]
            if single_species:
                groups = [(0, rows)]
            else:
                codes = species[rows]
                groups = [(c, rows[codes == c]) for c in np.unique(codes).tolist()]
            for code, group in groups:
                species_id = compiled.species_ids[code]
                profile = ctx.species(species_id)
                plant_access, game_access, plant_return, game_return = access[species_id]
                members = group.tolist()
                if len(members) == 1:
                    r = members[0]
                    stock = (
                        float(plant_left[cell] * plant_access[cell]),
                        float(game_left[cell] * game_access[cell]),
                    )
                    returns = (float(plant_return[cell]), float(game_return[cell]))
                    share, plant, game, fraction, marginal = single_unit_harvest(
                        stock, returns, labor_list[r], efficiency_list[r], 0 + target_share[r]
                    )
                    harvests.append(share)
                    hours.append(labor_list[r] * fraction)
                    marginals.append(marginal * efficiency_list[r])
                else:
                    accessible = np.array(
                        [plant_left[cell] * plant_access[cell], game_left[cell] * game_access[cell]]
                    )
                    rates_cell = np.array([plant_return[cell], game_return[cell]])
                    group_labor = labor[group]
                    group_efficiency = efficiency[group]
                    target = sum([target_share[r] for r in members])
                    outcome = cell_harvest(
                        accessible, rates_cell, group_labor, group_efficiency, target
                    )
                    plant, game = float(outcome.removal[0]), float(outcome.removal[1])
                    fraction = outcome.effort_fraction
                    marginal = outcome.marginal_kcal_per_effective_hour
                    harvests.extend(outcome.shares.tolist())
                    hours.extend(x * fraction for x in group_labor.tolist())
                    marginals.extend(marginal * e for e in group_efficiency.tolist())
                plant_left[cell] -= plant
                game_left[cell] -= game
                group_cells.append(cell)
                order_rows.extend(members)
                bounds.append(len(order_rows))
                plant_removed.append(plant)
                game_removed.append(game)
                rates.append(profile.cognition.familiarity_learning_rate)
                rules_used.append(rules[species_id])
        return [
            CellHarvests(
                cols,
                tuple(group_cells),
                tuple(bounds),
                np.array(order_rows, dtype=np.int64),
                np.array(harvests, dtype=np.float64),
                np.array(hours, dtype=np.float64),
                np.array(marginals, dtype=np.float64),
                tuple(plant_removed),
                tuple(game_removed),
                tuple(rates),
                tuple(rules_used),
            )
        ]
