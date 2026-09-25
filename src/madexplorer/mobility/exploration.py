"""Local spatial beliefs: perception and social information exchange (spec §10.1, §10.3).

Units never see the whole map. Each year they observe cells within a
perception radius shrunk by vegetation, with observation noise; observations
older than their memory horizon are ignored when read (lazy expiry). Neighboring
groups exchange fresher observations. Both steps emit sparse ``BeliefPatch``
proposals that touch only the cells that change.
"""

from collections.abc import Sequence

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.economy.foraging import accessible_food_kcal
from madexplorer.population.unit import YEAR_DTYPE, BeliefMap, BeliefPatch, PopulationUnit
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


class PerceptionSubsystem:
    """Each unit observes nearby land cells and forgets stale observations."""

    name = "perception"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefPatch]:
        """This year's observations of the cells each unit can see (sparse patches).

        Old observations are not scanned or erased here: expiry is lazy (see
        :class:`BeliefMap`), so the cost is proportional to the cells perceived.
        """
        rng = ctx.rng.stream(Streams.PERCEPTION)
        world = state.world
        cell_population = state.cell_population()
        food_by_species = {
            sid: accessible_food_kcal(state, profile.foraging)
            for sid, profile in ctx.scenario.species.items()
        }
        year = np.int32(state.year)
        updates: list[BeliefPatch] = []
        for unit in state.units.values():
            cognition = ctx.species(unit.species_id).cognition
            food = food_by_species[unit.species_id]
            radius = perception_radius_cells(
                cognition, float(world.vegetation_density[unit.cell]), world.cell_size_km
            )
            cells = world.land_cells_within(unit.cell, radius)
            noise = np.exp(cognition.observation_noise_sigma * rng.standard_normal(cells.size))
            others = cell_population[cells]
            updates.append(
                BeliefPatch(
                    unit.id,
                    cells,
                    np.full(cells.size, year, dtype=YEAR_DTYPE),
                    food[cells] * noise,
                    np.where(cells == unit.cell, others - unit.population, others),
                )
            )
        return updates


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

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefPatch]:
        """Collect what each unit learns from neighbors (based on pre-sharing beliefs)."""
        rng = ctx.rng.stream(Streams.KNOWLEDGE_SHARING)
        by_cell = state.units_by_cell()
        world = state.world
        proposals: list[BeliefPatch] = []
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
                patch = freshest_from_partners(
                    unit.id, unit.beliefs, [p.beliefs for p in partners], world.n_cells
                )
                if patch is not None:
                    proposals.append(patch)
        return proposals


def freshest_from_partners(
    unit_id: str, own: BeliefMap, partners: Sequence[BeliefMap], n_cells: int
) -> BeliefPatch | None:
    """Patch with every partner observation fresher than anything ``own`` holds.

    Per cell, the freshest partner observation replaces ``own`` if strictly fresher; among
    equally fresh partners the first wins (``argmax`` returns the first maximum), exactly
    as consulting partners one by one. ``None`` if nothing is fresher. Stale entries may be
    passed on; readers ignore them (lazy expiry), so this changes no current belief.
    """
    own = own.sized(n_cells)
    maps = [p.sized(n_cells) for p in partners]
    years = np.stack([m.year for m in maps])
    first = years.argmax(axis=0)
    freshest = years[first, np.arange(n_cells)]
    cells = np.flatnonzero(freshest > own.year)
    if cells.size == 0:
        return None
    chosen = first[cells]
    food_kcal = np.empty(cells.size, dtype=own.food_kcal.dtype)
    population = np.empty(cells.size, dtype=own.population.dtype)
    for k, source in enumerate(maps):
        take = chosen == k
        if take.any():
            food_kcal[take] = source.food_kcal[cells[take]]
            population[take] = source.population[cells[take]]
    return BeliefPatch(unit_id, cells, freshest[cells], food_kcal, population)
