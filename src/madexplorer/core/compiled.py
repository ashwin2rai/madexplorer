"""Compiled numeric scenario data for batched kernels (performance layer, not a model).

The scenario configuration is human-readable (YAML, pydantic models, string names).
Batched subsystem kernels need the same values as immutable arrays and integer indices,
so that a loop over thousands of units never walks pydantic attribute chains or hashes
names. :class:`CompiledScenario` is built once per :class:`~madexplorer.core.simulation.
Simulator` from the scenario and its knowledge model; it holds only derived views of
configuration and changes no equation.

Kept deliberately narrow: species indices and per-species numeric parameters, and the
technology table (bit positions, prerequisite masks, minimum-knowledge and capability
matrices). Names stay at the edges (configuration, events, recorder output).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.types import BoolArray, FloatArray, IntArray
from madexplorer.knowledge.system import CAPABILITIES, KnowledgeModel

# Species parameters compiled into per-species arrays: "<profile section>.<field>".
SPECIES_PARAMETERS: tuple[str, ...] = (
    "metabolism.adult_daily_kcal",
    "metabolism.reserve_days_max",
    "metabolism.comfort_temp_low_c",
    "metabolism.comfort_temp_high_c",
    "metabolism.cold_cost_per_c",
    "metabolism.heat_cost_per_c",
    "metabolism.starvation_mortality_sensitivity",
    "metabolism.fertility_food_midpoint",
    "metabolism.fertility_food_scale",
    "foraging.foraging_hours_per_day",
    "foraging.surplus_target",
    "subsistence.max_farm_labor_share",
    "cognition.memory_years",
    "cognition.observation_noise_sigma",
    "cognition.teaching_efficiency",
    "social.knowledge_sharing_probability",
    "social.food_sharing_propensity",
    "social_information.reports_per_interaction",
    "social_information.max_report_age_years",
    "social_information.transmission_confidence_decay",
    "migration.food_weight",
    "migration.water_weight",
    "migration.movement_cost_weight",
    "migration.movement_reference_km",
    "migration.uncertainty_weight",
    "migration.abandoned_stores_weight",
    "movement.carry_kcal_per_capita",
    "movement.travel_kcal_per_km",
)


@dataclass(frozen=True, eq=False)
class TechnologyTable:
    """Technologies as bit positions and matrices (in knowledge-system file order).

    Technology sets of units are ``frozenset`` of ids in the domain model; the table maps
    each distinct set to an integer bitmask once (cached) so prerequisite and capability
    lookups become array operations.
    """

    ids: tuple[str, ...]
    position: Mapping[str, int]
    requires_mask: IntArray  # (T,) bitmask of required technologies
    min_knowledge: FloatArray  # (T, domains): minimum level per domain (0 = none)
    has_minimum: BoolArray  # (T, domains): whether the domain is a prerequisite
    domain: IntArray  # (T,) domain index of each technology
    effects: FloatArray  # (T, capabilities): additive capability effects
    base_capabilities: FloatArray  # (capabilities,)
    _masks: dict[frozenset[str], int] = field(default_factory=dict)

    def mask(self, technologies: frozenset[str]) -> int:
        """Bitmask of a technology set (cached per distinct set)."""
        value = self._masks.get(technologies)
        if value is None:
            value = 0
            for tech in technologies:
                value |= 1 << self.position[tech]
            self._masks[technologies] = value
        return value

    def masks(self, sets: list[frozenset[str]]) -> IntArray:
        """Bitmasks of many technology sets, as an int64 array."""
        mask = self.mask
        return np.array([mask(s) for s in sets], dtype=np.int64)

    def holds(self, masks: IntArray) -> BoolArray:
        """``(units, T)``: whether each unit holds each technology."""
        bits = np.left_shift(np.int64(1), np.arange(len(self.ids), dtype=np.int64))
        held: BoolArray = (masks[:, None] & bits[None, :]) != 0
        return held

    @classmethod
    def build(cls, model: KnowledgeModel) -> "TechnologyTable":
        """Compile a knowledge model's technologies."""
        ids = tuple(model.technologies)
        if len(ids) > 62:
            raise ValueError("more than 62 technologies need a multi-word bitmask")
        position = {t: i for i, t in enumerate(ids)}
        n_domains = len(model.domains)
        requires = np.zeros(len(ids), dtype=np.int64)
        minimum = np.zeros((len(ids), n_domains))
        has_minimum = np.zeros((len(ids), n_domains), dtype=bool)
        domain = np.zeros(len(ids), dtype=np.int64)
        effects = np.zeros((len(ids), len(CAPABILITIES)))
        for i, tech_id in enumerate(ids):
            tech = model.technologies[tech_id]
            for required in tech.requires:
                requires[i] |= 1 << position[required]
            for name, level in tech.min_knowledge.items():
                minimum[i, model.index[name]] = level
                has_minimum[i, model.index[name]] = True
            domain[i] = model.index[tech.domain]
            for capability, delta in tech.effects.items():
                effects[i, CAPABILITIES.index(capability)] = delta
        base = np.array([model.system.base_capabilities[c] for c in CAPABILITIES])
        return cls(ids, position, requires, minimum, has_minimum, domain, effects, base)


@dataclass(frozen=True, eq=False)
class CompiledScenario:
    """Immutable numeric views of a scenario, consumed by batched subsystem kernels."""

    species_ids: tuple[str, ...]  # sorted
    species_index: Mapping[str, int]
    parameters: Mapping[str, FloatArray]  # SPECIES_PARAMETERS name -> (species,) values
    technologies: TechnologyTable | None
    knowledge_domains: tuple[str, ...]

    def parameter(self, name: str) -> FloatArray:
        """Per-species values of one compiled parameter, indexed by species index."""
        return self.parameters[name]

    def species_of(self, species_ids: list[str]) -> IntArray:
        """Species indices of many units."""
        index = self.species_index
        return np.array([index[s] for s in species_ids], dtype=np.int64)

    @classmethod
    def build(cls, scenario: Scenario, knowledge: KnowledgeModel | None) -> "CompiledScenario":
        """Compile ``scenario`` (and its knowledge model, if any)."""
        species_ids = tuple(sorted(scenario.species))
        parameters: dict[str, FloatArray] = {}
        for name in SPECIES_PARAMETERS:
            section, _, attribute = name.partition(".")
            parameters[name] = np.array(
                [
                    float(getattr(getattr(scenario.species[sid], section), attribute))
                    for sid in species_ids
                ]
            )
        return cls(
            species_ids=species_ids,
            species_index={sid: i for i, sid in enumerate(species_ids)},
            parameters=parameters,
            technologies=TechnologyTable.build(knowledge) if knowledge else None,
            knowledge_domains=knowledge.domains if knowledge else (),
        )
