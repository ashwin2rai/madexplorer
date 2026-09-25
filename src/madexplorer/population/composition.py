"""How population-unit state combines and divides (spec §6.4, §6.5, §38).

Every field of :class:`PopulationUnit` has one declared rule for merging two units
(fusion of social groups, or computational aggregation) and one for splitting a
unit (fission, and later selective migration). The rules live here, and only
here, so that new state added in MVP 3 (wealth, health, preference strata) must
declare its semantics before it can be merged or split. ``FIELD_RULES`` is
checked against the dataclass fields by the test suite.

Merging also rewires the social network: third-party trade ties that pointed at
the absorbed unit are redirected to the surviving unit, duplicate edges combine
additively (tie strength is accumulated exchange), and the edge between the two
merging units disappears rather than becoming a self-edge.
"""

from collections.abc import MutableMapping
from enum import Enum

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.unit import PopulationUnit


class MergeMode(Enum):
    """Why two units merge, which decides how their social-group count combines."""

    FUSION = "fusion"  # one group joins another's social structure
    AGGREGATION = "aggregation"  # computational coarsening; both groups persist inside the unit


# Field -> (merge rule, split rule). Documentation and a completeness contract: the test
# suite fails if a PopulationUnit field is missing, so every new field gets explicit semantics.
FIELD_RULES: dict[str, tuple[str, str]] = {
    "id": ("keep target", "new id"),
    "species_id": ("must match", "copy"),
    "cell": ("must match", "copy"),
    "females": ("vector sum", "binomial draw per cohort (given)"),
    "males": ("vector sum", "binomial draw per cohort (given)"),
    "reserve_kcal_per_capita": ("conserve total", "copy per-capita value (conserves total)"),
    "founded_year": ("keep target", "split year"),
    "parent_id": ("keep target", "parent id"),
    "energy_debt_kcal": ("sum", "proportional to people"),
    "harvest_kcal": ("sum", "proportional to people"),
    "food_ratio": ("population-weighted mean", "copy"),
    "energy_deficit": ("population-weighted mean", "copy"),
    "beliefs": ("freshest observation per cell", "copy"),
    "familiarity": ("max per cell", "copy"),
    "groups": ("sum (aggregation) / keep target (fusion)", "one group leaves a multi-group unit"),
    "knowledge": ("population-weighted mean", "copy"),
    "technologies": ("union", "copy"),
    "stores_kcal": ("sum", "proportional to people"),
    "fields_ha": ("sum", "proportional to people"),
    "ever_cultivated": ("or", "copy"),
    "labor_debt_hours": ("sum", "proportional to people"),
    "farm_harvest_kcal": ("sum", "proportional to people"),
    "farm_hours": ("sum", "proportional to people"),
    "forage_harvest_kcal": ("sum", "proportional to people"),
    "forage_hours": ("sum", "proportional to people"),
    "forage_marginal_kcal_per_hour": ("population-weighted mean", "copy"),
    "forage_plant_share": ("population-weighted mean", "copy"),
    "crop_yield_kcal_per_ha": ("keep target (same cell and technology)", "copy"),
    "clearing_hours": ("sum", "proportional to people"),
    "stored_kcal": ("sum", "proportional to people"),
    "residence_years": ("keep target (the larger unit)", "copy"),
    "harvest_history": ("population-weighted mean of aligned recent years", "copy"),
    "trade_ties": (
        "additive union, rewired network",
        "stay with the parent (daughter unconnected)",
    ),
}

_SUMMED = (
    "energy_debt_kcal",
    "harvest_kcal",
    "stores_kcal",
    "fields_ha",
    "labor_debt_hours",
    "farm_harvest_kcal",
    "farm_hours",
    "forage_harvest_kcal",
    "forage_hours",
    "clearing_hours",
    "stored_kcal",
)
_WEIGHTED_MEAN = (
    "food_ratio",
    "energy_deficit",
    "forage_marginal_kcal_per_hour",
    "forage_plant_share",
)


def _weighted(a: float, n_a: int, b: float, n_b: int) -> float:
    total = n_a + n_b
    return (a * n_a + b * n_b) / total if total else a


