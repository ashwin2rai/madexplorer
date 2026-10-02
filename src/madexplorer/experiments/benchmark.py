"""Performance benchmarks: controlled unit counts and timed reference runs (spec §29.5).

Two kinds of measurement:

- :func:`synthetic_benchmark` starts a scenario's world directly with ``n_units``
  forager (or farming) groups spread over land, lets perception and belief sharing
  run alone for a warm-up so belief maps reach a late-run state, then times a few
  full ticks. This isolates per-unit cost from the long colonization phase and is
  the performance regression benchmark.
- :func:`timed_run` times one ordinary run of a scenario with a per-subsystem
  breakdown (e.g. the slow 1,000-year MVP 2 seed used as the speed-up reference).

Each case runs in a fresh ``spawn``-ed process so peak RSS belongs to that case only.
Timings are machine-specific: compare results only against a reference recorded on the
same machine (the output records the numeric platform). Wall time on a shared machine is
sensitive to other load, so reports also give process CPU time, which is the better basis
for comparisons.
"""

import cProfile
import multiprocessing
import pstats
import resource
import time
import tracemalloc
from collections.abc import Sequence
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import InitialPopulation
from madexplorer.core.provenance import numeric_platform, run_manifest
from madexplorer.core.simulation import Simulator
from madexplorer.core.static import StaticContext
from madexplorer.population.beliefs import BYTES_PER_CELL, SparseBeliefStore
from madexplorer.population.initialization import found_unit
from madexplorer.population.lifecycle import create_unit
from madexplorer.population.unit import belief_slot

# Subsystems that build belief maps; the synthetic warm-up runs only these.
WARMUP_SUBSYSTEMS = frozenset({"perception", "knowledge_sharing"})


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # Linux: kB


def synthetic_simulator(
    scenario: Scenario,
    n_units: int,
    group_size: int = 30,
    farming: bool = False,
    unit_table: bool = True,
    belief_backend: str | None = None,
) -> Simulator:
    """A simulator whose initial units are replaced by ``n_units`` groups on random land cells.

    Placement uses its own generator seeded by the run seed (not a model stream). With
    ``farming`` every group holds all technologies and enough knowledge to keep them, so
    cultivation code paths are exercised from the first tick.
    """
    static = StaticContext.build(scenario)
    world = static.world
    if any(world.is_water[world.cell_id(*p.cell)] for p in scenario.config.initial_populations):
        # The founders are discarded below; only move them onto land when a resized world
        # would otherwise reject them (the canonical 40 x 40 world keeps its own founders).
        land_cell = world.coords(int(np.flatnonzero(~world.is_water)[0]))
        founders = [
            {**p.model_dump(), "cell": list(land_cell)} for p in scenario.config.initial_populations
        ]
        scenario = scenario.with_settings({"initial_populations": founders})
    sim = Simulator(scenario, static=static, unit_table=unit_table, belief_backend=belief_backend)
    sim.state.units.clear()
    placement = np.random.default_rng([scenario.config.simulation.seed, n_units])
    land = np.flatnonzero(~sim.world.is_water)
    cells = np.sort(placement.choice(land, size=n_units))
    technologies: tuple[str, ...] = ()
    knowledge_levels: dict[str, float] = {}
    if farming and scenario.knowledge is not None:
        technologies = tuple(t.id for t in scenario.knowledge.technologies)
        for tech in scenario.knowledge.technologies:
            for domain, level in tech.min_knowledge.items():
                knowledge_levels[domain] = max(knowledge_levels.get(domain, 0.0), 1.25 * level)
    species_id, profile = next(iter(scenario.species.items()))  # one species per benchmark
    for cell in cells.tolist():
        seed = InitialPopulation(
            species=species_id,
            cell=sim.world.coords(cell),
            population=group_size,
            initial_knowledge=knowledge_levels,
            technologies=technologies,
        )
        unit = found_unit(
            sim.ids.next("u"),
            seed,
            cell,
            profile,
            sim.tables[species_id],
            sim.state.year,
            placement,
            sim.knowledge,
        )
        create_unit(sim.state.population, unit)
    return sim


def warm_up_beliefs(sim: Simulator, years: int) -> None:
    """Run only perception and belief sharing for ``years`` so belief maps fill up."""
    subsystems = [s for s in sim.pipeline if s.name in WARMUP_SUBSYSTEMS]
    for _ in range(years):
        sim.state.year += 1
        ctx = sim.context()
        for subsystem in subsystems:
            for proposal in subsystem.evaluate(sim.state, ctx):
                proposal.apply(sim.state, ctx)


