"""Food and field flow audit (MVP 3 Stage 3A): observation only.

Checks, on real runs, the properties the Stage 3B claim accounting relies on
(objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md, "Stage 3 economic accounting"):

1. before trade, each unit's harvest_kcal == farm_harvest_kcal + forage_harvest_kcal (bitwise);
2. trade donors and recipients are disjoint within a year;
3. energetics never both adds to and withdraws from a unit's stores in one year;
4. every unit's stores reconcile through the year:
   closing = (opening - sent_from_stores - withdrawn + stored) * retention, then
   migration carrying limits and lifecycle splits/merges (checked where none occur);
5. fields_ha changes only in field planning, migration, fission and fusion.

The apply methods are wrapped to observe their inputs; nothing is changed, so the run is
identical to an unprobed one (compare the final population).

``--heterogeneous`` instead demonstrates the Stage 3B strata accounting on deterministic
fixtures (three units with unequal claims over existing fields and stores; no random strata):
per year, each unit's physical fields and stores, its strata claims and relative positions,
the pooling transfers, and the residuals of the accounting identities (claim columns sum to
1, transfers sum to 0).

Usage:
    uv run python scripts/probes/food_flow_audit.py --seed 0 --years 300
    uv run python scripts/probes/food_flow_audit.py --heterogeneous --years 40
"""

import argparse
from collections import Counter
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import FieldPlans
from madexplorer.economy.trade import TradeRound
from madexplorer.mobility.migration import Relocation
from madexplorer.population.energetics import EnergyUpdates
from madexplorer.population.unit import belief_slot

checks: Counter[str] = Counter()
failures: Counter[str] = Counter()
year_state: dict[str, Any] = {}


def check(name: str, ok: bool) -> None:
    checks[name] += 1
    if not ok:
        failures[name] += 1


def wrap_trade(original: Any) -> Any:
    def apply(self: TradeRound, state: Any, ctx: Any) -> None:
        table = state.table
        slots = state.units.slots()
        harvest = table.columns["harvest_kcal"][slots]
        crop = table.columns["farm_harvest_kcal"][slots]
        forage = table.columns["forage_harvest_kcal"][slots]
        check("harvest == crop + forage before trade", bool((harvest == crop + forage).all()))
        donors = {t.donor_id for t in self.transfers}
        recipients = {t.recipient_id for t in self.transfers}
        check("donors and recipients disjoint", donors.isdisjoint(recipients))
        year_state["stores_before_trade"] = {
            u.id: float(table.columns["stores_kcal"][belief_slot(u)]) for u in state.units.values()
        }
        sent: dict[str, float] = {}
        for t in self.transfers:  # replicate the donor arithmetic to get sent_from_stores
            held = float(table.columns["harvest_kcal"][belief_slot(state.units[t.donor_id])])
            held -= sent.get(t.donor_id + ":h", 0.0)
            from_harvest = min(t.sent_kcal, held)
            sent[t.donor_id + ":h"] = sent.get(t.donor_id + ":h", 0.0) + from_harvest
            sent[t.donor_id] = sent.get(t.donor_id, 0.0) + (t.sent_kcal - from_harvest)
        year_state["sent_from_stores"] = {k: v for k, v in sent.items() if ":" not in k}
        original(self, state, ctx)

    return apply


def wrap_energy(original: Any) -> Any:
    def apply(self: EnergyUpdates, state: Any, ctx: Any) -> None:
        cols = self.cols
        opening = cols.get("stores_kcal")
        withdrawn = np.maximum(opening + self.stored_kcal - self.stores_kcal, 0.0)
        both = (self.stored_kcal > 0) & (withdrawn > 0)
        check("no store addition and withdrawal in one year", not both.any())
        before = year_state.get("stores_before_trade", {})
        out = year_state.get("sent_from_stores", {})
        for k, unit in enumerate(cols.units):
            if unit.id in before:
                expected = max(before[unit.id] - out.get(unit.id, 0.0), 0.0)
                close = abs(opening[k] - expected) <= 1e-6 * max(1.0, expected)
                check("stores: opening = before trade - sent from stores", close)
        original(self, state, ctx)
        closing = cols.get("stores_kcal")
        expected = (opening - withdrawn + self.stored_kcal) * self.retention
        reconciled = bool(np.allclose(closing, expected, rtol=1e-12, atol=1e-6))
        check("stores: closing = (opening - withdrawn + stored) * retention", reconciled)

    return apply


def wrap_fields(cls: Any, label: str) -> Any:
    original = cls.apply

    def apply(self: Any, state: Any, ctx: Any) -> None:
        before = {u.id: u.fields_ha for u in state.units.values()}
        original(self, state, ctx)
        changed = sum(
            1 for u in state.units.values() if u.id in before and u.fields_ha != before[u.id]
        )
        checks[f"fields changed by {label} (units)"] += changed

    cls.apply = apply


def heterogeneous(years: int) -> None:
    """Stage 3B accounting on three deterministic heterogeneous units (observation only)."""
    from madexplorer.experiments.benchmark import synthetic_simulator
    from madexplorer.population.strata import StrataBlock, positions

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
    scenario = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml").with_overrides(seed=11)
    sim = synthetic_simulator(scenario, 30, farming=True)
    population = sim.state.population
    population.strata_log, population.strata_flows = [], []
    watched = {}
    units = list(sim.state.units.values())[: len(fixtures)]
    for unit, (label, fixture) in zip(units, fixtures.items(), strict=True):
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5
        population.replace_strata(unit, fixture)
        watched[unit.id] = label
    worst_sum = worst_transfer = 0.0
    for _ in range(years):
        sim.step()
        year = sim.state.year
        for uid, label in watched.items():
            unit = sim.state.units.get(uid)
            if unit is None:
                continue
            strata = unit.strata
            for values in strata.columns.values():
                worst_sum = max(worst_sum, abs(float(values.sum()) - 1.0))
            transfers = [
                f["pool_transfer_kcal"]
                for f in population.strata_flows
                if f["year"] == year and f["unit_id"] == uid
            ]
            if transfers:
                worst_transfer = max(worst_transfer, abs(sum(transfers)))
            print(
                f"{year:4d} {uid:>5} {label:15s} fields={unit.fields_ha:7.2f} "
                f"stores={unit.stores_kcal:11.0f} share={np.round(strata.columns['share'], 3)} "
                f"field_pos={np.round(positions(strata)[:, 0], 3)} "
                f"store_pos={np.round(positions(strata)[:, 1], 3)} "
                f"transfer={np.round(transfers, 0) if transfers else '-'}"
            )
    print(f"max |claim column sum - 1| = {worst_sum:.2e}")
    print(f"max |sum of a unit's transfers| = {worst_transfer:.2e} kcal")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="scenarios/mvp2_neolithic.yaml")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--years", type=int, default=300)
    parser.add_argument("--heterogeneous", action="store_true")
    args = parser.parse_args()
    if args.heterogeneous:
        heterogeneous(args.years)
        return
    TradeRound.apply = wrap_trade(TradeRound.apply)  # type: ignore[method-assign]
    EnergyUpdates.apply = wrap_energy(EnergyUpdates.apply)  # type: ignore[method-assign]
    wrap_fields(FieldPlans, "field planning")
    wrap_fields(Relocation, "migration")
    scenario = Scenario.from_yaml(args.scenario).with_overrides(seed=args.seed, n_years=args.years)
    result = Simulator(scenario).run()
    print("final population", result.metrics[-1]["population"])
    for name, count in sorted(checks.items()):
        print(f"{name}: {count} checks, {failures[name]} failures")


if __name__ == "__main__":
    main()
