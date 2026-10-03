# Per-year observer closures are defined in loops and called within the same iteration.
# ruff: noqa: B023
"""MVP 3 Stage 3D scientific and representation review: observation only.

Answers, on real runs and on the actual rule functions, the questions of the Stage 3D review
(objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md §M). Nothing in the model is changed: rules
are wrapped to observe their inputs and outputs, so every run is identical to an unprobed one.

Modes:

``representation``
    Frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure 400 y with and without
    cultivation; seeds 0-3) at w = 0, 0.25, 0.5, 1 (``strata.field_output_claim_weight``):
    active-strata distribution, units at capacity, exact compactions, capacity coalescences
    with their error by dimension, nearest-neighbor position distances within units, the cost of
    the accounting hook, and whether the represented field-claim distribution differs from
    w = 0 in any unit-year.
``nonlinear``
    Why harvest pooling volume grows nonlinearly in w. Records each differentiated unit-year
    at w = 0 (shares, field claims, kept crop g*Y, leftover L, fed) and evaluates the exact
    pooling volume as a function of w: short years contribute w*g*Y*sum|f - s|/2 (linear);
    fed years contribute sum_i max(w*g*Y*(s_i - f_i) - L*s_i, 0) (a sum of hinges, one per
    stratum whose pre-pool leftover crosses zero at w*_i = L*s_i / (g*Y*(s_i - f_i))). The
    curve is checked against real runs on a grid of w and at w*-0.01, w*, w*+0.01 around
    observed crossings.
``persistence``
    Convergence of an inherited position (minority share 0.2 at field and store position 2.5)
    under prescribed flows, using the real rule functions, in several regimes; and, in real
    runs, the halving times of field and store deviations of individual strata.
``sources``
    Where non-neutral strata come from: every fusion's predecessor resources per person, and
    a run with fusion disabled (homogeneous units only).
``capacity``
    Stress cases above the default capacity (8): two 8-strata predecessors with fixed field
    positions, one fed year of accounting at each w, then fusion and capacity coalescence;
    does w change which components are merged and the represented field distribution?
``fieldgap``
    In the reference runs, the per unit-year Wasserstein-1 distance between the
    field-position distributions at w = 0 and w = 1 (nonzero only through capacity
    coalescence choosing different pairs).

Usage:
    uv run python scripts/probes/strata_review.py representation [--jobs 2]
    uv run python scripts/probes/strata_review.py nonlinear
    uv run python scripts/probes/strata_review.py persistence
    uv run python scripts/probes/strata_review.py sources
    uv run python scripts/probes/strata_review.py capacity
    uv run python scripts/probes/strata_review.py fieldgap [--jobs 2]
"""

import argparse
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from multiprocessing import Pool
from typing import Any

import numpy as np

import madexplorer.core.simulation as simulation
import madexplorer.population.lifecycle as lifecycle
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.population import strata as strata_module
from madexplorer.population import strata_accounting
from madexplorer.population.strata import (
    DEFAULT_MAX_STRATA,
    StrataBlock,
    fuse_strata,
    normalize_strata,
    positions,
)
from madexplorer.population.strata_accounting import (
    FoodAccounts,
    field_claims_after_change,
    food_flows,
    store_claims_after_year,
)

WEIGHTS = (0.0, 0.25, 0.5, 1.0)
REFERENCE = {  # the frozen MVP 2.1 reference runs (baselines/mvp2_1)
    "neolithic": ("scenarios/mvp2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_pressure.yaml", 400, {"mechanisms.cultivation": True}),
    "pressure-cult": ("scenarios/mvp2_pressure.yaml", 400, {"mechanisms.cultivation": False}),
}
SEEDS = (0, 1, 2, 3)
BINS = (
    ("exact (0)", 0.0),
    ("float dust (<=1e-12)", 1e-12),
    ("<=1e-6", 1e-6),
    ("<=1e-3", 1e-3),
    ("<=1e-2", 1e-2),
    ("<=0.1", 0.1),
    ("> 0.1", float("inf")),
)


# ---------------------------------------------------------------- observation hooks


