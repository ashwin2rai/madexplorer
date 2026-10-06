# The report tables keep one entry per line.
# ruff: noqa: E501
"""Counterfactual store release / reserve management (MVP 3 Stage 4D): observation only.

NOT ACTIVE. Evaluates ``madexplorer.population.store_release`` (how much a unit releases from
its stores in a shortage year) against the authoritative MVP 2.1 rule ``X = min(D, K)``.
Nothing in the model changes: the probe wraps ``EnergyUpdates.apply`` to copy each unit's
energetics inputs and outcome (read-only).

Modes:

``controlled``
    Deterministic unit-level sequences through the real ``energy_balance`` (a closed toy with
    prescribed harvests, no demography): current rule vs reserve targets, under several
    retention rates, gaps and a carrying limit; plus a Stage 4C composition demonstration.
``runs``
    Frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure + cultivation 400 y;
    seeds 0-3): shortage prevalence, chains and gaps, retention and body-reserve state at
    shortages, the one-step counterfactual for the candidate ``R = b * Need`` over a sweep of
    b, hunger-with-retained-food, and a post-hoc (evaluation-only) look at the next
    authoritative shortage: retained food surviving spoilage and the uncovered need it could
    meet. Observer on/off neutrality is checked.

Policy inputs are decision-time quantities only (Need, H, K, b). Future authoritative years
are used only afterwards, to evaluate potential availability, never as policy inputs.

Usage:
    uv run python scripts/probes/store_release_counterfactual.py controlled
    uv run python scripts/probes/store_release_counterfactual.py runs [--jobs 2] [--out f.pkl]
    uv run python scripts/probes/store_release_counterfactual.py report --load f.pkl
"""

import argparse
import pickle
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from store_access_counterfactual import drive, strata_digest
from strata_capacity import physical_digest
from strata_review import SEEDS, scenario_for

from madexplorer.population.energetics import EnergyUpdates, energy_balance
from madexplorer.population.store_release import (
    need_buffer_target,
    release_current,
    release_with_reserve_target,
)
from madexplorer.population.strata_access import counterfactual_store_access

BUFFERS = (0.0, 0.05, 0.1, 0.2, 0.5, 1.0)  # reserve_target_fraction b (0 = MVP 2.1)
SCENARIOS = ("neolithic", "pressure+cult")
HORIZON = 10  # years searched for the next shortage (the species planning horizon)
DUST = 1e-9  # D <= DUST * Need: rounding-level shortage, excluded


# ---------------------------------------------------------------- observation


class EnergeticsObserver:
    """Copies every populated unit's energetics inputs and outcome, per year (read-only)."""

    def __init__(self) -> None:
        self.years: list[dict[str, Any]] = []
        self._saved: Any = None

    def install(self) -> "EnergeticsObserver":
        apply = EnergyUpdates.apply
        self._saved = apply

        def observed(updates: EnergyUpdates, state: Any, ctx: Any) -> None:
            cols = updates.cols
            people = cols.population().astype(np.float64)
            before = {
                "opening": cols.get("stores_kcal").copy(),  # K after trade
                "harvest": cols.get("harvest_kcal").copy(),  # H after trade
                "reserve": cols.get("reserve_kcal_per_capita") * people,
                "cell": np.asarray(cols.get("cell")).copy(),
            }
            apply(updates, state, ctx)
            self.years.append(
                {
                    "year": state.year,
                    "units": [u.id for u in cols.units],
                    "people": people,
                    "need": updates.need_kcal.copy(),
                    "retention": updates.retention.copy(),
                    "deficit": updates.deficit.copy(),  # unmet share after stores and reserves
                    "reserve_after": updates.reserve_kcal.copy(),
                    "stores_pre_retention": updates.stores_kcal.copy(),
                    **before,
                }
            )

        EnergyUpdates.apply = observed  # type: ignore[method-assign]
        return self

    def remove(self) -> None:
        EnergyUpdates.apply = self._saved  # type: ignore[method-assign]


def drive_observed(scenario: Any) -> tuple[Any, EnergeticsObserver]:
    observer = EnergeticsObserver().install()
    try:
        sim, _ = drive(scenario, None)
    finally:
        observer.remove()
    return sim, observer


# ---------------------------------------------------------------- analysis


