"""Knowledge accumulation by practice and loss by disuse (spec §11.1, §11.6).

For each domain ``d``::

    K_d += learning_speed * a_d * s_d * log1p(N * s_d / n_d) - (delta_d / retention) * K_d

``s_d`` is practice intensity (weighted activity shares), ``N`` group size, and
``n_d`` a practitioner scale. The equilibrium ``K*`` rises with practice and
with the log number of practitioners, so a shrinking or disengaged population
loses knowledge without any explicit "collapse" rule.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray
from madexplorer.economy.agriculture import unit_labor_hours
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.unit import PopulationUnit


def activity_shares(unit: PopulationUnit, labor_hours: float) -> dict[str, float]:
    """Share of the unit's labor (or harvest, for storing) devoted to each activity."""
    if labor_hours <= 0:
        return {}
    forage = unit.forage_hours / labor_hours
    return {
        "plant_foraging": forage * unit.forage_plant_share,
        "game_foraging": forage * (1.0 - unit.forage_plant_share),
        "farming": unit.farm_hours / labor_hours,
        "clearing": min(unit.clearing_hours / labor_hours, 1.0),
        "storing": min(unit.stored_kcal / unit.harvest_kcal, 1.0) if unit.harvest_kcal > 0 else 0.0,
    }


@model_rule(
    name="practice_learning",
    version="1.0",
    rationale=(
        "Knowledge grows with practice intensity and the log number of practitioners and decays "
        "proportionally without practice (Henrich-style population-size effect on cumulative "
        "culture)."
    ),
    source_type="theoretical",
    parameters=(
        "learning_rate",
        "decay_rate",
        "practitioner_scale",
        "learning_speed",
        "knowledge_retention",
    ),
    expected_domain="knowledge levels >= 0",
    known_limitations=(
        "No specialists or written archives yet; all members practice in proportion to labor."
    ),
)
def learn(
    knowledge: FloatArray,
    practice: FloatArray,
    population: int,
    model: KnowledgeModel,
    learning_speed: float,
    retention: float,
) -> FloatArray:
    """Advance a knowledge vector by one year of practice and forgetting."""
    practitioners = population * practice
    gain = (
        learning_speed
        * model.learning_rate
        * practice
        * np.log1p(practitioners / model.practitioner_scale)
    )
    loss = model.decay_rate / retention * knowledge
    updated: FloatArray = np.maximum(knowledge + gain - loss, 0.0)
    return updated


@dataclass(frozen=True)
class KnowledgeLevels:
    """New knowledge vector of one unit."""

    unit_id: str
    knowledge: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new levels."""
        state.units[self.unit_id].knowledge = self.knowledge


class LearningSubsystem:
    """Practice-based learning and forgetting."""

    name = "learning"

    def __init__(self, model: KnowledgeModel) -> None:
        self.model = model

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[KnowledgeLevels]:
        """Update every unit's knowledge from this year's activities."""
        updates: list[KnowledgeLevels] = []
        for unit in state.units.values():
            cognition = ctx.species(unit.species_id).cognition
            shares: Mapping[str, float] = activity_shares(unit, unit_labor_hours(unit, ctx))
            practice = self.model.practice_weights(shares)
            updates.append(
                KnowledgeLevels(
                    unit.id,
                    learn(
                        unit.knowledge,
                        practice,
                        unit.population,
                        self.model,
                        cognition.learning_speed,
                        cognition.knowledge_retention,
                    ),
                )
            )
        return updates
