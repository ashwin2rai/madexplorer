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
same machine (the output records the numeric platform).
"""

import multiprocessing
import resource
import time
from collections.abc import Sequence
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import InitialPopulation
from madexplorer.core.provenance import numeric_platform, run_manifest
from madexplorer.core.simulation import Simulator
from madexplorer.population.initialization import found_unit

# Subsystems that build belief maps; the synthetic warm-up runs only these.
WARMUP_SUBSYSTEMS = frozenset({"perception", "knowledge_sharing"})


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # Linux: kB


def synthetic_simulator(
    scenario: Scenario, n_units: int, group_size: int = 30, farming: bool = False
) -> Simulator:
    """A simulator whose initial units are replaced by ``n_units`` groups on random land cells.

    Placement uses its own generator seeded by the run seed (not a model stream). With
    ``farming`` every group holds all technologies and enough knowledge to keep them, so
    cultivation code paths are exercised from the first tick.
    """
    sim = Simulator(scenario)
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
        sim.state.units[unit.id] = unit
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


def _known_cells(sim: Simulator) -> float:
    units = list(sim.state.units.values())
    if not units:
        return 0.0
    year = sim.state.year
    memory = {sid: p.cognition.memory_years for sid, p in sim.scenario.species.items()}
    return float(np.mean([u.beliefs.known_cells(year, memory[u.species_id]) for u in units]))


def synthetic_case(
    scenario: Scenario,
    n_units: int,
    ticks: int,
    warmup_years: int,
    group_size: int = 30,
    farming: bool = False,
) -> dict[str, Any]:
    """Time ``ticks`` full steps from a warmed-up synthetic state."""
    sim = synthetic_simulator(scenario, n_units, group_size, farming)
    started = time.perf_counter()
    warm_up_beliefs(sim, warmup_years)
    warmup_seconds = time.perf_counter() - started
    known_after_warmup = _known_cells(sim)
    sim.timings = {}
    unit_counts: list[int] = []
    tick_seconds: list[float] = []
    for _ in range(ticks):
        unit_counts.append(len(sim.state.units))
        started = time.perf_counter()
        sim.step()
        tick_seconds.append(time.perf_counter() - started)
    mean_units = float(np.mean(unit_counts))
    total = float(np.sum(tick_seconds))
    return {
        "n_units": n_units,
        "farming": farming,
        "ticks": ticks,
        "warmup_years": warmup_years,
        "warmup_seconds": round(warmup_seconds, 3),
        "mean_units": round(mean_units, 1),
        "final_units": len(sim.state.units),
        "final_population": sim.state.total_population(),
        "known_cells_after_warmup": round(known_after_warmup, 1),
        "known_cells_final": round(_known_cells(sim), 1),
        "ms_per_tick": round(1000.0 * total / ticks, 2),
        "ms_per_tick_median": round(1000.0 * float(np.median(tick_seconds)), 2),
        "ms_per_unit_tick": round(1000.0 * total / ticks / max(mean_units, 1.0), 4),
        "subsystem_ms_per_tick": {
            k: round(1000.0 * v / ticks, 2)
            for k, v in sorted(sim.timings.items(), key=lambda kv: -kv[1])
        },
        "peak_rss_mb": round(_peak_rss_mb(), 1),
    }


def timed_case(scenario: Scenario) -> dict[str, Any]:
    """Run ``scenario`` once with a per-subsystem time breakdown."""
    sim = Simulator(scenario)
    sim.timings = {}
    started = time.perf_counter()
    result = sim.run()
    total = time.perf_counter() - started
    unit_years = sum(int(r["units"]) for r in result.metrics)
    return {
        "seed": scenario.config.simulation.seed,
        "years": len(result.metrics),
        "runtime_seconds": round(total, 2),
        "final_population": int(result.metrics[-1]["population"]),
        "final_units": int(result.metrics[-1]["units"]),
        "unit_years": unit_years,
        "ms_per_unit_year": round(1000.0 * total / max(unit_years, 1), 4),
        "subsystem_seconds": {
            k: round(v, 2) for k, v in sorted(sim.timings.items(), key=lambda kv: -kv[1])
        },
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
