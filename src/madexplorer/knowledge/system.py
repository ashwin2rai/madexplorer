"""Knowledge system definition: domains, capabilities, and technologies (spec §11).

A knowledge system is a versioned data file (e.g. ``technologies/neolithic.yaml``).
The engine knows only a fixed set of *capabilities* - the numbers that enter
production and storage equations - and a fixed set of *activities* whose
practice builds knowledge. Everything else (which domains exist, which
technologies exist, their prerequisites, the needs that direct their invention,
and their effects) is scenario data, so a technology tree is a hypothesis that
can be swapped or ablated without touching code.
"""

from collections.abc import Mapping
from typing import Literal, Self

import numpy as np
from pydantic import Field, model_validator

from madexplorer.config.base import FrozenModel
from madexplorer.core.types import FloatArray

# Engine-facing quantities that technologies modify.
Capability = Literal["crop_yield", "storage_retention", "clearing_efficiency", "soil_management"]
CAPABILITIES: tuple[Capability, ...] = (
    "crop_yield",
    "storage_retention",
    "clearing_efficiency",
    "soil_management",
)

# Activities whose practice builds knowledge; shares of the unit's year, in [0, 1].
Activity = Literal["plant_foraging", "game_foraging", "farming", "clearing", "storing"]

# Problem signals that direct innovation toward a domain (spec §11.4).
NeedSignal = Literal[
    "food_stress", "harvest_variability", "clearing_burden", "soil_depletion", "none"
]


class DomainSpec(FrozenModel):
    """Accumulation, decay, and transmission of one knowledge domain."""

    learning_rate: float = Field(ge=0)
    decay_rate: float = Field(ge=0, le=1)
    transmissibility: float = Field(ge=0, le=1)
    practitioner_scale: float = Field(gt=0)  # practitioners at which learning returns ~ log(2)
    half_efficiency_level: float = Field(gt=0)  # level at which practical efficiency is 0.5
    initial_level: float = Field(ge=0)
    practice: dict[Activity, float] = Field(default_factory=dict)


class TechnologySpec(FrozenModel):
    """One technology: prerequisites, the need that drives its invention, and its effects."""

    id: str
    domain: str
    min_knowledge: dict[str, float] = Field(default_factory=dict)
    requires: tuple[str, ...] = ()
    need: NeedSignal = "none"
    effects: dict[Capability, float] = Field(default_factory=dict)
    knowledge_bonus: float = Field(default=0.0, ge=0)


class InnovationSpec(FrozenModel):
    """Weights of the innovation hazard (spec §11.3)."""

    baseline_logit: float
    need_weight: float
    knowledge_weight: float
    population_weight: float
    population_scale: float = Field(gt=0)
    connectivity_weight: float
    surplus_weight: float
    instability_weight: float


class DiffusionSpec(FrozenModel):
    """Contact structure for knowledge and technology diffusion (spec §11.5)."""

    same_cell_contact: float = Field(ge=0)
    adjacent_contact: float = Field(ge=0)
    trade_contact: float = Field(ge=0)
    adoption_probability: float = Field(ge=0, le=1)
    adoption_knowledge_fraction: float = Field(ge=0, le=1)
    loss_knowledge_fraction: float = Field(ge=0, le=1)


class KnowledgeSystem(FrozenModel):
    """Complete knowledge-system definition."""

    name: str
    domains: dict[str, DomainSpec] = Field(min_length=1)
    base_capabilities: dict[Capability, float]
    technologies: tuple[TechnologySpec, ...] = ()
    innovation: InnovationSpec
    diffusion: DiffusionSpec

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        missing = set(CAPABILITIES) - set(self.base_capabilities)
        if missing:
            raise ValueError(f"base_capabilities missing {sorted(missing)}")
        ids = [t.id for t in self.technologies]
        if len(ids) != len(set(ids)):
            raise ValueError("technology ids must be unique")
        for tech in self.technologies:
            unknown = ({tech.domain} | set(tech.min_knowledge)) - set(self.domains)
            if unknown:
                raise ValueError(
                    f"technology {tech.id} references unknown domains {sorted(unknown)}"
                )
            if not set(tech.requires) <= set(ids):
                raise ValueError(f"technology {tech.id} requires unknown technologies")
        return self