def unit_series(observer: EnergeticsObserver) -> dict[str, dict[int, dict[str, float]]]:
    """Per unit, per year: the recorded energetics quantities."""
    series: dict[str, dict[int, dict[str, float]]] = defaultdict(dict)
    for y in observer.years:
        cols = {k: v for k, v in y.items() if isinstance(v, np.ndarray)}
        lists = {k: v.tolist() for k, v in cols.items()}
        for i, uid in enumerate(y["units"]):
            series[uid][y["year"]] = {k: lists[k][i] for k in lists}
    return series


def shortage_events(
    series: dict[str, dict[int, dict[str, float]]], carry_per_capita: float
) -> list[dict[str, Any]]:
    events = []
    for uid, years in series.items():
        ordered = sorted(years)
        for t in ordered:
            r = years[t]
            need, h, k = r["need"], r["harvest"], r["opening"]
            d = max(need - h, 0.0)
            if d <= DUST * need:
                continue
            x = max(k - r["stores_pre_retention"], 0.0)  # authoritative withdrawal
            current = release_current(d, k)
            events.append(
                {
                    "unit": uid, "year": t, "need": need, "harvest": h, "deficit": d,
                    "stores": k, "x": x, "x_rule": current.withdrawal, "reserve": r["reserve"],
                    "retention": r["retention"], "people": r["people"],
                    "energy_deficit": r["deficit"], "next": next_shortage(uid, t, years, carry_per_capita),
                }
            )  # fmt: skip
    return events


def next_shortage(
    uid: str, t: int, years: dict[int, dict[str, float]], carry_per_capita: float
) -> dict[str, Any] | None:
    """Post-hoc evaluation only: the unit's next authoritative shortage within HORIZON years,
    with the retention compounded on the way, the uncovered external need there and whether
    the unit relocated (and its carrying limit then)."""
    survival = years[t]["retention"]  # retained at t is kept through t's closing retention
    cell = years[t]["cell"]
    relocated_carry = None
    for y in range(t + 1, t + 1 + HORIZON):
        r = years.get(y)
        if r is None:
            return None  # the unit no longer exists under this id (fusion, extinction)
        if r["cell"] != cell and relocated_carry is None:
            relocated_carry = r["people"] * carry_per_capita
            cell = r["cell"]
        d = max(r["need"] - r["harvest"], 0.0)
        if d > DUST * r["need"]:
            x = max(r["opening"] - r["stores_pre_retention"], 0.0)
            return {
                "gap": y - t, "survival": survival, "uncovered": d - x, "stores": r["opening"],
                "relocated_carry": relocated_carry,
            }  # fmt: skip
        survival *= r["retention"]
    return {
        "gap": None,
        "survival": survival,
        "uncovered": 0.0,
        "stores": 0.0,
        "relocated_carry": relocated_carry,
    }


def evaluate(events: list[dict[str, Any]]) -> dict[float, list[dict[str, float]]]:
    out: dict[float, list[dict[str, float]]] = {}
    for b in BUFFERS:
        rows = []
        for e in events:
            target = need_buffer_target(e["need"], b)
            c = release_with_reserve_target(e["deficit"], e["stores"], target)
            s = c.retained_by_policy
            reserve = e["reserve"]
            starve_now = max(e["deficit"] - e["x_rule"] - reserve, 0.0)
            starve_c = max(c.unmet_external_need - reserve, 0.0)
            nxt = e["next"]
            surviving = s * nxt["survival"] if nxt else 0.0
            coverage = min(surviving, max(nxt["uncovered"], 0.0)) if nxt and nxt["gap"] else 0.0
            abandoned = 0.0
            if nxt and nxt["relocated_carry"] is not None:  # extra stock above the carry limit
                abandoned = (
                    min(surviving, max(nxt["stores"] + surviving - nxt["relocated_carry"], 0.0))
                    if nxt["gap"]
                    else 0.0
                )
            rows.append(
                {
                    "retained": s, "unmet": c.unmet_external_need,
                    "stores_left": e["stores"] - c.withdrawal,
                    "extra_reserve_draw": min(c.unmet_external_need, reserve) - min(e["deficit"] - e["x_rule"], reserve),
                    "extra_starvation": starve_c - starve_now,
                    "hunger_with_food": c.unmet_external_need > 0 and e["stores"] - c.withdrawal > 0,
                    "starvation_with_food": starve_c > 0 and e["stores"] - c.withdrawal > 0,
                    "people": e["people"], "need": e["need"],
                    "next_year_retained": s * e["retention"], "surviving_at_next_shortage": surviving,
                    "potential_coverage": coverage, "gap": (nxt or {}).get("gap"), "abandoned": abandoned,
                }
            )  # fmt: skip
        out[b] = rows
    return out


