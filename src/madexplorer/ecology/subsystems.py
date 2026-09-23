"""Ecology subsystem: capacities follow climate, stocks regrow."""

from collections.abc import Sequence
from dataclasses import dataclass

from madexplorer.core.state import SimulationState, StepContext
from madexplorer.ecology.resources import EcologyState, capacities, logistic_regrowth


@dataclass(frozen=True)
class EcologyUpdate:
    """Replace the ecological state."""

    ecology: EcologyState

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new stocks and capacities."""
        state.ecology = self.ecology


class EcologySubsystem:
    """Recomputes capacities from this year's climate and regrows wild food stocks."""

    name = "ecology"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[EcologyUpdate]:
        """Advance ecology by one year."""
        config = ctx.scenario.config.ecology
        plant_k, game_k = capacities(state.world, state.climate, config)
        eco = state.ecology
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
                )
            )
        ]
