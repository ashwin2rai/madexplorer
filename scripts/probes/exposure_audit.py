"""Technique acquisition and first practice (MVP 3 Stage 5D audit): observation only.

Reads the event stream of plain reference runs (nothing is installed or changed). For
``plant_cultivation`` it asks how units come to hold the technique (invention, adoption
from a contact, or a copy through fission or fusion), how many people a unit has when the
whole unit acquires it at once, and how long it takes until the unit first cultivates.
If cultivation follows acquisition by many years, a within-unit spread of the technique
would rarely constrain who cultivates.

Usage:
    uv run python scripts/probes/exposure_audit.py [--seeds 0 1 2 3]
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, drive, q, scenario_for

TECH = "plant_cultivation"


def audit(name: str, seed: int) -> dict[str, list[float] | Counter[str]]:
    sim, _ = drive(scenario_for(name, seed, 0.0), None)
    holders: set[str] = set()
    acquired: dict[str, tuple[int, str, int]] = {}  # unit -> (year, how, population)
    first_farm: dict[str, int] = {}
    how: Counter[str] = Counter()
    for e in sim.events:
        d = e.data
        if e.kind in ("invention", "technology_adopted") and d.get("technology") == TECH:
            uid = d["unit_id"]
            holders.add(uid)
            acquired[uid] = (e.year, e.kind, int(d.get("population", -1)))  # adoption: not recorded
            how[e.kind] += 1
        elif e.kind == "population_split" and d["unit_id"] in holders:
            holders.add(d["daughter_id"])
            how["fission copy"] += 1
        elif e.kind == "population_merge":
            src, dst = d["unit_id"], d["into_id"]
            if src in holders and dst not in holders:
                holders.add(dst)
                how["fusion union"] += 1
        elif e.kind == "technology_lost" and d.get("technology") == TECH:
            holders.discard(d["unit_id"])
            how["lost"] += 1
        elif e.kind == "cultivation_started":
            first_farm.setdefault(d["unit_id"], e.year)
    lag = [first_farm[u] - y for u, (y, _, _) in acquired.items() if u in first_farm]
    never = sum(1 for u in acquired if u not in first_farm)
    pop = [p for _, k, p in acquired.values() if k == "invention"]
    return {
        "how": how,
        "lag": lag,
        "pop": pop,
        "never": [float(never)],
        "acq": [float(len(acquired))],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = parser.parse_args()
    for name in ("neolithic", "pressure+cult"):
        rs = [audit(name, s) for s in args.seeds]
        how: Counter[str] = Counter()
        for r in rs:
            how.update(r["how"])  # type: ignore[arg-type]
        lag = np.concatenate([np.asarray(r["lag"], float) for r in rs])
        pop = np.concatenate([np.asarray(r["pop"], float) for r in rs])
        acq = sum(r["acq"][0] for r in rs)  # type: ignore[index]
        never = sum(r["never"][0] for r in rs)  # type: ignore[index]
        print(f"\n=== {name}, seeds {args.seeds}")
        print(f"acquisitions of {TECH}: {dict(how)}")
        if pop.size:  # adoption events do not record the population
            print(f"population at invention: {q(pop)}; 1/N p50 {1 / np.median(pop):.3f}")
        same = np.mean(lag == 0) if lag.size else float("nan")
        print(f"years from acquisition to first cultivation: {q(lag)}; same year {same:.2f}")
        print(f"acquired but never cultivated: {never:.0f} of {acq:.0f}")


if __name__ == "__main__":
    main()
