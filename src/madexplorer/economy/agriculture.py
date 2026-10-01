"""Cultivation: crop yields, clearing, soil dynamics, and field planning (spec §4.5, §18).

Cultivation is never switched on by a rule. Groups hold fields only when their
technology gives a positive crop-yield capability, and they expand or shrink
fields by comparing the return per hour of farming with the marginal return of
foraging. Farming typically returns less per hour than rich foraging but far
more per hectare and depletes wild stocks less, so it wins where crowding and
depletion have driven foraging returns down.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.config.schema import AgricultureConfig
from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.ecology.resources import miami_npp
from madexplorer.population.energetics import annual_need_columns, capability_column
from madexplorer.population.unit import PopulationUnit
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns

HECTARES_PER_KM2 = 100.0


@model_rule(
    name="arable_land",
    version="1.0",
    rationale=(
        "Arable area per cell shrinks linearly with slope up to a limit and is capped by a "
        "maximum fraction."
    ),
    source_type="heuristic",
    parameters=("arable_slope_limit", "max_arable_fraction"),
    expected_domain="hectares per cell, 0 on water",
    known_limitations="No terracing, drainage, or soil-depth constraints.",
)
def arable_hectares(world: WorldGrid, config: AgricultureConfig) -> FloatArray:
    """Cultivable hectares per cell."""
    fraction = (
        np.clip(1.0 - world.slope / config.arable_slope_limit, 0.0, 1.0)
        * config.max_arable_fraction
    )
    hectares: FloatArray = np.where(
        world.is_water, 0.0, fraction * world.cell_area_km2 * HECTARES_PER_KM2
    )
    return hectares


@model_rule(
    name="crop_potential_yield",
    version="1.0",
    rationale=(
        "Potential crop yield scales with this year's climatic productivity (relative to a "
        "reference NPP), static soil fertility, and the dynamic soil nutrient state."
    ),
    source_type="heuristic",
    parameters=("crop_max_yield_kcal_per_ha", "crop_reference_npp_g_m2"),
    expected_domain="kcal per hectare per year before technology and knowledge",
    known_limitations="One generic crop; no photoperiod, frost, or crop-specific water needs.",
)
def crop_potential_kcal_per_ha(
    world: WorldGrid, climate: ClimateYear, soil_nutrients: FloatArray, config: AgricultureConfig
) -> FloatArray:
    """Potential yield per hectare in each cell for this year's climate."""
    npp = miami_npp(climate.temperature_c, climate.rainfall_mm)
    climate_factor = np.clip(npp / config.crop_reference_npp_g_m2, 0.0, 1.0)
    potential: FloatArray = np.where(
        world.is_water,
        0.0,
        config.crop_max_yield_kcal_per_ha * climate_factor * world.soil_fertility * soil_nutrients,
    )
    return potential


def realized_yield_kcal_per_ha(
    potential: float, crop_capability: float, agriculture_efficiency: float
) -> float:
    """Yield a group obtains per hectare given its crop technology and agricultural knowledge."""
    return potential * max(crop_capability, 0.0) * agriculture_efficiency


@model_rule(
    name="clearing_labor",
    version="1.0",
    rationale=(
        "Clearing land costs labor that rises steeply with vegetation density and falls with tools."
    ),
    source_type="heuristic",
    parameters=("clearing_hours_per_ha", "clearing_vegetation_multiplier"),
    expected_domain="hours per hectare, >= 0",
    known_limitations="Cleared land does not yet change the vegetation field or movement friction.",
)
def clearing_hours_per_ha(
    vegetation: float, config: AgricultureConfig, clearing_efficiency: float
) -> float:
    """Labor to bring one hectare into cultivation."""
    raw = config.clearing_hours_per_ha * (1.0 + config.clearing_vegetation_multiplier * vegetation)
    return raw / max(clearing_efficiency, 1e-6)


