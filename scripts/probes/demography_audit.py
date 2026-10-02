"""Demographic and agricultural diagnostic audit of reference runs (observation only).

Why does the frozen model keep growing at roughly 1%/yr for centuries? This probe runs
matched seeds of a scenario and derives, from existing metrics, events and the state
between steps (no simulator state is added, and no random stream is touched):

- milestones: population crossing 1k/5k/10k/20k; first ``plant_cultivation`` invention and
  adoption; first cultivation; farm share of harvest reaching 10/25/50%;
- per period: crude birth and death rates, growth, fertility realization (births over the
  births expected at full fertility from the cohorts entering demography), mortality excess
  (deaths over those expected from baseline hazards alone), crowding's share of deaths, food
  ratio, harvest-to-need, farm share, occupied cells, people per occupied cell;
- interruptions: years of decline, the largest decline from a running maximum;
- the life table's intrinsic (Lotka) growth rate with full fertility and baseline
  mortality, the growth the model would show if food and crowding never bound.

Usage:
    uv run python scripts/probes/demography_audit.py --seeds 0 1 2 3 --years 600 \
        --out <dir>
"""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.metrics.recorder import MetricsRecorder
from madexplorer.species.life_history import LifeTables

POPULATION_MARKS = (1_000, 5_000, 10_000, 20_000)
FARM_SHARE_MARKS = (0.10, 0.25, 0.50)
PERIOD_YEARS = 50


def lotka_r(tables: LifeTables, female_birth_fraction: float, offspring: int) -> float:
    """Intrinsic growth rate r solving sum_x e^{-r x} l(x) m(x) = 1 (female line)."""
    survival = np.exp(-tables.hazard)  # annual survival by age
    alive = np.concatenate([[1.0], np.cumprod(survival)[:-1]])  # l(x) at the start of age x
    daughters = alive * survival * tables.fertility * offspring * female_birth_fraction
    ages = np.arange(daughters.size) + 1.0  # births at the end of the year of age x

    def excess(r: float) -> float:
        return float((np.exp(-r * ages) * daughters).sum()) - 1.0

    low, high = -0.2, 0.2
    for _ in range(100):
        mid = 0.5 * (low + high)
        low, high = (mid, high) if excess(mid) > 0 else (low, mid)
    return 0.5 * (low + high)


def _expected(sim: Simulator) -> tuple[float, float]:
    """Births at full fertility and deaths at baseline hazards, from the cohorts now
    (exactly the cohorts the next step's demography starts from)."""
    births = deaths = 0.0
    for unit in sim.state.units.values():
        tables = sim.tables[unit.species_id]
        n = tables.hazard.size
        q = 1.0 - np.exp(-tables.hazard)
        females, males = unit.females[:n], unit.males[:n]
        deaths += float(((females + males) * q).sum())
        births += float((females * (1.0 - q) * tables.fertility).sum())
    return births, deaths


def run(path: str, seed: int, years: int) -> dict[str, Any]:
    """Run one seed and return its yearly rows and milestones."""
    scenario = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=years)
    sim = Simulator(scenario)
    recorder = MetricsRecorder(scenario, 10**6)
    rows = []
    for _ in range(years):
        expected_births, baseline_deaths = _expected(sim)
        ctx = sim.step()
        row = recorder.record(sim.state, ctx)
        row["expected_full_births"] = expected_births
        row["baseline_deaths"] = baseline_deaths
        row["crowding_deaths_expected"] = ctx.ledger.crowding_deaths_expected
        rows.append(row)
        if sim.state.total_population() == 0:
            break
    first: dict[str, int | None] = {}
    for kind, key in (("invention", "invented"), ("technology_adopted", "adopted")):
        years_ = [
            e.year
            for e in sim.events
            if e.kind == kind and e.data.get("technology") == "plant_cultivation"
        ]
        first[f"plant_cultivation_{key}"] = min(years_) if years_ else None
    started = [e.year for e in sim.events if e.kind == "cultivation_started"]
    first["cultivation_started"] = min(started) if started else None
    profile = next(iter(scenario.species.values()))
    lh = profile.life_history
    r = lotka_r(sim.tables[profile.id], 1.0 - lh.male_birth_fraction, lh.offspring_per_birth)
    return {
        "seed": seed,
        "rows": rows,
        "first": first,
        "lotka_r": r,
        "founders": sum(p.population for p in scenario.config.initial_populations),
    }