COMPILED_SUBSYSTEMS = ("foraging", "field_planning")  # evaluates that call JIT kernels


def warm_kernels(sim: Simulator) -> float:
    """Compile (or load from the cache) the JIT kernels before timing; returns seconds.

    Runs the evaluates that call compiled kernels on a throwaway context and discards
    their proposals: they draw no random numbers and change no state, so the simulation
    is unaffected. Timed runs (``timed_case``) do not warm: their cost includes it.
    """
    started = time.perf_counter()
    ctx = sim.context()
    for subsystem in sim.pipeline:
        if subsystem.name in COMPILED_SUBSYSTEMS:
            subsystem.evaluate(sim.state, ctx)
    return time.perf_counter() - started


def prewarm_kernels(scenario: Scenario) -> float:
    """Compile (or load from the on-disk cache) every JIT kernel once; returns seconds.

    Runs two years of a copy of ``scenario`` (the kernels then compile for exactly the
    argument types production uses) and exercises the rare sparse-store row operations.
    Called before ensemble workers start, so they load cached code instead of each
    compiling the same kernels; results are unaffected (a separate simulator).
    """
    started = time.perf_counter()
    sim = Simulator(scenario.with_overrides(n_years=2), record_events=False)
    for _ in range(2):
        sim.step()
    store = sim.state.belief_store
    if isinstance(store, SparseBeliefStore) and sim.state.units:
        spare = store.capacity + 2  # unused slots: no simulation state is touched
        store.claim(spare)
        store.claim(spare + 1)
        source = belief_slot(next(iter(sim.state.units.values())))
        store.copy_row(source, spare)
        store.merge_row(spare, spare + 1)
        store.compact()
    return time.perf_counter() - started


def _known_cells(sim: Simulator) -> float:
    units = list(sim.state.units.values())
    if not units:
        return 0.0
    year = sim.state.year
    memory = {sid: p.cognition.memory_years for sid, p in sim.scenario.species.items()}
    store = sim.state.belief_store
    known = [
        int((store.entries(belief_slot(u))[1] > year - memory[u.species_id]).sum()) for u in units
    ]
    return float(np.mean(known))


def state_storage(sim: Simulator) -> dict[str, Any]:
    """Sizes of the per-unit state that grows with units and cells (a memory report).

    Beliefs are dense per-unit arrays over all cells; familiarity, residence and trade ties
    are per-unit dictionaries (entries counted, not bytes).
    """
    units = list(sim.state.units.values())
    store = sim.state.belief_store
    n = max(len(units), 1)
    current = _known_cells(sim) * len(units)  # current (within memory) entries in total
    if isinstance(store, SparseBeliefStore):
        belief_bytes = store.nbytes  # pools and slot index, allocated
        sparse = {
            "belief_pool_entries": store.pool_size,
            "belief_pool_used": store.used,
            "belief_pool_garbage": store.garbage,
            "belief_compactions": store.compactions,
            "belief_capacity_per_stored": round(store.pool_size / max(store.stored_entries, 1), 2),
        }
    else:
        belief_bytes = store.active * store.n_cells * BYTES_PER_CELL  # rows in use
        sparse = {}
    return {
        "units": len(units),
        "cells": sim.world.n_cells,
        "belief_backend": store.kind,
        "belief_mb": round(belief_bytes / 2**20, 2),
        "belief_bytes_per_unit": round(belief_bytes / n, 1),
        "belief_bytes_per_current_entry": round(belief_bytes / max(current, 1), 1),
        "belief_current_entries_per_unit": round(current / n, 1),
        "belief_stored_entries_per_unit": round(store.stored_entries / n, 1),
        **sparse,
        "belief_store_mb": round(store.nbytes / 2**20, 2),
        "belief_store_rows": store.capacity,
        "belief_store_active_rows": store.active,
        "belief_store_resizes": store.resizes,
        "belief_store_peak_resize_mb": round(store.peak_resize_bytes / 2**20, 2),
        "familiarity_entries": sum(len(u.familiarity) for u in units),
        "familiarity_entries_per_unit": round(sum(len(u.familiarity) for u in units) / n, 1),
        "residence_entries_per_unit": round(sum(len(u.recent_residence) for u in units) / n, 1),
        "trade_edges": sum(len(u.trade_ties) for u in units),
        "report_cells_per_unit": round(sum(u.report_cells.size for u in units) / n, 1),
    }


