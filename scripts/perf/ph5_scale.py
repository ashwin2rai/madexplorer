"""PH5 scaling campaign: one size per process (instrumentation only; no engine changes).

usage: scale.py <units> <width> <timed_ticks> <out.json> [--calls] [--tracemalloc]
"""

import cProfile
import gc
import json
import os
import pstats
import resource
import sys
import time
import tracemalloc
from collections import deque

import numpy as np

sys.path.insert(0, ".")
from madexplorer.config.loader import Scenario
from madexplorer.core.spatial import SpatialIndex
from madexplorer.experiments.benchmark import (
    synthetic_simulator,
    warm_kernels,
    warm_up_beliefs,
)
from madexplorer.knowledge.diffusion import merge_trade_contacts

n, w, timed = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
out = sys.argv[4]
CALLS, TRACE = "--calls" in sys.argv, "--tracemalloc" in sys.argv


def rss_mb() -> float:
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return float("nan")


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


report: dict = {
    "units_requested": n,
    "width": w,
    "belief_backend": os.environ.get("MADEXPLORER_BELIEFS"),
    "rss_after_import_mb": round(rss_mb(), 1),
}
t0 = time.perf_counter()
sc = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml").with_settings(
    {"world.topology.width": w, "world.topology.height": w}
)
sim = synthetic_simulator(sc, n)
report["build_s"] = round(time.perf_counter() - t0, 1)
t0 = time.perf_counter()
warm_up_beliefs(sim, 20)
report["belief_warmup_s"] = round(time.perf_counter() - t0, 1)
report["jit_load_s"] = round(warm_kernels(sim), 3)
report["jit_cache"] = "warm (madexplorer jit-warmup run before the campaign)"
for _ in range(2):  # untimed ordinary ticks: caches, reachability, row growth settle
    sim.step()
report["rss_before_timed_mb"] = round(rss_mb(), 1)

# ----------------------------------------------------------------- timed ticks
sim.timings = {}
cpu, wall, counts = [], [], []
for _ in range(timed):
    counts.append(len(sim.state.units))
    c, t = time.process_time(), time.perf_counter()
    sim.step()
    cpu.append(time.process_time() - c)
    wall.append(time.perf_counter() - t)
timings = dict(sim.timings)
sim.timings = None
units = float(np.mean(counts))
report.update(
    units=round(units, 1),
    cells=sim.world.n_cells,
    land_cells=int((~sim.world.is_water).sum()),
    timed_ticks=timed,
    cpu_ms_per_tick=round(1000 * float(np.mean(cpu)), 1),
    cpu_ms_per_tick_each=[round(1000 * x, 1) for x in cpu],
    wall_ms_per_tick=round(1000 * float(np.mean(wall)), 1),
    us_per_unit_tick_cpu=round(1e6 * float(np.mean(cpu)) / units, 1),
    subsystem_ms_per_tick={
        k: round(1000 * v / timed, 2) for k, v in sorted(timings.items(), key=lambda kv: -kv[1])
    },
)

# ----------------------------------------------------------------- density and contacts
state = sim.state
cols_cells = np.array([u.cell for u in state.units.values()])
_, per_cell = np.unique(cols_cells, return_counts=True)
report["units_per_land_cell"] = round(len(state.units) / report["land_cells"], 3)
report["units_per_occupied_cell"] = {
    "mean": round(float(per_cell.mean()), 2),
    "p50_p90_p99_max": [int(x) for x in np.quantile(per_cell, [0.5, 0.9, 0.99, 1.0])],
    "unit_weighted_mean": round(float((per_cell**2).sum() / per_cell.sum()), 2),
}
units_list = tuple(state.units.values())
index = SpatialIndex.build(units_list)
receiver, partner = index.local_pairs(sim.static.neighborhood_table(1))
weight = np.ones(receiver.size)
position = np.arange(receiver.size) - np.searchsorted(receiver, receiver)
r2, _, _, _ = merge_trade_contacts(
    units_list, index.row_of, receiver, partner, weight, position, 1.0
)
U = len(units_list)
ms = report["subsystem_ms_per_tick"]
report["contacts"] = {
    "sharing_candidate_pairs": int(receiver.size),
    "diffusion_contacts": int(r2.size),
    "trade_edges": int(sum(len(u.trade_ties) for u in units_list)),
    "per_unit_sharing": round(receiver.size / U, 2),
    "per_unit_diffusion": round(r2.size / U, 2),
    "us_per_sharing_pair": round(1000 * ms.get("knowledge_sharing", 0) / max(receiver.size, 1), 3),
    "us_per_diffusion_contact": round(1000 * ms.get("diffusion", 0) / max(r2.size, 1), 3),
}

# ----------------------------------------------------------------- memory breakdown
seen: set[int] = set()