@model_rule(
    name="soil_nutrient_dynamics",
    version="2.0",
    rationale=(
        "The nutrient state is the fertility of the cell's cultivated land. While a cell is "
        "cultivated, cropping depletes it in proportion to its level (reduced by soil "
        "management) and slow natural inputs (deposition, fixation, weathering) replenish it, "
        "so unmanaged continuous cropping settles at a low equilibrium "
        "r_c / (r_c + d(1 - m)). Once cultivation stops the land recovers faster, as fallow. "
        "How much of the cell is farmed does not matter: uncultivated land in the same cell "
        "does not restore fertility to the fields (no free fallowing)."
    ),
    source_type="heuristic",
    parameters=(
        "soil_depletion_rate",
        "soil_cultivated_recovery_rate",
        "soil_recovery_rate",
    ),
    expected_domain="nutrient state in [0, 1]",
    known_limitations=(
        "One fertility pool per cell: newly cleared land inherits the state of existing "
        "fields, and there are no separate fallow, exhausted, manured or eroded pools."
    ),
)
def update_soil_nutrients(
    nutrients: FloatArray,
    cultivated: BoolArray,
    soil_management: FloatArray,
    config: AgricultureConfig,
) -> FloatArray:
    """Advance the fertility of cultivated land by one year (fallow where not cultivated)."""
    management = np.clip(soil_management, 0.0, 1.0)
    depletion = config.soil_depletion_rate * (1.0 - management) * nutrients
    recovery_rate = np.where(
        cultivated, config.soil_cultivated_recovery_rate, config.soil_recovery_rate
    )
    change = np.where(cultivated, -depletion, 0.0) + recovery_rate * (1.0 - nutrients)
    updated: FloatArray = np.clip(nutrients + change, 0.0, 1.0)
    return updated


@model_rule(
    name="field_adjustment",
    version="1.2",
    rationale=(
        "Groups expand fields when farming's return per hour, with clearing labor amortized over "
        "the tenure they expect (years resident so far, capped by the planning horizon), beats "
        "marginal foraging by a margin; they shrink fields when the return on existing fields "
        "(clearing already sunk) falls short. Adjustment speed is bounded, and fields never "
        "exceed what meets requirement plus the surplus target (satisficing, as in foraging)."
    ),
    source_type="heuristic",
    parameters=(
        "field_adjustment_rate",
        "initial_plot_ha",
        "return_comparison_margin",
        "max_farm_labor_share",
        "planning_horizon_years",
    ),
    expected_domain="new field area >= 0 hectares",
    known_limitations="Myopic (uses this year's returns); no risk diversification motive yet.",
)
def adjusted_fields_ha(
    fields_ha: float,
    yield_per_ha: float,
    cultivation_hours_per_ha: float,
    clearing_hours: float,
    expected_tenure_years: float,
    forage_marginal: float,
    adjustment_rate: float,
    initial_plot_ha: float,
    margin: float,
) -> tuple[float, float]:
    """Return ``(desired_fields_ha, return_gap)`` for next year."""
    threshold = forage_marginal * (1.0 + margin)
    new_land_return = yield_per_ha / (
        cultivation_hours_per_ha + clearing_hours / max(expected_tenure_years, 1.0)
    )
    expand_gap = (new_land_return - threshold) / max(new_land_return, threshold, 1e-9)
    if expand_gap > 0:
        return fields_ha + adjustment_rate * expand_gap * (fields_ha + initial_plot_ha), expand_gap
    existing_return = yield_per_ha / cultivation_hours_per_ha
    keep_gap = (existing_return - threshold) / max(existing_return, threshold, 1e-9)
    if keep_gap < 0 and fields_ha > 0:
        return fields_ha * (1.0 + adjustment_rate * max(keep_gap, -1.0)), keep_gap
    return fields_ha, 0.0


