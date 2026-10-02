"""How population-unit state combines and divides (spec §6.4, §6.5, §38).

Every field of :class:`PopulationUnit` has one declared rule for merging two units
(fusion of social groups, or computational aggregation) and one for splitting a
unit (fission, and later selective migration), declared with the field in
:mod:`madexplorer.population.fields` (``FIELD_RULES``), so that new state added in
MVP 3 must declare its semantics before it can be merged or split. Extensive and
intensive fields share one rule each; this module implements those and every
field-specific rule on unit objects. :mod:`madexplorer.population.lifecycle`
applies the same rules to table rows (an independent implementation, compared by
differential tests).

Merging also rewires the social network: third-party trade ties that pointed at
the absorbed unit are redirected to the surviving unit, duplicate edges combine
additively (tie strength is accumulated exchange), and the edge between the two
merging units disappears rather than becoming a self-edge.
"""

import math
from collections.abc import Callable, MutableMapping
from enum import Enum

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.familiarity import FamiliarityRule
from madexplorer.population.fields import EXTENSIVE_FIELDS, INTENSIVE_FIELDS
from madexplorer.population.strata import (
    CLAIMS,
    UNASSIGNED,
    Coalescence,
    Compaction,
    fuse_strata,
    normalize_strata,
)
from madexplorer.population.unit import PopulationUnit


class MergeMode(Enum):
    """Why two units merge, which decides how their social-group count combines."""

    FUSION = "fusion"  # one group joins another's social structure
    AGGREGATION = "aggregation"  # computational coarsening; both groups persist inside the unit


def _unassigned_stratum_ids(n: int) -> IntArray:
    """Ids for components created outside a store: assigned when the unit is bound."""
    return np.full(n, UNASSIGNED, dtype=np.int64)


def _weighted(a: float, n_a: int, b: float, n_b: int) -> float:
    total = n_a + n_b
    return (a * n_a + b * n_b) / total if total else a


def merge_state(
    target: PopulationUnit,
    source: PopulationUnit,
    mode: MergeMode,
    merge_year: int,
    familiarity: FamiliarityRule,
    new_stratum_ids: Callable[[int], IntArray] | None = None,
) -> list[Compaction | Coalescence]:
    """Fold ``source``'s state into ``target`` (network rewiring is :func:`absorb`'s job).

    Familiarity is combined as both units' effective values at ``merge_year``. Strata are
    inherited (:func:`~madexplorer.population.strata.fuse_strata`) from the predecessors'
    populations and stocks before they combine and normalized
    (:func:`~madexplorer.population.strata.normalize_strata`); ``new_stratum_ids`` gives ids
    to components created by normalization, whose records are returned (registered units
    need the store's allocator; without one, new components are unassigned until binding).
    """
    if target.species_id != source.species_id or target.cell != source.cell:
        raise ValueError("only co-located units of one species can merge")
    strata, records = normalize_strata(
        fuse_strata(
            [
                (unit.strata, unit.population, [getattr(unit, stock) for stock in CLAIMS.values()])
                for unit in (target, source)
            ]
        ),
        new_stratum_ids or _unassigned_stratum_ids,
    )
    n_t, n_s = target.population, source.population
    total_reserve = target.total_reserve_kcal + source.total_reserve_kcal
    for name in INTENSIVE_FIELDS:
        setattr(target, name, _weighted(getattr(target, name), n_t, getattr(source, name), n_s))
    for name in EXTENSIVE_FIELDS:
        setattr(target, name, getattr(target, name) + getattr(source, name))
    if math.isnan(target.move_hazard) or math.isnan(source.move_hazard):
        known = [h for h in (target.move_hazard, source.move_hazard) if not math.isnan(h)]
        target.move_hazard = known[0] if known else math.nan
    else:
        target.move_hazard = _weighted(target.move_hazard, n_t, source.move_hazard, n_s)
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
    target.report_cells = np.union1d(target.report_cells, source.report_cells)
    # MVP 2.1 (B1): the residence loop once named its variable `year`, shadowing the merge
    # year, so familiarity decayed to the source's last residence year (preserved in the
    # frozen MVP 2 reference). Familiarity is now decayed to the merge year.
    for cell, residence_year in source.recent_residence.items():
        target.recent_residence[cell] = max(
            residence_year, target.recent_residence.get(cell, residence_year)
        )
    target.familiarity.merge(source.familiarity, n_t, n_s, merge_year, familiarity)
    target.strata = strata
    return records


def rewire_ties(units: MutableMapping[str, PopulationUnit], source_id: str, target_id: str) -> None:
    """Redirect every tie touching ``source_id`` to ``target_id``, combining duplicates."""
    source, target = units[source_id], units[target_id]
    for partner, tie in source.trade_ties.items():
        if partner != target_id:
            target.trade_ties[partner] = target.trade_ties.get(partner, 0.0) + tie
    target.trade_ties.pop(source_id, None)
    # Ties are symmetric among live units (trade adds both directions, decay and pruning
    # treat both alike, rewiring preserves it), so the units holding a tie to the source
    # are its own live partners: O(degree) rather than a scan of every unit. Each holder's
    # dictionary is updated independently, so the visiting order does not matter.
    holders = [
        units[p]
        for p in source.trade_ties
        if p != target_id and p in units and source_id in units[p].trade_ties
    ]
    source.trade_ties = {}
    for unit in holders:
        tie = unit.trade_ties.pop(source_id)
        unit.trade_ties[target_id] = unit.trade_ties.get(target_id, 0.0) + tie


def absorb(
    units: MutableMapping[str, PopulationUnit],
    source_id: str,
    target_id: str,
    mode: MergeMode,
    year: int,
    familiarity: FamiliarityRule,
    new_stratum_ids: Callable[[int], IntArray] | None = None,
) -> list[Compaction | Coalescence]:
    """Merge ``source_id`` into ``target_id``, rewire the network, and remove the source."""
    rewire_ties(units, source_id, target_id)
    records = merge_state(
        units[target_id], units[source_id], mode, year, familiarity, new_stratum_ids
    )
    del units[source_id]
    return records


def split_off(
    parent: PopulationUnit,
    leave_f: IntArray,
    leave_m: IntArray,
    daughter_id: str,
    year: int,
    familiarity: FamiliarityRule,
) -> PopulationUnit:
    """Detach the people in ``leave_f``/``leave_m`` from ``parent`` as a new unit.

    Extensive quantities (stores, fields, debts, this year's flows) are divided in
    proportion to people; intensive, per-capita and informational state is copied. The
    caller guarantees ``0 < departing < parent.population``.
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
        beliefs=parent.beliefs.copy(),  # maps are owned and patched in place
        report_cells=parent.report_cells.copy(),
        recent_residence=dict(parent.recent_residence),
        familiarity=parent.familiarity.materialized(year, familiarity),
        knowledge=parent.knowledge.copy(),
        technologies=parent.technologies,
        ever_cultivated=parent.ever_cultivated,
        crop_yield_kcal_per_ha=parent.crop_yield_kcal_per_ha,
        residence_years=parent.residence_years,
        move_hazard=parent.move_hazard,
        strata=parent.strata.unassigned_copy(),  # new components; ids assigned on insertion
    )
    daughter.harvest_history.extend(parent.harvest_history)
    for name in INTENSIVE_FIELDS:
        setattr(daughter, name, getattr(parent, name))
    for name in EXTENSIVE_FIELDS:
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
