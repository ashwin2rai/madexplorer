# Per-run closures are defined in loops and called within the same iteration; the report
# table keeps one entry per line.
# ruff: noqa: B023, E501
"""Strata capacity sensitivity (MVP 3 Stage 4A): observation only.

Runs the frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure with cultivation
400 y; seeds 0-3) at several strata capacities ``S_MAX`` and at w = 0 and 1
(``strata.field_output_claim_weight``), and reports what the capacity changes: active-strata
distribution, unit-years at capacity, capacity coalescences and the field-position variance
they remove, runtime and accounting cost, sidecar size, socioeconomic observables, and how
much w redirects coalescence into the represented field distribution (per unit-year
Wasserstein-1 distance between the w = 0 and w = 1 field distributions).

Diagnostic mechanism: ``population.strata.S_MAX`` is a module global read at call time by
every strata capacity check and by ``StrataTable`` allocation, so it is set per run before
the simulator is built (``n_strata`` is int8: capacities up to 127). Production keeps
``S_MAX = 8``; nothing else changes, and physical outcomes do not depend on strata.

Usage:
    uv run python scripts/probes/strata_capacity.py [--capacities 4,8,16,32] [--jobs 2]
"""

import argparse
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from strata_review import (
    SEEDS,
    Observer,
    drive,
    field_measure,
    people_weighted_dev,
    scenario_for,
)

from madexplorer.population import strata as strata_module
from madexplorer.population.strata import STRATUM_COLUMNS

SCENARIOS = ("neolithic", "pressure+cult")


