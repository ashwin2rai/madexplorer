# The report tables keep one entry per line.
# ruff: noqa: E501
"""MVP 2.1 vs MVP 2.2 (fertility input): equivalence and paired stochastic comparison.

MVP 3 Stage 5J. MVP 2.2 is a candidate model pending scientific approval.

``equivalence``  production MVP 2.2 (``scenarios/mvp2_2_*.yaml``) against the Stage 5I
                 experimental H1 branch, run fresh on the MVP 2.1 scenarios: per-year
                 component hashes and final physical digests must be identical. Also checks
                 that production MVP 2.1 equals the experimental H0 branch.
``run``          the prespecified paired experiment: every seed in ``--seeds`` (default
                 0-31) of neolithic (600 y) and pressure + cultivation (400 y) under MVP 2.1
                 and MVP 2.2, production code only; one file per run.
``analyse``      paired statistics (median, mean, IQR, range, share H1 > H0, bootstrap
                 intervals over seed pairs), granaries histories and outliers.

Usage:
    uv run python scripts/probes/fertility_version_comparison.py equivalence [--jobs 2] [--seeds 0 1 ...]
    uv run python scripts/probes/fertility_version_comparison.py run [--jobs 2] [--seeds ...] --out DIR
    uv run python scripts/probes/fertility_version_comparison.py analyse --load DIR
"""

import argparse
import pickle
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import fertility_intake_experiment as experiment
from _common import physical_digest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.metrics.recorder import MetricsRecorder

SCENARIOS = {  # name: (MVP 2.1 file, MVP 2.2 file, horizon, settings)
    "neolithic": ("scenarios/mvp2_neolithic.yaml", "scenarios/mvp2_2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_pressure.yaml", "scenarios/mvp2_2_pressure.yaml", 400,
                      {"mechanisms.cultivation": True}),
}  # fmt: skip
VERSIONS = ("2.1", "2.2")
PRESPECIFIED_SEEDS = tuple(range(32))
TECHS = (
    "storage_pits",
    "plant_cultivation",
    "seed_selection",
    "ground_stone_axes",
    "fallow_rotation",
    "granaries",
)


def scenario(name: str, version: str, seed: int, years: int | None = None) -> Scenario:
    v21, v22, horizon, settings = SCENARIOS[name]
    path = v21 if version == "2.1" else v22
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=years or horizon)
    return base.with_settings({**settings, "strata.field_output_claim_weight": 0.0})


# ---------------------------------------------------------------- equivalence


def _trajectory(sim: Simulator, years: int) -> tuple[list[dict[str, str]], str]:
    hashes = []
    for _ in range(years):
        sim.step()
        hashes.append(experiment._hashes(sim))
        if not sim.state.units:
            break
    return hashes, physical_digest(sim)