def social_contacts(sim: Simulator) -> int:
    """Candidate encounter pairs among co-located and adjacent same-species groups.

    The pairwise contact set that belief sharing draws encounters from (diffusion's local
    contacts are the same pairs, plus trade ties); it grows with local density.
    """
    from madexplorer.mobility.exploration import candidate_encounters

    units = list(sim.state.units.values())
    receiver, _ = candidate_encounters(units, sim.static.neighborhood_table(1))
    return int(receiver.size)


def transient_python_memory_mb(sim: Simulator, ticks: int) -> float:
    """Mean peak of Python-traced memory allocated and released within a tick (MB).

    An allocation-pressure proxy (tracemalloc, a separate untimed pass): temporary tuples,
    dicts, dataclasses and numpy buffers raise it; state that persists does not.
    """
    tracemalloc.start()
    peaks = []
    try:
        for _ in range(ticks):
            current, _ = tracemalloc.get_traced_memory()
            tracemalloc.reset_peak()
            sim.step()
            _, peak = tracemalloc.get_traced_memory()
            peaks.append(peak - current)
    finally:
        tracemalloc.stop()
    return float(np.mean(peaks)) / 2**20


def python_calls_per_tick(sim: Simulator, ticks: int) -> float:
    """Python function calls per tick, counted under cProfile (a separate, untimed pass).

    CPython has no cheap allocation counter; the number of Python-level calls is the
    overhead proxy the performance work tracks (object traversal, small numpy calls,
    proposal construction). The pass advances the simulation like ordinary ticks.
    """
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(ticks):
        sim.step()
    profile.disable()
    stats = pstats.Stats(profile)
    return float(stats.total_calls) / ticks  # type: ignore[attr-defined]


def synthetic_case(
    scenario: Scenario,
    n_units: int,
    ticks: int,
    warmup_years: int,
    group_size: int = 30,
    farming: bool = False,
    count_calls: bool = True,
) -> dict[str, Any]:
    """Time ``ticks`` full steps from a warmed-up synthetic state.

    With ``count_calls``, two further untimed ticks count Python calls per tick.
    """
    sim = synthetic_simulator(scenario, n_units, group_size, farming)
    started = time.perf_counter()
    warm_up_beliefs(sim, warmup_years)
    warmup_seconds = time.perf_counter() - started
    known_after_warmup = _known_cells(sim)
    jit_seconds = warm_kernels(sim)
    sim.timings = {}
    unit_counts: list[int] = []
    tick_seconds: list[float] = []
    cpu_started = time.process_time()
    for _ in range(ticks):
        unit_counts.append(len(sim.state.units))
        started = time.perf_counter()
        sim.step()
        tick_seconds.append(time.perf_counter() - started)
    cpu_total = time.process_time() - cpu_started
    mean_units = float(np.mean(unit_counts))
    total = float(np.sum(tick_seconds))
    timings = dict(sim.timings)
    sim.timings = None  # the untimed passes below must not add to the breakdown
    storage = state_storage(sim)
    storage["social_contacts"] = social_contacts(sim)
    rss = _peak_rss_mb()
    calls = python_calls_per_tick(sim, 2) if count_calls else float("nan")
    transient = transient_python_memory_mb(sim, 2) if count_calls else float("nan")
    return {
        "n_units": n_units,
        "farming": farming,
        "ticks": ticks,
        "warmup_years": warmup_years,
        "warmup_seconds": round(warmup_seconds, 3),
        "jit_warm_seconds": round(jit_seconds, 3),
        "mean_units": round(mean_units, 1),
        "final_units": len(sim.state.units),
        "final_population": sim.state.total_population(),
        "known_cells_after_warmup": round(known_after_warmup, 1),
        "known_cells_final": round(_known_cells(sim), 1),
        "ms_per_tick": round(1000.0 * total / ticks, 2),
        "ms_per_tick_median": round(1000.0 * float(np.median(tick_seconds)), 2),
        "cpu_ms_per_tick": round(1000.0 * cpu_total / ticks, 2),
        "ms_per_unit_tick": round(1000.0 * total / ticks / max(mean_units, 1.0), 4),
        "subsystem_ms_per_tick": {
            k: round(1000.0 * v / ticks, 2)
            for k, v in sorted(timings.items(), key=lambda kv: -kv[1])
        },
        "peak_rss_mb": round(rss, 1),
        "cells": sim.world.n_cells,
        "us_per_unit_tick_cpu": round(1e6 * cpu_total / ticks / max(mean_units, 1.0), 1),
        "storage": storage,
        "python_calls_per_tick": round(calls),
        "python_calls_per_unit_tick": round(calls / max(storage["units"], 1), 1),
        "transient_python_mb_per_tick": round(transient, 2),
        "us_per_contact_tick_cpu": round(
            1e6 * cpu_total / ticks / max(storage["social_contacts"], 1), 2
        ),
    }