class Observer:
    """Wraps rules for one run; ``year`` is set by the driver before each step."""

    def __init__(self, coalescence: bool = True) -> None:
        self.observe_coalescence = coalescence  # recompute merge errors (slow; diagnostics)
        self.year = 0
        self.hook_seconds = 0.0
        self.coalescences: list[dict[str, float]] = []
        self.fusions: list[dict[str, float]] = []
        self.food: list[dict[str, Any]] = []
        self.record_food = False
        self._saved: list[tuple[Any, str, Any]] = []

    def install(self) -> "Observer":
        hook = simulation.account_strata
        coalesce = strata_module.coalesce_to_capacity
        fuse = lifecycle.fuse_strata
        flows = strata_accounting.food_flows

        def timed(state: Any, ctx: Any) -> None:
            started = time.perf_counter()
            hook(state, ctx)
            self.hook_seconds += time.perf_counter() - started

        def coalesce_observed(block: StrataBlock, new_ids: Any, capacity: int) -> Any:
            self.coalescences.extend(coalescence_errors(block, capacity))
            return coalesce(block, new_ids, capacity)

        def fuse_observed(parts: Any) -> StrataBlock:
            self.fusions.append(fusion_record(parts))
            return fuse(parts)

        def flows_observed(
            share: Any, field: Any, store: Any, w: float, acc: FoodAccounts, rows: Any
        ) -> Any:
            if self.record_food and acc.crop is not None:
                self.food.extend(food_records(self.year, share, field, acc, rows))
            return flows(share, field, store, w, acc, rows)

        wrapped: list[tuple[Any, str, Any]] = (
            [(strata_module, "coalesce_to_capacity", coalesce_observed)]
            if self.observe_coalescence
            else []
        )
        for module, name, new in (
            *wrapped,
            (simulation, "account_strata", timed),
            (lifecycle, "fuse_strata", fuse_observed),
            (strata_accounting, "food_flows", flows_observed),
        ):
            self._saved.append((module, name, getattr(module, name)))
            setattr(module, name, new)
        return self

    def remove(self) -> None:
        for module, name, original in reversed(self._saved):
            setattr(module, name, original)
        self._saved.clear()


def coalescence_errors(block: StrataBlock, capacity: int) -> list[dict[str, float]]:
    """Error by dimension of the merges ``coalesce_to_capacity`` will make (same greedy rule,
    recomputed on a copy: the pair chosen and each dimension's share of its cost)."""
    share = block.columns["share"].tolist()
    pos = positions(block).tolist()
    out = []
    alive = list(range(len(share)))
    s = list(share)
    p = [list(x) for x in pos]
    while len(alive) > capacity:
        best = None
        for a, i in enumerate(alive):
            for j in alive[a + 1 :]:
                weight = s[i] * s[j] / (s[i] + s[j])
                cost = weight * sum((p[i][k] - p[j][k]) ** 2 for k in range(2))
                if best is None or cost < best[0]:
                    best = (cost, i, j, weight)
        assert best is not None
        cost, i, j, weight = best
        out.append(
            {
                "cost": cost,
                "field_error": weight * (p[i][0] - p[j][0]) ** 2,
                "store_error": weight * (p[i][1] - p[j][1]) ** 2,
                "field_gap": abs(p[i][0] - p[j][0]),
                "store_gap": abs(p[i][1] - p[j][1]),
                "field_variance": weighted_variance(np.array(s)[alive], np.array(p)[alive, 0]),
                "store_variance": weighted_variance(np.array(s)[alive], np.array(p)[alive, 1]),
            }
        )
        merged = s[i] + s[j]
        p[i] = [(s[i] * p[i][k] + s[j] * p[j][k]) / merged for k in range(2)]
        s[i] = merged
        alive.remove(j)
    return out


def weighted_variance(weight: np.ndarray, values: np.ndarray) -> float:
    w = weight / weight.sum()
    mean = (w * values).sum()
    return float((w * (values - mean) ** 2).sum())


def fusion_record(parts: Any) -> dict[str, float]:
    """Resources per person of the predecessors (only those with people)."""
    kept = [(n, stocks) for _, n, stocks in parts if n > 0]
    per = np.array([[stocks[k] / n for k in range(2)] for n, stocks in kept])
    totals = np.array([sum(stocks[k] for _, stocks in kept) for k in range(2)])
    spread = [
        float(per[:, k].max() / per[:, k].min()) if per[:, k].min() > 0 else float("inf")
        for k in range(2)
    ]
    return {
        "field_ratio": spread[0] if totals[0] > 0 else 1.0,
        "store_ratio": spread[1] if totals[1] > 0 else 1.0,
        "field_stock": float(totals[0]),
        "store_stock": float(totals[1]),
    }


def food_records(
    year: int, share: Any, field: Any, acc: FoodAccounts, rows: Any
) -> list[dict[str, Any]]:
    share, field = np.atleast_2d(share), np.atleast_2d(field)
    index = np.atleast_1d(rows)
    assert acc.harvest is not None and acc.forage is not None and acc.crop is not None
    assert acc.leftover is not None and acc.fed is not None
    out = []
    for k, r in enumerate(index.tolist()):
        crop = float(acc.crop[r])
        own = crop + float(acc.forage[r])
        kept = min(float(acc.harvest[r]) / own, 1.0) if own > 0 else 0.0
        n = int((share[k] > 0).sum())
        out.append(
            {
                "year": year,
                "unit": acc.units[r].id if acc.units else str(r),
                "share": share[k, :n].copy(),
                "field": field[k, :n].copy(),
                "gY": kept * crop,
                "crop": crop,
                "leftover": float(acc.leftover[r]),
                "fed": bool(acc.fed[r]),
            }
        )
    return out


# ---------------------------------------------------------------- shared helpers


def scenario_for(name: str, seed: int, weight: float, years: int | None = None) -> Scenario:
    path, horizon, settings = REFERENCE[name]
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=years or horizon)
    return base.with_settings({**settings, "strata.field_output_claim_weight": weight})


