"""P5 agriculture validation on the intensification-pressure scenario (Tier 2, small).

Runs matched seeds of ``scenarios/mvp2_pressure.yaml`` with cultivation on and off and
prints, per seed and arm, the measures the validation question needs: cultivation
occurrence, farm food share, population, local density, food stress and sedentism. Values
are means over the last ``--window`` years unless marked final.

Usage:
    uv run python scripts/probes/pressure_validation.py --seeds 0 1 --years 400
"""

import argparse
import json
import math
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator

MEASURES = (
    "population",
    "occupied_cells",
    "farm_share_of_harvest",
    "sedentary_share",
    "mean_food_ratio",
    "mean_energy_deficit",
    "crude_death_rate",
    "crowding_death_share",
)


def run(job: tuple[str, int, int, bool, int]) -> dict[str, object]:
    """One seed and arm: window means of MEASURES plus milestones and density."""
    path, seed, years, cultivation, window = job
    scenario = Scenario.from_yaml(path).with_settings({"mechanisms.cultivation": cultivation})
    sim = Simulator(scenario.with_overrides(seed=seed, n_years=years), record_events=False)
    rows = sim.run().metrics
    tail = rows[-window:]
    out: dict[str, object] = {"seed": seed, "cultivation": cultivation}
    for key in MEASURES:
        values = [float(r[key]) for r in tail if not math.isnan(float(r[key]))]
        out[key] = float(np.mean(values)) if values else math.nan
    out["people_per_occupied_cell"] = float(
        np.mean([float(r["population"]) / max(float(r["occupied_cells"]), 1.0) for r in tail])
    )
    out["final_population"] = float(rows[-1]["population"])
    share = np.array([float(r["farm_share_of_harvest"]) for r in rows])
    cultivated = np.array([float(r["cultivated_ha"]) for r in rows])
    first = np.flatnonzero(cultivated > 0)
    out["first_fields_year"] = int(rows[first[0]]["year"]) if first.size else None
    for level in (0.1, 0.25, 0.5):
        hit = np.flatnonzero(share >= level)
        out[f"farm_share_{int(level * 100)}pct_year"] = (
            int(rows[hit[0]]["year"]) if hit.size else None
        )
    out["population_by_century"] = {
        int(r["year"]): int(r["population"]) for r in rows if int(r["year"]) % 100 == 0
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="scenarios/mvp2_pressure.yaml")
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--years", type=int, default=400)
    parser.add_argument("--window", type=int, default=50)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    jobs = [
        (args.scenario, seed, args.years, cultivation, args.window)
        for seed in args.seeds
        for cultivation in (True, False)
    ]
    with ProcessPoolExecutor(args.jobs) as pool:
        results = list(pool.map(run, jobs))
    for result in results:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
