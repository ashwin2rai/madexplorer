# The report table keeps one entry per line.
# ruff: noqa: E501
"""Strata capacity sensitivity (MVP 3 Stages 4A/4B): observation only.

Runs the frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure with cultivation
400 y; seeds 0-3) at several strata capacities (``strata.max_strata``) and at w = 0 and 1
(``strata.field_output_claim_weight``), and reports, per capacity:

- representation load: active-strata distribution, unit-years at capacity, exact
  compactions, capacity coalescences;
- representation error from the sidecar coalescence events (field, store and combined;
  totals and per-merge quantiles);
- convergence toward the highest tested capacity (a provisional comparison point, not
  truth): per unit-year Wasserstein-1 distances of the field- and store-position
  distributions, and the relative difference of total pooling-transfer volume;
- w coupling: how far w alone moves the represented field distribution (w = 1 vs w = 0);
- physical isolation: metrics, frozen events, RNG states and final unit physical state must
  be identical across capacities (strata are not causal);
- cost: run time, the accounting hook, capacity coalescence, the exact-duplicate check, and
  actual StrataTable bytes per row.

Usage:
    uv run python scripts/probes/strata_capacity.py [--capacities 4,8,16,32] [--jobs 2]
"""

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from strata_review import SEEDS, Observer, drive, people_weighted_dev, scenario_for

from madexplorer.population import strata as strata_module
from madexplorer.population.strata import StrataBlock, StrataTable, positions

SCENARIOS = ("neolithic", "pressure+cult")

Measure = list[tuple[float, float]]


def measure(block: StrataBlock, dim: int) -> Measure:
    """Share by position in one dimension (equal positions to 1e-12 pooled)."""
    pairs = sorted(
        zip(positions(block)[:, dim].tolist(), block.columns["share"].tolist(), strict=True)
    )
    groups: list[list[float]] = []
    for position, share in pairs:
        if groups and abs(position - groups[-1][0]) <= 1e-12 * max(1.0, position):
            groups[-1][1] += share
        else:
            groups.append([position, share])
    return [(p, s) for p, s in groups]


def w1(a: Measure, b: Measure) -> float:
    """Wasserstein-1 distance between two share-weighted position measures."""
    if a == b:
        return 0.0
    pa, sa = (np.array(x) for x in zip(*a, strict=True))
    pb, sb = (np.array(x) for x in zip(*b, strict=True))
    grid = np.unique(np.concatenate([pa, pb]))
    fa = np.array([sa[pa <= x].sum() for x in grid])
    fb = np.array([sb[pb <= x].sum() for x in grid])
    return float((np.abs(fa - fb)[:-1] * np.diff(grid)).sum())


NEUTRAL: Measure = [(1.0, 1.0)]


def physical_digest(sim: Any) -> str:
    """The frozen event stream, RNG states and unit physical state (metrics are covered by
    the MVP 2.1 oracles; this probe steps without the recorder)."""
    h = hashlib.sha256()
    h.update(json.dumps([(e.year, e.kind, e.data) for e in sim.events], default=str).encode())
    for name in sorted(sim.rng._streams):
        h.update(repr(sim.rng.stream(name).bit_generator.state).encode())
    for unit in sim.state.units.values():
        h.update(unit.id.encode())
        for array in (unit.females, unit.males, unit.knowledge):
            h.update(np.ascontiguousarray(array).tobytes())
        h.update(repr((unit.cell, unit.stores_kcal, unit.fields_ha, unit.food_ratio,
                       unit.harvest_kcal, list(unit.harvest_history))).encode())  # fmt: skip
    return h.hexdigest()


