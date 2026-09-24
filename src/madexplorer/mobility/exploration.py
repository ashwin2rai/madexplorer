"""Local spatial beliefs: perception and social information exchange (spec §10.1, §10.3).

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
from madexplorer.population.unit import NEVER_OBSERVED, BeliefMap, PopulationUnit
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
class BeliefUpdate:
    """Replace a unit's spatial belief map."""

    unit_id: str
    beliefs: BeliefMap

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the new belief map."""
        state.units[self.unit_id].beliefs = self.beliefs


class PerceptionSubsystem:
    """Each unit observes nearby land cells and forgets stale observations."""

    name = "perception"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefUpdate]:
        """Produce updated belief maps."""
        rng = ctx.rng.stream(Streams.PERCEPTION)
        world = state.world
        cell_population = state.cell_population()
        food_by_species = {
            sid: accessible_food_kcal(state, profile.foraging)
            for sid, profile in ctx.scenario.species.items()
        }
        updates: list[BeliefUpdate] = []
        for unit in state.units.values():
            cognition = ctx.species(unit.species_id).cognition
            food = food_by_species[unit.species_id]
            radius = perception_radius_cells(
                cognition, float(world.vegetation_density[unit.cell]), world.cell_size_km
            )
            horizon = state.year - cognition.memory_years
            year, food_kcal, water, population = unit.beliefs.sized(world.n_cells).arrays()
            year[year <= horizon] = NEVER_OBSERVED  # forget stale observations
            cells = world.land_cell_ids_within(unit.cell, radius)
            noise = np.exp(cognition.observation_noise_sigma * rng.standard_normal(cells.size))
            year[cells] = state.year
            food_kcal[cells] = food[cells] * noise
            water[cells] = world.water_access[cells]
            others = cell_population[cells]
            population[cells] = np.where(cells == unit.cell, others - unit.population, others)
            beliefs = BeliefMap(year, food_kcal, water, population)
            updates.append(BeliefUpdate(unit.id, beliefs))
        return updates


@dataclass(frozen=True)
class SharedKnowledge:
    """Observations one unit receives from its neighbors."""

    unit_id: str
    beliefs: BeliefMap  # the unit's map after adopting fresher partner observations

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Adopt the merged map.

        It was computed from pre-sharing beliefs, and each proposal changes only its own
        unit's map, so applying proposals in any order gives the same result.
        """
        state.units[self.unit_id].beliefs = self.beliefs


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
        """Collect what each unit learns from neighbors (based on pre-sharing beliefs)."""
        rng = ctx.rng.stream(Streams.KNOWLEDGE_SHARING)
        by_cell = state.units_by_cell()
        world = state.world
        proposals: list[SharedKnowledge] = []
        for unit in state.units.values():
            probability = ctx.species(unit.species_id).social.knowledge_sharing_probability
            partners: list[PopulationUnit] = []
            for cell in world.cells_within(unit.cell, 1):
                for other in by_cell.get(cell, []):
                    if other is unit or other.species_id != unit.species_id:
                        continue
                    if rng.random() < probability:
                        partners.append(other)
            if partners:
                merged = freshest_from_partners(unit.beliefs, [p.beliefs for p in partners])
                if merged is not None:
                    proposals.append(SharedKnowledge(unit.id, merged))
        return proposals


def freshest_from_partners(own: BeliefMap, partners: Sequence[BeliefMap]) -> BeliefMap | None:
    """``own`` updated with every partner observation fresher than anything known so far.

    Per cell, the freshest partner observation replaces ``own`` if strictly fresher; among
    equally fresh partners the first wins (``argmax`` returns the first maximum), exactly
    as consulting partners one by one. ``None`` if nothing is fresher.
    """
    n = max([own.n_cells, *(p.n_cells for p in partners)])
    own = own.sized(n)
    maps = [p.sized(n) for p in partners]
    years = np.stack([m.year for m in maps])
    first = years.argmax(axis=0)
    columns = np.arange(n)
    freshest = years[first, columns]
    fresher = freshest > own.year
    if not fresher.any():
        return None
    cells = np.flatnonzero(fresher)
    chosen = first[cells]
    year, food_kcal, water, population = own.arrays()
    year[cells] = freshest[cells]
    for k, source in enumerate(maps):
        take = cells[chosen == k]
        if take.size:
            food_kcal[take] = source.food_kcal[take]
            water[take] = source.water_access[take]
            population[take] = source.population[take]
    return BeliefMap(year, food_kcal, water, population)