def deep(obj: object, skip: frozenset[str] = frozenset()) -> int:
    """Bytes reachable from ``obj`` not counted before (ndarray data included)."""
    total = 0
    stack = [obj]
    while stack:
        o = stack.pop()
        if id(o) in seen or o is None or isinstance(o, (type, type(sys))):
            continue
        seen.add(id(o))
        if isinstance(o, np.ndarray):
            total += sys.getsizeof(o)
            if o.base is not None:
                stack.append(o.base)
            continue
        total += sys.getsizeof(o)
        if isinstance(o, dict):
            stack.extend(o.keys())
            stack.extend(o.values())
        elif isinstance(o, (list, tuple, set, frozenset, deque)):
            stack.extend(o)
        elif isinstance(o, (str, bytes, int, float, bool, complex)):
            pass
        else:
            d = getattr(o, "__dict__", None)
            if d is not None:
                total += sys.getsizeof(d)
                stack.extend(v for k, v in d.items() if k not in skip)
            for slot in getattr(type(o), "__slots__", ()) or ():
                if hasattr(o, slot) and slot not in skip:
                    stack.append(getattr(o, slot))
    return total


gc.collect()
mem: dict[str, float] = {}
store, table = state.belief_store, state.table
mem["beliefs (sparse store)"] = deep(store)
mem["unit table (scalars, cohorts, knowledge, technologies)"] = deep(table)
mem["unit table: of which cohorts"] = table.females.nbytes + table.males.nbytes
fields = (
    "familiarity",
    "recent_residence",
    "report_cells",
    "harvest_history",
    "trade_ties",
    "id",
    "parent_id",
    "species_id",
)
per_field = dict.fromkeys(fields, 0)
objects = 0
for u in units_list:  # unit objects: object + __dict__ itself, then external fields
    seen.add(id(u))
    objects += sys.getsizeof(u) + sys.getsizeof(u.__dict__)
    for f in fields:
        per_field[f] += deep(u.__dict__[f])
mem["unit objects (object + __dict__)"] = objects
for f in fields:
    mem[f"unit field: {f}"] = per_field[f]
mem["unit registry (dict, slot cache)"] = deep(state.units, frozenset())
mem["static: neighborhood tables"] = deep(sim.static._neighborhoods)
mem["static: perceived-cell cache"] = deep(sim.static._perceived)
mem["static: movement reachability caches"] = sum(
    deep(m._reachable) + deep(m._reachable_arrays) for m in sim.static.movement.values()
)
mem["static: world, life tables, forage, rest"] = deep(sim.static)
mem["ecology + climate"] = deep(state.ecology) + deep(state.climate)
mem["compiled scenario + capability cache"] = deep(sim.compiled) + deep(sim.capability_cache)
mem["event log"] = deep(sim.events)
mem["rest of simulator"] = deep(sim)
accounted = sum(v for k, v in mem.items() if "of which" not in k)
report["memory_mb"] = {k: round(v / 2**20, 2) for k, v in mem.items()}
report["memory_accounted_mb"] = round(accounted / 2**20, 1)
report["rss_now_mb"] = round(rss_mb(), 1)
report["peak_rss_mb"] = round(peak_rss_mb(), 1)
report["bytes_per_unit_accounted"] = round(accounted / U)
python_side = objects + sum(per_field.values()) + mem["unit registry (dict, slot cache)"]
report["python_side_bytes_per_unit"] = round(python_side / U)
report["numeric_bytes_per_unit"] = round(
    (mem["beliefs (sparse store)"] + mem["unit table (scalars, cohorts, knowledge, technologies)"])
    / U
)
report["beliefs"] = {
    "stored_entries_per_unit": round(store.stored_entries / U, 1),
    "pool_entries_per_unit": round(store.pool_size / U, 1),
    "bytes_per_unit": round(store.nbytes / U),
}
report["familiarity_entries_per_unit"] = round(sum(len(u.familiarity) for u in units_list) / U, 1)

# ------------------------------------------- transient allocation (ordinary ticks only)
if TRACE:
    peaks = []
    for _ in range(3):
        before = (store.resizes, store.compactions, table.resizes)
        tracemalloc.start()
        cur, _ = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        sim.step()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        growth = (store.resizes, store.compactions, table.resizes) != before
        peaks.append({"mb": round((peak - cur) / 2**20, 1), "storage_growth_tick": growth})
    ordinary = [p["mb"] for p in peaks if not p["storage_growth_tick"]]
    report["transient_mb_per_tick"] = {
        "ordinary_mean": round(float(np.mean(ordinary)), 1) if ordinary else None,
        "ticks": peaks,
    }

if CALLS:
    p = cProfile.Profile()
    p.enable()
    sim.step()
    p.disable()
    calls = pstats.Stats(p).total_calls  # type: ignore[attr-defined]
    report["python_calls_per_unit_tick"] = round(calls / len(state.units), 1)

with open(out, "w") as handle:
    json.dump(report, handle, indent=1)
print(
    json.dumps(
        {
            k: report[k]
            for k in (
                "units",
                "width",
                "cpu_ms_per_tick",
                "us_per_unit_tick_cpu",
                "peak_rss_mb",
                "memory_accounted_mb",
            )
        }
    )
)
