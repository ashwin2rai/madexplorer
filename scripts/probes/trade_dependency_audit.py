# The report tables keep one entry per line.
# ruff: noqa: E501
"""Between-unit food dependency (MVP 3 Stage 5G): read-only audit. NOT A MECHANISM.

Does MVP 2.1's reciprocal provisioning (``economy/trade.py``) create repeated, concentrated,
consequential asymmetric material relations between population units? A hook on
``TradeSubsystem.evaluate`` records every transfer with the inputs of the matching (each
unit's need, harvest, stores, reserve, offer), re-runs the same greedy matching to check it
reproduces the authoritative transfers exactly, and repeats it with one donor withheld
(static accounting only: who else would have covered the shortfall). Recipients' energy
outcomes with and without a transfer use the production ``energy_balance`` rule on the same
inputs. Nothing feeds back (checked by digest against a plain run); nothing is a
behavioral claim about refusal, bargaining or long-run dynamics.

Usage:
    uv run python scripts/probes/trade_dependency_audit.py [--jobs 2] [--seeds 0 1 2 3]
"""

import argparse
import math
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, physical_digest, q, scenario_for

from madexplorer.core.simulation import Simulator
from madexplorer.economy.trade import TradeSubsystem, delivered_fraction
from madexplorer.population.energetics import (
    annual_need_columns,
    capability_column,
    energy_balance,
)

SCENARIOS = ("neolithic", "pressure+cult")


def match(
    deficits: list[tuple[float, str, float, float]],
    offers: dict[str, float],
    donors_of: dict[str, list[tuple[float, str]]],
    decay_km: float,
) -> list[tuple[str, str, float, float]]:
    """The greedy matching of ``TradeSubsystem.evaluate`` on recorded inputs: most severe
    relative deficit first, nearest offers first. Returns (donor, recipient, sent, received)."""
    offers = dict(offers)
    out = []
    for _, rid, deficit, _need in sorted(deficits):
        remaining = deficit
        for cost, did in donors_of[rid]:
            if remaining <= 0:
                break
            if offers[did] <= 0:
                continue
            fraction = delivered_fraction(cost, decay_km)
            sent = min(offers[did], remaining / fraction)
            offers[did] -= sent
            remaining -= sent * fraction
            out.append((did, rid, sent, sent * fraction))
    return out


