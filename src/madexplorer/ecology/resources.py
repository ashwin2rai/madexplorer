"""Wild plant and game food resources (spec §4.4, §18).

Productivity comes from climate via the Miami model; edible plant and game
stocks regrow logistically toward climate-dependent capacities and are
depleted by harvest, so overharvesting and recovery emerge from the dynamics.
"""

from dataclasses import dataclass

import numpy as np

from madexplorer.config.schema import EcologyConfig
from madexplorer.core.governance import model_rule
from madexplorer.core.types import FloatArray
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid


@model_rule(
    name="miami_npp",
    version="1.0",
    rationale=(
        "Net primary productivity limited by the scarcer of temperature and rainfall (Lieth 1975)."
    ),
    source_type="empirical",
    parameters=(),
    expected_domain="g dry matter / m2 / year, in [0, 3000]",
    known_limitations="Ignores CO2, soil water holding capacity, and seasonality.",
)
def miami_npp(temperature_c: FloatArray, rainfall_mm: FloatArray) -> FloatArray:
    """Net primary productivity from annual temperature and rainfall."""
    from_temperature = 3000.0 / (1.0 + np.exp(1.315 - 0.119 * temperature_c))
    from_rainfall = 3000.0 * (1.0 - np.exp(-0.000664 * rainfall_mm))
    npp: FloatArray = np.minimum(from_temperature, from_rainfall)
    return npp


@model_rule(
    name="vegetation_density",
    version="1.0",
    rationale="Vegetation density saturates with productivity (Michaelis-Menten form).",
    source_type="heuristic",
    parameters=("vegetation_half_saturation_npp_g_m2",),
    expected_domain="[0, 1)",
    known_limitations="Static in MVP 1: no succession, fire, or clearing.",
)
def vegetation_density(npp_g_m2: FloatArray, half_saturation: float) -> FloatArray:
    """Canopy/understory density index derived from productivity."""
    density: FloatArray = npp_g_m2 / (npp_g_m2 + half_saturation)
    return density


@model_rule(
    name="edible_capacity",
    version="1.0",
    rationale="A fixed fraction of primary production energy is edible plant food or game.",
    source_type="placeholder",
    parameters=("npp_energy_kcal_per_g", "plant_edible_fraction", "game_edible_fraction"),
    expected_domain="kcal per cell; zero on water",
    known_limitations="Single aggregate plant and game resource; no species-level food web.",
)
def edible_capacity_kcal(
    npp_g_m2: FloatArray, cell_area_km2: float, energy_kcal_per_g: float, edible_fraction: float
) -> FloatArray:
    """Standing edible energy a cell supports at ecological equilibrium."""
    capacity: FloatArray = npp_g_m2 * 1e6 * cell_area_km2 * energy_kcal_per_g * edible_fraction
    return capacity


@model_rule(
    name="logistic_regrowth",
    version="1.0",
    rationale=(
        "Stocks below capacity regrow logistically with a small recolonization term so depleted "
        "cells recover; stocks above a reduced capacity decay exponentially toward it."
    ),
    source_type="theoretical",
    parameters=(
        "plant_regrowth_rate_per_year",
        "game_regrowth_rate_per_year",
        "recolonization_fraction",
    ),
    expected_domain="0 <= stock <= max(previous stock, capacity)",
    known_limitations="No age structure, predation, or dispersal between cells.",
)
def logistic_regrowth(
    stock: FloatArray, capacity: FloatArray, rate: float, recolonization: float
) -> FloatArray:
    """Advance a renewable stock by one year."""
    safe_capacity = np.where(capacity > 0, capacity, 1.0)
    growth = rate * (stock + recolonization * capacity) * (1.0 - stock / safe_capacity)
    below = np.minimum(stock + growth, capacity)
    above = capacity + (stock - capacity) * np.exp(-rate)
    regrown: FloatArray = np.where(capacity <= 0, 0.0, np.where(stock <= capacity, below, above))
    return np.maximum(regrown, 0.0)


@dataclass(eq=False)
class EcologyState:
    """Mutable wild-food stocks and the current year's capacities (kcal per cell)."""

    plant_stock_kcal: FloatArray
    game_stock_kcal: FloatArray
    plant_capacity_kcal: FloatArray
    game_capacity_kcal: FloatArray


def capacities(
    world: WorldGrid, climate: ClimateYear, config: EcologyConfig
) -> tuple[FloatArray, FloatArray]:
    """Plant and game capacities for the given year's climate."""
    npp = miami_npp(climate.temperature_c, climate.rainfall_mm) * world.soil_fertility
    npp = np.where(world.is_water, 0.0, npp)
    area = world.cell_area_km2
    plant = edible_capacity_kcal(
        npp, area, config.npp_energy_kcal_per_g, config.plant_edible_fraction
    )
    game = edible_capacity_kcal(
        npp, area, config.npp_energy_kcal_per_g, config.game_edible_fraction
    )
    return plant, game


def initial_ecology(world: WorldGrid, climate: ClimateYear, config: EcologyConfig) -> EcologyState:
    """Stocks start at equilibrium with the base climate."""
    plant, game = capacities(world, climate, config)
    return EcologyState(plant.copy(), game.copy(), plant, game)