def job(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    scenario = scenario_for(name, seed, 0.0)
    sim, observer = drive_observed(scenario)
    plain, _ = drive(scenario, None)
    carry = float(next(iter(scenario.species.values())).movement.carry_kcal_per_capita)
    profile = next(iter(scenario.species.values()))
    cap_pc = profile.metabolism.reserve_days_max * profile.metabolism.adult_daily_kcal
    series = unit_series(observer)
    events = shortage_events(series, carry)
    rule_gap = max(
        (abs(e["x"] - e["x_rule"]) / max(e["stores"], e["need"]) for e in events), default=0.0
    )
    chains, gaps = [], []
    for years in series.values():
        short = sorted(t for t, r in years.items() if r["need"] - r["harvest"] > DUST * r["need"])
        run = 0
        for i, t in enumerate(short):
            run = (
                run + 1
                if i and t - short[i - 1] == 1 and all(y in years for y in (t - 1, t))
                else 1
            )
            if i + 1 == len(short) or short[i + 1] != t + 1:
                chains.append(run)
            if i:
                gaps.append(t - short[i - 1])
    unit_years = sum(len(y) for y in series.values())
    out = {
        "name": name, "seed": seed, "unit_years": unit_years, "events": events,
        "per_b": evaluate(events), "chains": chains, "gaps": gaps, "rule_gap": rule_gap,
        "reserve_cap_per_capita": cap_pc,
        "neutral": physical_digest(sim) == physical_digest(plain) and strata_digest(sim) == strata_digest(plain),
    }  # fmt: skip
    print(
        f"  done {name} seed {seed}: {len(events)} shortage unit-years, observer neutral {out['neutral']}",
        flush=True,
    )
    return out


# ---------------------------------------------------------------- report


def q(values: list[float] | np.ndarray, qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> str:
    """``p50/p90/p99/max``."""
    values = np.asarray([v for v in values if v is not None], dtype=float)
    if values.size == 0:
        return "-"
    return "/".join(f"{np.quantile(values, x):.3g}" for x in qs) + f"/max {values.max():.3g}"


def report(results: list[dict[str, Any]]) -> None:
    print(
        "authoritative state identical with the observer on/off:",
        all(r["neutral"] for r in results),
    )
    print(f"max |X_recorded - min(D, K)| / max(K, Need): {max(r['rule_gap'] for r in results):.3g}")
    for name in SCENARIOS:
        res = [r for r in results if r["name"] == name]
        events = [e for r in res for e in r["events"]]
        cap = res[0]["reserve_cap_per_capita"]
        print(f"\n=== {name}, seeds {tuple(r['seed'] for r in res)} ===")
        withdrawals = [e for e in events if e["x"] > 0]
        depleted = [e for e in withdrawals if e["x"] < e["deficit"] * (1 - 1e-12)]
        covered = [e for e in withdrawals if e["x"] >= e["deficit"] * (1 - 1e-12)]
        print("-- prevalence")
        print(
            f"unit-years {sum(r['unit_years'] for r in res)}; shortage unit-years (D > {DUST:g} Need) {len(events)}; with stores K > 0 {sum(e['stores'] > 0 for e in events)}; withdrawals {len(withdrawals)}"
        )
        print(
            f"  stores cover D {len(covered)}; stores exhausted short of D {len(depleted)}; no stores {sum(e['stores'] == 0 for e in events)}"
        )
        print(
            f"  D / Need {q([e['deficit'] / e['need'] for e in events])}; K / Need where K > 0 {q([e['stores'] / e['need'] for e in events if e['stores'] > 0])}"
        )
        rets = np.array([e["retention"] for e in events if e["stores"] > 0])
        vals, counts = np.unique(np.round(rets, 6), return_counts=True)
        print(
            "  storage retention at shortages with stores: "
            + ", ".join(f"{v:g}: {c}" for v, c in zip(vals, counts, strict=True))
        )
        full = [e["reserve"] >= cap * e["people"] * (1 - 1e-9) for e in events]
        print(
            f"  body reserves at the cap before the shortage {np.mean(full):.3f}; reserve / D {q([e['reserve'] / e['deficit'] for e in events])}"
        )
        chains = [c for r in res for c in r["chains"]]
        gaps = [g for r in res for g in r["gaps"]]
        cc = np.bincount(chains)
        print(
            f"-- shortage chains (consecutive years, one unit id): {len(chains)} chains; length 1/2/3/>=4: "
            f"{cc[1] if len(cc) > 1 else 0}/{cc[2] if len(cc) > 2 else 0}/{cc[3] if len(cc) > 3 else 0}/{cc[4:].sum()}; max {max(chains, default=0)}"
        )
        print(
            "   gap to the next shortage (years) p10/p50/p90 "
            + "/".join(f"{np.quantile(gaps, x):.0f}" for x in (0.1, 0.5, 0.9))
            + f"; share gap 1 {np.mean(np.array(gaps) == 1):.3f}"
        )
        nxt = [e["next"] for e in events if e["stores"] > 0]
        within = [n for n in nxt if n and n["gap"]]
        print(
            f"   shortages with stores followed by another shortage within {HORIZON} y (same unit id): {len(within)} of {len(nxt)}; "
            f"retained-food survival to it {q([n['survival'] for n in within])}; uncovered need there > 0: {sum(n['uncovered'] > 0 for n in within)}"
        )
        print("-- one-step counterfactual R = b * Need (rows: b; over shortage unit-years)")
        print(
            f"{'b':>5} {'binds':>7} {'retained kcal':>13} {'/ withdrawn':>11} {'hunger+food':>11} {'people':>8} {'unmet kcal':>11} {'extra reserve draw':>18} {'extra starvation kcal':>21} {'starv.+food':>11} {'next-yr kept':>12} {'surv. at next short.':>20} {'potential cover':>15} {'abandoned':>9}"
        )
        withdrawn = sum(e["x"] for e in events)
        for b in BUFFERS:
            rows = [row for r in res for row in r["per_b"][b]]
            binds = [row for row in rows if row["retained"] > 0]
            hf = [row for row in rows if row["hunger_with_food"]]
            sf = [row for row in rows if row["starvation_with_food"]]
            ret = sum(row["retained"] for row in rows)
            print(
                f"{b:>5} {len(binds):>7} {ret:>13.3g} {ret / withdrawn:>11.3f} {len(hf):>11} {sum(row['people'] for row in hf):>8.0f} "
                f"{sum(row['unmet'] for row in hf):>11.3g} {sum(row['extra_reserve_draw'] for row in rows):>18.3g} {sum(row['extra_starvation'] for row in rows):>21.3g} "
                f"{len(sf):>11} {sum(row['next_year_retained'] for row in rows):>12.3g} {sum(row['surviving_at_next_shortage'] for row in rows):>20.3g} "
                f"{sum(row['potential_coverage'] for row in rows):>15.3g} {sum(row['abandoned'] for row in rows):>9.3g}"
            )
        for b in BUFFERS[1:]:
            rows = [row for r in res for row in r["per_b"][b] if row["retained"] > 0]
            if not rows:
                continue
            ret = sum(row["retained"] for row in rows)
            print(
                f"  b={b}: per binding event retained/Need {q([row['retained'] / row['need'] for row in rows])}; "
                f"kept next year {sum(row['next_year_retained'] for row in rows) / ret:.3f} of retained; at next shortage {sum(row['surviving_at_next_shortage'] for row in rows) / ret:.3f}; "
                f"potential coverage {sum(row['potential_coverage'] for row in rows) / ret:.3f}; extra reserve draw {sum(row['extra_reserve_draw'] for row in rows) / ret:.3f}; "
                f"extra starvation {sum(row['extra_starvation'] for row in rows) / ret:.3f} (all per kcal retained)"
            )


# ---------------------------------------------------------------- controlled


def toy(
    harvests: list[float],
    b: float,
    retention: float,
    stores: float = 0.0,
    need: float = 1000.0,
    reserve: float = 160.0,
    cap: float = 160.0,
    carry: float | None = None,
    move_year: int | None = None,
) -> dict[str, float]:
    """A closed unit through the real ``energy_balance``: harvests prescribed, need fixed,
    no demography or trade. In shortage years only the stores above ``b * need`` are offered
    to ``energy_balance``; the rest is added back. Closing stores are retained at
    ``retention``; ``move_year`` abandons stores above ``carry``."""
    starvation = spoiled = withheld = hunger_food_years = 0.0
    trace = []
    for year, h in enumerate(harvests):
        if move_year == year and carry is not None:
            stores = min(stores, carry)
        short = h < need
        protected = min(stores, need_buffer_target(need, b)) if short else 0.0
        bal = energy_balance(need, h, reserve, cap, stores - protected, can_store=True)
        if short:
            current = release_current(need - h, stores).withdrawal
            withdrawn = (stores - protected) - bal.stores_kcal
            withheld += current - withdrawn
            hunger_food_years += (need - h - withdrawn > 0) and protected > 0
        starvation += bal.deficit * need
        closing = bal.stores_kcal + protected
        spoiled += closing * (1 - retention)
        stores, reserve = closing * retention, bal.reserve_kcal
        trace.append(round(stores))
    return {"starvation": starvation, "spoiled": spoiled, "withheld": withheld,
            "hunger_with_food_years": hunger_food_years, "final_stores": stores, "final_reserve": reserve, "trace": trace}  # fmt: skip


def controlled() -> None:
    need = 1000.0
    cases = {
        "deficit then abundance": dict(harvests=[1500, 600, 1500, 1500], retention=0.5),
        "consecutive shortages": dict(harvests=[1600, 600, 500, 400], retention=0.5),
        "long gap (r = 0.5)": dict(
            harvests=[1600, 600, 1000, 1000, 1000, 1000, 400], retention=0.5
        ),
        "high spoilage (r = 0.15)": dict(harvests=[1600, 700, 600], retention=0.15),
        "low spoilage (r = 0.8)": dict(harvests=[1600, 700, 600], retention=0.8),
        "carry limit at a move": dict(
            harvests=[1600, 800, 1000, 600], retention=0.8, carry=150.0, move_year=2
        ),
        "exhaustion under current rule": dict(harvests=[1300, 500, 500], retention=0.8),
        "full store, moderate deficit": dict(
            harvests=[1000, 900, 1000], retention=0.8, stores=1000.0
        ),
    }
    print(
        "Controlled replay of a CLOSED toy unit (valid only because nothing here feeds back: no demography,"
    )
    print(
        "trade or migration decisions). Need 1000/y, body reserve cap 160 (≈ 60 days), real energy_balance; kcal over the sequence."
    )
    print(
        "starvation = unmet energy after stores and reserves (drives mortality); stores trace = after retention."
    )
    for label, kw in cases.items():
        print(f"\n== {label}: harvests {kw['harvests']}, retention {kw['retention']}")
        for b in (0.0, 0.2, 0.5, 1.0):
            r = toy(b=b, need=need, **kw)  # type: ignore[arg-type]
            print(
                f"  b={b:<4} starvation {r['starvation']:7.1f}  spoiled {r['spoiled']:7.1f}  withheld {r['withheld']:6.1f}  "
                f"hunger-with-food years {r['hunger_with_food_years']:.0f}  final stores {r['final_stores']:6.1f} reserve {r['final_reserve']:5.1f}  stores {r['trace']}"
            )
    print(
        "\n== body reserves vs stores: withholding S converts S of lossless body reserve into S*r of stores"
    )
    print(
        "  harvests [1600, 700, 1300] (one shortage, then a surplus that refills reserves first):"
    )
    for r_ in (0.15, 0.5, 0.8):
        cells = []
        for b in (0.0, 0.1, 0.5):
            c = toy([1600, 700, 1300], b, r_)
            cells.append(
                f"b={b}: starvation {c['starvation']:5.1f}, final stores + reserve {c['final_stores'] + c['final_reserve']:6.1f}"
            )
        print(f"  r={r_}: " + "; ".join(cells))
    print(
        "\n== composition (not activated): a candidate release X, then the Stage 4C allocator (a = 1)"
    )
    share, claim = np.array([0.8, 0.2]), np.array([0.5, 0.5])
    for b in (0.0, 0.5):
        rel = release_with_reserve_target(600.0, 800.0, need_buffer_target(need, b))
        acc = counterfactual_store_access(share, claim, need, 400.0, rel.withdrawal, 1.0)
        print(
            f"  b={b}: X={rel.withdrawal:.0f} retained {rel.retained_by_policy:.0f}; x_i={acc.counterfactual_store_access_kcal}; unmet_i={acc.counterfactual_unmet_external_need_kcal}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=("controlled", "runs", "report"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    parser.add_argument("--out")
    parser.add_argument("--load")
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "report":
        with open(args.load, "rb") as f:
            results = pickle.load(f)
        for r in results:  # re-evaluate the policy on the recorded states (cheap)
            r["per_b"] = evaluate(r["events"])
        report(results)
        return
    seeds = tuple(int(s) for s in args.seeds.split(","))
    work = [(name, seed) for name in SCENARIOS for seed in seeds]
    with Pool(args.jobs, maxtasksperchild=1) as pool:
        results = pool.map(job, work, chunksize=1)
    if args.out:
        with open(args.out, "wb") as f:
            pickle.dump(results, f)
    report(results)


if __name__ == "__main__":
    main()
