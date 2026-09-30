"""Field-abandonment audit (P5, fast freeze): decision-level probe, observation only.

Runs one seed of ``mvp2_neolithic`` with field growth to target (A) on (plus any ``--set``
switches) and records, for
every migration decision of a unit holding fields, the stay/move utility decomposition:

- home utility without the crop (wild food only) and the crop's contribution to staying;
- the best destination's utility and the explicit ``abandoned_fields`` penalty;
- the utility gain and move probability as the model computes them;
- the same decision re-evaluated offline with the penalty at zero, the crop at zero, or both.

The counterfactuals reuse ``MigrationSubsystem._prepare`` / ``_scores`` with modified
``MoveCosts``; they consume no random draws, so the simulated trajectory is unchanged
(the final population printed can be compared with an unprobed run of the same seed).

Usage:
    uv run python scripts/probes/field_abandonment_audit.py --seed 0 --years 500 \
        --from-year 300 --every 5 --out <dir>
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import clearing_hours_per_ha
from madexplorer.mobility.migration import MigrationSubsystem, food_utility, migration_probability

FIELDS = (
    "year",
    "population",
    "residence_years",
    "fields_ha",
    "crop_share_of_need",  # farm kcal / need
    "home_wild_ratio",  # R at home without the crop (years of need per head)
    "home_utility_wild",  # home utility with the crop removed from the food term
    "crop_contribution",  # food_weight * (U(R_wild + crop) - U(R_wild))
    "dest_utility",  # best destination, full model (penalty included)
    "penalty",  # abandoned_fields cost (utility units)
    "stores_cost",
    "gain",  # full model: U(best) - U(home)
    "hazard",
    "gain_no_penalty",
    "hazard_no_penalty",
    "gain_no_crop",  # crop removed from the stay term, penalty kept
    "hazard_no_crop",
    "gain_neither",
    "hazard_neither",
    "rebuild_hours_per_capita",  # fields_ha * clearing h/ha at home vegetation / people
    "marginal_forage_kcal_h",
    "need_kcal",
    "replacement_cost",  # rebuild hours * marginal forage kcal/h / need (years of need)
    "gain_replacement",  # penalty replaced by replacement_cost * abandoned_stores_weight
    "hazard_replacement",
)


def _best_gain(scores: np.ndarray, cells: np.ndarray, home: int) -> tuple[float, int]:
    values = np.where(cells == home, -np.inf, scores)
    if not np.isfinite(values).any():
        return float("nan"), -1
    k = int(np.argmax(values))
    return float(scores[k] - scores[cells == home][0]), k


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="scenarios/mvp2_neolithic.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--years", type=int, default=500)
    parser.add_argument("--from-year", type=int, default=300)
    parser.add_argument("--every", type=int, default=5)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="PATH=BOOL",
        help="extra mechanism switch, e.g. mechanisms.field_replacement_cost=true",
    )
    args = parser.parse_args()

    settings: dict[str, object] = {"mechanisms.field_growth_to_target": True}
    for item in args.set:
        key, value = item.split("=", 1)
        settings[key] = value.lower() in ("1", "true", "yes")
    scenario = Scenario.from_yaml(args.scenario).with_settings(settings)
    scenario = scenario.with_overrides(seed=args.seed, n_years=args.years)
    sim = Simulator(scenario, record_events=False)
    rows: list[tuple[float, ...]] = []
    original = MigrationSubsystem.evaluate

    def probed(self: MigrationSubsystem, state, ctx):  # type: ignore[no-untyped-def]
        if state.year >= args.from_year and state.year % args.every == 0:
            record(self, state, ctx)
        return original(self, state, ctx)

    def replacement_cost(p, state, ctx) -> float:  # type: ignore[no-untyped-def]
        """Years of need of foraging forgone to re-clear the current fields (home vegetation)."""
        unit = p.unit
        per_ha = clearing_hours_per_ha(
            float(state.world.vegetation_density[unit.cell]),
            scenario.config.agriculture,
            ctx.capabilities(unit)["clearing_efficiency"],
        )
        need = p.costs.need_kcal
        kcal = unit.fields_ha * per_ha * unit.forage_marginal_kcal_per_hour
        return kcal / need if need > 0 else 0.0

    def record(self: MigrationSubsystem, state, ctx) -> None:  # type: ignore[no-untyped-def]
        prepared = [
            p
            for u in state.units.values()
            if u.fields_ha > 0 and (p := self._prepare(u, state, ctx))
        ]
        if not prepared:
            return
        variants = {
            "full": prepared,
            "no_penalty": [replace(p, costs=replace(p.costs, fields_cost=0.0)) for p in prepared],
            "no_crop": [replace(p, costs=replace(p.costs, farm_kcal=0.0)) for p in prepared],
            "replacement": [
                replace(
                    p,
                    costs=replace(
                        p.costs,
                        fields_cost=p.behavior.abandoned_stores_weight
                        * replacement_cost(p, state, ctx),
                    ),
                )
                for p in prepared
            ],
            "neither": [
                replace(p, costs=replace(p.costs, farm_kcal=0.0, fields_cost=0.0)) for p in prepared
            ],
        }
        blocks = {
            name: self._scores(ps, state.year, state.world.water_access)
            for name, ps in variants.items()
        }
        agri = scenario.config.agriculture
        for i, p in enumerate(prepared):
            unit, cells, behavior = p.unit, p.candidates, p.behavior
            home = unit.cell
            scores, _ = blocks["full"][i]
            gain, k = _best_gain(scores, cells, home)
            if k < 0:
                continue
            neither_scores, neither_ratio = blocks["neither"][i]
            home_row = cells == home
            wild_ratio = float(neither_ratio[home_row][0])
            need = p.costs.need_kcal
            crop_ratio = wild_ratio + p.costs.farm_kcal / need if need > 0 else wild_ratio
            u = food_utility(np.array([wild_ratio, crop_ratio]), behavior)
            out = {
                name: _best_gain(blocks[name][i][0], cells, home)[0]
                for name in ("no_penalty", "no_crop", "neither", "replacement")
            }
            per_ha = clearing_hours_per_ha(
                float(state.world.vegetation_density[home]),
                agri,
                ctx.capabilities(unit)["clearing_efficiency"],
            )
            rows.append(
                (
                    state.year,
                    unit.population,
                    unit.residence_years,
                    unit.fields_ha,
                    p.costs.farm_kcal / need if need > 0 else np.nan,
                    wild_ratio,
                    float(neither_scores[home_row][0]),
                    behavior.food_weight * float(u[1] - u[0]),
                    float(scores[k]),
                    p.costs.fields_cost,
                    p.costs.stores_cost,
                    gain,
                    migration_probability(gain, behavior),
                    out["no_penalty"],
                    migration_probability(out["no_penalty"], behavior),
                    out["no_crop"],
                    migration_probability(out["no_crop"], behavior),
                    out["neither"],
                    migration_probability(out["neither"], behavior),
                    unit.fields_ha * per_ha / max(unit.population, 1),
                    unit.forage_marginal_kcal_per_hour,
                    need,
                    replacement_cost(p, state, ctx),
                    out["replacement"],
                    migration_probability(out["replacement"], behavior),
                )
            )

    MigrationSubsystem.evaluate = probed  # type: ignore[method-assign]
    try:
        for _ in range(args.years):
            sim.step()
    finally:
        MigrationSubsystem.evaluate = original  # type: ignore[method-assign]

    args.out.mkdir(parents=True, exist_ok=True)
    data = np.array(rows, dtype=np.float64).reshape(-1, len(FIELDS))
    np.savez_compressed(args.out / f"decisions_seed{args.seed}.npz", data=data, fields=FIELDS)
    summary = {
        "seed": args.seed,
        "settings": settings,
        "years": args.years,
        "final_population": sim.state.total_population(),
        "final_units": len(sim.state.units),
        "farmer_decisions": int(data.shape[0]),
    }
    (args.out / f"summary_seed{args.seed}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
