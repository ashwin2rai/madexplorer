"""Local knowledge: perception and social information exchange (spec §10.1, §10.3).

Units never see the whole map. Each year they observe cells within a
perception radius shrunk by vegetation, with observation noise, and forget
observations older than their memory horizon. Neighboring groups exchange
fresher observations.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.economy.foraging import accessible_food_kcal
from madexplorer.population.unit import Observation
from madexplorer.species.profile import Cognition


@model_rule(
    name="perception_radius",
    version="1.0",
    rationale="Line of sight and search radius shrink with local vegetation density.",
    source_type="heuristic",
    parameters=("perception_radius_km", "vegetation_occlusion"),
    expected_domain="radius in cells, >= 1",
    known_limitations="Terrain visibility (ridges, valleys) is not modeled.",
)
def perception_radius_cells(cognition: Cognition, vegetation: float, cell_size_km: float) -> int:
    """Perception radius in cells from the observer's current cell."""
    km = cognition.perception_radius_km * (1.0 - cognition.vegetation_occlusion * vegetation)
    return max(1, round(km / cell_size_km))


@dataclass(frozen=True)
class KnowledgeUpdate:
    """Replace a unit's knowledge map."""

    unit_id: str
    knowledge: dict[int, Observation]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new knowledge map."""
        state.units[self.unit_id].knowledge = self.knowledge


class PerceptionSubsystem:
    """Each unit observes nearby land cells and forgets stale observations."""

    name = "perception"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[KnowledgeUpdate]:
        """Produce updated knowledge maps."""
        rng = ctx.rng.stream(Streams.PERCEPTION)
        world = state.world
        cell_population = state.cell_population()
        food_by_species = {
            sid: accessible_food_kcal(state, profile.foraging)
            for sid, profile in ctx.scenario.species.items()
        }
        updates: list[KnowledgeUpdate] = []
        for unit in state.units.values():
            cognition = ctx.species(unit.species_id).cognition
            food = food_by_species[unit.species_id]
            radius = perception_radius_cells(
                cognition, float(world.vegetation_density[unit.cell]), world.cell_size_km
            )
            horizon = state.year - cognition.memory_years
            knowledge = {c: o for c, o in unit.knowledge.items() if o.year > horizon}
            cells = [c for c in world.cells_within(unit.cell, radius) if not world.is_water[c]]
            noise = np.exp(cognition.observation_noise_sigma * rng.standard_normal(len(cells)))
            n_self = unit.population
            for cell, factor in zip(cells, noise, strict=True):
                others = int(cell_population[cell]) - (n_self if cell == unit.cell else 0)
                knowledge[cell] = Observation(
                    year=state.year,
                    food_kcal=float(food[cell] * factor),
                    water_access=float(world.water_access[cell]),
                    population=others,
                )
            updates.append(KnowledgeUpdate(unit.id, knowledge))
        return updates


@dataclass(frozen=True)
class SharedKnowledge:
    """Observations one unit receives from its neighbors."""

    unit_id: str
    received: dict[int, Observation]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Merge received observations that are fresher than the unit's own."""
        knowledge = state.units[self.unit_id].knowledge
        for cell, obs in self.received.items():
            mine = knowledge.get(cell)
            if mine is None or obs.year > mine.year:
                knowledge[cell] = obs


@model_rule(
    name="neighbor_knowledge_sharing",
    version="1.0",
    rationale=(
        "Groups in the same or adjacent cells exchange observations with a fixed probability per "
        "pair."
    ),
    source_type="heuristic",
    parameters=("knowledge_sharing_probability",),
    expected_domain="each directed pair shares at most once per year",
    known_limitations=(
        "No trust, language, or cross-species barriers; shared observations are taken at face "
        "value."
    ),
)
class KnowledgeSharingSubsystem:
    """Social transmission of spatial information between nearby groups."""

    name = "knowledge_sharing"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[SharedKnowledge]:
        """Collect what each unit learns from neighbors (based on pre-sharing knowledge)."""
        rng = ctx.rng.stream(Streams.PERCEPTION)
        by_cell = state.units_by_cell()
        world = state.world
        proposals: list[SharedKnowledge] = []
        for unit in state.units.values():
            probability = ctx.species(unit.species_id).social.knowledge_sharing_probability
            received: dict[int, Observation] = {}
            for cell in world.cells_within(unit.cell, 1):
                for other in by_cell.get(cell, []):
                    if other is unit or other.species_id != unit.species_id:
                        continue
                    if rng.random() >= probability:
                        continue
                    for c, obs in other.knowledge.items():
                        best = received.get(c) or unit.knowledge.get(c)
                        if best is None or obs.year > best.year:
                            received[c] = obs
            if received:
                proposals.append(SharedKnowledge(unit.id, received))
        return proposals
