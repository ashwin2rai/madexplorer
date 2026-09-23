"""Coarsening: merge similar co-located units to bound computational cost (spec §6.2, §6.5).

When a cell holds more units of one species than the resolution budget,
the most similar pair (identical technologies, closest knowledge vectors) is
merged into one multi-group unit. People, food, fields, and reserves are
conserved exactly; knowledge is population-weighted, and the knowledge distance
at merge time is recorded as the approximation error. Fission later buds
single groups back off, so resolution adapts in both directions.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray
from madexplorer.population.groups import merge_into


@model_rule(
    name="knowledge_distance",
    version="1.0",
    rationale="Mean absolute difference of domain knowledge levels; zero when no knowledge system.",
    source_type="heuristic",
    parameters=("max_knowledge_distance",),
    expected_domain=">= 0",
    known_limitations="Ignores age structure and nutritional state differences between units.",
)
def knowledge_distance(a: FloatArray, b: FloatArray) -> float:
    """Distance between two knowledge vectors."""
    return float(np.abs(a - b).mean()) if a.size else 0.0


@dataclass(frozen=True)
class Coalesce:
    """Merge ``source`` into ``target`` for resolution purposes."""

    source_id: str
    target_id: str
    distance: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Merge the units and record the approximation."""
        source, target = state.units[self.source_id], state.units[self.target_id]
        merged = source.population
        merge_into(target, source, combine_groups=True)
        del state.units[self.source_id]
        ctx.ledger.resolution_merges += 1
        ctx.events.emit(
            state.year,
            "resolution_merge",
            unit_id=self.source_id,
            into_id=self.target_id,
            reason="coarsening",
            cell=list(state.world.coords(target.cell)),
            merged_population=merged,
            resulting_population=target.population,
            groups=target.groups,
            knowledge_distance=round(self.distance, 4),
        )


class CoarseningSubsystem:
    """Keeps each cell within the per-species unit budget."""

    name = "coarsening"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Coalesce]:
        """Plan merges cell by cell, updating a lightweight shadow of merged units."""
        config = ctx.scenario.config.resolution
        proposals: list[Coalesce] = []
        for units in state.units_by_cell().values():
            by_species: dict[str, list[tuple[str, int, FloatArray, frozenset[str]]]] = {}
            for u in units:
                if u.id not in ctx.trace_units:
                    by_species.setdefault(u.species_id, []).append(
                        (u.id, u.population, u.knowledge, u.technologies)
                    )
            for species_id in sorted(by_species):
                pool = by_species[species_id]
                while len(pool) > config.max_units_per_cell:
                    best: tuple[float, int, int] | None = None
                    for i in range(len(pool)):
                        for j in range(i + 1, len(pool)):
                            if pool[i][3] != pool[j][3]:
                                continue
                            d = knowledge_distance(pool[i][2], pool[j][2])
                            if d <= config.max_knowledge_distance and (best is None or d < best[0]):
                                best = (d, i, j)
                    if best is None:
                        break
                    d, i, j = best
                    a, b = pool[i], pool[j]
                    target, source = (a, b) if a[1] >= b[1] else (b, a)
                    total = target[1] + source[1]
                    blended = (target[2] * target[1] + source[2] * source[1]) / max(total, 1)
                    proposals.append(Coalesce(source[0], target[0], d))
                    pool = [p for k, p in enumerate(pool) if k not in (i, j)]
                    pool.append((target[0], total, blended, target[3]))
        return proposals