@model_rule(
    name="field_growth_to_target",
    version="1.0",
    rationale=(
        "When new land pays (the same return comparison as field_adjustment), a group closes a "
        "fraction of the gap between its fields and the area that meets its requirement plus "
        "the surplus target each year, as an investment decision on a multi-year timescale. "
        "The step is limited by labor: land cleared this year (its clearing labor is charged "
        "to next year) must still leave enough of next year's farm labor share to work all "
        "fields, existing ones included. Existing fields shrink as in field_adjustment."
    ),
    source_type="heuristic",
    parameters=(
        "field_adjustment_rate",
        "return_comparison_margin",
        "max_farm_labor_share",
        "cultivation_hours_per_ha",
        "clearing_hours_per_ha",
    ),
    expected_domain="new field area in [0, need area]; expansion <= labor-feasible area",
    known_limitations=(
        "Myopic returns; the target is the whole requirement, and mixed subsistence arises "
        "only through the yearly return comparison (foraging's marginal return rises as "
        "foraging effort falls); arable limits are applied per cell afterwards."
    ),
)
def fields_toward_target(
    fields_ha: float,
    yield_per_ha: float,
    cultivation_hours_per_ha: float,
    clearing_hours: float,
    expected_tenure_years: float,
    forage_marginal: float,
    adjustment_rate: float,
    margin: float,
    need_ha: float,
    farm_labor_hours: float,
    labor_share: float,
) -> tuple[float, float, str]:
    """Return ``(desired_fields_ha, return_gap, binding_limit)`` for next year.

    ``farm_labor_hours`` is labor capacity times ``labor_share`` (the farm labor share).
    ``binding_limit`` is "target" or "labor" for an expansion, "" otherwise.
    """
    threshold = forage_marginal * (1.0 + margin)
    new_land_return = yield_per_ha / (
        cultivation_hours_per_ha + clearing_hours / max(expected_tenure_years, 1.0)
    )
    expand_gap = (new_land_return - threshold) / max(new_land_return, threshold, 1e-9)
    if expand_gap > 0:
        target_step = adjustment_rate * (need_ha - fields_ha)
        # Next year: (L - dF * clearing) * share >= (F + dF) * cultivation.
        labor_step = max(farm_labor_hours - fields_ha * cultivation_hours_per_ha, 0.0) / (
            labor_share * clearing_hours + cultivation_hours_per_ha
        )
        step = min(target_step, labor_step)
        if step <= 0:
            return fields_ha, expand_gap, ""
        return fields_ha + step, expand_gap, "target" if target_step <= labor_step else "labor"
    existing_return = yield_per_ha / cultivation_hours_per_ha
    keep_gap = (existing_return - threshold) / max(existing_return, threshold, 1e-9)
    if keep_gap < 0 and fields_ha > 0:
        return fields_ha * (1.0 + adjustment_rate * max(keep_gap, -1.0)), keep_gap, ""
    return fields_ha, 0.0, ""


@model_rule(
    name="expected_tenure",
    version="1.0",
    rationale=(
        "Durable field investment is amortized over the years the group expects to stay: "
        "with last year's annual move hazard m and stay probability p = 1 - m, the expected "
        "number of future years within the planning horizon H is sum_{t=1..H} p^t = "
        "p(1 - p^H)/(1 - p) (H when p = 1). The hazard is last year's, so investment and "
        "moving do not depend on each other within a year. Without a known hazard (just "
        "arrived, never evaluated) the pre-reform proxy min(max(residence, 1), H) is used."
    ),
    source_type="theoretical",
    parameters=("planning_horizon_years",),
    expected_domain="[0, H] years",
    known_limitations="Assumes a constant hazard over the horizon.",
)
def expected_tenure_years(move_hazard: float, horizon_years: int, residence_years: int) -> float:
    """Expected future years in the current cell within the planning horizon."""
    if math.isnan(move_hazard):
        return float(min(max(residence_years, 1), horizon_years))
    p = min(max(1.0 - move_hazard, 0.0), 1.0)
    if 1.0 - p < 1e-9:
        return float(horizon_years)
    return p * (1.0 - p**horizon_years) / (1.0 - p)


def unit_labor_hours(unit: PopulationUnit, ctx: StepContext) -> float:
    """Annual labor capacity of a unit."""
    profile = ctx.species(unit.species_id)
    tables = ctx.tables[unit.species_id]
    adults = unit.weighted_count(tables.labor)
    return adults * profile.foraging.foraging_hours_per_day * 365.0


def unit_crop_yield(unit: PopulationUnit, potential: FloatArray, ctx: StepContext) -> float:
    """Realized yield per hectare for a unit in its current cell."""
    capabilities = ctx.capabilities(unit)
    efficiency = ctx.knowledge.efficiency(unit.knowledge, "agriculture") if ctx.knowledge else 1.0
    return realized_yield_kcal_per_ha(
        float(potential[unit.cell]), capabilities["crop_yield"], efficiency
    )


