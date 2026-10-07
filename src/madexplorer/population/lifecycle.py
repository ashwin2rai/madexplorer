"""Unit lifecycle on the authoritative rows: create, remove, split, merge (PH3b).

The model rules for combining and dividing unit state are declared in
:mod:`madexplorer.population.fields` (``FIELD_RULES``; the extensive and intensive field
groups) and implemented on objects by :mod:`madexplorer.population.composition`
(:func:`merge_state`, :func:`split_off`); this module adds no semantics. With a unit
table (production), the same rules are applied directly to unit-table rows and
belief-store rows: a daughter's row is copied from its parent's and then divided, a merge
folds the source row into the target row, and a unit that leaves the simulation frees its
rows without its state being copied back onto the object. Only the irregular external
state (familiarity, residence, report cells, harvest history, trade ties) is handled on
objects, by the same code paths.

Without a table (the object-authoritative reference engine) every function delegates to
the composition functions, so whole-engine differential tests compare the two paths.
Floating-point operations are the reference's, in the same order, on the same operands
(Python floats read from the rows), so results are bit-identical.
"""

from collections import deque

import numpy as np

from madexplorer.core.types import IntArray
from madexplorer.population.composition import (
    MergeMode,
    _weighted,
    absorb,
    merge_harvest_history,
    merge_residence,
    merged_hazard,
    rewire_ties,
    split_off,
)
from madexplorer.population.familiarity import FamiliarityRule
from madexplorer.population.fields import EXTENSIVE_FIELDS, INTENSIVE_FIELDS
from madexplorer.population.store import PopulationStore
from madexplorer.population.strata import (
    CLAIMS,
    Coalescence,
    Compaction,
    fuse_strata,
    log_normalization,
    normalize_strata,
)
from madexplorer.population.unit import (
    HARVEST_MEMORY_YEARS,
    PopulationUnit,
    belief_slot,
    bound_unit,
)


def create_unit(population: PopulationStore, unit: PopulationUnit) -> None:
    """Insert a detached unit (founding, synthetic states); it gets a slot at the end of
    the processing order."""
    population.units[unit.id] = unit


def remove_unit(population: PopulationStore, unit_id: str) -> PopulationUnit:
    """Remove a unit that leaves the simulation (extinction).

    With a table its rows are freed without copying state back: read what is needed (an
    event's fields) before removing it.
    """
    if population.table is not None:
        return population.units.discard(unit_id)
    return population.units.pop(unit_id)


def split_unit(
    population: PopulationStore,
    parent_id: str,
    leave_f: IntArray,
    leave_m: IntArray,
    daughter_id: str,
    year: int,
    familiarity: FamiliarityRule,
) -> PopulationUnit:
    """Split the people in ``leave_f``/``leave_m`` off ``parent_id`` as a new unit, inserted
    at the end of the processing order (:func:`~madexplorer.population.composition.split_off`)."""
    units, table, store = population.units, population.table, population.beliefs
    parent = units[parent_id]
    if table is None:
        daughter = split_off(parent, leave_f, leave_m, daughter_id, year, familiarity)
        units[daughter.id] = daughter
        _log_fission(population, year, parent, daughter)
        return daughter
    p = belief_slot(parent)
    before = int(table.population[p])
    moved = int(leave_f.sum() + leave_m.sum())
    if not 0 < moved < before:
        raise ValueError("a split must leave people on both sides")
    n = int(table.n_ages[p])
    remain_f = table.females[p, :n] - leave_f
    remain_m = table.males[p, :n] - leave_m
    if (remain_f < 0).any() or (remain_m < 0).any():
        raise ValueError("departing cohorts exceed the parent's")
    share = moved / before
    d = population.claim_slot(int(table.species_code[p]))  # may grow the table
    table.copy_row(p, d)
    store.copy_row(p, d)
    strata = population.strata
    assert strata is not None
    strata.copy_row(p, d, population.new_stratum_ids(int(strata.n_strata[p])))
    columns = table.columns
    columns["founded_year"][d] = year
    groups = columns["groups"]
    groups[d] = 1
    for name in EXTENSIVE_FIELDS:
        column = columns[name]
        value = float(column[p])
        portion = value * share
        column[d] = portion
        column[p] = value - portion
    if groups[p] > 1:
        groups[p] -= 1
    table.set_cohorts(d, leave_f, leave_m)
    table.set_cohorts(p, remain_f, remain_m)
    daughter = bound_unit(
        d,
        store,
        table,
        strata,
        id=daughter_id,
        species_id=parent.species_id,
        parent_id=parent.id,
        report_cells=parent.report_cells.copy(),
        recent_residence=dict(parent.recent_residence),
        familiarity=parent.familiarity.materialized(year, familiarity),
        harvest_history=deque(parent.harvest_history, maxlen=HARVEST_MEMORY_YEARS),
        trade_ties={},
    )
    units[daughter_id] = daughter
    _log_fission(population, year, parent, daughter)
    return daughter