class Timers:
    """Time spent in capacity coalescence and in the exact-duplicate check (wrapped)."""

    def __init__(self) -> None:
        self.coalesce = 0.0
        self.duplicates = 0.0
        coalesce, duplicates = strata_module.coalesce_to_capacity, StrataTable.duplicate_rows

        def timed_coalesce(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            result = coalesce(*args, **kwargs)
            self.coalesce += time.perf_counter() - started
            return result

        def timed_duplicates(table: StrataTable, slots: Any) -> Any:
            started = time.perf_counter()
            result = duplicates(table, slots)
            self.duplicates += time.perf_counter() - started
            return result

        self._saved = (coalesce, duplicates)
        strata_module.coalesce_to_capacity = timed_coalesce  # type: ignore[assignment]
        StrataTable.duplicate_rows = timed_duplicates  # type: ignore[method-assign]

    def remove(self) -> None:
        strata_module.coalesce_to_capacity, StrataTable.duplicate_rows = self._saved  # type: ignore[method-assign]


def one_run(name: str, seed: int, capacity: int, weight: float) -> dict[str, Any]:
    scenario = scenario_for(name, seed, weight).with_settings({"strata.max_strata": capacity})
    observer, timers = Observer(coalescence=False), Timers()
    counts: Counter[int] = Counter()
    fields: dict[tuple[int, str], Measure] = {}
    stores: dict[tuple[int, str], Measure] = {}
    rows = [0]

    def each_year(sim: Any) -> None:
        for unit in sim.state.units.values():
            n = len(unit.strata)
            counts[n] += 1
            rows[0] += n
            if n > 1:
                key = (sim.state.year, unit.id)
                fields[key] = measure(unit.strata, 0)
                stores[key] = measure(unit.strata, 1)

    try:
        sim, seconds = drive(scenario, observer, each_year)
    finally:
        timers.remove()
    events = sim.state.population.strata_log or []
    coal = [e for e in events if e["event"] == "capacity_coalescence"]
    flows = sim.state.population.strata_flows or []
    table = sim.state.population.strata
    assert table is not None
    return {
        "counts": counts,
        "fields": fields,
        "stores": stores,
        "compactions": sum(e["event"] == "exact_compaction" for e in events),
        "field_errors": [e["field_error"] for e in coal],
        "store_errors": [e["store_error"] for e in coal],
        "combined_errors": [e["combined_error"] for e in coal],
        "pool_volume": sum(abs(r["pool_transfer_kcal"]) for r in flows) / 2,
        "seconds": seconds,
        "hook": observer.hook_seconds,
        "coalesce_seconds": timers.coalesce,
        "duplicate_seconds": timers.duplicates,
        "sidecar_rows": rows[0],
        "bytes_per_row": table.nbytes / table.capacity,
        "physical": physical_digest(sim),
        "dev": people_weighted_dev(sim),
    }


def job(spec: tuple[str, int, tuple[int, ...]]) -> dict[str, Any]:
    name, seed, capacities = spec
    runs = {(c, w): one_run(name, seed, c, w) for c in capacities for w in (0.0, 1.0)}
    top = max(capacities)
    out: dict[str, Any] = {"name": name, "seed": seed, "per": {}}
    for (c, w), run in runs.items():
        ref = runs[(top, w)]
        keys = run["fields"].keys() | ref["fields"].keys()
        field_gap = [w1(run["fields"].get(k, NEUTRAL), ref["fields"].get(k, NEUTRAL)) for k in keys]
        store_gap = [w1(run["stores"].get(k, NEUTRAL), ref["stores"].get(k, NEUTRAL)) for k in keys]
        summary = {k: v for k, v in run.items() if k not in ("fields", "stores")}
        summary["field_vs_top"] = field_gap
        summary["store_vs_top"] = store_gap
        summary["pool_vs_top"] = (
            abs(run["pool_volume"] - ref["pool_volume"]) / ref["pool_volume"]
            if ref["pool_volume"]
            else 0.0
        )
        if w == 0.0:  # w coupling at this capacity
            other = runs[(c, 1.0)]
            both = run["fields"].keys() | other["fields"].keys()
            summary["w_gaps"] = [g for k in both
                                 if (g := w1(run["fields"].get(k, NEUTRAL), other["fields"].get(k, NEUTRAL))) > 1e-12]  # fmt: skip
            summary["multi_unit_years"] = len(both)
        out["per"][(c, w)] = summary
    digests = {run["physical"] for run in runs.values()}
    out["physical_identical"] = len(digests) == 1
    print(
        f"  done {name} seed {seed} (physical identical across runs: {out['physical_identical']})",
        flush=True,
    )
    return out


def q(values: list[float], qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> str:
    if not values:
        return "-"
    return "/".join(f"{np.quantile(values, x):.2g}" for x in qs) + f"/{max(values):.2g}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--capacities", default="4,8,16,32")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    capacities = tuple(int(c) for c in args.capacities.split(","))
    work = [(name, seed, capacities) for name in SCENARIOS for seed in SEEDS]
    with Pool(args.jobs, maxtasksperchild=1) as pool:
        results = pool.map(job, work, chunksize=1)
    print(f"\nphysical outputs identical across capacities and w within every scenario/seed: "
          f"{all(r['physical_identical'] for r in results)}")  # fmt: skip
    top = max(capacities)
    for name in SCENARIOS:
        res = [r for r in results if r["name"] == name]
        print(f"\n=== {name}, seeds {SEEDS} ===  columns: max_strata; cells: w=0 | w=1 where two")
        print(f"{'':44}" + "".join(f"{c:>26}" for c in capacities))
        table: dict[str, list[str]] = {}
        for c in capacities:
            cells: dict[str, list[str]] = {}
            for w in (0.0, 1.0):
                runs = [r["per"][(c, w)] for r in res]
                counts: Counter[int] = Counter()
                for run in runs:
                    counts.update(run["counts"])
                values = np.repeat(list(counts), list(counts.values()))
                fe = [x for r in runs for x in r["field_errors"]]
                se = [x for r in runs for x in r["store_errors"]]
                ce = [x for r in runs for x in r["combined_errors"]]
                fg = [x for r in runs for x in r["field_vs_top"]]
                sg = [x for r in runs for x in r["store_vs_top"]]
                secs = sum(r["seconds"] for r in runs)
                entries = {
                    "active strata mean / median": f"{values.mean():.2f}/{np.median(values):.0f}",
                    "  p90 / p99": f"{np.quantile(values, 0.9):.0f}/{np.quantile(values, 0.99):.0f}",
                    "unit-years at capacity": f"{counts[c] / values.size:.4f}",
                    "exact compactions": f"{sum(r['compactions'] for r in runs)}",
                    "capacity coalescences": f"{len(ce)}",
                    "error total field / store": f"{sum(fe):.3g}/{sum(se):.3g}",
                    "error total combined": f"{sum(ce):.3g}",
                    "per-merge field err p50/90/99/max": q(fe),
                    "per-merge store err p50/90/99/max": q(se),
                    f"field W1 vs {top} p50/90/99/max": q(fg),
                    f"store W1 vs {top} p50/90/99/max": q(sg),
                    f"pooling volume rel. diff vs {top} (max)": f"{max(r['pool_vs_top'] for r in runs):.2e}",
                    "time-mean field / store |pos-1| (final)": "/".join(
                        f"{np.mean([r['dev'][d] for r in runs]):.4f}" for d in (0, 1)),
                    "run seconds (sum)": f"{secs:.0f}",
                    "  accounting hook / coalesce / dup": (
                        f"{sum(r['hook'] for r in runs) / secs:.3f}/"
                        f"{sum(r['coalesce_seconds'] for r in runs) / secs:.3f}/"
                        f"{sum(r['duplicate_seconds'] for r in runs) / secs:.3f}"),
                    "strata sidecar rows (sum)": f"{sum(r['sidecar_rows'] for r in runs)}",
                    "StrataTable bytes/row (actual)": f"{runs[0]['bytes_per_row']:.0f}",
                }  # fmt: skip
                for label, value in entries.items():
                    cells.setdefault(label, []).append(value)
            for label, value in cells.items():
                table.setdefault(label, []).append(" | ".join(value))
            gaps = [g for r in res for g in r["per"][(c, 0.0)]["w_gaps"]]
            multi = sum(r["per"][(c, 0.0)]["multi_unit_years"] for r in res)
            table.setdefault("w moves field repr.: share of unit-yrs", []).append(
                f"{len(gaps) / multi:.3f}"
            )
            table.setdefault("  W1 when moved p50/90/99/max", []).append(q(gaps))
        for label, cells_ in table.items():
            print(f"{label:44}" + "".join(f"{x:>26}" for x in cells_))


if __name__ == "__main__":
    main()