def labor_hours_columns(cols: "UnitColumns", ctx: StepContext) -> FloatArray:
    """:func:`unit_labor_hours` for the rows of ``cols`` (same operations, bit-identical)."""
    compiled = ctx.compiled
    assert compiled is not None
    adults = cols.weighted({k: ctx.tables[sid].labor for k, sid in enumerate(compiled.species_ids)})
    hours: FloatArray = (
        adults * compiled.parameter("foraging.foraging_hours_per_day")[cols.species()] * 365.0
    )
    return hours


def crop_yield_columns(cols: "UnitColumns", potential: FloatArray, ctx: StepContext) -> FloatArray:
    """:func:`unit_crop_yield` for the rows of ``cols`` (bit-identical)."""
    capability = capability_column(cols, ctx, "crop_yield")
    knowledge = ctx.knowledge
    if knowledge is not None and "agriculture" in knowledge.index:
        domain = knowledge.index["agriculture"]
        level = cols.knowledge()[:, domain].astype(np.float64)
        efficiency = level / (level + float(knowledge.half_efficiency[domain]))
    else:
        efficiency = np.ones(len(cols))
    realized: FloatArray = potential[cols.get("cell")] * np.maximum(capability, 0.0) * efficiency
    return realized


def _object_columns(units: Sequence[PopulationUnit], ctx: StepContext) -> "UnitColumns":
    from madexplorer.core.columns import ObjectColumns

    compiled = ctx.compiled
    assert compiled is not None
    return ObjectColumns(units, compiled.species_index, compiled.technologies)


def labor_hours_batch(units: Sequence[PopulationUnit], ctx: StepContext) -> FloatArray:
    """:func:`labor_hours_columns` for unit objects (reference and tests)."""
    return labor_hours_columns(_object_columns(units, ctx), ctx)


def crop_yield_batch(
    units: Sequence[PopulationUnit], potential: FloatArray, ctx: StepContext
) -> FloatArray:
    """:func:`crop_yield_columns` for unit objects (reference and tests)."""
    return crop_yield_columns(_object_columns(units, ctx), potential, ctx)