def _first_year(rows: list[dict[str, Any]], key: str, threshold: float) -> int | None:
    for row in rows:
        if float(row.get(key, 0.0)) >= threshold:
            return int(row["year"])
    return None


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Milestones, per-period diagnostics and interruptions of one run."""
    rows = result["rows"]
    pop = np.array([r["population"] for r in rows], dtype=np.float64)
    founders = result["founders"]
    years = np.array([r["year"] for r in rows])
    summary: dict[str, Any] = {
        "seed": result["seed"],
        "founding_population": founders,
        "final_year": int(years[-1]),
        "final_population": int(pop[-1]),
        "annualized_growth": math.log(pop[-1] / founders) / years[-1],
        "lotka_r_full_fertility_baseline_mortality": result["lotka_r"],
        "milestones": {
            **{f"population_{m}": _first_year(rows, "population", m) for m in POPULATION_MARKS},
            **result["first"],
            "first_farm_harvest": _first_year(rows, "farm_share_of_harvest", 1e-12),
            **{
                f"farm_share_{int(100 * m)}pct": _first_year(rows, "farm_share_of_harvest", m)
                for m in FARM_SHARE_MARKS
            },
        },
    }
    running_max = np.maximum.accumulate(pop)
    summary["interruptions"] = {
        "declining_years": int((np.diff(pop) < 0).sum()),
        "largest_drawdown": float(1.0 - (pop / running_max).min()),
        "largest_drawdown_year": int(years[int(np.argmin(pop / running_max))]),
    }
    periods = []
    for start in range(0, int(years[-1]), PERIOD_YEARS):
        window = [r for r in rows if start < r["year"] <= start + PERIOD_YEARS]
        if not window:
            continue
        people = sum(r["population"] for r in window)
        births = sum(r["births"] for r in window)
        deaths = sum(r["deaths"] for r in window)
        first_pop = window[0]["population"] - window[0]["births"] + window[0]["deaths"]

        def weighted(key: str, rows_: list[dict[str, Any]] = window) -> float:
            values = [(float(r[key]), r["population"]) for r in rows_ if key in r]
            total = sum(w for _, w in values)
            return sum(v * w for v, w in values) / total if total else float("nan")

        cells = np.mean([r["occupied_cells"] for r in window])
        periods.append(
            {
                "years": f"{start + 1}-{start + PERIOD_YEARS}",
                "end_population": window[-1]["population"],
                "growth_per_year": math.log(window[-1]["population"] / max(first_pop, 1))
                / len(window),
                "cbr": 1000.0 * births / people,
                "cdr": 1000.0 * deaths / people,
                "fertility_realization": births
                / max(sum(r["expected_full_births"] for r in window), 1e-9),
                "mortality_excess": deaths / max(sum(r["baseline_deaths"] for r in window), 1e-9),
                "crowding_death_share": sum(r["crowding_deaths_expected"] for r in window)
                / max(deaths, 1),
                "food_ratio": weighted("mean_food_ratio"),
                "energy_deficit": weighted("mean_energy_deficit"),
                "harvest_to_need": float(np.mean([r["harvest_to_need"] for r in window])),
                "farm_share": float(np.mean([r.get("farm_share_of_harvest", 0) for r in window])),
                "occupied_cells": float(cells),
                "people_per_cell": float(np.mean([r["population"] for r in window]) / cells),
                "sedentary_share": weighted("sedentary_share"),
            }
        )
    summary["periods"] = periods
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="scenarios/mvp2_neolithic.yaml")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--years", type=int, default=600)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with ProcessPoolExecutor(args.jobs) as pool:
        results = list(
            pool.map(
                run, [args.scenario] * len(args.seeds), args.seeds, [args.years] * len(args.seeds)
            )
        )
    summaries = [summarize(r) for r in results]
    text = json.dumps(summaries, indent=1, default=float)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "summary.json").write_text(text)
        for result in results:
            (args.out / f"rows_seed{result['seed']}.json").write_text(
                json.dumps(result["rows"], default=float)
            )
    print(text)


if __name__ == "__main__":
    main()