def measure_w1(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """Wasserstein-1 distance between two share-weighted field-position measures."""
    pa, sa = (np.array(x) for x in zip(*a, strict=True))
    pb, sb = (np.array(x) for x in zip(*b, strict=True))
    grid = np.unique(np.concatenate([pa, pb]))
    fa = np.array([sa[pa <= x].sum() for x in grid])
    fb = np.array([sb[pb <= x].sum() for x in grid])
    return float((np.abs(fa - fb)[:-1] * np.diff(grid)).sum())


def job(spec: tuple[str, int, int]) -> dict[str, Any]:
    name, seed, capacity = spec
    strata_module.S_MAX = capacity  # diagnostic: this process's strata capacity
    out: dict[str, Any] = {"name": name, "seed": seed, "capacity": capacity, "runs": {}}
    measures: dict[float, dict[tuple[int, str], list[tuple[float, float]]]] = {}
    for weight in (0.0, 1.0):
        observer = Observer()
        counts: Counter[int] = Counter()
        measure: dict[tuple[int, str], list[tuple[float, float]]] = {}
        devs: list[tuple[float, float]] = []
        rows = [0]

        def each_year(sim: Any) -> None:
            for unit in sim.state.units.values():
                n = len(unit.strata)
                counts[n] += 1
                rows[0] += n
                if n > 1:
                    measure[(sim.state.year, unit.id)] = field_measure(unit.strata)
            devs.append(people_weighted_dev(sim))

        sim, seconds = drive(scenario_for(name, seed, weight), observer, each_year)
        measures[weight] = measure
        events = Counter(e["event"] for e in sim.state.population.strata_log or [])
        lost = [c["field_error"] / c["field_variance"] for c in observer.coalescences
                if c["field_variance"] > 0]  # fmt: skip
        table = sim.state.population.strata
        assert table is not None
        out["runs"][weight] = {
            "counts": dict(counts),
            "events": dict(events),
            "coalescences": len(observer.coalescences),
            "field_error": sum(c["field_error"] for c in observer.coalescences),
            "store_error": sum(c["store_error"] for c in observer.coalescences),
            "distinct_field_merges": sum(c["field_gap"] > 1e-9 for c in observer.coalescences),
            "field_var_lost": lost,
            "seconds": seconds,
            "hook_seconds": observer.hook_seconds,
            "sidecar_rows": rows[0],
            "flow_rows": len(sim.state.population.strata_flows or []),
            "time_mean_dev": np.mean(devs, axis=0).tolist(),
            "table_bytes": sum(table.columns[c].nbytes for c in STRATUM_COLUMNS)
            + table.stratum_id.nbytes
            + table.n_strata.nbytes,
            "table_rows": int(table.n_strata.shape[0]),
        }
    gaps = []
    for key in measures[0.0].keys() | measures[1.0].keys():
        a = measures[0.0].get(key, [(1.0, 1.0)])
        b = measures[1.0].get(key, [(1.0, 1.0)])
        if a != b:
            gap = measure_w1(a, b)
            if gap > 1e-12:
                gaps.append(gap)
    out["w_gaps"] = gaps
    out["multi_unit_years"] = len(measures[0.0])
    print(f"  done {name} seed {seed} S_MAX={capacity}", flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--capacities", default="4,8,16,32")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    capacities = [int(c) for c in args.capacities.split(",")]
    work = [(name, seed, cap) for cap in capacities for name in SCENARIOS for seed in SEEDS]
    with Pool(args.jobs, maxtasksperchild=1) as pool:
        results = pool.map(job, work, chunksize=1)
    for name in SCENARIOS:
        print(f"\n=== {name}, seeds {SEEDS} ===  (columns: S_MAX; cells: w=0 | w=1)")
        print(f"{'':40}" + "".join(f"{c:>24}" for c in capacities))
        table: dict[str, list[str]] = {}

        def put(label: str, cells: list[str]) -> None:
            table.setdefault(label, []).append(" | ".join(cells))

        for cap in capacities:
            res = [r for r in results if r["name"] == name and r["capacity"] == cap]

            def runs(w: float, res: list[dict[str, Any]] = res) -> list[dict[str, Any]]:
                return [r["runs"][w] for r in res]

            cells: dict[str, list[str]] = {}
            for w in (0.0, 1.0):
                counts: Counter[int] = Counter()
                for run in runs(w):
                    counts.update({int(k): v for k, v in run["counts"].items()})
                values = np.repeat(list(counts), list(counts.values()))
                total = values.size
                lost = [x for run in runs(w) for x in run["field_var_lost"]]
                entries = {
                    "mean strata / unit-year": f"{values.mean():.2f}",
                    "p90 / p99 / max": f"{np.quantile(values, 0.9):.0f}/"
                    f"{np.quantile(values, 0.99):.0f}/{values.max()}",
                    "unit-years at capacity": f"{counts[cap] / total:.4f}",
                    "capacity coalescences": f"{sum(r['coalescences'] for r in runs(w))}",
                    "  of distinct field positions": f"{sum(r['distinct_field_merges'] for r in runs(w))}",
                    "  coalescence field err (sum)": f"{sum(r['field_error'] for r in runs(w)):.3g}",
                    "  store err (sum)": f"{sum(r['store_error'] for r in runs(w)):.3g}",
                    "  field var lost/merge p90": f"{np.quantile(lost, 0.9):.3f}" if lost else "-",
                    "exact compactions": f"{sum(r['events'].get('exact_compaction', 0) for r in runs(w))}",
                    "time-mean field |pos-1|": f"{np.mean([r['time_mean_dev'][0] for r in runs(w)]):.4f}",
                    "time-mean store |pos-1|": f"{np.mean([r['time_mean_dev'][1] for r in runs(w)]):.4f}",
                    "run seconds (sum)": f"{sum(r['seconds'] for r in runs(w)):.0f}",
                    "accounting hook share": f"{sum(r['hook_seconds'] for r in runs(w)) / sum(r['seconds'] for r in runs(w)):.3f}",
                    "strata sidecar rows (sum)": f"{sum(r['sidecar_rows'] for r in runs(w))}",
                    "StrataTable bytes/row": f"{runs(w)[0]['table_bytes'] / runs(w)[0]['table_rows']:.0f}",
                }  # fmt: skip
                for label, value in entries.items():
                    cells.setdefault(label, []).append(value)
            for label, value in cells.items():
                put(label, value)
            gaps = [g for r in res for g in r["w_gaps"]]
            multi = sum(r["multi_unit_years"] for r in res)
            put("w redirects field repr. (unit-yrs)", [f"{len(gaps) / multi:.3f}"])
            put("  W1 when redirected p50/p99", [
                f"{np.quantile(gaps, 0.5):.3g}/{np.quantile(gaps, 0.99):.3g}" if gaps else "-"
            ])  # fmt: skip
        for label, cells_ in table.items():
            print(f"{label:40}" + "".join(f"{c:>24}" for c in cells_))


if __name__ == "__main__":
    main()
