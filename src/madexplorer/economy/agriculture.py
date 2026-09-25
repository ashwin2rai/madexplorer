"""Cultivation: crop yields, clearing, soil dynamics, and field planning (spec §4.5, §18).

Cultivation is never switched on by a rule. Groups hold fields only when their
technology gives a positive crop-yield capability, and they expand or shrink
fields by comparing the return per hour of farming with the marginal return of
foraging. Farming typically returns less per hour than rich foraging but far
more per hectare and depletes wild stocks less, so it wins where crowding and
depletion have driven foraging returns down.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.config.schema import AgricultureConfig
from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import BoolArray, FloatArray
from madexplorer.ecology.resources import miami_npp
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.unit import PopulationUnit
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid

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


class FarmingSubsystem:
    """Harvests existing fields; field work takes priority over foraging (crops are committed)."""

    name = "farming"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[FarmHarvest]:
        """Compute crop harvests for every unit."""
        config = ctx.scenario.config.agriculture
        potential = ctx.crop_potential(state)
        proposals: list[FarmHarvest] = []
        for unit in state.units.values():
            yield_per_ha = unit_crop_yield(unit, potential, ctx)
            if unit.fields_ha <= 0:
                proposals.append(FarmHarvest(unit.id, 0.0, 0.0, yield_per_ha))
                continue
            share = ctx.species(unit.species_id).subsistence.max_farm_labor_share
            available = max(unit_labor_hours(unit, ctx) - unit.labor_debt_hours, 0.0) * share
            required = unit.fields_ha * config.cultivation_hours_per_ha
            worked = min(1.0, available / required) if required > 0 else 0.0
            proposals.append(
                FarmHarvest(
                    unit.id, unit.fields_ha * yield_per_ha * worked, required * worked, yield_per_ha
                )
            )
        return proposals


@dataclass(frozen=True)
class FieldPlan:
    """Next year's field area for one unit, with the clearing labor it costs."""

    unit_id: str
    fields_ha: float
    clearing_hours: float
    farm_return: float
    forage_marginal: float
    gap: float

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


class FieldPlanningSubsystem:
    """Decides next year's field area for every unit."""

    name = "field_planning"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[FieldPlan]:
        """Compare farming and foraging returns; share limited arable land within cells."""
        config = ctx.scenario.config.agriculture
        potential = ctx.crop_potential(state)
        arable = ctx.arable_ha
        desired: dict[str, tuple[float, float, float, float]] = {}
        for unit in state.units.values():
            behavior = ctx.species(unit.species_id).subsistence
            yield_per_ha = unit_crop_yield(unit, potential, ctx)
            farm_return = yield_per_ha / config.cultivation_hours_per_ha
            if yield_per_ha <= 0 or unit.population == 0:
                desired[unit.id] = (0.0, farm_return, unit.forage_marginal_kcal_per_hour, -1.0)
                continue
            clearing = clearing_hours_per_ha(
                float(state.world.vegetation_density[unit.cell]),
                config,
                ctx.capabilities(unit)["clearing_efficiency"],
            )
            horizon = ctx.species(unit.species_id).cognition.planning_horizon_years
            fields, gap = adjusted_fields_ha(
                unit.fields_ha,
                yield_per_ha,
                config.cultivation_hours_per_ha,
                clearing,
                min(max(unit.residence_years, 1), horizon),
                unit.forage_marginal_kcal_per_hour,
                behavior.field_adjustment_rate,
                behavior.initial_plot_ha,
                behavior.return_comparison_margin,
            )
            labor_cap = (
                behavior.max_farm_labor_share
                * unit_labor_hours(unit, ctx)
                / config.cultivation_hours_per_ha
            )
            profile = ctx.species(unit.species_id)
            temperature = float(state.climate.temperature_c[unit.cell])
            target = annual_need_kcal(unit, profile, ctx.tables[unit.species_id], temperature)
            need_cap = target * (1.0 + profile.foraging.surplus_target) / yield_per_ha
            desired[unit.id] = (
                min(fields, labor_cap, need_cap),
                farm_return,
                unit.forage_marginal_kcal_per_hour,
                gap,
            )
        proposals: list[FieldPlan] = []
        for cell, units in state.units_by_cell().items():
            total = sum(desired[u.id][0] for u in units)
            scale = min(1.0, float(arable[cell]) / total) if total > 0 else 1.0
            for unit in units:
                fields, farm_return, forage_marginal, gap = desired[unit.id]
                fields *= scale
                if fields < 0.05:
                    fields = 0.0
                expansion = max(fields - unit.fields_ha, 0.0)
                clearing = 0.0
                if expansion > 0:
                    efficiency = ctx.capabilities(unit)["clearing_efficiency"]
                    per_ha = clearing_hours_per_ha(
                        float(state.world.vegetation_density[cell]), config, efficiency
                    )
                    clearing = expansion * per_ha
                if fields != unit.fields_ha:
                    proposals.append(
                        FieldPlan(unit.id, fields, clearing, farm_return, forage_marginal, gap)
                    )
        return proposals
