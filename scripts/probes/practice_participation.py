# ruff: noqa: E501
"""Activity demand versus labor capacity (MVP 3 Stage 5A): observation only.

Reads each unit-year's activity hours after the step (units that existed at its start) (``farm_hours``, ``forage_hours``,
``clearing_hours``, ``labor_debt_hours``) against its labor capacity at the start of the year (``labor_hours_columns``:
cohorts x age-labor curve x foraging hours/day x 365) to ask whether finite activity demand
could make practice partial without any randomness. The full-time-equivalent fraction of an
activity is ``hours / capacity``: the population share that would perform it if its hours
were concentrated on people working it with their whole activity budget. Nothing in the model
changes (checked by digest against a plain run).

``controlled`` runs the authoritative learning rule (``knowledge.learning.learn``, neolithic
parameters) for one unit whose cultivation practice is either spread over everyone (the
current assumption) or concentrated on the full-time-equivalent fraction, and reports the
practitioners' agricultural efficiency ``K / (K + K_half)`` that crop yield uses.

Usage:
    uv run python scripts/probes/practice_participation.py controlled
    uv run python scripts/probes/practice_participation.py runs [--jobs 2] [--years N]
"""

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, drive, physical_digest, q, scenario_for

from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import labor_hours_columns

SCENARIOS = ("neolithic", "pressure+cult")
YEARS: int | None = None