def equivalence_job(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    years = SCENARIOS[name][2]
    out: dict[str, Any] = {"name": name, "seed": seed}
    for version, mode in (("2.1", "h0"), ("2.2", "h1")):
        prod = Simulator(scenario(name, version, seed))
        assert prod.scenario.config.mechanisms.dietary_intake_fertility == (version == "2.2")
        p_hash, p_digest = _trajectory(prod, years)
        exp_sim, branch = experiment.branched_simulator(scenario(name, "2.1", seed), mode)
        e_hash, e_digest = _trajectory(exp_sim, years)
        div, parts = experiment.first_divergence(p_hash, e_hash)
        out[version] = {"digest_equal": p_digest == e_digest, "first_divergence": div, "parts": parts,
                        "years": len(p_hash), "restore_failures": branch.restore_failures if branch else 0}  # fmt: skip
    return out


# ---------------------------------------------------------------- paired runs


def run_job(spec: tuple[str, str, int]) -> dict[str, Any]:
    name, version, seed = spec
    sc = scenario(name, version, seed)
    sim = Simulator(sc)
    recorder = MetricsRecorder(sc, 10**9, light=False)
    tables = sim.context().tables
    reproductive = {sid: t.female_reproductive for sid, t in tables.items()}
    keep = ("population", "births", "deaths", "units", "fissions", "fusions", "extinctions", "migrations", "inventions",
            "adoptions", "cultivated_ha", "stores_per_capita_kcal", "mean_energy_deficit", "mean_food_ratio",
            "trade_volume_kcal", "transport_loss_kcal", "farm_share_of_harvest", "harvest_to_need",
            "tech_share_granaries", "tech_share_storage_pits", "tech_share_plant_cultivation", "plant_stock_fraction",
            "game_stock_fraction", "mean_group_size")  # fmt: skip
    rows = []
    started = time.perf_counter()
    for _ in range(sc.config.simulation.n_years):
        ctx = sim.step()
        row = recorder.record(sim.state, ctx)
        fertile = 0
        for u in sim.state.units.values():
            r = reproductive[u.species_id]
            n = min(r.size, u.females.size)
            fertile += int((u.females[:n] * (r[:n] > 0)).sum())
        rows.append({**{k: row[k] for k in keep}, "year": row["year"], "fertile_females": fertile,
                     "harvest_kcal": ctx.ledger.harvest_kcal, "need_kcal": ctx.ledger.need_kcal})  # fmt: skip
        if not sim.state.units:
            break
    firsts: dict[str, int] = {}
    for e in sim.events:
        tech = e.data.get("technology")
        if e.kind in ("invention", "technology_adopted") and tech in TECHS and tech not in firsts:
            firsts[tech] = e.year
    return {"name": name, "version": version, "seed": seed, "rows": rows, "firsts": firsts,
            "digest": physical_digest(sim), "seconds": time.perf_counter() - started,
            "config_hash": sc.config_hash(), "switch": sc.config.mechanisms.dietary_intake_fertility}  # fmt: skip


# ---------------------------------------------------------------- analysis


def bootstrap(values: np.ndarray, stat: Any, n: int = 10_000, seed: int = 1) -> tuple[float, float]:
    """95 % percentile interval of ``stat`` over resampled seed pairs."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, values.size, size=(n, values.size))
    boot = np.array([stat(values[i]) for i in idx])
    return float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def describe(label: str, a: np.ndarray, b: np.ndarray, relative: bool = True) -> None:
    diff = b - a
    line = (f"   {label:<36} H0 med {np.median(a):10.4g}  H1 med {np.median(b):10.4g}  diff mean {diff.mean():+10.4g} "
            f"med {np.median(diff):+10.4g} IQR [{np.quantile(diff, 0.25):+.3g}, {np.quantile(diff, 0.75):+.3g}] "
            f"range [{diff.min():+.3g}, {diff.max():+.3g}]  H1>H0 {np.mean(diff > 0):.2f} (= {np.mean(diff == 0):.2f})")  # fmt: skip
    if relative and (a > 0).all():
        ratio = b / a
        lo, hi = bootstrap(ratio, np.median)
        line += f"  ratio med {np.median(ratio):.3f} [{lo:.3f}, {hi:.3f}] range [{ratio.min():.3f}, {ratio.max():.3f}]"
    print(line)


def analyse_scenario(
    name: str, runs: dict[tuple[str, int], dict[str, Any]], seeds: list[int]
) -> None:
    pairs = [
        (runs[("2.1", s)], runs[("2.2", s)])
        for s in seeds
        if ("2.1", s) in runs and ("2.2", s) in runs
    ]
    print(
        f"\n=== {name}: {len(pairs)} seed pairs (seeds {seeds[0]}-{seeds[-1]}), horizon {SCENARIOS[name][2]} y"
    )
    print(
        f"   switch: MVP 2.1 runs {sorted({p[0]['switch'] for p in pairs})}, MVP 2.2 runs {sorted({p[1]['switch'] for p in pairs})}"
    )

    def final(r: dict[str, Any], k: str) -> float:
        return float(r["rows"][-1][k])

    def total(r: dict[str, Any], k: str) -> float:
        return float(sum(row[k] for row in r["rows"]))

    def tail(r: dict[str, Any], k: str, n: int = 50) -> float:
        return float(np.mean([row[k] for row in r["rows"][-n:]]))

    metrics = [
        ("final population", lambda r: final(r, "population"), True),
        ("cumulative births", lambda r: total(r, "births"), True),
        ("cumulative deaths", lambda r: total(r, "deaths"), True),
        ("final reproductive-age females", lambda r: final(r, "fertile_females"), True),
        ("extinction events", lambda r: total(r, "extinctions"), False),
        ("final units", lambda r: final(r, "units"), True),
        ("fission events", lambda r: total(r, "fissions"), True),
        ("fusion events", lambda r: total(r, "fusions"), True),
        ("migrations", lambda r: total(r, "migrations"), True),
        ("cultivated ha (final 50 y)", lambda r: tail(r, "cultivated_ha"), True),
        ("food production kcal (cumulative)", lambda r: total(r, "harvest_kcal"), True),
        ("harvest / need (final 50 y)", lambda r: tail(r, "harvest_to_need"), True),
        ("stores per capita (final 50 y)", lambda r: tail(r, "stores_per_capita_kcal"), True),
        ("mean energy deficit (final 50 y)", lambda r: tail(r, "mean_energy_deficit"), False),
        ("trade volume kcal (cumulative)", lambda r: total(r, "trade_volume_kcal"), True),
        ("inventions", lambda r: total(r, "inventions"), True),
        ("adoptions", lambda r: total(r, "adoptions"), True),
        ("plant stock fraction (final 50 y)", lambda r: tail(r, "plant_stock_fraction"), True),
        ("game stock fraction (final 50 y)", lambda r: tail(r, "game_stock_fraction"), True),
    ]
    print(
        "-- paired outcomes (H0 = MVP 2.1, H1 = MVP 2.2); ratio interval: bootstrap 95 % of the median over seed pairs"
    )
    for label, f, rel in metrics:
        a = np.array([f(p[0]) for p in pairs])
        b = np.array([f(p[1]) for p in pairs])
        describe(label, a, b, rel)
    horizon = SCENARIOS[name][2]
    print("-- population ratio H1/H0 over time: median [IQR] and share > 1")
    for t in sorted({25, 50, 100, 200, 300, 400, horizon}):
        vals = np.array([p[1]["rows"][t - 1]["population"] / p[0]["rows"][t - 1]["population"]
                         for p in pairs if len(p[0]["rows"]) >= t and len(p[1]["rows"]) >= t])  # fmt: skip
        if vals.size:
            print(
                f"   year {t:>3}: {np.median(vals):.3f} [{np.quantile(vals, 0.25):.3f}, {np.quantile(vals, 0.75):.3f}] share > 1 {np.mean(vals > 1):.2f}, = 1 {np.mean(vals == 1):.2f}"
            )
    # direct effect: births in the years before any divergence vs after
    print("-- granaries (an outcome of the intervention; descriptive only)")
    g0 = [p[0]["firsts"].get("granaries") for p in pairs]
    g1 = [p[1]["firsts"].get("granaries") for p in pairs]
    both = sum(a is not None and b is not None for a, b in zip(g0, g1, strict=True))
    only0 = sum(a is not None and b is None for a, b in zip(g0, g1, strict=True))
    only1 = sum(a is None and b is not None for a, b in zip(g0, g1, strict=True))
    print(
        f"   reached: H0 {sum(x is not None for x in g0)}/{len(pairs)}, H1 {sum(x is not None for x in g1)}/{len(pairs)}; both {both}, H0 only {only0}, H1 only {only1}, neither {len(pairs) - both - only0 - only1}"
    )
    disc = only0 + only1
    if disc:
        from math import comb

        k = min(only0, only1)
        p = min(1.0, 2 * sum(comb(disc, i) for i in range(k + 1)) / 2**disc)
        print(f"   exact McNemar (discordant pairs {disc}): two-sided p = {p:.3f}")
    years0 = [x for x in g0 if x is not None]
    years1 = [x for x in g1 if x is not None]
    if years0 or years1:
        print(f"   first granaries year: H0 {sorted(years0)}; H1 {sorted(years1)}")
    for p in pairs:
        a, b = p[0]["firsts"].get("granaries"), p[1]["firsts"].get("granaries")
        if a is None and b is None:
            continue
        s = p[0]["seed"]
        t0 = min(x for x in (a, b) if x is not None)
        pre = [
            (r["rows"][t0 - 11]["population"], r["rows"][t0 - 11]["stores_per_capita_kcal"])
            for r in p
            if len(r["rows"]) > t0 - 11 >= 0
        ]
        fin = (final(p[0], "population"), final(p[1], "population"))
        st = (tail(p[0], "stores_per_capita_kcal"), tail(p[1], "stores_per_capita_kcal"))
        print(f"   seed {s}: granaries H0 {a} / H1 {b}; 10 y before first: population {pre[0][0]:.0f} / {pre[1][0]:.0f}, stores pc {pre[0][1]:.3g} / {pre[1][1]:.3g}; "
              f"final population {fin[0]:.0f} / {fin[1]:.0f} ({fin[1] / fin[0]:.3f}); stores pc final 50 y {st[0]:.3g} / {st[1]:.3g}")  # fmt: skip
    print("-- other technology first years (median H0 / H1; reached H0 / H1)")
    for tech in TECHS:
        a = [p[0]["firsts"].get(tech) for p in pairs]
        b = [p[1]["firsts"].get(tech) for p in pairs]
        aa, bb = [x for x in a if x is not None], [x for x in b if x is not None]
        print(
            f"   {tech:<18} {np.median(aa) if aa else float('nan'):6.0f} / {np.median(bb) if bb else float('nan'):6.0f}; {len(aa)} / {len(bb)}"
        )
    print("-- largest final-population differences (outliers kept)")
    ratios = sorted(
        ((final(p[1], "population") / final(p[0], "population"), p) for p in pairs),
        key=lambda x: x[0],
    )
    for ratio, p in ratios[:2] + ratios[-3:]:
        s = p[0]["seed"]
        div = next(
            (
                t
                for t, (x, y) in enumerate(zip(p[0]["rows"], p[1]["rows"], strict=False))
                if x["births"] != y["births"]
            ),
            None,
        )
        print(f"   seed {s}: ratio {ratio:.3f}; first birth difference year {None if div is None else div + 1}; granaries {p[0]['firsts'].get('granaries')} / {p[1]['firsts'].get('granaries')}; "
              f"plant_cultivation {p[0]['firsts'].get('plant_cultivation')} / {p[1]['firsts'].get('plant_cultivation')}; final stores pc {tail(p[0], 'stores_per_capita_kcal'):.3g} / {tail(p[1], 'stores_per_capita_kcal'):.3g}")  # fmt: skip
    print("-- first year with different births (start of divergence): " + ", ".join(
        str(next((t + 1 for t, (x, y) in enumerate(zip(p[0]["rows"], p[1]["rows"], strict=False)) if x["births"] != y["births"]), "none"))
        for p in pairs))  # fmt: skip


def analyse_main(load: Path) -> None:
    runs: dict[str, dict[tuple[str, int], dict[str, Any]]] = defaultdict(dict)
    for path in sorted(load.glob("*.pkl")):
        with path.open("rb") as fh:
            r = pickle.load(fh)
        runs[r["name"]][(r["version"], r["seed"])] = r
    for name in SCENARIOS:
        if name in runs:
            seeds = sorted({s for _v, s in runs[name]})
            analyse_scenario(name, runs[name], seeds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("equivalence", "run", "analyse"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(PRESPECIFIED_SEEDS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    args = parser.parse_args()
    if args.mode == "analyse":
        analyse_main(args.load)
        return
    started = time.perf_counter()
    if args.mode == "equivalence":
        specs = [(n, s) for n in SCENARIOS for s in args.seeds]
        ok = True
        with Pool(args.jobs) as workers:
            for r in workers.imap(equivalence_job, specs, chunksize=1):
                for version in VERSIONS:
                    e = r[version]
                    good = (
                        e["digest_equal"]
                        and e["first_divergence"] is None
                        and e["restore_failures"] == 0
                    )
                    ok &= good
                    print(f"{r['name']} seed {r['seed']} MVP {version} vs experimental {'H0' if version == '2.1' else 'H1'}: "
                          f"{'IDENTICAL' if good else 'DIFFERENT'} ({e['years']} years; first divergence {e['first_divergence']} {e['parts']})", flush=True)  # fmt: skip
        print(
            f"EQUIVALENCE {'IDENTICAL' if ok else 'DIFFERENT'} in {time.perf_counter() - started:.0f} s"
        )
        sys.exit(0 if ok else 1)
    args.out.mkdir(parents=True, exist_ok=True)
    specs = [(n, v, s) for n in SCENARIOS for s in args.seeds for v in VERSIONS
             if not (args.out / f"{n}_{v}_{s}.pkl").exists()]  # fmt: skip
    with Pool(args.jobs) as workers:
        for r in workers.imap_unordered(run_job, specs, chunksize=1):
            print(
                f"done {r['name']} MVP {r['version']} seed {r['seed']} ({r['seconds']:.0f} s) after {time.perf_counter() - started:.0f} s; final population {r['rows'][-1]['population']}",
                flush=True,
            )
            with (args.out / f"{r['name']}_{r['version']}_{r['seed']}.pkl").open("wb") as fh:
                pickle.dump(r, fh)


if __name__ == "__main__":
    main()