def field_measure(block: StrataBlock) -> list[tuple[float, float]]:
    """Share by field position, equal positions (to 1e-12) pooled: grouping-invariant."""
    pairs = sorted(
        zip(positions(block)[:, 0].tolist(), block.columns["share"].tolist(), strict=True)
    )
    groups: list[list[float]] = []
    for position, share in pairs:
        if groups and abs(position - groups[-1][0]) <= 1e-12 * max(1.0, position):
            groups[-1][1] += share
        else:
            groups.append([position, share])
    return [(p, s) for p, s in groups]


def nearest_distances(block: StrataBlock) -> list[float]:
    """Each stratum's Euclidean distance to the nearest other stratum of its unit."""
    pos = positions(block)
    diff = np.sqrt(((pos[:, None, :] - pos[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(diff, np.inf)
    return diff.min(axis=1).tolist()


def people_weighted_dev(sim: Simulator) -> tuple[float, float]:
    people, pos = [], []
    for unit in sim.state.units.values():
        people.append(unit.strata.columns["share"] * unit.population)
        pos.append(positions(unit.strata))
    w = np.concatenate(people)
    w = w / w.sum()
    dev = np.abs(np.concatenate(pos) - 1.0)
    return float((w * dev[:, 0]).sum()), float((w * dev[:, 1]).sum())


def drive(
    scenario: Scenario,
    observer: Observer,
    each_year: Callable[[Simulator], None] | None = None,
) -> tuple[Simulator, float]:
    """Run the scenario step by step with the observer installed (strata recorded)."""
    observer.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        for _ in range(scenario.config.simulation.n_years):
            observer.year = sim.state.year + 1
            sim.step()
            if not sim.state.units:
                break
            if each_year is not None:
                each_year(sim)
        return sim, time.perf_counter() - started
    finally:
        observer.remove()


def quantiles(values: list[float], qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> list[float]:
    return [float(np.quantile(values, q)) for q in qs] if values else [float("nan")] * len(qs)


# ---------------------------------------------------------------- representation


def representation_job(job: tuple[str, int]) -> dict[str, Any]:
    name, seed = job
    out: dict[str, Any] = {"name": name, "seed": seed, "runs": {}}
    reference: dict[tuple[int, str], list[tuple[float, float]]] = {}
    for weight in WEIGHTS:
        observer = Observer()
        counts: Counter[int] = Counter()
        nearest: list[float] = []
        measure: dict[tuple[int, str], list[tuple[float, float]]] = {}
        devs: list[tuple[float, float]] = []

        def each_year(sim: Simulator) -> None:
            year = sim.state.year
            for unit in sim.state.units.values():
                n = len(unit.strata)
                counts[n] += 1
                if n > 1:
                    if year % 5 == 0:
                        nearest.extend(nearest_distances(unit.strata))
                    measure[(year, unit.id)] = field_measure(unit.strata)
            devs.append(people_weighted_dev(sim))

        sim, seconds = drive(scenario_for(name, seed, weight), observer, each_year)
        if weight == 0.0:
            reference = measure
        differing = 0
        worst = 0.0
        for key in set(reference) | set(measure):
            a, b = reference.get(key, []), measure.get(key, [])
            if len(a) != len(b):
                differing += 1
                continue
            gap = max(
                (max(abs(x[0] - y[0]), abs(x[1] - y[1])) for x, y in zip(a, b, strict=True)),
                default=0,
            )
            worst = max(worst, gap)
            differing += gap > 1e-12
        events = Counter(e["event"] for e in sim.state.population.strata_log or [])
        out["runs"][weight] = {
            "counts": dict(counts),
            "nearest": nearest,
            "events": dict(events),
            "coalescences": observer.coalescences,
            "seconds": seconds,
            "hook_seconds": observer.hook_seconds,
            "field_measure_differing_unit_years": differing,
            "field_measure_max_gap": worst,
            "multi_unit_years": len(measure),
            "time_mean_dev": np.mean(devs, axis=0).tolist() if devs else [0.0, 0.0],
            "final_dev": list(devs[-1]) if devs else [0.0, 0.0],
            "years": sim.state.year,
        }
        print(f"  done {name} seed {seed} w={weight} ({seconds:.0f} s)", flush=True)
    return out


def representation(jobs: int) -> None:
    work = [(name, seed) for name in REFERENCE for seed in SEEDS]
    with Pool(jobs) as pool:
        results = pool.map(representation_job, work, chunksize=1)
    for name in REFERENCE:
        print(f"\n=== {name} (seeds {SEEDS}, {REFERENCE[name][1]} y) ===")
        print(f"{'':38}" + "".join(f"{w:>12}" for w in WEIGHTS))
        rows: dict[str, list[str]] = defaultdict(list)
        for weight in WEIGHTS:
            runs = [r["runs"][weight] for r in results if r["name"] == name]
            counts: Counter[int] = Counter()
            for run in runs:
                counts.update({int(k): v for k, v in run["counts"].items()})
            total = sum(counts.values())
            values = np.repeat(list(counts), list(counts.values()))
            rows["unit-years"].append(f"{total}")
            rows["mean strata / unit-year"].append(f"{values.mean():.3f}")
            rows["median / p90 / p99 / max"].append(
                "/".join(f"{np.quantile(values, q):.0f}" for q in (0.5, 0.9, 0.99))
                + f"/{values.max()}"
            )
            rows["share of unit-years with 1 stratum"].append(f"{counts[1] / total:.3f}")
            rows["unit-years at DEFAULT_MAX_STRATA"].append(
                f"{counts[DEFAULT_MAX_STRATA]} ({counts[DEFAULT_MAX_STRATA] / total:.4f})"
            )
            ev: Counter[str] = Counter()
            for run in runs:
                ev.update(run["events"])
            rows["fusion inheritances"].append(f"{ev['fusion_inheritance']}")
            rows["exact compactions"].append(f"{ev['exact_compaction']}")
            rows["capacity coalescences"].append(f"{ev['capacity_coalescence']}")
            coal = [c for run in runs for c in run["coalescences"]]
            if coal:
                f_err = sum(c["field_error"] for c in coal)
                s_err = sum(c["store_error"] for c in coal)
                rows["coalescence error field / store"].append(f"{f_err:.2e}/{s_err:.2e}")
                rows["  merges with field gap > 1e-9"].append(
                    f"{sum(c['field_gap'] > 1e-9 for c in coal)}"
                )
                rel = [
                    c["field_error"] / c["field_variance"] for c in coal if c["field_variance"] > 0
                ]
                rows["  max field error / unit field var"].append(f"{max(rel):.2e}" if rel else "-")
            else:
                rows["coalescence error field / store"].append("-")
                rows["  merges with field gap > 1e-9"].append("0")
                rows["  max field error / unit field var"].append("-")
            near = [d for run in runs for d in run["nearest"]]
            bins = Counter()
            for d in near:
                for label, edge in BINS:
                    if d <= edge:
                        bins[label] += 1
                        break
            for label, _ in BINS:
                rows[f"nearest dist {label}"].append(
                    f"{bins[label] / len(near):.3f}" if near else "-"
                )
            q = quantiles(near)
            rows["nearest dist median / p90 / p99"].append("/".join(f"{x:.2g}" for x in q))
            rows["field-measure unit-years != w0"].append(
                f"{sum(r['field_measure_differing_unit_years'] for r in runs)}"
            )
            rows["field-measure max gap vs w0"].append(
                f"{max(r['field_measure_max_gap'] for r in runs):.1e}"
            )
            tm = np.mean([r["time_mean_dev"] for r in runs], axis=0)
            rows["time-mean |pos-1| field / store"].append(f"{tm[0]:.4f}/{tm[1]:.4f}")
            hook = sum(r["hook_seconds"] for r in runs) / sum(r["seconds"] for r in runs)
            rows["accounting hook share of run time"].append(f"{hook:.3f}")
        for label, cells in rows.items():
            print(f"{label:38}" + "".join(f"{c:>12}" for c in cells))


# ---------------------------------------------------------------- nonlinear pooling


def harvest_volume(records: list[dict[str, Any]], weight: float) -> dict[str, float]:
    """Exact harvest pooling volume at ``weight`` from w = 0 records (see module doc)."""
    short = fed = 0.0
    negative_strata = 0
    negative_kcal = 0.0
    units: set[tuple[int, str]] = set()
    crop = 0.0
    dispersion: list[float] = []
    per_unit: list[float] = []
    for r in records:
        s, f, gy, leftover = r["share"], r["field"], r["gY"], r["leftover"]
        if not r["fed"]:
            short += weight * gy * np.abs(f - s).sum() / 2
            continue
        raw = leftover * s + weight * gy * (f - s)
        neg = np.maximum(-raw, 0.0)
        volume = float(neg.sum())
        fed += volume
        if volume > 0:
            per_unit.append(volume)
            negative_strata += int((neg > 0).sum())
            negative_kcal += volume
            units.add((r["year"], r["unit"]))
            crop += r["crop"]
            dispersion.append(float((s * np.abs(f / s - 1)).sum()))
    per_unit.sort(reverse=True)
    top = sum(per_unit[:10]) / fed if fed else 0.0
    return {
        "short": short,
        "fed": fed,
        "total": short + fed,
        "negative_strata": negative_strata,
        "negative_kcal": negative_kcal,
        "affected_unit_years": len(units),
        "affected_crop": crop,
        "affected_dispersion": float(np.mean(dispersion)) if dispersion else 0.0,
        "top10_share": top,
    }


def crossings(records: list[dict[str, Any]]) -> list[tuple[float, int, str, float]]:
    """(w*, year, unit, slope) for every fed stratum-year whose leftover crosses 0 at w* <= 1."""
    out = []
    for r in records:
        if not r["fed"]:
            continue
        s, f, gy, leftover = r["share"], r["field"], r["gY"], r["leftover"]
        for k in range(len(s)):
            slope = gy * (s[k] - f[k])
            if slope > 0:
                w_star = leftover * s[k] / slope
                if w_star <= 1.0:
                    out.append((float(w_star), r["year"], r["unit"], float(slope)))
    return sorted(out)


def actual_volume(scenario: Scenario) -> tuple[float, Simulator, Observer]:
    observer = Observer()
    observer.record_food = True
    sim, _ = drive(scenario, observer)
    flows = sim.state.population.strata_flows or []
    return sum(abs(r["harvest_pool_transfer_kcal"]) for r in flows) / 2, sim, observer


def nonlinear() -> None:
    name, years = "neolithic", 400
    for seed in SEEDS:
        observer = Observer()
        observer.record_food = True
        drive(scenario_for(name, seed, 0.0, years), observer)
        records = observer.food
        print(
            f"\n=== {name} seed {seed}, {years} y: differentiated unit-years at energetics: "
            f"{len(records)} (fed {sum(r['fed'] for r in records)}) ==="
        )
        if records:
            fed = [r for r in records if r["fed"] and r["crop"] > 0]
            ratio = [r["leftover"] / r["gY"] for r in fed if r["gY"] > 0]
            print(
                f"  fed unit-years with crop: {len(fed)}; leftover / kept crop  median "
                f"{np.median(ratio):.3f}, p10 {np.quantile(ratio, 0.1):.3f}, "
                f"share with L = 0: {np.mean([x == 0 for x in ratio]):.3f}"
            )
        print(
            f"  {'w':>5} {'short (lin)':>12} {'fed (hinge)':>12} {'total':>12} {'neg strata':>10} "
            f"{'unit-yrs':>8} {'crop of those':>13} {'their disp':>10} {'top10 share':>11}"
        )
        for w in np.round(np.arange(0, 1.0001, 0.1), 2):
            v = harvest_volume(records, float(w))
            print(
                f"  {w:5.2f} {v['short']:12.4g} {v['fed']:12.4g} {v['total']:12.4g} "
                f"{v['negative_strata']:10d} {v['affected_unit_years']:8d} "
                f"{v['affected_crop']:13.4g} {v['affected_dispersion']:10.3f} "
                f"{v['top10_share']:11.3f}"
            )
        cross = crossings(records)
        if cross:
            ws = [c[0] for c in cross]
            print(
                f"  crossings w* <= 1: {len(cross)}; w* quantiles 10/50/90%: "
                + "/".join(f"{np.quantile(ws, q):.3f}" for q in (0.1, 0.5, 0.9))
            )
        if seed != 0:
            continue
        # Real runs on the grid: the recorded curve must equal the run's sidecar volume.
        print("  real runs vs exact curve:")
        for w in (0.1, 0.25, 0.5, 0.75, 1.0):
            actual, _, _ = actual_volume(scenario_for(name, seed, w, years))
            exact = harvest_volume(records, w)["total"]
            print(
                f"    w={w:4}: run {actual:.10g}  curve {exact:.10g}  rel diff "
                f"{abs(actual - exact) / max(exact, 1):.1e}"
            )
        # Continuity around observed crossings: the crossing stratum's leftover is linear in
        # w and its transfer starts from zero; nothing structural changes.
        chosen = [cross[len(cross) // 4], cross[len(cross) // 2], cross[3 * len(cross) // 4]]
        for w_star, year, unit, slope in chosen:
            print(
                f"  crossing w*={w_star:.4f} (year {year}, {unit}, slope {slope:.3g} kcal/unit w)"
            )
            for w in (w_star - 0.01, w_star, w_star + 0.01):
                actual, sim, obs = actual_volume(scenario_for(name, seed, float(w), years))
                rec = [r for r in obs.food if r["year"] == year and r["unit"] == unit]
                raw = (
                    (
                        rec[0]["leftover"] * rec[0]["share"]
                        + w * rec[0]["gY"] * (rec[0]["field"] - rec[0]["share"])
                    ).min()
                    if rec
                    else float("nan")
                )
                events = Counter(e["event"] for e in sim.state.population.strata_log or [])
                n = sum(len(u.strata) for u in sim.state.units.values())
                print(
                    f"    w={w:.4f}: min raw leftover in that unit-year {raw:12.4g}; total "
                    f"volume {actual:.6g} "
                    f"(curve {harvest_volume(records, float(w))['total']:.6g}); "
                    f"units {len(sim.state.units)}, strata {n}, fusion/fission events "
                    f"{events['fusion_inheritance']}/{events['fission_copy']}, compactions "
                    f"{events['exact_compaction']}"
                )


# ---------------------------------------------------------------- persistence


def regime_run(
    weight: float,
    field_growth: float,
    retention: float,
    agriculture: bool = True,
    deficit: bool = False,
    years: int = 200,
) -> dict[str, Any]:
    """Two strata (share 0.8 / 0.2); the minority starts at field and store position 2.5.

    Prescribed physical flows per year (need 1e6 kcal): crop Y = 0.8 * need * F / F_start,
    forage tops the harvest up to 1.2 * need (fed: leftover L = H - need, all stored) or,
    with ``deficit``, harvest is 0.9 * need and the shortfall is withdrawn from stores.
    """
    need = 1e6
    share = np.array([0.8, 0.2])
    field = np.array([0.5, 0.5])
    store = np.array([0.5, 0.5])
    fields, stores = (10.0 if agriculture else 0.0), 2e5
    if not agriculture:
        field = share.copy()
    out: dict[str, Any] = {"field": [], "store": []}
    for _ in range(years):
        crop = 0.8 * need * fields / 10.0 if agriculture else 0.0
        if deficit:
            harvest = 0.9 * need
            forage = max(harvest - crop, 0.0)
            harvest = crop + forage
            withdrawn = min(need - harvest, stores) if harvest < need else 0.0
            stored, leftover, fed = 0.0, 0.0, harvest >= need
        else:
            forage = max(1.2 * need - crop, 0.0)
            harvest = crop + forage
            leftover = harvest - need
            stored, withdrawn, fed = leftover, 0.0, True
        opening = stores
        closing = (opening - withdrawn + stored) * retention
        accounts = FoodAccounts(
            (),
            *(np.array([v]) for v in (opening, stored, withdrawn, closing)),
            harvest=np.array([harvest]),
            crop=np.array([crop]),
            forage=np.array([forage]),
            leftover=np.array([leftover]),
            fed=np.array([fed]),
        )
        flows = food_flows(share, field, store, weight, accounts, 0)
        store = store_claims_after_year(
            share, store, opening, stored, closing, flows.stored_correction
        )
        stores = closing
        new_fields = fields * (1 + field_growth)
        field = field_claims_after_change(share, field, fields, new_fields)
        if new_fields == 0:
            field = share.copy()
        fields = new_fields
        out["field"].append(float(field[1] / share[1]))
        out["store"].append(float(store[1] / share[1]))
    return out


def halving(series: list[float], start: float = 2.5) -> str:
    target = 1 + (start - 1) / 2
    for year, value in enumerate(series, 1):
        if abs(value - 1) <= abs(target - 1):
            return f"{year}"
    return f">{len(series)}"


def persistence() -> None:
    regimes = {
        "expanding fields +5%/y (r=0.8)": dict(field_growth=0.05, retention=0.8),
        "expanding fields +1%/y (r=0.8)": dict(field_growth=0.01, retention=0.8),
        "stable fields (r=0.8)": dict(field_growth=0.0, retention=0.8),
        "shrinking fields -5%/y (r=0.8)": dict(field_growth=-0.05, retention=0.8),
        "stable, high store turnover (r=0.3)": dict(field_growth=0.0, retention=0.3),
        "stable, low store turnover (r=0.97)": dict(field_growth=0.0, retention=0.97),
        "stable, deficit years (withdrawals)": dict(field_growth=0.0, retention=0.8, deficit=True),
        "no agriculture (r=0.8)": dict(field_growth=0.0, retention=0.8, agriculture=False),
    }
    print("minority (share 0.2) starting at field and store position 2.5; prescribed flows")
    print(
        f"{'regime':40}{'w':>6}{'field halving y':>16}{'field @50y':>11}"
        f"{'store halving y':>16}{'store @50y':>11}{'store @200y':>12}"
    )
    for label, kwargs in regimes.items():
        for weight in (0.0, 0.5, 1.0):
            r = regime_run(weight, **kwargs)  # type: ignore[arg-type]
            print(
                f"{label:40}{weight:>6}{halving(r['field']):>16}{r['field'][49]:>11.3f}"
                f"{halving(r['store']):>16}{r['store'][49]:>11.3f}{r['store'][-1]:>12.3f}"
            )
    # Real runs: halving times of individual strata deviations (ids persist until merged).
    for weight in (0.0, 1.0):
        print(
            f"\nreal runs, neolithic 600 y seeds {SEEDS}, w={weight}: stratum deviation lifetimes"
        )
        stats: dict[str, list[tuple[str, int]]] = {"field": [], "store": []}
        for seed in SEEDS:
            track: dict[int, dict[str, Any]] = {}

            def each_year(sim: Simulator) -> None:
                year = sim.state.year
                for unit in sim.state.units.values():
                    if len(unit.strata) == 1:
                        continue
                    pos = positions(unit.strata)
                    for k, sid in enumerate(unit.strata.stratum_id.tolist()):
                        entry = track.setdefault(sid, {"first": year, "series": []})
                        entry["series"].append((year, abs(pos[k, 0] - 1), abs(pos[k, 1] - 1)))

            drive(scenario_for("neolithic", seed, weight), Observer(), each_year)
            for entry in track.values():
                series = entry["series"]
                for d, name in ((1, "field"), (2, "store")):
                    start = series[0][d]
                    if start < 0.05:
                        continue
                    end = next((y for y, *dev in series if dev[d - 1] <= start / 2), None)
                    if end is not None:
                        stats[name].append(("halved", end - series[0][0]))
                    else:
                        stats[name].append(("ended first", series[-1][0] - series[0][0] + 1))
        for name, values in stats.items():
            halved = [t for kind, t in values if kind == "halved"]
            ended = [t for kind, t in values if kind == "ended first"]
            print(
                f"  {name}: {len(values)} strata starting |pos-1| >= 0.05; halved {len(halved)} "
                f"(years median {np.median(halved) if halved else float('nan'):.0f}, p90 "
                f"{np.quantile(halved, 0.9) if halved else float('nan'):.0f}); ended unhalved "
                f"{len(ended)} (lifetime median {np.median(ended) if ended else float('nan'):.0f}, "
                f"p90 {np.quantile(ended, 0.9) if ended else float('nan'):.0f})"
            )


# ---------------------------------------------------------------- sources


def sources() -> None:
    for name in ("neolithic", "pressure+cult"):
        print(f"\n=== {name}, seeds {SEEDS}, w=0 ===")
        fusions: list[dict[str, float]] = []
        for seed in SEEDS:
            observer = Observer()
            drive(scenario_for(name, seed, 0.0), observer)
            fusions += observer.fusions

        def share(test: Callable[[dict[str, float]], bool]) -> str:
            return f"{sum(map(test, fusions))} ({np.mean([test(f) for f in fusions]):.2f})"

        print(f"  fusions: {len(fusions)}")
        print(f"  with fields (any predecessor): {share(lambda f: f['field_stock'] > 0)}")
        print(f"  field per person differs > 1%: {share(lambda f: f['field_ratio'] > 1.01)}")
        print(f"  field per person ratio >= 2: {share(lambda f: f['field_ratio'] >= 2)}")
        print(f"  with stores: {share(lambda f: f['store_stock'] > 0)}")
        print(f"  store per person differs > 1%: {share(lambda f: f['store_ratio'] > 1.01)}")
        print(f"  store per person ratio >= 2: {share(lambda f: f['store_ratio'] >= 2)}")
    # Homogeneous control: no fusion (and no aggregation), maximal w.
    for name in ("neolithic", "pressure+cult"):
        scenario = scenario_for(name, 0, 1.0).with_settings({"mechanisms.fusion": False})
        most = [1]

        def each_year(sim: Simulator) -> None:
            most[0] = max(
                most[0], max((len(u.strata) for u in sim.state.units.values()), default=1)
            )

        sim, _ = drive(scenario, Observer(), each_year)
        flows = sim.state.population.strata_flows or []
        print(
            f"\nno fusion, {name} seed 0, w=1: max strata in any unit-year {most[0]}; "
            f"flow rows {len(flows)}; final units {len(sim.state.units)}; "
            f"final dev {people_weighted_dev(sim)}"
        )


# ---------------------------------------------------------------- capacity stress


def capacity(cases: int = 200) -> None:
    rng = np.random.default_rng(20261003)  # probe-only randomness for stress configurations
    changed = 0
    w1_field_wasserstein: list[float] = []
    exact_loss: dict[float, list[float]] = defaultdict(list)
    for _ in range(cases):
        parts = []
        for _side in range(2):
            share = rng.dirichlet(np.ones(DEFAULT_MAX_STRATA))
            field = rng.dirichlet(np.ones(DEFAULT_MAX_STRATA))
            store = rng.dirichlet(np.ones(DEFAULT_MAX_STRATA))
            parts.append(
                (
                    share,
                    field,
                    store,
                    float(rng.uniform(50, 200)),
                    float(rng.uniform(2, 20)),
                    float(rng.uniform(1e5, 1e6)),
                )
            )
        exact = None
        results = {}
        for weight in WEIGHTS:
            blocks = []
            for share, field, store, people, fields, stores in parts:
                need = people * 7e5
                crop = 0.9 * need
                harvest = 1.3 * need
                leftover = harvest - need
                closing = (stores + leftover) * 0.8
                acc = FoodAccounts(
                    (),
                    *(np.array([v]) for v in (stores, leftover, 0.0, closing)),
                    harvest=np.array([harvest]),
                    crop=np.array([crop]),
                    forage=np.array([harvest - crop]),
                    leftover=np.array([leftover]),
                    fed=np.array([True]),
                )
                flows = food_flows(share, field, store, weight, acc, 0)
                new_store = store_claims_after_year(
                    share, store, stores, leftover, closing, flows.stored_correction
                )
                block = StrataBlock(
                    {"share": share, "field_claim": field, "store_claim": new_store},
                    np.arange(DEFAULT_MAX_STRATA, dtype=np.int64),
                )
                blocks.append((block, people, (fields, closing)))
            fused = fuse_strata(blocks)
            if exact is None:
                exact = fused
            counter = iter(range(10**6))
            normalized, _ = normalize_strata(
                fused,
                lambda n: np.array([next(counter) for _ in range(n)], dtype=np.int64),
                DEFAULT_MAX_STRATA,
            )
            results[weight] = normalized
            before = weighted_variance(fused.columns["share"], positions(fused)[:, 0])
            after = weighted_variance(normalized.columns["share"], positions(normalized)[:, 0])
            exact_loss[weight].append((before - after) / before)
        base = sorted(field_measure(results[0.0]))
        differs = False
        for weight in WEIGHTS[1:]:
            other = sorted(field_measure(results[weight]))
            if len(other) != len(base) or not np.allclose(other, base, rtol=0, atol=1e-12):
                differs = True
            if weight == 1.0:
                w1_field_wasserstein.append(wasserstein(results[0.0], results[1.0]))
        changed += differs
    print(
        f"stress cases: {cases} fusions of two {DEFAULT_MAX_STRATA}-strata units "
        f"({2 * DEFAULT_MAX_STRATA} -> {DEFAULT_MAX_STRATA})"
    )
    print(
        f"  cases where w changes the represented field distribution: {changed} "
        f"({changed / cases:.2f})"
    )
    print(
        f"  field-position Wasserstein-1 distance, w=1 vs w=0: median "
        f"{np.median(w1_field_wasserstein):.4f}, p90 {np.quantile(w1_field_wasserstein, 0.9):.4f}, "
        f"max {max(w1_field_wasserstein):.4f}"
    )
    for weight in WEIGHTS:
        values = exact_loss[weight]
        print(
            f"  w={weight}: field-variance lost to coalescence (vs exact fused): median "
            f"{np.median(values):.3f}, p90 {np.quantile(values, 0.9):.3f}"
        )


def wasserstein(a: StrataBlock, b: StrataBlock) -> float:
    """1-D Wasserstein-1 distance between share-weighted field-position distributions."""

    def cdf_points(block: StrataBlock) -> tuple[np.ndarray, np.ndarray]:
        pos = positions(block)[:, 0]
        order = np.argsort(pos)
        return pos[order], np.cumsum(block.columns["share"][order])

    pa, ca = cdf_points(a)
    pb, cb = cdf_points(b)
    grid = np.unique(np.concatenate([pa, pb]))
    fa = np.array([ca[pa <= x][-1] if (pa <= x).any() else 0.0 for x in grid])
    fb = np.array([cb[pb <= x][-1] if (pb <= x).any() else 0.0 for x in grid])
    return float((np.abs(fa - fb)[:-1] * np.diff(grid)).sum())


# ---------------------------------------------------------------- field divergence across w


def fieldgap_job(job: tuple[str, int]) -> dict[str, Any]:
    """Per unit-year Wasserstein-1 distance between the field-position distributions at
    w = 0 and w = 1, and each unit-year's own field dispersion for scale."""
    name, seed = job
    snapshots: dict[float, dict[tuple[int, str], StrataBlock]] = {}
    for weight in (0.0, 1.0):
        blocks: dict[tuple[int, str], StrataBlock] = {}

        def each_year(sim: Simulator) -> None:
            for unit in sim.state.units.values():
                if len(unit.strata) > 1:
                    block = unit.strata  # a view of the table row: copy it
                    blocks[(sim.state.year, unit.id)] = StrataBlock(
                        {k: v.copy() for k, v in block.columns.items()}, block.stratum_id.copy()
                    )

        drive(scenario_for(name, seed, weight), Observer(), each_year)
        snapshots[weight] = blocks
    gaps, scales = [], []
    for key in snapshots[0.0].keys() | snapshots[1.0].keys():
        a = snapshots[0.0].get(key, StrataBlock.neutral())
        b = snapshots[1.0].get(key, StrataBlock.neutral())
        gap = wasserstein(a, b)
        if gap > 1e-12:
            gaps.append(gap)
            pos = positions(a)[:, 0]
            scales.append(float((a.columns["share"] * np.abs(pos - 1)).sum()))
    return {
        "name": name,
        "seed": seed,
        "unit_years": len(snapshots[0.0]),
        "gaps": gaps,
        "scales": scales,
    }


def fieldgap(jobs: int) -> None:
    work = [(name, seed) for name in ("neolithic", "pressure+cult") for seed in SEEDS]
    with Pool(jobs) as pool:
        results = pool.map(fieldgap_job, work, chunksize=1)
    for name in ("neolithic", "pressure+cult"):
        runs = [r for r in results if r["name"] == name]
        gaps = [g for r in runs for g in r["gaps"]]
        scales = [s for r in runs for s in r["scales"]]
        total = sum(r["unit_years"] for r in runs)
        rel = [g / s for g, s in zip(gaps, scales, strict=True) if s > 0]
        print(
            f"{name}: multi-strata unit-years {total}; field distribution differs (W1 > 1e-12) "
            f"in {len(gaps)} ({len(gaps) / total:.3f})"
        )
        if gaps:
            print(
                "  W1(w=1 vs w=0) quantiles 50/90/99/max: "
                + "/".join(f"{np.quantile(gaps, q):.3g}" for q in (0.5, 0.9, 0.99))
                + f"/{max(gaps):.3g}"
            )
            print(
                "  relative to the unit's mean |field pos - 1| (w=0) 50/90/99: "
                + "/".join(f"{np.quantile(rel, q):.3g}" for q in (0.5, 0.9, 0.99))
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "mode",
        choices=("representation", "nonlinear", "persistence", "sources", "capacity", "fieldgap"),
    )
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.mode in ("representation", "fieldgap"):
        globals()[args.mode](args.jobs)
    else:
        globals()[args.mode]()


if __name__ == "__main__":
    main()
