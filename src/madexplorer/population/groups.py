"""Group fission, fusion, and extinction (spec §6.4, §16.1, §16.2).

Fission and fusion are hazards, not thresholds. Fission is driven by group
size (coordination cost) and food stress; fusion by small size and lack of
mates. Both conserve individuals and energy reserves exactly.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import IntArray
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.profile import SocialBehavior


def sigmoid(x: float) -> float:
    """Numerically stable logistic function."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


@model_rule(
    name="fission_hazard",
    version="1.0",
    rationale=(
        "Probability a group splits rises with size per social group relative to a reference "
        "size (coordination and scalar stress) and with food stress (1 - food ratio)."
    ),
    source_type="heuristic",
    parameters=(
        "reference_group_size",
        "fission_baseline_logit",
        "fission_size_weight",
        "fission_food_stress_weight",
    ),
    expected_domain="annual probability in (0, 1)",
    known_limitations="No factionalism, inequality, or kinship structure until MVP 3/4.",
)
def fission_hazard(
    population: int, food_ratio: float, social: SocialBehavior, groups: int = 1
) -> tuple[float, dict[str, float]]:
    """Annual fission probability and its logit components."""
    per_group = max(population, 1) / max(groups, 1)
    components = {
        "baseline": social.fission_baseline_logit,
        "size": social.fission_size_weight * math.log(per_group / social.reference_group_size),
        "food_stress": social.fission_food_stress_weight * max(0.0, 1.0 - food_ratio),
    }
    return sigmoid(sum(components.values())), components


@model_rule(
    name="fusion_hazard",
    version="1.0",
    rationale=(
        "Small groups, and groups lacking a fertile adult of either sex, join a co-located group."
    ),
    source_type="heuristic",
    parameters=(
        "fusion_baseline_logit",
        "fusion_small_group_weight",
        "fusion_mate_shortage_weight",
    ),
    expected_domain="annual probability in (0, 1)",
    known_limitations=(
        "Only co-located groups of the same species can fuse; one fusion per cell per year."
    ),
)
def fusion_hazard(
    population: int, lacks_mate: bool, social: SocialBehavior
) -> tuple[float, dict[str, float]]:
    """Annual fusion probability for a group and its logit components."""
    components = {
        "baseline": social.fusion_baseline_logit,
        "small_group": social.fusion_small_group_weight
        * max(0.0, -math.log(max(population, 1) / social.reference_group_size)),
        "mate_shortage": social.fusion_mate_shortage_weight * float(lacks_mate),
    }
    return sigmoid(sum(components.values())), components


def split_cohorts(
    females: IntArray, males: IntArray, fraction: float, rng: np.random.Generator
) -> tuple[IntArray, IntArray, IntArray, IntArray]:
    """Binomially sample a departing fraction from each cohort.

    Returns ``(remaining_f, remaining_m, departing_f, departing_m)``; totals are conserved.
    """
    leave_f = rng.binomial(females, fraction)
    leave_m = rng.binomial(males, fraction)
    return females - leave_f, males - leave_m, leave_f, leave_m


def merge_into(
    target: PopulationUnit, source: PopulationUnit, combine_groups: bool = False
) -> None:
    """Absorb ``source`` into ``target``, conserving people, food, fields, and beliefs.

    ``combine_groups`` keeps both social groups (resolution coarsening); otherwise
    the source group is absorbed into the target's social structure (fusion).
    """
    n_target, n_source = target.population, source.population
    total_reserve = target.total_reserve_kcal + source.total_reserve_kcal
    if target.knowledge.size and n_target + n_source > 0:
        target.knowledge = (target.knowledge * n_target + source.knowledge * n_source) / (
            n_target + n_source
        )
    target.technologies = target.technologies | source.technologies
    target.females = target.females + source.females
    target.males = target.males + source.males
    n = target.population
    target.reserve_kcal_per_capita = total_reserve / n if n else 0.0
    target.energy_debt_kcal += source.energy_debt_kcal
    target.stores_kcal += source.stores_kcal
    target.fields_ha += source.fields_ha
    target.ever_cultivated = target.ever_cultivated or source.ever_cultivated
    target.labor_debt_hours += source.labor_debt_hours
    if combine_groups:
        target.groups += source.groups
    for partner, tie in source.trade_ties.items():
        if partner != target.id:
            target.trade_ties[partner] = max(tie, target.trade_ties.get(partner, 0.0))
    target.trade_ties.pop(source.id, None)
    for cell, obs in source.beliefs.items():
        mine = target.beliefs.get(cell)
        if mine is None or obs.year > mine.year:
            target.beliefs[cell] = obs
    for cell, value in source.familiarity.items():
        target.familiarity[cell] = max(value, target.familiarity.get(cell, 0.0))


