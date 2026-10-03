"""Crop-output attribution sensitivity (MVP 3 Stage 3C): observation only.

Runs the same scenario at several ``strata.field_output_claim_weight`` values (w) from
identical initial conditions and reports continuous measurements, not categories or a
preferred value (objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md §L15):

- people-weighted dispersion (mean |position - 1|) of relative field and store positions,
  and their people-weighted correlation across strata;
- crop attribution moved by field control (sum over strata of |d_i| / 2, kcal) relative to
  the crop of differentiated units;
- cumulative pooling volume by component (harvest, store);
- active strata, exact compactions and capacity coalescences;
- a check that the physical run and the field positions do not depend on w (the field
  dispersion series must be identical up to rounding);
- the cost of the strata accounting hook.

Physical outcomes do not depend on w, so differences between the columns isolate the
accounting consequence of the hypothesis. ``--controlled`` instead follows the three
deterministic Stage 3B fixture units (unequal fields, cross-cutting, unequal stores).

Usage:
    uv run python scripts/probes/crop_attribution_sensitivity.py --seed 0 --years 400
    uv run python scripts/probes/crop_attribution_sensitivity.py --controlled --years 40
"""

import argparse
import time
from collections import Counter
from typing import Any

import numpy as np

import madexplorer.core.simulation as simulation
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.population import strata_accounting
from madexplorer.population.strata import S_MAX, StrataBlock, positions

WEIGHTS = (0.0, 0.25, 0.5, 1.0)
SCENARIO = "scenarios/mvp2_neolithic.yaml"


class Probe:
    """Wraps the accounting hook and the food-flow rule to observe them (nothing changed)."""

    def __init__(self) -> None:
        self.hook_seconds = 0.0
        self.moved_kcal = 0.0  # crop attribution moved by field control: sum |d| / 2
        self.crop_kcal = 0.0  # crop of differentiated units
        hook, flows = strata_accounting.account_strata, strata_accounting.food_flows

        def timed(state: Any, ctx: Any) -> None:
            started = time.perf_counter()
            hook(state, ctx)
            self.hook_seconds += time.perf_counter() - started

        def observed(share: Any, field: Any, store: Any, w: float, acc: Any, rows: Any) -> Any:
            result = flows(share, field, store, w, acc, rows)
            self.moved_kcal += float(np.abs(result.correction).sum()) / 2.0
            if acc.crop is not None:
                self.crop_kcal += float(np.sum(acc.crop[rows]))
            return result

        simulation.account_strata = timed  # type: ignore[assignment]
        strata_accounting.food_flows = observed  # type: ignore[assignment]
        self._restore = (hook, flows)

    def close(self) -> None:
        simulation.account_strata, strata_accounting.food_flows = self._restore


def strata_of(sim: Simulator) -> tuple[np.ndarray, np.ndarray]:
    """People per stratum and (field, store) positions, over all units."""
    people, pos = [], []
    for unit in sim.state.units.values():
        block = unit.strata
        people.append(block.columns["share"] * unit.population)
        pos.append(positions(block))
    return np.concatenate(people), np.concatenate(pos)


def weighted(people: np.ndarray, pos: np.ndarray) -> dict[str, float]:
    w = people / people.sum()
    dev = np.abs(pos - 1.0)
    mean = (w[:, None] * pos).sum(axis=0)
    cov = (w * (pos[:, 0] - mean[0]) * (pos[:, 1] - mean[1])).sum()
    var = (w[:, None] * (pos - mean) ** 2).sum(axis=0)
    corr = cov / np.sqrt(var[0] * var[1]) if var.min() > 0 else float("nan")
    return {
        "field_dev": float((w * dev[:, 0]).sum()),
        "store_dev": float((w * dev[:, 1]).sum()),
        "corr": float(corr),
    }


def run(scenario: Scenario, years: int) -> dict[str, Any]:
    probe = Probe()
    try:
        sim = Simulator(scenario, record_strata=True)
        series: list[dict[str, float]] = []
        started = time.perf_counter()
        for _ in range(years):
            sim.step()
            series.append(weighted(*strata_of(sim)))
        elapsed = time.perf_counter() - started
    finally:
        probe.close()
    flows = sim.state.population.strata_flows or []
    events = Counter(e["event"] for e in sim.state.population.strata_log or [])
    n = [len(u.strata) for u in sim.state.units.values()]
    return {
        "sim": sim,
        "series": series,
        "seconds": elapsed,
        "hook_seconds": probe.hook_seconds,
        "moved": probe.moved_kcal,
        "crop": probe.crop_kcal,
        "harvest_volume": sum(abs(r["harvest_pool_transfer_kcal"]) for r in flows) / 2,
        "store_volume": sum(abs(r["store_pool_transfer_kcal"]) for r in flows) / 2,
        "flow_rows": len(flows),
        "events": events,
        "mean_strata": float(np.mean(n)),
        "at_capacity": sum(k == S_MAX for k in n),
        "units": len(n),
        "population": sim.state.total_population(),
    }