class Recorder:
    def __init__(self) -> None:
        self.years: list[dict[str, Any]] = []
        self.mismatch = 0
        self._saved: Any = None

    def install(self) -> None:
        original = TradeSubsystem.evaluate
        rec = self

        def evaluate(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = original(sub, state, ctx)
            cols = ctx.columns(state)
            if not len(cols):
                return proposals
            config = ctx.scenario.config.trade
            p = ctx.compiled.parameter
            species = cols.species()
            need = annual_need_columns(cols, state, ctx)
            harvest, stores = cols.get("harvest_kcal"), cols.get("stores_kcal")
            people = cols.population().astype(float)
            reserve = cols.get("reserve_kcal_per_capita") * people
            cap = (
                people
                * p("metabolism.reserve_days_max")[species]
                * p("metabolism.adult_daily_kcal")[species]
            )
            can_store = capability_column(cols, ctx, "storage_retention") > 0
            share = p("social.food_sharing_propensity")[species]
            cells = cols.get("cell").tolist()
            info: dict[str, tuple[Any, ...]] = {}
            offers: dict[str, float] = {}
            offering: dict[int, list[str]] = defaultdict(list)
            deficits = []
            for k, u in enumerate(cols.units):
                b = float(harvest[k] + stores[k] - need[k])
                info[u.id] = (float(need[k]), float(harvest[k]), float(stores[k]), float(reserve[k]),
                              float(cap[k]), bool(can_store[k]), cells[k], int(people[k]), u.species_id)  # fmt: skip
                if b > 0:
                    offers[u.id] = float(share[k]) * b
                    offering[cells[k]].append(u.id)
                elif b < 0 and need[k] > 0:
                    deficits.append((b / float(need[k]), u.id, -b, float(need[k])))
            donors_of = {}
            for _, rid, _, _ in deficits:
                reach = ctx.movement[info[rid][8]].reachable(info[rid][6])
                donors_of[rid] = sorted(
                    (cost, did) for cell, cost in reach.items() for did in offering.get(cell, ())
                    if info[did][8] == info[rid][8]
                )  # fmt: skip
            actual = [
                (t.donor_id, t.recipient_id, t.sent_kcal, t.received_kcal)
                for t in proposals[0].transfers
            ]
            again = match(deficits, offers, donors_of, config.transport_decay_km)
            if again != actual:
                rec.mismatch += 1
            # Withhold each recipient's largest donor (static accounting sensitivity).
            received: dict[str, Counter[str]] = defaultdict(Counter)
            for did, rid, _s, r in actual:
                received[rid][did] += r
            withheld = {}
            for rid, by_donor in received.items():
                top = by_donor.most_common(1)[0][0]
                cf = match(deficits, {**offers, top: 0.0}, donors_of, config.transport_decay_km)
                withheld[rid] = (top, sum(r for _d, rr, _s, r in cf if rr == rid))
            sent_by: Counter[str] = Counter()
            for did, _rid, s, _r in actual:
                sent_by[did] += s
            rec.years.append({
                "year": state.year, "info": info, "transfers": actual, "withheld": withheld,
                "n_deficit": len(deficits), "n_offer": len(offers),
                "unserved": {rid: d for _, rid, d, _ in deficits},  # deficit before trade
                "reach": {rid: len(v) for rid, v in donors_of.items()},
                "costs": {(did, rid): c for rid, v in donors_of.items() for c, did in v},
                "sent_by": dict(sent_by),
            })  # fmt: skip
            return proposals

        self._saved = original
        TradeSubsystem.evaluate = evaluate  # type: ignore[method-assign]

    def remove(self) -> None:
        TradeSubsystem.evaluate = self._saved  # type: ignore[method-assign]


def run(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    scenario = scenario_for(name, seed, 0.0)
    rec = Recorder()
    rec.install()
    try:
        sim = Simulator(scenario)
        years = 0
        for years in range(1, scenario.config.simulation.n_years + 1):  # noqa: B007
            sim.step()
            if not sim.state.units:
                break
    finally:
        rec.remove()
    plain = Simulator(scenario)
    for _ in range(years):
        plain.step()
        if not plain.state.units:
            break
    events = [(e.year, e.kind, dict(e.data)) for e in sim.events
              if e.kind in ("population_split", "population_merge", "unit_extinct")]  # fmt: skip
    return {"name": name, "seed": seed, "years": rec.years, "mismatch": rec.mismatch,
            "neutral": physical_digest(sim) == physical_digest(plain), "events": events}  # fmt: skip


def _balance(i: tuple[Any, ...], harvest: float) -> tuple[float, float]:
    need, _h, stores, reserve, cap, can_store = i[:6]
    b = energy_balance(need, harvest, reserve, cap, stores, can_store)
    return b.food_ratio, b.deficit


def fertility_multiplier(food_ratio: float, mid: float = 0.8, scale: float = 0.1) -> float:
    """``demography.py`` food response (human.yaml mid 0.8, scale 0.1)."""

    def logistic(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-(x - mid) / scale))

    return min(logistic(food_ratio) / logistic(1.0), 1.0)


def analyse(runs: list[dict[str, Any]]) -> None:
    unit_years = deficit_years = 0
    rec_years: list[dict[str, Any]] = []
    donor_years = 0
    donor_fr_drop: list[float] = []
    pair_years: Counter[tuple[str, str, str]] = Counter()
    roles: dict[tuple[str, str], set[str]] = defaultdict(set)
    volume = need_total = 0.0
    kin_kcal = [0.0, 0.0]  # received from a direct fission parent or daughter, total received
    for r in runs:
        tag = f"{r['seed']}"
        kin = {
            frozenset((e[2]["unit_id"], e[2]["daughter_id"]))
            for e in r["events"]
            if e[1] == "population_split"
        }
        prev_top: dict[str, str] = {}
        history: dict[str, list[int]] = defaultdict(list)
        for y in r["years"]:
            info = y["info"]
            unit_years += len(info)
            deficit_years += y["n_deficit"]
            need_total += sum(v[0] for v in info.values())
            by_rec: dict[str, Counter[str]] = defaultdict(Counter)
            for did, rid, s, rcv in y["transfers"]:
                by_rec[rid][did] += rcv
                pair_years[(tag, did, rid)] += 1
                kin_kcal[0] += rcv if frozenset((did, rid)) in kin else 0.0
                kin_kcal[1] += rcv
                roles[(tag, did)].add("donor")
                roles[(tag, rid)].add("recipient")
                volume += s
            for did, s in y["sent_by"].items():
                i = info[did]
                donor_years += 1
                fr0, _ = _balance(i, i[1])
                fr1, _ = _balance(i, max(i[1] - s, 0.0))
                donor_fr_drop.append(fertility_multiplier(fr0) - fertility_multiplier(fr1))
            for rid, by_donor in by_rec.items():
                i = info[rid]
                got = sum(by_donor.values())
                after = i[1] + got  # harvest the recipient will hold at energetics
                fr_a, def_a = _balance(i, after)
                fr_0, def_0 = _balance(i, i[1])
                top, cf = y["withheld"][rid]
                fr_w, def_w = _balance(i, after - got + cf)
                shares = np.array(list(by_donor.values())) / got
                history[rid].append(y["year"])
                rec_years.append({
                    "dep": got / i[0], "cover": got / y["unserved"][rid], "donors": len(by_donor),
                    "hhi": float((shares**2).sum()), "top_share": float(shares.max()),
                    "reach": y["reach"][rid], "same_top": prev_top.get(rid) == top,
                    "had_prev": rid in prev_top,
                    "retained": cf / got,  # total received with the top donor withheld / actual
                    "replaced": min(max((cf - (got - by_donor[top])) / by_donor[top], 0.0), 1.0),
                    "def_none": def_0, "def_actual": def_a, "def_withheld": def_w,
                    "fr_none": fr_0, "fr_actual": fr_a, "fr_withheld": fr_w,
                    "cost_top": y["costs"][(top, rid)],
                    "chronic": sum(1 for yy in history[rid] if y["year"] - 5 < yy <= y["year"]) >= 3,
                })  # fmt: skip
            prev_top = {rid: by.most_common(1)[0][0] for rid, by in by_rec.items()}
    n = len(rec_years)
    a = {k: np.array([x[k] for x in rec_years], dtype=float) for k in rec_years[0]} if n else {}
    print(
        f"  unit-years {unit_years}; deficit before trade {deficit_years} ({deficit_years / unit_years:.4f}); receiving {n} ({n / unit_years:.4f}); trade volume / total need {volume / need_total:.2e}"
    )
    if not n:
        return
    print(
        f"  dependency received/need: {q(a['dep'])}; share of own deficit covered: {q(a['cover'], (0.1, 0.5, 0.9))}"
    )
    print(
        f"  donors per recipient-year: {q(a['donors'])}; reachable offering units: {q(a['reach'])}; top-donor share {q(a['top_share'], (0.1, 0.5))}; HHI {q(a['hhi'], (0.1, 0.5))}"
    )
    print(
        f"  top donor path cost (0 = same cell): {q(a['cost_top'], (0.5, 0.9))}; same cell {float((a['cost_top'] == 0).mean()):.3f}"
    )
    prev = a["had_prev"].astype(bool)
    print(
        f"  received the year before: {prev.mean():.3f}; same top donor as the year before (when so): {a['same_top'][prev].mean() if prev.any() else float('nan'):.3f}; chronic (>= 3 of last 5 y): {a['chronic'].mean():.3f}"
    )
    lens = np.array(list(pair_years.values()))
    print(
        f"  donor-recipient pairs {lens.size}; years per pair p50/p90/p99/max {q(lens)}; pairs lasting >= 5 y {float((lens >= 5).mean()):.3f}"
    )
    both = sum(1 for v in roles.values() if v == {"donor", "recipient"})
    print(
        f"  received kcal between direct fission parent and daughter: {kin_kcal[0] / max(kin_kcal[1], 1e-9):.3f}"
    )
    print(
        f"  units ever recipient {sum('recipient' in v for v in roles.values())}; ever donor {sum('donor' in v for v in roles.values())}; both roles {both}"
    )
    print(
        f"  withholding the top donor: total received kept p10/p50/p90 {q(a['retained'], (0.1, 0.5, 0.9))}; top donor's part replaced by others p10/p50/p90 {q(a['replaced'], (0.1, 0.5, 0.9))}; fully replaced (>= 99 %) {float((a['replaced'] >= 0.99).mean()):.3f}; not at all {float((a['replaced'] <= 0.01).mean()):.3f}"
    )
    print(
        "  static energy accounting for recipients (production energy_balance on the recorded inputs):"
    )
    print(
        f"    deficit: none {q(a['def_none'], (0.5, 0.9))} -> actual {q(a['def_actual'], (0.5, 0.9))} -> top donor withheld {q(a['def_withheld'], (0.5, 0.9))}"
    )
    lifted = (a["def_none"] > 0) & (a["def_actual"] == 0)
    print(
        f"    deficit > 0 without trade: {float((a['def_none'] > 0).mean()):.3f}; lifted to 0 by trade: {lifted.mean():.3f}; deficit > 0 with top donor withheld: {float((a['def_withheld'] > 0).mean()):.3f}"
    )
    dfert = np.array(
        [
            fertility_multiplier(x) - fertility_multiplier(y)
            for x, y in zip(a["fr_actual"], a["fr_none"], strict=True)
        ]
    )
    dmort = np.exp(3.0 * (a["def_none"] - a["def_actual"]))
    print(
        f"    fertility multiplier gain from trade: {q(dfert, (0.5, 0.9, 0.99))}; starvation hazard ratio none/actual (adult, sensitivity 3): {q(dmort, (0.5, 0.9, 0.99))}"
    )
    print(
        f"  donors: donor-years {donor_years}; fertility multiplier loss from sending (food_ratio uses harvest only): {q(donor_fr_drop, (0.5, 0.9, 0.99))}; > 0.01 {float((np.array(donor_fr_drop) > 0.01).mean()):.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = parser.parse_args()
    started = time.perf_counter()
    with Pool(args.jobs) as workers:
        runs = list(workers.imap_unordered(run, [(n, s) for n in SCENARIOS for s in args.seeds]))
    print(
        f"{len(runs)} runs in {time.perf_counter() - started:.0f} s; matching reproduced exactly in every year: {all(r['mismatch'] == 0 for r in runs)}; observer-neutral: {all(r['neutral'] for r in runs)}"
    )
    for name in SCENARIOS:
        group = [r for r in runs if r["name"] == name]
        print(f"\n=== {name} (seeds {sorted(r['seed'] for r in group)})")
        analyse(group)


if __name__ == "__main__":
    main()