def timed_case(scenario: Scenario) -> dict[str, Any]:
    """Run ``scenario`` once with a per-subsystem time breakdown."""
    sim = Simulator(scenario)
    sim.timings = {}
    tick_ends: list[float] = []
    started, cpu_started = time.perf_counter(), time.process_time()
    result = sim.run(progress=lambda _row: tick_ends.append(time.perf_counter()))
    total = time.perf_counter() - started
    cpu_total = time.process_time() - cpu_started
    ticks = np.diff(np.array([started, *tick_ends]))
    units = np.array([int(r["units"]) for r in result.metrics])
    windows = {}
    n = ticks.size
    for label, (lo, hi) in {
        "early": (0.10, 0.15),
        "middle": (0.45, 0.50),
        "late": (0.95, 1.00),
    }.items():
        rows = slice(int(lo * n), max(int(hi * n), int(lo * n) + 1))
        ms = 1000.0 * float(ticks[rows].mean())
        mean_units = float(units[rows].mean())
        windows[label] = {
            "years": [
                int(result.metrics[rows.start]["year"]),
                int(result.metrics[rows.stop - 1]["year"]),
            ],
            "ms_per_tick": round(ms, 2),
            "mean_units": round(mean_units, 1),
            "ms_per_unit_tick": round(ms / max(mean_units, 1.0), 4),
        }
    subsystem_total = sum(sim.timings.values())
    unit_years = sum(int(r["units"]) for r in result.metrics)
    return {
        "seed": scenario.config.simulation.seed,
        "years": len(result.metrics),
        "runtime_seconds": round(total, 2),
        "cpu_seconds": round(cpu_total, 2),
        "final_population": int(result.metrics[-1]["population"]),
        "final_units": int(result.metrics[-1]["units"]),
        "unit_years": unit_years,
        "ms_per_unit_year": round(1000.0 * total / max(unit_years, 1), 4),
        "subsystem_seconds": {
            k: round(v, 2) for k, v in sorted(sim.timings.items(), key=lambda kv: -kv[1])
        },
        "subsystem_share": {
            k: round(v / subsystem_total, 4)
            for k, v in sorted(sim.timings.items(), key=lambda kv: -kv[1])
        },
        "windows": windows,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


def _in_fresh_process(function: Any, *args: Any) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    with context.Pool(processes=1, maxtasksperchild=1) as pool:
        result: dict[str, Any] = pool.apply(function, args)
    return result


def _header(scenario: Scenario, **extra: Any) -> dict[str, Any]:
    manifest = run_manifest(scenario)
    keep = ("scenario_name", "world_seed", "config_hash", "git_commit", "git_dirty")
    return {
        **{k: manifest[k] for k in keep},
        "source_tree_sha256": manifest["source_tree_sha256"],
        "numeric_platform": numeric_platform(),
        "cpu_count": multiprocessing.cpu_count(),
        "timestamp_utc": manifest["timestamp_utc"],
        **extra,
    }


def synthetic_benchmark(
    scenario: Scenario,
    unit_counts: Sequence[int] = (100, 500, 1000, 2000),
    ticks: int = 30,
    warmup_years: int = 20,
    farming: bool = False,
) -> dict[str, Any]:
    """Synthetic cases for each unit count, each in a fresh process."""
    cases = [
        _in_fresh_process(synthetic_case, scenario, n, ticks, warmup_years, 30, farming)
        for n in unit_counts
    ]
    return {**_header(scenario, kind="synthetic"), "cases": cases}


def timed_runs(scenario: Scenario, seeds: Sequence[int], n_years: int | None) -> dict[str, Any]:
    """Timed ordinary runs, one fresh process per seed."""
    runs = [
        _in_fresh_process(timed_case, scenario.with_overrides(seed=s, n_years=n_years))
        for s in seeds
    ]
    return {**_header(scenario, kind="timed_runs"), "runs": runs}
