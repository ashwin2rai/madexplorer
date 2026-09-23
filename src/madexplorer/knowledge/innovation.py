"""Directed innovation (spec §11.3, §11.4).

Each candidate technology (prerequisites met, not yet held) has an annual
invention hazard that requires both *need* - a problem signal named by the
technology - and *capacity* - domain knowledge, population, connectivity, and
surplus - while instability suppresses it::

    hazard = sigmoid(b0 + w_need*need + w_k*log(K/K_min) + w_n*log1p(N/n0)
                     + w_c*log1p(contacts) + w_s*surplus - w_i*instability + propensity)
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.economy.agriculture import unit_labor_hours
from madexplorer.knowledge.system import InnovationSpec, KnowledgeModel, NeedSignal, TechnologySpec
from madexplorer.population.energetics import annual_need_kcal
from madexplorer.population.groups import sigmoid
from madexplorer.population.unit import PopulationUnit


def need_signals(
    unit: PopulationUnit, state: SimulationState, ctx: StepContext
) -> dict[NeedSignal, float]:
    """Problem signals a group experiences, each roughly in [0, 1+]."""
    profile = ctx.species(unit.species_id)
    best_return = max(
        profile.foraging.plant_return_kcal_per_hour, profile.foraging.game_return_kcal_per_hour
    )
    forage_decline = (
        max(0.0, 1.0 - unit.forage_marginal_kcal_per_hour / best_return) if best_return > 0 else 0.0
    )
    labor = unit_labor_hours(unit, ctx)
    return {
        "food_stress": max(0.0, 1.0 - unit.food_ratio) + forage_decline,
        "harvest_variability": unit.harvest_variability(),
        "clearing_burden": unit.clearing_hours / labor if labor > 0 else 0.0,
        "soil_depletion": (1.0 - float(state.ecology.soil_nutrients[unit.cell]))
        if unit.fields_ha > 0
        else 0.0,
        "none": 0.0,
    }


@model_rule(
    name="innovation_hazard",
    version="1.0",
    rationale=(
        "Invention requires pressure (a technology-specific need signal) and capacity (domain "
        "knowledge relative to the requirement, group size, contacts, surplus); instability "
        "suppresses it, so extreme need without capacity usually fails."
    ),
    source_type="heuristic",
    parameters=(
        "baseline_logit",
        "need_weight",
        "knowledge_weight",
        "population_weight",
        "population_scale",
        "connectivity_weight",
        "surplus_weight",
        "instability_weight",
        "invention_propensity",
    ),
    expected_domain="annual probability in (0, 1)",
    known_limitations="No specialists yet; innovation is a property of the whole group.",
)
def innovation_hazard(
    tech: TechnologySpec,
    need: float,
    knowledge_ratio: float,
    population: int,
    connectivity: float,
    surplus: float,
    instability: float,
    spec: InnovationSpec,
    propensity: float,
) -> tuple[float, dict[str, float]]:
    """Annual invention probability and its logit components."""
    components = {
        "baseline": spec.baseline_logit,
        "need": spec.need_weight * need,
        "knowledge": spec.knowledge_weight * math.log(max(knowledge_ratio, 1e-6)),
        "population": spec.population_weight * math.log1p(population / spec.population_scale),
        "connectivity": spec.connectivity_weight * math.log1p(connectivity),
        "surplus": spec.surplus_weight * surplus,
        "instability": -spec.instability_weight * instability,
        "propensity": propensity,
    }
    return sigmoid(sum(components.values())), components


@dataclass(frozen=True)
class Invention:
    """A group invents a technology."""

    unit_id: str
    technology: str
    hazard: float
    components: dict[str, float]
    domain_index: int
    knowledge_bonus: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Add the technology and its knowledge bonus; record provenance."""
        unit = state.units[self.unit_id]
        unit.technologies = unit.technologies | {self.technology}
        knowledge = unit.knowledge.copy()
        knowledge[self.domain_index] += self.knowledge_bonus
        unit.knowledge = knowledge
        ctx.ledger.inventions += 1
        ctx.events.emit(
            state.year,
            "invention",
            unit_id=unit.id,
            technology=self.technology,
            cell=list(state.world.coords(unit.cell)),
            population=unit.population,
            hazard=round(self.hazard, 6),
            components={k: round(v, 3) for k, v in self.components.items()},
        )


class InnovationSubsystem:
    """Draws inventions for every group and candidate technology."""

    name = "innovation"

    def __init__(self, model: KnowledgeModel) -> None:
        self.model = model

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Invention]:
        """Evaluate hazards against the current state."""
        rng = ctx.rng.stream(Streams.INNOVATION)
        spec = self.model.system.innovation
        by_cell = state.units_by_cell()
        proposals: list[Invention] = []
        for unit in state.units.values():
            candidates = [
                t
                for t in self.model.system.technologies
                if t.id not in unit.technologies
                and self.model.prerequisites_met(t, unit.knowledge, unit.technologies)
            ]
            if not candidates:
                continue
            profile = ctx.species(unit.species_id)
            signals = need_signals(unit, state, ctx)
            neighbors = (
                sum(len(by_cell.get(c, [])) for c in state.world.cells_within(unit.cell, 1)) - 1
            )
            connectivity = neighbors + sum(unit.trade_ties.values())
            need = annual_need_kcal(
                unit,
                profile,
                ctx.tables[unit.species_id],
                float(state.climate.temperature_c[unit.cell]),
            )
            surplus = (
                min(1.0, unit.stores_kcal / need + max(0.0, unit.food_ratio - 1.0))
                if need > 0
                else 0.0
            )
            for tech in candidates:
                ratios = [
                    self.model.level(unit.knowledge, d) / v
                    for d, v in tech.min_knowledge.items()
                    if v > 0
                ]
                knowledge_ratio = (
                    min(ratios) if ratios else 1.0 + self.model.level(unit.knowledge, tech.domain)
                )
                hazard, components = innovation_hazard(
                    tech,
                    signals[tech.need],
                    knowledge_ratio,
                    unit.population,
                    connectivity,
                    surplus,
                    unit.energy_deficit,
                    spec,
                    profile.cognition.invention_propensity,
                )
                if unit.id in ctx.trace_units:
                    ctx.events.emit(
                        state.year,
                        "trace_innovation",
                        unit_id=unit.id,
                        technology=tech.id,
                        hazard=round(hazard, 6),
                        components={k: round(v, 3) for k, v in components.items()},
                    )
                if rng.random() < hazard:
                    proposals.append(
                        Invention(
                            unit.id,
                            tech.id,
                            hazard,
                            components,
                            self.model.index[tech.domain],
                            tech.knowledge_bonus,
                        )
                    )
                    break  # at most one invention per group per year
        return proposals