def canonical(seed: int, years: int) -> None:
    base = Scenario.from_yaml(SCENARIO).with_overrides(seed=seed, n_years=years)
    results = {}
    for w in WEIGHTS:
        results[w] = run(base.with_settings({"strata.field_output_claim_weight": w}), years)
    neutral = results[0.0]
    print(f"mvp2_neolithic seed {seed}, {years} years; columns: w")
    print(f"{'':34}" + "".join(f"{w:>14}" for w in WEIGHTS))

    def line(label: str, values: list[Any], fmt: str = "{:>14.4g}") -> None:
        print(f"{label:34}" + "".join(fmt.format(v) for v in values))

    final = [r["series"][-1] for r in results.values()]
    line("final population", [r["population"] for r in results.values()], "{:>14}")
    line("final field |pos-1| (people-wt)", [f["field_dev"] for f in final])
    line("final store |pos-1| (people-wt)", [f["store_dev"] for f in final])
    line("final corr(field, store)", [f["corr"] for f in final])
    for key in ("field_dev", "store_dev"):
        mean = [np.mean([s[key] for s in r["series"]]) for r in results.values()]
        line(f"time-mean {key}", mean)
    line("crop attribution moved (kcal)", [r["moved"] for r in results.values()])
    line(
        "  / crop of differentiated units",
        [r["moved"] / r["crop"] if r["crop"] else 0.0 for r in results.values()],
    )
    line("harvest pooling volume (kcal)", [r["harvest_volume"] for r in results.values()])
    line("store pooling volume (kcal)", [r["store_volume"] for r in results.values()])
    line("flow rows", [r["flow_rows"] for r in results.values()], "{:>14}")
    line("final mean strata per unit", [r["mean_strata"] for r in results.values()])
    line("final units at S_MAX", [r["at_capacity"] for r in results.values()], "{:>14}")
    for kind in ("exact_compaction", "capacity_coalescence", "fusion_inheritance"):
        line(kind, [r["events"][kind] for r in results.values()], "{:>14}")
    line("run seconds", [r["seconds"] for r in results.values()])
    line("accounting hook seconds", [r["hook_seconds"] for r in results.values()])
    print("\nevery 50 years: field |pos-1| / store |pos-1| (people-weighted)")
    for year in range(49, years, 50):
        cells = [
            f"{r['series'][year]['field_dev']:.4f}/{r['series'][year]['store_dev']:.4f}"
            for r in results.values()
        ]
        print(f"  year {year + 1:4}" + "".join(f"{c:>18}" for c in cells))
    # Isolation: field positions (and everything physical) do not depend on w.
    for w in WEIGHTS[1:]:
        r = results[w]
        dev = max(
            abs(a["field_dev"] - b["field_dev"])
            for a, b in zip(r["series"], neutral["series"], strict=True)
        )
        same = r["population"] == neutral["population"] and r["units"] == neutral["units"]
        print(f"w={w}: max |field dispersion - w0| {dev:.2e}; population and units equal: {same}")


def controlled(years: int) -> None:
    from madexplorer.experiments.benchmark import synthetic_simulator

    def block(share: list[float], field: list[float], store: list[float]) -> StrataBlock:
        columns = {"share": share, "field_claim": field, "store_claim": store}
        return StrataBlock(
            {k: np.array(v) for k, v in columns.items()}, np.zeros(2, dtype=np.int64)
        )

    fixtures = {
        "unequal fields": block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2]),
        "cross-cutting": block([0.5, 0.5], [0.7, 0.3], [0.2, 0.8]),
        "unequal stores": block([0.6, 0.4], [0.6, 0.4], [0.3, 0.7]),
    }
    base = Scenario.from_yaml(SCENARIO).with_overrides(seed=11)
    trace: dict[float, dict[str, list[tuple[int, str]]]] = {}
    for w in WEIGHTS:
        sim = synthetic_simulator(
            base.with_settings({"strata.field_output_claim_weight": w}), 30, farming=True
        )
        population = sim.state.population
        population.strata_log, population.strata_flows = [], []
        units = list(sim.state.units.values())[: len(fixtures)]
        ids = {}
        for unit, (label, fixture) in zip(units, fixtures.items(), strict=True):
            unit.fields_ha, unit.stores_kcal = 4.0, 3e5
            population.replace_strata(unit, fixture)
            ids[unit.id] = label
        trace[w] = {label: [] for label in fixtures}
        for _ in range(years):
            sim.step()
            for uid, label in ids.items():
                unit = sim.state.units.get(uid)
                if unit is None:
                    continue
                pos = positions(unit.strata)
                cell = " ".join(f"{f:.3f}/{s:.3f}" for f, s in pos.tolist())
                trace[w][label].append((sim.state.year, cell))
    print("relative field/store position of each component (fields identical across w)")
    for label in fixtures:
        print(f"\n{label}")
        for k, (year, _) in enumerate(trace[0.0][label]):
            if year in (1, 2, 5, 10, 20, 30, 40) or k == len(trace[0.0][label]) - 1:
                cells = [trace[w][label][k][1] for w in WEIGHTS if k < len(trace[w][label])]
                print(
                    f"  year {year:3}  "
                    + "  |  ".join(f"w={w}: {c}" for w, c in zip(WEIGHTS, cells, strict=False))
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--years", type=int, default=400)
    parser.add_argument("--controlled", action="store_true")
    args = parser.parse_args()
    if args.controlled:
        controlled(args.years)
    else:
        canonical(args.seed, args.years)


if __name__ == "__main__":
    main()
