"""Ecology subsystem: capacities follow climate, stocks regrow."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.state import SimulationState, StepContext
from madexplorer.ecology.resources import (
    EcologyState,
    capacities,
    displacement_multipliers,
    logistic_regrowth,
)
from madexplorer.economy.agriculture import HECTARES_PER_KM2, update_soil_nutrients
from madexplorer.population.energetics import capability_column


@dataclass(frozen=True)
class EcologyUpdate:
    """Replace the ecological state."""

    ecology: EcologyState

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new stocks and capacities."""
        state.ecology = self.ecology


class EcologySubsystem:
    """Recomputes capacities from climate and land use, regrows wild food, updates soils."""

    name = "ecology"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[EcologyUpdate]:
        """Advance ecology by one year."""
        config = ctx.scenario.config.ecology
        plant_k, game_k = capacities(state.world, state.climate, config)
        eco = state.ecology
        agriculture = ctx.scenario.config.agriculture
        fields = state.cell_fields_ha()
        soil = eco.soil_nutrients
        if fields.any():
            cell_ha = state.world.cell_area_km2 * HECTARES_PER_KM2
            plant_mult, game_mult = displacement_multipliers(
                fields / cell_ha,
                agriculture.wild_plant_displacement,
                agriculture.wild_game_displacement,
            )
            plant_k, game_k = plant_k * plant_mult, game_k * game_mult
            management = np.zeros_like(fields)
            cols = ctx.columns(state)
            unit_fields = cols.get("fields_ha")
            farming = np.flatnonzero(unit_fields > 0)
            if farming.size:
                level = capability_column(cols.subset(farming), ctx, "soil_management")
                cells = cols.get("cell")[farming]
                # Unbuffered and in row order: the same sequence of additions as the loop.
                np.add.at(management, cells, level * unit_fields[farming] / fields[cells])
            soil = update_soil_nutrients(soil, fields > 0, management, agriculture)
        elif (soil < 1.0).any():
            soil = update_soil_nutrients(
                soil, np.zeros(soil.shape, dtype=bool), np.zeros_like(soil), agriculture
            )
        return [
            EcologyUpdate(
                EcologyState(
                    plant_stock_kcal=logistic_regrowth(
                        eco.plant_stock_kcal,
                        plant_k,
                        config.plant_regrowth_rate_per_year,
                        config.recolonization_fraction,
                    ),
                    game_stock_kcal=logistic_regrowth(
                        eco.game_stock_kcal,
                        game_k,
                        config.game_regrowth_rate_per_year,
                        config.recolonization_fraction,
                    ),
                    plant_capacity_kcal=plant_k,
                    game_capacity_kcal=game_k,
                    soil_nutrients=soil,
                )
            )
        ]
