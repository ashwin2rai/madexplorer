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
from madexplorer.core.types import IntArray
from madexplorer.economy.foraging import accessible_food_kcal
from madexplorer.population.unit import Observation, PopulationUnit
from madexplorer.species.profile import Cognition

_NEVER = -(2**62)  # older than any observation year


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
    beliefs: dict[int, Observation]

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
            beliefs = {c: o for c, o in unit.beliefs.items() if o.year > horizon}
            cells = world.land_cells_within(unit.cell, radius)
            noise = np.exp(cognition.observation_noise_sigma * rng.standard_normal(len(cells)))
            n_self = unit.population
            for cell, factor in zip(cells, noise, strict=True):
                others = int(cell_population[cell]) - (n_self if cell == unit.cell else 0)
                beliefs[cell] = Observation(
                    year=state.year,
                    food_kcal=float(food[cell] * factor),
                    water_access=float(world.water_access[cell]),
                    population=others,
                )
            updates.append(BeliefUpdate(unit.id, beliefs))
        return updates


@dataclass(frozen=True)
class SharedKnowledge:
    """Observations one unit receives from its neighbors."""

    unit_id: str
    received: dict[int, Observation]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Adopt the received observations (each is fresher than the unit's own).

        Sharing proposals were computed from pre-sharing beliefs and each one changes only
        its own unit's map, so the freshness check made in ``evaluate`` still holds here.
        """
        state.units[self.unit_id].beliefs.update(self.received)


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
        years = _BeliefYears(world.n_cells)
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
                received = freshest_from_partners(unit, partners, years)
                if received:
                    proposals.append(SharedKnowledge(unit.id, received))
        return proposals


class _BeliefYears:
    """Per-step cache of each unit's belief years as a dense per-cell array."""

    def __init__(self, n_cells: int) -> None:
        self.n_cells = n_cells
        self._years: dict[str, IntArray] = {}

    def of(self, unit: PopulationUnit) -> IntArray:
        """Observation year per cell (``_NEVER`` where the unit knows nothing)."""
        years = self._years.get(unit.id)
        if years is None:
            years = np.full(self.n_cells, _NEVER, dtype=np.int64)
            beliefs = unit.beliefs
            if beliefs:
                cells = np.fromiter(beliefs.keys(), dtype=np.int64, count=len(beliefs))
                years[cells] = np.fromiter(
                    (o.year for o in beliefs.values()), dtype=np.int64, count=len(beliefs)
                )
            self._years[unit.id] = years
        return years


def freshest_from_partners(
    unit: PopulationUnit, partners: Sequence[PopulationUnit], years: _BeliefYears
) -> dict[int, Observation]:
    """Partner observations fresher than anything ``unit`` knows, per cell.

    Partners are consulted in order and only a strictly fresher observation replaces the
    best so far, so on equal years the first partner wins.
    """
    best = years.of(unit)
    winner = np.full(best.shape, -1, dtype=np.int64)
    for k, partner in enumerate(partners):
        partner_years = years.of(partner)
        fresher = partner_years > best
        if fresher.any():
            best = np.where(fresher, partner_years, best)
            winner[fresher] = k
    cells = np.flatnonzero(winner >= 0)
    maps = [partner.beliefs for partner in partners]
    return {c: maps[k][c] for c, k in zip(cells.tolist(), winner[cells].tolist(), strict=True)}
