"""Knowledge diffusion, technology adoption, and technology loss (spec §11.5, §11.6).

Contacts are co-located groups, groups in adjacent cells, and trade partners.
Knowledge flows down gradients::

    gain_i += teaching * transmissibility * sum_j contact_ij * max(K_j - K_i, 0)

A group adopts a contact's technology when it knows enough to use it, and loses
a technology when the supporting knowledge decays below a fraction of the
requirement.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.unit import PopulationUnit


def contacts(
    unit: PopulationUnit,
    state: SimulationState,
    by_cell: dict[int, list[PopulationUnit]],
    model: KnowledgeModel,
) -> dict[str, float]:
    """Contact strength with every other unit this unit interacts with."""
    spec = model.system.diffusion
    strength: dict[str, float] = {}
    for cell in state.world.cells_within(unit.cell, 1):
        weight = spec.same_cell_contact if cell == unit.cell else spec.adjacent_contact
        for other in by_cell.get(cell, []):
            if other is not unit and other.species_id == unit.species_id:
                strength[other.id] = strength.get(other.id, 0.0) + weight
    for partner, tie in unit.trade_ties.items():
        if partner in state.units:
            strength[partner] = strength.get(partner, 0.0) + spec.trade_contact * tie
    return strength


@model_rule(
    name="gradient_knowledge_diffusion",
    version="1.0",
    rationale=(
        "Knowledge flows from more to less knowledgeable contacts in proportion to contact "
        "strength."
    ),
    source_type="theoretical",
    parameters=(
        "transmissibility",
        "same_cell_contact",
        "adjacent_contact",
        "trade_contact",
        "teaching_efficiency",
    ),
    expected_domain="gain per domain in [0, max gap to any contact]",
    known_limitations="Symmetric contact; no language or cultural barriers yet.",
)
def diffusion_gains(
    knowledge: FloatArray,
    receivers: IntArray,
    sources: IntArray,
    strengths: FloatArray,
    transmissibility: FloatArray,
    teaching: FloatArray,
) -> FloatArray:
    """Knowledge gained this year by every unit, shape ``(units, domains)``.

    For receiver ``i``: ``teaching_i * transmissibility * sum_e strength_e * max(K_src - K_i, 0)``,
    capped per domain at the largest gap to any contact. ``knowledge`` is
    ``(units, domains)``; edge ``e`` carries knowledge from ``sources[e]`` to ``receivers[e]``
    with weight ``strengths[e]``. Edges are grouped by receiver in contact order.
    """
    gains = np.zeros_like(knowledge)
    if receivers.size == 0:
        return gains
    gaps = np.maximum(knowledge[sources] - knowledge[receivers], 0.0)
    starts = np.flatnonzero(np.r_[True, receivers[1:] != receivers[:-1]])
    owners = receivers[starts]
    weighted = strengths[:, None] * gaps
    # Sum each receiver's contiguous block with numpy's own reduction: for 8+ contacts it
    # adds pairwise, so reduceat (strictly sequential) would differ in the last bits.
    ends = np.r_[starts[1:], receivers.size]
    summed = np.stack(
        [weighted[a:b].sum(axis=0) for a, b in zip(starts.tolist(), ends.tolist(), strict=True)]
    )
    largest = np.maximum.reduceat(gaps, starts, axis=0)
    gain = teaching[owners, None] * transmissibility[None, :] * summed
    gains[owners] = np.minimum(gain, largest)
    return gains


@dataclass(frozen=True)
class DiffusionUpdate:
    """Knowledge gained and technologies adopted or lost by one unit."""

    unit_id: str
    gain: FloatArray
    adopted: tuple[tuple[str, str], ...]  # (technology, source unit)
    lost: tuple[str, ...]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit gains, adoptions, and losses with provenance events."""
        unit = state.units[self.unit_id]
        unit.knowledge = unit.knowledge + self.gain
        held = set(unit.technologies) - set(self.lost)
        for tech in self.lost:
            ctx.ledger.technology_losses += 1
            ctx.events.emit(
                state.year,
                "technology_lost",
                unit_id=unit.id,
                technology=tech,
                reason="knowledge_below_requirement",
                cell=list(state.world.coords(unit.cell)),
            )
        for tech, source in self.adopted:
            held.add(tech)
            ctx.ledger.adoptions += 1
            ctx.events.emit(
                state.year,
                "technology_adopted",
                unit_id=unit.id,
                technology=tech,
                source_unit=source,
                cell=list(state.world.coords(unit.cell)),
            )
        unit.technologies = frozenset(held)


class DiffusionSubsystem:
    """Diffuses knowledge and technologies through contacts; removes unsupported technologies."""

    name = "diffusion"

    def __init__(self, model: KnowledgeModel) -> None:
        self.model = model

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[DiffusionUpdate]:
        """All units read pre-diffusion knowledge (staged update)."""
        rng = ctx.rng.stream(Streams.TECHNOLOGY_ADOPTION)
        spec = self.model.system.diffusion
        by_cell = state.units_by_cell()
        units = list(state.units.values())
        if not units:
            return []
        index = {u.id: i for i, u in enumerate(units)}
        strengths = [contacts(u, state, by_cell, self.model) for u in units]
        receivers: list[int] = []
        sources: list[int] = []
        weights: list[float] = []
        for i, strength in enumerate(strengths):
            for j, w in strength.items():
                receivers.append(i)
                sources.append(index[j])
                weights.append(w)
        knowledge = np.stack([u.knowledge for u in units])
        teaching = np.array(
            [ctx.species(u.species_id).cognition.teaching_efficiency for u in units]
        )
        gains = diffusion_gains(
            knowledge,
            np.array(receivers, dtype=np.int64),
            np.array(sources, dtype=np.int64),
            np.array(weights, dtype=np.float64),
            self.model.transmissibility,
            teaching,
        )
        supported = self.model.knowledge_supported(knowledge, spec.loss_knowledge_fraction)
        updates: list[DiffusionUpdate] = []
        for i, unit in enumerate(units):
            strength = strengths[i]
            gain = gains[i]
            lost = self.model.unsupported_given(unit.technologies, supported[i])
            held = unit.technologies - frozenset(lost)
            adopted: list[tuple[str, str]] = []
            candidates: dict[str, str] = {}
            for j in sorted(strength):
                for tech in sorted(state.units[j].technologies - held):
                    candidates.setdefault(tech, j)
            for tech, source in sorted(candidates.items()):
                spec_t = self.model.technologies[tech]
                probability = spec.adoption_probability * min(1.0, strength[source])
                ok = self.model.prerequisites_met(
                    spec_t,
                    unit.knowledge,
                    held | {t for t, _ in adopted},
                    spec.adoption_knowledge_fraction,
                )
                if ok and rng.random() < probability:
                    adopted.append((tech, source))
            if gain.any() or adopted or lost:
                updates.append(DiffusionUpdate(unit.id, gain, tuple(adopted), lost))
        return updates