@dataclass(frozen=True)
class FarmHarvest:
    """This year's crop harvest for one unit."""

    unit_id: str
    harvest_kcal: float
    hours: float
    yield_kcal_per_ha: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Record the harvest; foraging adds wild food afterwards."""
        unit = state.units[self.unit_id]
        unit.farm_harvest_kcal = self.harvest_kcal
        unit.farm_hours = self.hours
        unit.crop_yield_kcal_per_ha = self.yield_kcal_per_ha
        unit.clearing_hours = 0.0
        ctx.ledger.farm_harvest_kcal += self.harvest_kcal


@dataclass(frozen=True, eq=False)
class FarmHarvests:
    """This year's crop harvest of many units, committed as columns."""

    cols: "UnitColumns"
    harvest_kcal: FloatArray
    hours: FloatArray
    yield_kcal_per_ha: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Record the harvests (as :class:`FarmHarvest` does, row by row)."""
        cols = self.cols
        cols.set("farm_harvest_kcal", self.harvest_kcal)
        cols.set("farm_hours", self.hours)
        cols.set("crop_yield_kcal_per_ha", self.yield_kcal_per_ha)
        cols.set("clearing_hours", 0.0)
        ledger = ctx.ledger
        total = ledger.farm_harvest_kcal
        for harvest in self.harvest_kcal.tolist():
            total += harvest
        ledger.farm_harvest_kcal = total


class FarmingSubsystem:
    """Harvests existing fields; field work takes priority over foraging (crops are committed)."""

    name = "farming"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[FarmHarvests]:
        """Compute crop harvests for every unit (one batched proposal)."""
        cols = ctx.columns(state)
        if len(cols) == 0:
            return []
        config = ctx.scenario.config.agriculture
        compiled = ctx.compiled
        assert compiled is not None
        n_units = len(cols)
        yield_per_ha = crop_yield_columns(cols, ctx.crop_potential(state), ctx)
        fields = cols.get("fields_ha")
        farming = fields > 0
        debt = cols.get("labor_debt_hours")
        share = compiled.parameter("subsistence.max_farm_labor_share")[cols.species()]
        available = np.maximum(labor_hours_columns(cols, ctx) - debt, 0.0) * share
        required = fields * config.cultivation_hours_per_ha
        worked = np.where(
            required > 0,
            np.minimum(
                1.0, np.divide(available, required, out=np.zeros(n_units), where=required > 0)
            ),
            0.0,
        )
        harvest = np.where(farming, fields * yield_per_ha * worked, 0.0)
        hours = np.where(farming, required * worked, 0.0)
        return [FarmHarvests(cols, harvest, hours, yield_per_ha)]


@dataclass(frozen=True)
class FieldPlan:
    """Next year's field area for one unit, with the clearing labor it costs."""

    unit_id: str
    fields_ha: float
    clearing_hours: float
    farm_return: float
    forage_marginal: float
    gap: float
    limit: str = ""  # binding limit of an expansion: target, labor, arable (diagnostic)

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the plan and record the start of cultivation."""
        unit = state.units[self.unit_id]
        if not unit.ever_cultivated and self.fields_ha > 0:
            unit.ever_cultivated = True
            ctx.events.emit(
                state.year,
                "cultivation_started",
                unit_id=unit.id,
                cell=list(state.world.coords(unit.cell)),
                fields_ha=round(self.fields_ha, 2),
                farm_return_kcal_per_hour=round(self.farm_return, 1),
                forage_marginal_kcal_per_hour=round(self.forage_marginal, 1),
                population=unit.population,
            )
        elif unit.fields_ha > 0 and self.fields_ha == 0 and self.gap < 0:
            ctx.events.emit(
                state.year,
                "cultivation_abandoned",
                unit_id=unit.id,
                cell=list(state.world.coords(unit.cell)),
                farm_return_kcal_per_hour=round(self.farm_return, 1),
                forage_marginal_kcal_per_hour=round(self.forage_marginal, 1),
            )
        unit.fields_ha = self.fields_ha
        unit.labor_debt_hours += self.clearing_hours
        unit.clearing_hours = self.clearing_hours


@dataclass(frozen=True, eq=False)
class FieldPlans:
    """Next year's field areas of many units, applied in (cell, unit) order.

    Equivalent to one :class:`FieldPlan` per row in that order (events included).
    """

    cols: "UnitColumns"
    rows: IntArray  # row positions in cols, in application order
    fields_ha: FloatArray
    clearing_hours: FloatArray
    farm_return: FloatArray
    forage_marginal: FloatArray
    gap: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the plans and record starts and abandonments of cultivation."""
        cols, rows = self.cols, self.rows
        if rows.size == 0:
            return
        before = cols.get("fields_ha")[rows].tolist()
        ever = cols.get("ever_cultivated")[rows].tolist()
        cells = cols.get("cell")[rows].tolist()
        population = cols.population()[rows].tolist()
        new = self.fields_ha.tolist()
        started = []
        for k, r in enumerate(rows.tolist()):
            if not ever[k] and new[k] > 0:
                started.append(r)
                ctx.events.emit(
                    state.year,
                    "cultivation_started",
                    unit_id=cols.units[r].id,
                    cell=list(state.world.coords(cells[k])),
                    fields_ha=round(new[k], 2),
                    farm_return_kcal_per_hour=round(float(self.farm_return[k]), 1),
                    forage_marginal_kcal_per_hour=round(float(self.forage_marginal[k]), 1),
                    population=population[k],
                )
            elif before[k] > 0 and new[k] == 0 and self.gap[k] < 0:
                ctx.events.emit(
                    state.year,
                    "cultivation_abandoned",
                    unit_id=cols.units[r].id,
                    cell=list(state.world.coords(cells[k])),
                    farm_return_kcal_per_hour=round(float(self.farm_return[k]), 1),
                    forage_marginal_kcal_per_hour=round(float(self.forage_marginal[k]), 1),
                )
        if started:
            cols.set_rows("ever_cultivated", np.array(started, dtype=np.int64), True)
        cols.set_rows("fields_ha", rows, self.fields_ha)
        cols.set_rows(
            "labor_debt_hours", rows, cols.get("labor_debt_hours")[rows] + self.clearing_hours
        )
        cols.set_rows("clearing_hours", rows, self.clearing_hours)