def merge_state(target: PopulationUnit, source: PopulationUnit, mode: MergeMode) -> None:
    """Fold ``source``'s state into ``target`` (network rewiring is :func:`absorb`'s job)."""
    if target.species_id != source.species_id or target.cell != source.cell:
        raise ValueError("only co-located units of one species can merge")
    n_t, n_s = target.population, source.population
    total_reserve = target.total_reserve_kcal + source.total_reserve_kcal
    for name in _WEIGHTED_MEAN:
        setattr(target, name, _weighted(getattr(target, name), n_t, getattr(source, name), n_s))
    for name in _SUMMED:
        setattr(target, name, getattr(target, name) + getattr(source, name))
    if target.knowledge.size and n_t + n_s > 0:
        target.knowledge = (target.knowledge * n_t + source.knowledge * n_s) / (n_t + n_s)
    target.technologies = target.technologies | source.technologies
    target.ever_cultivated = target.ever_cultivated or source.ever_cultivated
    if mode is MergeMode.AGGREGATION:
        target.groups += source.groups
    history = [
        _weighted(a, n_t, b, n_s)
        for a, b in zip(
            reversed(target.harvest_history), reversed(source.harvest_history), strict=False
        )
    ]
    target.harvest_history.clear()
    target.harvest_history.extend(reversed(history))
    target.females = target.females + source.females
    target.males = target.males + source.males
    n = target.population
    target.reserve_kcal_per_capita = total_reserve / n if n else 0.0
    target.beliefs = target.beliefs.merged_with(source.beliefs)
    for cell, value in source.familiarity.items():
        target.familiarity[cell] = max(value, target.familiarity.get(cell, 0.0))


def rewire_ties(units: MutableMapping[str, PopulationUnit], source_id: str, target_id: str) -> None:
    """Redirect every tie touching ``source_id`` to ``target_id``, combining duplicates."""
    source, target = units[source_id], units[target_id]
    for partner, tie in source.trade_ties.items():
        if partner != target_id:
            target.trade_ties[partner] = target.trade_ties.get(partner, 0.0) + tie
    target.trade_ties.pop(source_id, None)
    source.trade_ties = {}
    for unit in units.values():
        if unit is source or unit is target:
            continue
        if source_id in unit.trade_ties:
            tie = unit.trade_ties.pop(source_id)
            unit.trade_ties[target_id] = unit.trade_ties.get(target_id, 0.0) + tie


def absorb(
    units: MutableMapping[str, PopulationUnit], source_id: str, target_id: str, mode: MergeMode
) -> None:
    """Merge ``source_id`` into ``target_id``, rewire the network, and remove the source."""
    rewire_ties(units, source_id, target_id)
    merge_state(units[target_id], units[source_id], mode)
    del units[source_id]


def split_off(
    parent: PopulationUnit,
    leave_f: IntArray,
    leave_m: IntArray,
    daughter_id: str,
    year: int,
) -> PopulationUnit:
    """Detach the people in ``leave_f``/``leave_m`` from ``parent`` as a new unit.

    Extensive quantities (stores, fields, debts, this year's flows) are divided in
    proportion to people; per-capita and informational state is copied. The caller
    guarantees ``0 < departing < parent.population``.
    """
    before = parent.population
    moved = int(leave_f.sum() + leave_m.sum())
    if not 0 < moved < before:
        raise ValueError("a split must leave people on both sides")
    share = moved / before
    daughter = PopulationUnit(
        id=daughter_id,
        species_id=parent.species_id,
        cell=parent.cell,
        females=leave_f,
        males=leave_m,
        reserve_kcal_per_capita=parent.reserve_kcal_per_capita,
        founded_year=year,
        parent_id=parent.id,
        food_ratio=parent.food_ratio,
        energy_deficit=parent.energy_deficit,
        beliefs=parent.beliefs.copy(),  # maps are owned and patched in place
        familiarity=dict(parent.familiarity),
        knowledge=parent.knowledge.copy(),
        technologies=parent.technologies,
        ever_cultivated=parent.ever_cultivated,
        forage_marginal_kcal_per_hour=parent.forage_marginal_kcal_per_hour,
        forage_plant_share=parent.forage_plant_share,
        crop_yield_kcal_per_ha=parent.crop_yield_kcal_per_ha,
        residence_years=parent.residence_years,
    )
    daughter.harvest_history.extend(parent.harvest_history)
    for name in _SUMMED:
        portion = getattr(parent, name) * share
        setattr(daughter, name, portion)
        setattr(parent, name, getattr(parent, name) - portion)
    if parent.groups > 1:
        parent.groups -= 1
    parent.females = parent.females - leave_f
    parent.males = parent.males - leave_m
    if np.any(parent.females < 0) or np.any(parent.males < 0):
        raise ValueError("departing cohorts exceed the parent's")
    return daughter
