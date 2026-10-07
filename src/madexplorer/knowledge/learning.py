"""Knowledge accumulation by practice and loss by disuse (spec §11.1, §11.6).

For each domain ``d``::

    K_d += learning_speed * a_d * s_d * log1p(N * s_d / n_d) - (delta_d / retention) * K_d

``s_d`` is practice intensity (weighted activity shares), ``N`` group size, and
``n_d`` a practitioner scale. The equilibrium ``K*`` rises with practice and
with the log number of practitioners, so a shrinking or disengaged population
loses knowledge without any explicit "collapse" rule.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.exactsum import python_sum_columns
from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray
from madexplorer.economy.agriculture import labor_hours_columns
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.unit import PopulationUnit

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns


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


@dataclass(frozen=True, eq=False)
class KnowledgeMatrix:
    """New knowledge vectors of many units (rows in unit order), committed as a column."""

    cols: "UnitColumns"
    knowledge: FloatArray  # (units, domains)

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new levels."""
        self.cols.set_knowledge(self.knowledge)


def activity_shares_columns(cols: "UnitColumns", labor_hours: FloatArray) -> dict[str, FloatArray]:
    """:func:`activity_shares` for the rows of ``cols``; 0 without labor (bit-identical)."""
    forage_hours = cols.get("forage_hours")
    plant = cols.get("forage_plant_share")
    farm_hours = cols.get("farm_hours")
    clearing = cols.get("clearing_hours")
    stored = cols.get("stored_kcal")
    harvest = cols.get("harvest_kcal")
    working = labor_hours > 0
    safe = np.where(working, labor_hours, 1.0)
    forage = forage_hours / safe
    storing = np.minimum(np.divide(stored, np.where(harvest > 0, harvest, 1.0)), 1.0)
    shares = {
        "plant_foraging": forage * plant,
        "game_foraging": forage * (1.0 - plant),
        "farming": farm_hours / safe,
        "clearing": np.minimum(clearing / safe, 1.0),
        "storing": np.where(harvest > 0, storing, 0.0),
    }
    return {a: np.where(working, v, 0.0) for a, v in shares.items()}


class LearningSubsystem:
    """Practice-based learning and forgetting."""

    name = "learning"

    def __init__(self, model: KnowledgeModel) -> None:
        self.model = model

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[KnowledgeMatrix]:
        """Update every unit's knowledge from this year's activities (one batched proposal).

        Practice weights reproduce ``practice_weights`` (a Python ``sum`` over each
        domain's activities, compensated since Python 3.12) with
        :func:`~madexplorer.core.exactsum.python_sum_columns`.
        """
        cols = ctx.columns(state)
        if len(cols) == 0:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        model = self.model
        shares = activity_shares_columns(cols, labor_hours_columns(cols, ctx))
        zeros = np.zeros(len(cols))
        columns = []
        for domain in model.domains:
            practice = model.system.domains[domain].practice
            terms = [w * shares.get(a, zeros) for a, w in practice.items()]
            columns.append(python_sum_columns(terms) if terms else zeros + 0)
        practice_matrix = np.stack(columns, axis=1)
        species = cols.species()
        speed = np.array(
            [ctx.species(sid).cognition.learning_speed for sid in compiled.species_ids]
        )[species]
        retention = np.array(
            [ctx.species(sid).cognition.knowledge_retention for sid in compiled.species_ids]
        )[species]
        population = cols.population()
        knowledge = cols.knowledge()
        practitioners = population[:, None] * practice_matrix
        gain = (
            speed[:, None]
            * model.learning_rate[None, :]
            * practice_matrix
            * np.log1p(practitioners / model.practitioner_scale[None, :])
        )
        loss = model.decay_rate[None, :] / retention[:, None] * knowledge
        updated = np.maximum(knowledge + gain - loss, 0.0)
        return [KnowledgeMatrix(cols, updated)]