def _log_fission(
    population: PopulationStore, year: int, parent: PopulationUnit, daughter: PopulationUnit
) -> None:
    """Sidecar event: the daughter's strata are copies of the parent's as new components."""
    if population.strata_log is not None:
        population.strata_log.append(
            {
                "year": year,
                "event": "fission_copy",
                "unit_id": parent.id,
                "daughter_id": daughter.id,
                "parent_stratum_ids": parent.strata.stratum_id.tolist(),
                "daughter_stratum_ids": daughter.strata.stratum_id.tolist(),
            }
        )


def merge_units(
    population: PopulationStore,
    source_id: str,
    target_id: str,
    mode: MergeMode,
    year: int,
    familiarity: FamiliarityRule,
) -> None:
    """Merge ``source_id`` into ``target_id``, rewire the trade network and remove the source
    (:func:`~madexplorer.population.composition.absorb`); strata are inherited
    (:func:`~madexplorer.population.strata.fuse_strata`) and kept within capacity."""
    units, table, store = population.units, population.table, population.beliefs
    inherited = [units[uid].strata.stratum_id.tolist() for uid in (target_id, source_id)]
    if table is None:
        records = absorb(
            units,
            source_id,
            target_id,
            mode,
            year,
            familiarity,
            population.new_stratum_ids,
            population.max_strata,
        )
        _log_fusion(population, year, target_id, source_id, mode, inherited, records)
        return
    target, source = units[target_id], units[source_id]
    if target.species_id != source.species_id or target.cell != source.cell:
        raise ValueError("only co-located units of one species can merge")
    t, s = belief_slot(target), belief_slot(source)
    strata = population.strata
    assert strata is not None
    counts, columns = table.population, table.columns
    n_t, n_s = int(counts[t]), int(counts[s])
    fused, records = normalize_strata(
        fuse_strata(  # predecessor populations and stocks, before anything combines
            [
                (strata.unload(r), n, [float(columns[stock][r]) for stock in CLAIMS.values()])
                for r, n in ((t, n_t), (s, n_s))
            ]
        ),
        population.new_stratum_ids,
        population.max_strata,
    )
    rewire_ties(units, source_id, target_id)
    reserve = columns["reserve_kcal_per_capita"]
    total_reserve = float(reserve[t]) * n_t + float(reserve[s]) * n_s
    for name in INTENSIVE_FIELDS:
        column = columns[name]
        column[t] = _weighted(float(column[t]), n_t, float(column[s]), n_s)
    for name in EXTENSIVE_FIELDS:
        column = columns[name]
        column[t] = float(column[t]) + float(column[s])
    hazards = columns["move_hazard"]
    hazards[t] = merged_hazard(float(hazards[t]), n_t, float(hazards[s]), n_s)
    knowledge = table.knowledge
    if knowledge.shape[1] and n_t + n_s > 0:
        knowledge[t] = (knowledge[t] * n_t + knowledge[s] * n_s) / (n_t + n_s)
    table.set_technologies(t, table.technologies[t] | table.technologies[s])
    cultivated = columns["ever_cultivated"]
    cultivated[t] = bool(cultivated[t]) or bool(cultivated[s])
    if mode is MergeMode.AGGREGATION:
        columns["groups"][t] += columns["groups"][s]
    merge_harvest_history(target, source, n_t, n_s)
    n = int(table.n_ages[t])
    table.set_cohorts(
        t,
        table.females[t, :n] + table.females[s, :n],
        table.males[t, :n] + table.males[s, :n],
    )
    merged = int(counts[t])
    reserve[t] = total_reserve / merged if merged else 0.0
    store.merge_row(s, t)
    target.report_cells = np.union1d(target.report_cells, source.report_cells)
    merge_residence(target, source)
    # Effective familiarity of both units at the merge year (MVP 2.1, B1 fixed).
    target.familiarity.merge(source.familiarity, n_t, n_s, year, familiarity)
    strata.load(t, fused)
    units.discard(source_id)
    _log_fusion(population, year, target_id, source_id, mode, inherited, records)


def _log_fusion(
    population: PopulationStore,
    year: int,
    target_id: str,
    source_id: str,
    mode: MergeMode,
    inherited: list[list[int]],
    records: list[Compaction | Coalescence],
) -> None:
    """Sidecar strata events of a fusion (observation only; nothing reads them)."""
    log = population.strata_log
    if log is None:
        return
    log.append(
        {
            "year": year,
            "event": "fusion_inheritance",
            "unit_id": target_id,
            "absorbed_unit_id": source_id,
            "mode": mode.value,
            "target_stratum_ids": inherited[0],
            "absorbed_stratum_ids": inherited[1],
            "result_stratum_ids": population.units[target_id].strata.stratum_id.tolist(),
        }
    )
    log_normalization(log, year, target_id, records)