def run(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    scenario = scenario_for(name, seed, 0.0, YEARS)
    sim = Simulator(scenario, record_strata=True)
    rows: dict[str, list[Any]] = {
        k: [] for k in ("unit", "year", "fields", "cap", "farm", "forage", "clear", "debt")
    }
    for _ in range(scenario.config.simulation.n_years):
        ctx = sim.context()  # capacity at the start of the year, when hours are allocated
        cols = ctx.columns(sim.state)
        capacity = dict(
            zip((u.id for u in cols.units), labor_hours_columns(cols, ctx).tolist(), strict=True)
        )
        sim.step()
        if not sim.state.units:
            break
        cols = sim.context().columns(sim.state)
        keep = [
            k for k, u in enumerate(cols.units) if u.id in capacity
        ]  # fission daughters are new
        rows["unit"] += [cols.units[k].id for k in keep]
        rows["year"] += [sim.state.year] * len(keep)
        rows["cap"] += [capacity[cols.units[k].id] for k in keep]
        for key, column in (
            ("fields", "fields_ha"),
            ("farm", "farm_hours"),
            ("forage", "forage_hours"),
            ("clear", "clearing_hours"),
            ("debt", "labor_debt_hours"),
        ):
            values = cols.get(column)
            rows[key] += [float(values[k]) for k in keep]
    plain, _ = drive(scenario, None)
    arrays = {k: np.array(v) for k, v in rows.items()}
    return {
        "name": name,
        "seed": seed,
        "a": arrays,
        "neutral": physical_digest(sim) == physical_digest(plain),
    }


def spells(units: np.ndarray, years: np.ndarray, on: np.ndarray) -> list[int]:
    """Lengths of consecutive-year runs with ``on`` per unit."""
    out = []
    order = np.lexsort((years, units))
    run_len, last_unit, last_year = 0, None, None
    for k in order.tolist():
        u, y, flag = units[k], years[k], bool(on[k])
        contiguous = u == last_unit and y == last_year + 1
        if flag and contiguous and run_len:
            run_len += 1
        else:
            if run_len:
                out.append(run_len)
            run_len = 1 if flag else 0
        last_unit, last_year = u, y
    if run_len:
        out.append(run_len)
    return out


def report(results: list[dict[str, Any]]) -> None:
    for name in SCENARIOS:
        rs = [r for r in results if r["name"] == name]
        a = {k: np.concatenate([r["a"][k] for r in rs]) for k in rs[0]["a"]}
        cap = np.where(a["cap"] > 0, a["cap"], np.nan)
        farming = a["fields"] > 0
        farm, forage, clear = a["farm"] / cap, a["forage"] / cap, a["clear"] / cap
        used = (a["farm"] + a["forage"] + a["debt"]) / cap
        print(
            f"\n=== {name}, seeds {[r['seed'] for r in rs]}; observer neutral: {all(r['neutral'] for r in rs)}"
        )
        print(f"unit-years {farming.size}; with fields {int(farming.sum())} ({farming.mean():.2f})")
        print("Fraction of labor capacity (p50/p90/p99/max):")
        print(f"  cultivation, farming unit-years: {q(farm[farming])}")
        print(f"  foraging, all unit-years:        {q(forage[np.isfinite(forage)])}")
        print(f"  foraging, farming unit-years:    {q(forage[farming])}")
        print(f"  clearing (charged next year), farming unit-years: {q(clear[farming])}")
        print(f"  total used (farm + forage + debt), all: {q(used[np.isfinite(used)])}")
        f = farm[farming]
        print(
            f"  farming unit-years with 0 < cultivation FTE < 0.5: {np.mean((f > 0) & (f < 0.5)):.2f}; < 0.25: {np.mean((f > 0) & (f < 0.25)):.2f}; >= 0.9 (labor-capped): {np.mean(f >= 0.9 - 1e-9):.2f}"
        )
        cl = a["clear"] > 0
        print(f"  farming unit-years with clearing: {np.mean(cl[farming]):.2f}")
        idle = 1 - used
        print(f"  unused capacity share, all unit-years: {q(idle[np.isfinite(idle)])}")
        # Spells per run: unit ids repeat across seeds.
        s = [x for r in rs for x in spells(r["a"]["unit"], r["a"]["year"], r["a"]["fields"] > 0)]
        print(f"  cultivation spells per unit (years, p50/p90/p99/max): {q(s)}; n={len(s)}")
        c = [x for r in rs for x in spells(r["a"]["unit"], r["a"]["year"], r["a"]["clear"] > 0)]
        print(f"  consecutive clearing years (p50/p90/p99/max): {q(c)}; n={len(c)}")


def controlled() -> None:
    from madexplorer.config.loader import Scenario
    from madexplorer.knowledge.learning import learn
    from madexplorer.knowledge.system import KnowledgeModel

    scenario = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml")
    assert scenario.knowledge is not None
    model = KnowledgeModel(scenario.knowledge)
    ag, eco = model.index["agriculture"], model.index["ecology"]
    weights = {d: model.system.domains[d].practice for d in model.domains}

    def practice(farm: float, forage: float, plant: float = 0.5) -> np.ndarray:
        shares = {
            "farming": farm,
            "plant_foraging": forage * plant,
            "game_foraging": forage * (1 - plant),
        }
        return np.array(
            [sum(w * shares.get(a, 0.0) for a, w in weights[d].items()) for d in model.domains]
        )

    def efficiency(k: np.ndarray, i: int) -> float:
        return float(k[i] / (k[i] + model.half_efficiency[i]))

    print("One unit of N people; cultivation takes a share s of total labor, foraging the rest.")
    print("spread: everyone farms s; concentrated: a fraction f = s / 0.9 farms 0.9 of their time,")
    print(
        "the rest forage full time (same total hours). Agricultural efficiency after 1/5/20/100 y"
    )
    print("(practitioners' K / (K + K_half)), and the non-practitioners' level at 100 y.")
    print(
        "| N | s | f | spread 1/5/20/100 y | concentrated (practitioners) | non-practitioners 100 y | ecology eff. spread / B at 100 y |"
    )
    print("|---|---|---|---|---|---|---|")
    for n in (20, 40, 80):
        for s in (0.1, 0.25, 0.45, 0.7):
            f = s / 0.9
            k0 = model.initial_levels()
            spread, a, b = k0.copy(), k0.copy(), k0.copy()
            out = {"spread": [], "a": []}
            for year in range(1, 101):
                spread = learn(spread, practice(s, 1 - s), n, model, 1.0, 1.0)
                a = learn(a, practice(0.9, 0.1), round(n * f), model, 1.0, 1.0)
                b = learn(b, practice(0.0, 1.0), n - round(n * f), model, 1.0, 1.0)
                if year in (1, 5, 20, 100):
                    out["spread"].append(efficiency(spread, ag))
                    out["a"].append(efficiency(a, ag))
            fmt = lambda v: "/".join(f"{x:.2f}" for x in v)  # noqa: E731
            print(
                f"| {n} | {s} | {f:.2f} | {fmt(out['spread'])} | {fmt(out['a'])} | {efficiency(b, ag):.2f} | {efficiency(spread, eco):.3f} / {efficiency(b, eco):.3f} |"
            )


def _set_years(years: int | None) -> None:
    global YEARS
    YEARS = years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("controlled", "runs"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--years", type=int)
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    specs = [(name, seed) for name in SCENARIOS for seed in SEEDS]
    with Pool(args.jobs, initializer=_set_years, initargs=(args.years,)) as pool:
        report(pool.map(run, specs, chunksize=1))


if __name__ == "__main__":
    main()