class KnowledgeModel:
    """Runtime view of a :class:`KnowledgeSystem` with vector indexing and cached lookups."""

    def __init__(self, system: KnowledgeSystem) -> None:
        self.system = system
        self.domains: tuple[str, ...] = tuple(system.domains)
        self.index: dict[str, int] = {d: i for i, d in enumerate(self.domains)}
        self.technologies: dict[str, TechnologySpec] = {t.id: t for t in system.technologies}
        specs = [system.domains[d] for d in self.domains]
        self.learning_rate = np.array([s.learning_rate for s in specs])
        self.decay_rate = np.array([s.decay_rate for s in specs])
        self.transmissibility = np.array([s.transmissibility for s in specs])
        self.practitioner_scale = np.array([s.practitioner_scale for s in specs])
        self.half_efficiency = np.array([s.half_efficiency_level for s in specs])
        self._capability_cache: dict[frozenset[str], dict[Capability, float]] = {}

    def initial_levels(self, overrides: Mapping[str, float] | None = None) -> FloatArray:
        """Starting knowledge vector, with optional per-domain overrides."""
        levels = np.array([self.system.domains[d].initial_level for d in self.domains])
        for domain, value in (overrides or {}).items():
            levels[self.index[domain]] = value
        return levels

    def level(self, knowledge: FloatArray, domain: str) -> float:
        """Knowledge level in ``domain`` (0 when the domain does not exist)."""
        i = self.index.get(domain)
        return float(knowledge[i]) if i is not None else 0.0

    def efficiency(self, knowledge: FloatArray, domain: str) -> float:
        """Practical efficiency ``K / (K + K_half)`` in [0, 1) for a domain."""
        i = self.index.get(domain)
        if i is None:
            return 1.0
        k = float(knowledge[i])
        return k / (k + float(self.half_efficiency[i]))

    def capabilities(self, technologies: frozenset[str]) -> dict[Capability, float]:
        """Capability values: base plus additive effects of held technologies."""
        cached = self._capability_cache.get(technologies)
        if cached is None:
            cached = dict(self.system.base_capabilities)
            for tech_id in sorted(technologies):
                for capability, delta in self.technologies[tech_id].effects.items():
                    cached[capability] = cached[capability] + delta
            self._capability_cache[technologies] = cached
        return cached

    def practice_weights(self, activity_shares: Mapping[str, float]) -> FloatArray:
        """Per-domain practice intensity from activity shares."""
        return np.array(
            [
                sum(
                    w * activity_shares.get(a, 0.0)
                    for a, w in self.system.domains[d].practice.items()
                )
                for d in self.domains
            ]
        )

    def unsupported(
        self, held: frozenset[str], knowledge: FloatArray, fraction: float
    ) -> tuple[str, ...]:
        """Held technologies whose knowledge fell below ``fraction`` of the requirement,
        plus any that depend on a lost technology (iterated to a fixed point)."""
        kept = {
            t
            for t in held
            if all(
                self.level(knowledge, d) >= fraction * v
                for d, v in self.technologies[t].min_knowledge.items()
            )
        }
        changed = True
        while changed:
            changed = False
            for t in sorted(kept):
                if not set(self.technologies[t].requires) <= kept:
                    kept.discard(t)
                    changed = True
        return tuple(sorted(held - kept))

    def prerequisites_met(
        self,
        tech: TechnologySpec,
        knowledge: FloatArray,
        held: frozenset[str],
        fraction: float = 1.0,
    ) -> bool:
        """Whether knowledge (scaled by ``fraction``) and required technologies suffice."""
        if not set(tech.requires) <= held:
            return False
        return all(self.level(knowledge, d) >= fraction * v for d, v in tech.min_knowledge.items())


def default_capabilities() -> dict[Capability, float]:
    """Capabilities when a scenario has no knowledge system: no cultivation, no storage."""
    return {
        "crop_yield": 0.0,
        "storage_retention": 0.0,
        "clearing_efficiency": 1.0,
        "soil_management": 0.0,
    }
