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
from madexplorer.population.composition import MergeMode
from madexplorer.population.familiarity import familiarity_rule
from madexplorer.population.lifecycle import merge_units, remove_unit, split_unit
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


@dataclass(frozen=True, eq=False)
class Fission:
    """Split the drawn departing cohorts off a parent (the daughter starts in the same cell).

    The stochastic decision, including who leaves, is made in evaluation; applying it is
    deterministic.
    """

    parent_id: str
    leave_f: IntArray
    leave_m: IntArray
    hazard: float
    components: dict[str, float]

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Create the daughter unit with the departing cohorts and shares of food and fields
        (nothing happens if nobody, or everybody, was drawn to leave)."""
        ctx.invalidate_spatial()
        parent = state.units[self.parent_id]
        source_population = parent.population
        moved = int(self.leave_f.sum() + self.leave_m.sum())
        if moved == 0 or moved == source_population:
            return
        rule = familiarity_rule(ctx.species(parent.species_id), ctx.mechanisms)
        daughter = split_unit(
            state.population,
            parent.id,
            self.leave_f,
            self.leave_m,
            ctx.ids.next("u"),
            state.year,
            rule,
        )
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
        ctx.invalidate_spatial()
        source, target = state.units[self.source_id], state.units[self.target_id]
        merged = source.population
        rule = familiarity_rule(ctx.species(target.species_id), ctx.mechanisms)
        merge_units(
            state.population, self.source_id, self.target_id, MergeMode.FUSION, state.year, rule
        )
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
        ctx.invalidate_spatial()
        unit = state.units[self.unit_id]
        cell, founded_year = unit.cell, unit.founded_year
        remove_unit(state.population, self.unit_id)
        ctx.ledger.extinctions += 1
        ctx.events.emit(
            state.year,
            "unit_extinct",
            unit_id=self.unit_id,
            cell=list(state.world.coords(cell)),
            founded_year=founded_year,
        )


class ExtinctionSubsystem:
    """Removes empty units."""

    name = "extinction"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Extinction]:
        """Find units with zero members."""
        cols = ctx.columns(state)
        empty = np.flatnonzero(cols.population() == 0).tolist()
        return [Extinction(cols.units[i].id) for i in empty]


class FissionSubsystem:
    """Draws group splits."""

    name = "fission"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Fission]:
        """Evaluate each group's fission hazard, then draw who leaves each splitting group.

        The fission stream is consumed in two passes: every group's hazard draw (and, if it
        splits, its departing fraction) in unit order, then the departing cohorts of the
        splitting groups in the same order. A multi-group unit buds off exactly one of its
        social groups (fraction ``1 / groups``).
        """
        rng = ctx.rng.stream(Streams.FISSION)
        splitting: list[tuple[PopulationUnit, float, float, dict[str, float]]] = []
        cols = ctx.columns(state)
        population = cols.population().tolist()
        food = cols.get("food_ratio").tolist()
        groups = cols.get("groups").tolist()
        for unit, n, food_ratio, n_groups in zip(cols.units, population, food, groups, strict=True):
            if n < 2:
                continue
            social = ctx.species(unit.species_id).social
            hazard, components = fission_hazard(n, food_ratio, social, n_groups)
            if rng.random() < hazard:
                fraction = rng.uniform(social.fission_fraction_min, social.fission_fraction_max)
                share = 1.0 / n_groups if n_groups > 1 else float(fraction)
                splitting.append((unit, share, hazard, components))
        proposals: list[Fission] = []
        for unit, share, hazard, components in splitting:
            _, _, leave_f, leave_m = split_cohorts(unit.females, unit.males, share, rng)
            proposals.append(Fission(unit.id, leave_f, leave_m, hazard, components))
        return proposals


class FusionSubsystem:
    """Draws group mergers among co-located same-species groups."""

    name = "fusion"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Fusion]:
        """The smallest group in each cell may join the largest other group there."""
        rng = ctx.rng.stream(Streams.FUSION)
        proposals: list[Fusion] = []
        index = ctx.spatial(state)
        cols = ctx.columns(state)
        population = cols.population().tolist()
        units = cols.units
        order, starts = index.order.tolist(), index.starts.tolist()
        for k in range(len(starts) - 1):
            members = order[starts[k] : starts[k + 1]]
            if len(members) < 2:
                continue
            by_species: dict[str, list[int]] = {}
            for r in members:
                by_species.setdefault(units[r].species_id, []).append(r)
            for species_id in sorted(by_species):
                group = by_species[species_id]
                if len(group) < 2:
                    continue
                tables = ctx.tables[species_id]
                smallest = min(group, key=lambda r: population[r])  # first minimum, as before
                target = max((r for r in group if r != smallest), key=lambda r: population[r])
                has_f, has_m = units[smallest].has_reproductive_pair(
                    tables.female_reproductive, tables.male_reproductive
                )
                social = ctx.species(species_id).social
                hazard, components = fusion_hazard(
                    population[smallest], not (has_f and has_m), social
                )
                if rng.random() < hazard:
                    proposals.append(
                        Fusion(units[smallest].id, units[target].id, hazard, components)
                    )
        return proposals
