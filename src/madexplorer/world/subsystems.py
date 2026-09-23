"""Environment subsystems: climate update."""

from collections.abc import Sequence
from dataclasses import dataclass

from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.world.climate import ClimateYear, next_climate_year


@dataclass(frozen=True)
class ClimateUpdate:
    """Replace the current climate year."""

    climate: ClimateYear

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new climate."""
        state.climate = self.climate


class ClimateSubsystem:
    """Draws the year's temperature and rainfall fields."""

    name = "climate"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[ClimateUpdate]:
        """Advance climate by one year."""
        config = ctx.scenario.config
        elapsed = state.year - config.simulation.start_year
        climate = next_climate_year(
            state.climate,
            state.world,
            config.world.climate,
            elapsed,
            ctx.rng.stream(Streams.ENVIRONMENT),
            ctx.mechanisms.climate_variability,
        )
        return [ClimateUpdate(climate)]