@dataclass(frozen=True)
class Fission:
    """Split a daughter group off a parent (the daughter starts in the same cell)."""

    parent_id: str
    fraction: float
    hazard: float
    components: dict[str, float]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Create the daughter unit with conditional cohorts and shares of food and fields.

        A multi-group unit buds off exactly one of its social groups.
        """
        parent = state.units[self.parent_id]
        rng = ctx.rng.stream(Streams.SOCIAL)
        source_population = parent.population
        fraction = 1.0 / parent.groups if parent.groups > 1 else self.fraction
        keep_f, keep_m, leave_f, leave_m = split_cohorts(
            parent.females, parent.males, fraction, rng
        )
        moved = int(leave_f.sum() + leave_m.sum())
        if moved == 0 or moved == source_population:
            return
        daughter = PopulationUnit(
            id=ctx.ids.next("u"),
            species_id=parent.species_id,
            cell=parent.cell,
            females=leave_f,
            males=leave_m,
            reserve_kcal_per_capita=parent.reserve_kcal_per_capita,
            founded_year=state.year,
            parent_id=parent.id,
            food_ratio=parent.food_ratio,
            energy_deficit=parent.energy_deficit,
            beliefs=dict(parent.beliefs),
            familiarity=dict(parent.familiarity),
            knowledge=parent.knowledge.copy(),
            technologies=parent.technologies,
            stores_kcal=parent.stores_kcal * moved / source_population,
            fields_ha=parent.fields_ha * moved / source_population,
            ever_cultivated=parent.ever_cultivated,
            residence_years=parent.residence_years,
            forage_marginal_kcal_per_hour=parent.forage_marginal_kcal_per_hour,
        )
        parent.stores_kcal -= daughter.stores_kcal
        parent.fields_ha -= daughter.fields_ha
        if parent.groups > 1:
            parent.groups -= 1
        parent.females, parent.males = keep_f, keep_m
        state.units[daughter.id] = daughter
        ctx.ledger.fissions += 1
        ctx.events.emit(
            state.year,
            "population_split",
            unit_id=parent.id,
            daughter_id=daughter.id,
            reason="fission",
            cell=list(state.world.coords(parent.cell)),
            source_population=source_population,
            moved_population=moved,
            hazard=round(self.hazard, 4),
            components={k: round(v, 4) for k, v in self.components.items()},
        )


@dataclass(frozen=True)
class Fusion:
    """Merge a (small) group into a co-located group of the same species."""

    source_id: str
    target_id: str
    hazard: float
    components: dict[str, float]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Absorb the source unit into the target."""
        source, target = state.units[self.source_id], state.units[self.target_id]
        merged = source.population
        merge_into(target, source)
        del state.units[self.source_id]
        ctx.ledger.fusions += 1
        ctx.events.emit(
            state.year,
            "population_merge",
            unit_id=self.source_id,
            into_id=self.target_id,
            reason="fusion",
            cell=list(state.world.coords(target.cell)),
            merged_population=merged,
            resulting_population=target.population,
            hazard=round(self.hazard, 4),
            components={k: round(v, 4) for k, v in self.components.items()},
        )


@dataclass(frozen=True)
class Extinction:
    """Remove a unit with no surviving members."""

    unit_id: str

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Delete the unit and record the event."""
        unit = state.units.pop(self.unit_id)
        ctx.ledger.extinctions += 1
        ctx.events.emit(
            state.year,
            "unit_extinct",
            unit_id=unit.id,
            cell=list(state.world.coords(unit.cell)),
            founded_year=unit.founded_year,
        )


class ExtinctionSubsystem:
    """Removes empty units."""

    name = "extinction"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Extinction]:
        """Find units with zero members."""
        return [Extinction(u.id) for u in state.units.values() if u.population == 0]


class FissionSubsystem:
    """Draws group splits."""

    name = "fission"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Fission]:
        """Evaluate each group's fission hazard."""
        rng = ctx.rng.stream(Streams.SOCIAL)
        proposals: list[Fission] = []
        for unit in state.units.values():
            if unit.population < 2:
                continue
            social = ctx.species(unit.species_id).social
            hazard, components = fission_hazard(
                unit.population, unit.food_ratio, social, unit.groups
            )
            if rng.random() < hazard:
                fraction = rng.uniform(social.fission_fraction_min, social.fission_fraction_max)
                proposals.append(Fission(unit.id, float(fraction), hazard, components))
        return proposals


class FusionSubsystem:
    """Draws group mergers among co-located same-species groups."""

    name = "fusion"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Fusion]:
        """The smallest group in each cell may join the largest other group there."""
        rng = ctx.rng.stream(Streams.SOCIAL)
        proposals: list[Fusion] = []
        for units in state.units_by_cell().values():
            by_species: dict[str, list[PopulationUnit]] = {}
            for unit in units:
                by_species.setdefault(unit.species_id, []).append(unit)
            for species_id in sorted(by_species):
                group = by_species[species_id]
                if len(group) < 2:
                    continue
                tables = ctx.tables[species_id]
                smallest = min(group, key=lambda u: u.population)
                target = max((u for u in group if u is not smallest), key=lambda u: u.population)
                has_f, has_m = smallest.has_reproductive_pair(
                    tables.female_reproductive, tables.male_reproductive
                )
                social = ctx.species(species_id).social
                hazard, components = fusion_hazard(
                    smallest.population, not (has_f and has_m), social
                )
                if rng.random() < hazard:
                    proposals.append(Fusion(smallest.id, target.id, hazard, components))
        return proposals