class FieldPlanningSubsystem:
    """Decides next year's field area for every unit."""

    name = "field_planning"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[FieldPlans]:
        """Compare farming and foraging returns; share limited arable land within cells.

        The per-unit decisions and the per-cell arable sharing run in one compiled call
        (:func:`~madexplorer.economy.agriculture_kernel.plan_fields`), bit-identical to
        :meth:`_evaluate_reference`.
        """
        from madexplorer.economy.agriculture_kernel import plan_fields

        config = ctx.scenario.config.agriculture
        potential = ctx.crop_potential(state)
        mechanisms = ctx.mechanisms
        cols = ctx.columns(state)
        n_units = len(cols)
        if n_units == 0:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        profiles = [ctx.species(sid) for sid in compiled.species_ids]

        def per_species(values: list[float]) -> FloatArray:
            return np.array(values, dtype=np.float64)

        index = ctx.spatial(state)
        f64, i64 = np.float64, np.int64
        out = [np.empty(n_units) for _ in range(5)]
        plan_rows = np.empty(n_units, dtype=i64)
        largest = int(np.diff(index.starts).max()) if index.cells.size else 0
        count = plan_fields(
            np.ascontiguousarray(crop_yield_columns(cols, potential, ctx), dtype=f64),
            np.ascontiguousarray(labor_hours_columns(cols, ctx), dtype=f64),
            np.ascontiguousarray(annual_need_columns(cols, state, ctx), dtype=f64),
            np.ascontiguousarray(cols.population(), dtype=i64),
            np.ascontiguousarray(cols.get("fields_ha"), dtype=f64),
            np.ascontiguousarray(cols.get("forage_marginal_kcal_per_hour"), dtype=f64),
            np.ascontiguousarray(cols.get("residence_years"), dtype=i64),
            np.ascontiguousarray(cols.get("move_hazard"), dtype=f64),
            np.ascontiguousarray(cols.get("cell"), dtype=i64),
            np.ascontiguousarray(cols.species(), dtype=i64),
            np.ascontiguousarray(capability_column(cols, ctx, "clearing_efficiency"), dtype=f64),
            np.ascontiguousarray(state.world.vegetation_density, dtype=f64),
            np.ascontiguousarray(ctx.arable_ha, dtype=f64),
            np.ascontiguousarray(index.order, dtype=i64),
            np.ascontiguousarray(index.starts, dtype=i64),
            np.ascontiguousarray(index.cells, dtype=i64),
            np.array([p.cognition.planning_horizon_years for p in profiles], dtype=i64),
            per_species([p.subsistence.max_farm_labor_share for p in profiles]),
            per_species([p.foraging.surplus_target for p in profiles]),
            per_species([p.subsistence.field_adjustment_rate for p in profiles]),
            per_species([p.subsistence.return_comparison_margin for p in profiles]),
            per_species([p.subsistence.initial_plot_ha for p in profiles]),
            float(config.cultivation_hours_per_ha),
            float(config.clearing_hours_per_ha),
            float(config.clearing_vegetation_multiplier),
            bool(mechanisms.expected_tenure),
            bool(mechanisms.field_growth_to_target),
            plan_rows,
            out[0],
            out[1],
            out[2],
            out[3],
            out[4],
            np.empty(n_units),
            np.empty(n_units),
            np.empty(n_units),
            np.empty(largest),
        )
        return [
            FieldPlans(
                cols,
                plan_rows[:count].copy(),
                out[0][:count].copy(),
                out[1][:count].copy(),
                out[2][:count].copy(),
                out[3][:count].copy(),
                out[4][:count].copy(),
            )
        ]

    def _evaluate_reference(self, state: SimulationState, ctx: StepContext) -> Sequence[FieldPlans]:
        """The PH3b Python path (reference for the compiled kernel; differential tests)."""
        config = ctx.scenario.config.agriculture
        potential = ctx.crop_potential(state)
        arable = ctx.arable_ha
        mechanisms = ctx.mechanisms
        cols = ctx.columns(state)
        n_units = len(cols)
        if n_units == 0:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        yields = crop_yield_columns(cols, potential, ctx).tolist()
        labor = labor_hours_columns(cols, ctx).tolist()
        needs = annual_need_columns(cols, state, ctx).tolist()
        population = cols.population().tolist()
        fields_now = cols.get("fields_ha").tolist()
        marginal = cols.get("forage_marginal_kcal_per_hour").tolist()
        residence = cols.get("residence_years").tolist()
        hazard = cols.get("move_hazard").tolist()
        cells = cols.get("cell").tolist()
        species = cols.species().tolist()
        clearing_efficiency = capability_column(cols, ctx, "clearing_efficiency").tolist()
        vegetation = state.world.vegetation_density
        profiles = [ctx.species(sid) for sid in compiled.species_ids]
        desired: list[tuple[float, float, float, float, str]] = []
        for i in range(n_units):
            yield_per_ha = yields[i]
            farm_return = yield_per_ha / config.cultivation_hours_per_ha
            if yield_per_ha <= 0 or population[i] == 0:
                desired.append((0.0, farm_return, marginal[i], -1.0, ""))
                continue
            profile = profiles[species[i]]
            behavior = profile.subsistence
            clearing = clearing_hours_per_ha(
                float(vegetation[cells[i]]), config, clearing_efficiency[i]
            )
            horizon = profile.cognition.planning_horizon_years
            if mechanisms.expected_tenure:
                tenure = expected_tenure_years(hazard[i], horizon, residence[i])
            else:
                tenure = min(max(residence[i], 1), horizon)
            farm_labor = behavior.max_farm_labor_share * labor[i]
            labor_cap = farm_labor / config.cultivation_hours_per_ha
            need_cap = needs[i] * (1.0 + profile.foraging.surplus_target) / yield_per_ha
            if mechanisms.field_growth_to_target:
                fields, gap, _limit = fields_toward_target(
                    fields_now[i],
                    yield_per_ha,
                    config.cultivation_hours_per_ha,
                    clearing,
                    tenure,
                    marginal[i],
                    behavior.field_adjustment_rate,
                    behavior.return_comparison_margin,
                    need_cap,
                    farm_labor,
                    behavior.max_farm_labor_share,
                )
            else:
                fields, gap = adjusted_fields_ha(
                    fields_now[i],
                    yield_per_ha,
                    config.cultivation_hours_per_ha,
                    clearing,
                    tenure,
                    marginal[i],
                    behavior.field_adjustment_rate,
                    behavior.initial_plot_ha,
                    behavior.return_comparison_margin,
                )
            desired.append((min(fields, labor_cap, need_cap), farm_return, marginal[i], gap, ""))
        index = ctx.spatial(state)
        order, starts = index.order.tolist(), index.starts.tolist()
        plan_rows: list[int] = []
        plan_fields: list[float] = []
        plan_clearing: list[float] = []
        plan_return: list[float] = []
        plan_marginal: list[float] = []
        plan_gap: list[float] = []
        for k, cell in enumerate(index.cells.tolist()):
            members = order[starts[k] : starts[k + 1]]
            total = sum([desired[r][0] for r in members])
            scale = min(1.0, float(arable[cell]) / total) if total > 0 else 1.0
            for r in members:
                fields, farm_return, forage_marginal, gap, _ = desired[r]
                fields *= scale
                if fields < 0.05:
                    fields = 0.0
                expansion = max(fields - fields_now[r], 0.0)
                clearing = 0.0
                if expansion > 0:
                    per_ha = clearing_hours_per_ha(
                        float(vegetation[cell]), config, clearing_efficiency[r]
                    )
                    clearing = expansion * per_ha
                if fields != fields_now[r]:
                    plan_rows.append(r)
                    plan_fields.append(fields)
                    plan_clearing.append(clearing)
                    plan_return.append(farm_return)
                    plan_marginal.append(forage_marginal)
                    plan_gap.append(gap)
        return [
            FieldPlans(
                cols,
                np.array(plan_rows, dtype=np.int64),
                np.array(plan_fields, dtype=np.float64),
                np.array(plan_clearing, dtype=np.float64),
                np.array(plan_return, dtype=np.float64),
                np.array(plan_marginal, dtype=np.float64),
                np.array(plan_gap, dtype=np.float64),
            )
        ]
