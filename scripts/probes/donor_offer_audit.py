# The report tables keep one entry per line.
# ruff: noqa: E501
"""Donor decisions in food provisioning (MVP 3 Stage 6A). Observation only.
COUNTERFACTUAL / NOT ACTIVE.

``record`` runs the MVP 2.2 reference scenarios (``scenarios/mvp2_2_*.yaml``) with two
read-only hooks:

- ``TradeSubsystem.evaluate``: each unit's pre-trade need, harvest, stores, body reserve and
  cap, storage retention, last year's deficit, harvest memory and tie total; the reachable
  offering donors of every deficit unit; the authoritative transfers;
- ``EnergeticsSubsystem.evaluate``: the authoritative post-trade energy outcome.

``analyse`` rebuilds offers and deficits with ``economy/donor_offer.py`` from the raw
inputs and replays the matching (``provisioning_counterfactual.match``); D0 must reproduce
every authoritative transfer exactly. It then decomposes each donor-year (surplus, offer,
shipment, delivery, retention), measures offer use and the static and later cost of giving
to the donor, tests what the donor could know, and re-matches each recorded year with the
offer fraction replaced (``PHIS``: sensitivity conditions, not strategies). Nothing is
re-simulated per setting and nothing feeds back (checked by digest).

Usage:
    uv run python scripts/probes/donor_offer_audit.py record [--jobs 2] [--seeds 0 1 2 3] --out DIR
    uv run python scripts/probes/donor_offer_audit.py analyse --load DIR [--jobs 2]
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

from _common import SEEDS, physical_digest, q

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.donor_offer import (
    DUST_KCAL,
    balances,
    deficits_of,
    donor_payment,
    giving_cost,
    offer_use,
    offers_at,
    unmet,
)
from madexplorer.economy.provisioning_counterfactual import Match, choice_levels, match, without
from madexplorer.economy.trade import TradeSubsystem
from madexplorer.population.demography import fertility_multiplier
from madexplorer.population.energetics import (
    EnergeticsSubsystem,
    annual_need_columns,
    capability_column,
    energy_balance,
)

MVP2_2 = {  # the MVP 2.2 reference runs (baselines/mvp2_2)
    "neolithic": ("scenarios/mvp2_2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 400, {"mechanisms.cultivation": True}),
}
PHIS = (0.0, 0.1, 0.2, 0.3, 0.45, 0.6, 1.0)  # offer fraction of surplus; 0.3 = production (D0)
REMATCH_PHIS = (0.15, 0.3, 0.6)  # network rematching without the primary donor (costly)
HORIZONS = (1, 3, 5, 10)
MID, SCALE = 0.8, 0.1  # human.yaml fertility_food_midpoint / scale


def scenario(name: str, seed: int) -> Scenario:
    path, horizon, settings = MVP2_2[name]
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=horizon)
    return base.with_settings(settings) if settings else base


def fert(intake: float) -> float:
    return float(fertility_multiplier(np.array([intake]), MID, SCALE)[0])


def intake_of(need: float, harvest: float, stores: float) -> float:
    """``dietary_intake_ratio`` for one unit."""
    if need <= 0 or harvest >= need:
        return 1.0
    return min((harvest + min(need - harvest, stores)) / need, 1.0)


# ---------------------------------------------------------------- recording


class Recorder:
    def __init__(self) -> None:
        self.trade: list[dict[str, Any]] = []
        self.energy: dict[int, dict[str, tuple[float, ...]]] = {}
        self._saved: dict[str, Any] = {}

    def install(self) -> None:
        rec = self
        trade0, energy0 = TradeSubsystem.evaluate, EnergeticsSubsystem.evaluate

        def trade(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = trade0(sub, state, ctx)
            cols = ctx.columns(state)
            if not len(cols):
                return proposals
            p = ctx.compiled.parameter
            species = cols.species()
            need = annual_need_columns(cols, state, ctx).tolist()
            harvest, stores = cols.get("harvest_kcal").tolist(), cols.get("stores_kcal").tolist()
            people = cols.population().astype(float)
            reserve = (cols.get("reserve_kcal_per_capita") * people).tolist()
            cap = (people * p("metabolism.reserve_days_max")[species]
                   * p("metabolism.adult_daily_kcal")[species]).tolist()  # fmt: skip
            retention = capability_column(cols, ctx, "storage_retention").tolist()
            share = p("social.food_sharing_propensity")[species].tolist()
            prev_deficit = cols.get("energy_deficit").tolist()
            cells = cols.get("cell").tolist()
            ids = [u.id for u in cols.units]
            info = {}
            offering: dict[int, list[str]] = defaultdict(list)
            for k, u in enumerate(cols.units):
                info[u.id] = {
                    "need": need[k], "harvest": harvest[k], "stores": stores[k],
                    "reserve": reserve[k], "cap": cap[k], "retention": retention[k],
                    "share": share[k], "cell": cells[k], "people": int(people[k]),
                    "species": u.species_id, "prev_deficit": prev_deficit[k],
                    "history": tuple(u.harvest_history), "variability": u.harvest_variability(),
                    "ties": sum(u.trade_ties.values()),
                }  # fmt: skip
                if harvest[k] + stores[k] - need[k] > 0:
                    offering[cells[k]].append(u.id)
            donors_of = {}
            for uid in ids:
                i = info[uid]
                if i["harvest"] + i["stores"] - i["need"] < 0 and i["need"] > 0:
                    reach = ctx.movement[i["species"]].reachable(i["cell"])
                    donors_of[uid] = sorted(
                        (cost, did) for cell, cost in reach.items() for did in offering.get(cell, ())
                        if info[did]["species"] == i["species"]
                    )  # fmt: skip
            rec.trade.append({
                "year": state.year, "order": ids, "info": info, "donors_of": donors_of,
                "decay": ctx.scenario.config.trade.transport_decay_km,
                "actual": [(t.donor_id, t.recipient_id, t.sent_kcal, t.received_kcal)
                           for t in proposals[0].transfers],
            })  # fmt: skip
            return proposals

        def energy(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = energy0(sub, state, ctx)
            if proposals:
                u = proposals[0]
                cols = u.cols
                people = cols.population().astype(float)
                h, st = cols.get("harvest_kcal").tolist(), cols.get("stores_kcal").tolist()
                rec.energy[state.year] = {
                    unit.id: (float(u.need_kcal[k]), h[k], st[k], float(u.reserve_kcal[k]),
                              float(u.stores_kcal[k]) * float(u.retention[k]), float(u.food_ratio[k]),
                              float(u.deficit[k]), int(people[k]), float(u.retention[k]),
                              None if u.dietary_intake is None else float(u.dietary_intake[k]))
                    for k, unit in enumerate(cols.units)
                }  # fmt: skip
            return proposals

        self._saved = {"trade": trade0, "energy": energy0}
        TradeSubsystem.evaluate = trade  # type: ignore[method-assign]
        EnergeticsSubsystem.evaluate = energy  # type: ignore[method-assign]

    def remove(self) -> None:
        TradeSubsystem.evaluate = self._saved["trade"]  # type: ignore[method-assign]
        EnergeticsSubsystem.evaluate = self._saved["energy"]  # type: ignore[method-assign]


def _run(sc: Scenario, years: int | None = None) -> tuple[Simulator, int]:
    sim = Simulator(sc)
    done = 0
    for done in range(1, (years or sc.config.simulation.n_years) + 1):  # noqa: B007
        sim.step()
        if not sim.state.units:
            break
    return sim, done


def record_job(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    sc = scenario(name, seed)
    rec = Recorder()
    rec.install()
    try:
        sim, years = _run(sc)
    finally:
        rec.remove()
    plain, _ = _run(sc, years)
    events = [(e.year, e.kind, dict(e.data)) for e in sim.events
              if e.kind in ("population_split", "population_merge", "unit_extinct")]  # fmt: skip
    return {"name": name, "seed": seed, "trade": rec.trade, "energy": rec.energy, "events": events,
            "neutral": physical_digest(sim) == physical_digest(plain)}  # fmt: skip


# ---------------------------------------------------------------- analysis helpers


def inputs(y: dict[str, Any]) -> tuple[dict[str, float], dict[str, float], list[Any]]:
    """(balance, share, deficits) rebuilt from the raw pre-trade inputs in production order."""
    info = y["info"]
    order = y["order"]
    b = balances({u: info[u]["harvest"] for u in order}, {u: info[u]["stores"] for u in order},
                 {u: info[u]["need"] for u in order})  # fmt: skip
    share = {u: info[u]["share"] for u in order}
    return b, share, deficits_of(b, {u: info[u]["need"] for u in order})


def _replay(
    y: dict[str, Any], offers: dict[str, float], deficits: list[Any], record: bool = False
) -> Match:
    return match(deficits, offers, y["donors_of"], y["decay"], record=record)


def _primary(m: Match) -> tuple[dict[str, str], dict[str, dict[str, float]]]:
    by: dict[str, dict[str, float]] = defaultdict(dict)
    for d, r, _s, g in m.transfers:
        by[r][d] = by[r].get(d, 0.0) + g
    return {r: max(v, key=lambda k: (v[k], k)) for r, v in by.items()}, by


def kin_distance(a: str, b: str, parent: dict[str, str], depth: int = 6) -> int:
    """Fission links between two units through their nearest common ancestor (fusion keeps
    the target's id and is ignored); ``depth + 1`` when none within ``depth`` generations."""

    def line(u: str) -> list[str]:
        out = [u]
        while len(out) <= depth and out[-1] in parent:
            out.append(parent[out[-1]])
        return out

    la, lb = line(a), line(b)
    pos = {u: k for k, u in enumerate(la)}
    best = depth + 1
    for k, u in enumerate(lb):
        if u in pos:
            best = min(best, pos[u] + k)
    return best


def _hhi(values: list[float]) -> float:
    total = sum(values)
    return sum((v / total) ** 2 for v in values) if total > 0 else 0.0


def _auc(score: np.ndarray, label: np.ndarray) -> float:
    """Rank AUC (ties averaged): P(score of a positive > score of a negative)."""
    pos, neg = label.sum(), (~label).sum()
    if pos == 0 or neg == 0:
        return float("nan")
    order = np.argsort(score, kind="stable")
    ranks = np.empty(score.size)
    s = score[order]
    i = 0
    while i < s.size:
        j = i
        while j + 1 < s.size and s[j + 1] == s[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[label].sum() - pos * (pos + 1) / 2) / (pos * neg))


# ---------------------------------------------------------------- analysis (one run)


def analyse_run(run: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = defaultdict(list)
    out["years"] = out["exact_years"] = out["offer_exact_years"] = 0
    out["energy_err"] = 0.0
    sens: dict[float, dict[str, float]] = {phi: defaultdict(float) for phi in PHIS}
    gift: dict[str, dict[int, Any]] = defaultdict(dict)  # unit -> year -> GivingCost
    surplus_years: dict[str, dict[int, bool]] = defaultdict(dict)  # unit -> year -> shipped?
    parent = {
        e[2]["daughter_id"]: e[2]["unit_id"] for e in run["events"] if e[1] == "population_split"
    }
    budget: dict[str, float] = defaultdict(float)
    for y in run["trade"]:
        out["years"] += 1
        info, year = y["info"], y["year"]
        b, share, deficits = inputs(y)
        d0_offers = offers_at(b, share)
        d0 = _replay(y, d0_offers, deficits, record=True)
        exact = d0.transfers == y["actual"]
        out["exact_years"] += exact
        if not exact:
            continue
        uses = offer_use(d0_offers, d0)
        left = unmet(deficits, d0)
        reach: dict[str, list[str]] = defaultdict(list)  # donor -> recipients in range
        for rid, cand in y["donors_of"].items():
            for _c, did in cand:
                reach[did].append(rid)
        # --- A. per donor-year decomposition and offer use
        energy = run["energy"].get(year, {})
        for did, use in uses.items():
            i = info[did]
            cost = giving_cost(i["need"], i["harvest"], i["stores"], i["reserve"], i["cap"],
                               i["retention"], use.shipments)  # fmt: skip
            if did in energy:  # authoritative post-trade energetics agree with the static replay
                e = energy[did]
                h1, s1 = donor_payment(i["harvest"], i["stores"], use.shipments)
                ref = energy_balance(i["need"], h1, i["reserve"], i["cap"], s1, i["retention"] > 0)
                out["energy_err"] = max(out["energy_err"], abs(ref.food_ratio - e[5]), abs(ref.deficit - e[6]),
                                        abs(ref.stores_kcal * i["retention"] - e[4]))  # fmt: skip
            rivals = len(reach.get(did, ()))
            out["donor"].append({
                "year": year, "id": did, "need": i["need"], "harvest": i["harvest"], "stores": i["stores"],
                "surplus": b[did], "offer": use.offered, "shipped": use.shipped, "delivered": use.delivered,
                "state": use.state, "rivals": rivals, "people": i["people"], "retention": i["retention"],
                "harvest_covers": i["harvest"] >= i["need"],
                "unmet_in_reach": sum(left[r] > DUST_KCAL for r in reach.get(did, ())),
                "from_stores": cost.from_stores, "carried": cost.carried, "reserve_cost": cost.reserve,
                "retained_cost": cost.retained, "d_deficit": cost.deficit, "fr_after": cost.food_ratio_after,
                "intake_after": cost.intake_after, "variability": i["variability"],
                "hist_len": len(i["history"]), "prev_deficit": i["prev_deficit"], "ties": i["ties"],
            })  # fmt: skip
            surplus_years[did][year] = use.shipped > DUST_KCAL
            if use.shipped > DUST_KCAL:
                gift[did][year] = cost
        # --- recipient-side demand against offers
        for _, rid, deficit, need in deficits:
            cand = y["donors_of"].get(rid, [])
            out["recipient"].append({"year": year, "id": rid, "deficit": deficit, "need": need,
                                     "unmet": left[rid], "reach": len(cand), "people": info[rid]["people"]})  # fmt: skip
        out["year_balance"].append((sum(d0_offers.values()), sum(x for _, _, x, _ in deficits),
                                    d0.totals()[0], sum(left.values())))  # fmt: skip
        # --- kin substrate (descriptive): fission genealogy of donor and recipient, by cost rank
        pairs = {(d, r): g for d, r, _s, g in d0.transfers if g > DUST_KCAL}
        for _, rid, _x, _n in deficits:
            for rank, (_c, did) in enumerate(y["donors_of"].get(rid, [])):
                out["kin"].append((min(rank, 3), kin_distance(did, rid, parent), (did, rid) in pairs,
                                   pairs.get((did, rid), 0.0)))  # fmt: skip
        # --- S1 illustration: keep enough to cover the worst remembered shortfall next year
        for key, r_fixed in (("s1", None), ("s1r1", 1.0)):
            offers_s1 = {}
            for did, o in d0_offers.items():
                i = info[did]
                per_capita = i["need"] / i["people"] if i["people"] else 0.0
                worst = (
                    max((max(0.0, 1.0 - h / per_capita) for h in i["history"]), default=0.0)
                    if per_capita > 0
                    else 0.0
                )
                r = i["retention"] if r_fixed is None else r_fixed
                buffer = worst * i["need"] / r if r > 0 else (float("inf") if worst > 0 else 0.0)
                offers_s1[did] = min(o, max(b[did] - buffer, 0.0))
                budget[f"{key}_reduced"] += float(offers_s1[did] < o)
                budget[f"{key}_zero"] += float(offers_s1[did] <= 0.0)
            m1 = _replay(y, offers_s1, deficits)
            budget[f"{key}_delivered"] += m1.totals()[1]
            budget[f"{key}_unmet"] += sum(unmet(deficits, m1).values())
        budget["donors"] += len(d0_offers)
        budget["d0_delivered"] += d0.totals()[1]
        budget["d0_unmet"] += sum(left.values())
        # --- B. offer-fraction sensitivity (same inputs, full re-matching)
        base_rec = d0.received()
        base_prim, _ = _primary(d0)
        for phi in PHIS:
            offers = offers_at(b, phi)
            m = d0 if phi == 0.3 else _replay(y, offers, deficits, record=True)
            agg = sens[phi]
            shipped, arrived = m.totals()
            agg["shipped"] += shipped
            agg["delivered"] += arrived
            agg["offered"] += sum(offers.values())
            agg["deficit"] += sum(x for _, _, x, _ in deficits)
            rec = m.received()
            prim, by = _primary(m)
            for _, rid, deficit, need in deficits:
                i = info[rid]
                got = rec.get(rid, 0.0)
                agg["recipients"] += 1
                agg["unmet"] += max(deficit - got, 0.0)
                agg["still_short"] += float(deficit - got > 1e-9 * need)
                h_after = i["harvest"] + got
                agg["intake"] += intake_of(need, h_after, i["stores"])
                agg["fert"] += fert(intake_of(need, h_after, i["stores"]))
                eb = energy_balance(
                    need, h_after, i["reserve"], i["cap"], i["stores"], i["retention"] > 0
                )
                agg["energy_deficit_kcal"] += eb.deficit * need
                d_rec = got - base_rec.get(rid, 0.0)
                agg["gain"] += float(d_rec > 0.01 * need)
                agg["loss"] += float(d_rec < -0.01 * need)
                if rid in by:
                    agg["served"] += 1
                    agg["donors_per"] += len(by[rid])
                    agg["top_share"] += max(by[rid].values()) / sum(by[rid].values())
                    agg["single_dep"] += float(max(by[rid].values()) > 0.5 * sum(by[rid].values()))
                    agg["prim_changed"] += float(prim.get(rid) != base_prim.get(rid))
            sent = m.sent()
            agg["hhi"] += _hhi(list(sent.values()))
            agg["hhi_years"] += 1.0 if sent else 0.0
            agg["donors_used"] += sum(v > DUST_KCAL for v in sent.values())
            u = offer_use(offers, m)
            agg["exhausted"] += sum(x.state == "exhausted" for x in u.values())
            agg["n_offers"] += len(u)
            for did, x in u.items():
                i = info[did]
                c = giving_cost(
                    i["need"],
                    i["harvest"],
                    i["stores"],
                    i["reserve"],
                    i["cap"],
                    i["retention"],
                    x.shipments,
                )
                agg["donor_carried"] += c.carried
                h1, s1 = donor_payment(i["harvest"], i["stores"], x.shipments)
                kept = energy_balance(i["need"], h1, i["reserve"], i["cap"], s1, i["retention"] > 0)
                agg["donor_retained_after"] += kept.stores_kcal * i["retention"]
                agg["donor_fr_below1"] += float(c.food_ratio_after < 1.0)
            for dec in m.decisions:
                if dec.recipient in rec:
                    agg["eff25"] += float(choice_levels(dec, 0.25)["effective"])
                    agg["decisions"] += 1
            if phi in REMATCH_PHIS:  # network rematching without each recipient's primary donor
                for r, p in prim.items():
                    alt = _replay(y, without(offers, p), deficits).received().get(r, 0.0)
                    lost = by[r][p]
                    replaced = (
                        min(max((alt - (rec[r] - lost)) / lost, 0.0), 1.0) if lost > 0 else 1.0
                    )
                    agg["net_n"] += 1
                    agg["net_full"] += float(replaced >= 1.0 - 1e-9)
                    agg["net_none"] += float(replaced <= 1e-9)
    out["sens"] = {phi: dict(v) for phi, v in sens.items()}
    out["s1"] = dict(budget)
    # --- C. later consequences for donors (descriptive; authoritative histories by unit id)
    energy_years = sorted(run["energy"])
    by_unit: dict[str, dict[int, tuple[float, ...]]] = defaultdict(dict)
    for yr in energy_years:
        for uid, e in run["energy"][yr].items():
            by_unit[uid][yr] = e
    last_year = energy_years[-1] if energy_years else 0
    for uid, years in surplus_years.items():
        hist = by_unit.get(uid, {})
        for yr, shipped in years.items():
            for h in HORIZONS:
                if yr + h > last_year:
                    continue
                alive = all((yr + k) in hist for k in range(1, h + 1))
                window = [hist[yr + k] for k in range(1, h + 1) if (yr + k) in hist]
                gap = any(
                    e[0] > 0 and e[1] < e[0] and e[1] + e[2] < e[0] for e in window
                )  # intake < 1
                starve = any(e[6] > 0 for e in window)
                short = any(e[1] < e[0] for e in window)  # harvest after trade below need
                out["later"].append((h, shipped, alive, short, gap, starve))
    # shadow buffer: what the donor's own giving cost would have left it, all else equal
    for uid, gifts in gift.items():
        hist = by_unit.get(uid, {})
        stores_x, reserve_x = 0.0, 0.0
        total_cost = 0.0
        covered_gap = covered_def = 0.0
        for yr in range(min(gifts), last_year + 1):
            e = hist.get(yr)
            if e is None:
                break  # merged away, extinct or renamed: the shadow is lost with the unit
            need, h, st, _res, _ret, _fr, de, _p, retention, _in = e
            gap = max(need - h - st, 0.0) if h < need else 0.0  # stores exhausted: intake < 1
            use = min(stores_x, gap)
            covered_gap += use
            stores_x -= use
            deficit_kcal = de * need
            use_def = min(stores_x + reserve_x, deficit_kcal)
            covered_def += use_def
            take = min(stores_x, use_def)
            stores_x -= take
            reserve_x -= use_def - take
            stores_x *= retention
            if yr in gifts:
                c = gifts[yr]
                stores_x += c.retained
                reserve_x += c.reserve
                total_cost += c.carried
        out["shadow"].append(
            (total_cost, covered_gap, covered_def, sum(g.sent for g in gifts.values()))
        )
    # --- D. information: does what the donor knows predict its own later shortage?
    for row in out["donor"]:
        hist = by_unit.get(row["id"], {})
        yr = row["year"]
        if yr + 5 > last_year or not all((yr + k) in hist for k in range(1, 6)):
            continue
        window = [hist[yr + k] for k in range(1, 6)]
        row["future_gap5"] = any(e[1] < e[0] and e[1] + e[2] < e[0] for e in window)
        row["future_short5"] = any(e[1] < e[0] for e in window)
    return dict(out)


# ---------------------------------------------------------------- report


def _frac(x: float, n: float) -> str:
    return f"{x / n:.3f}" if n else "-"


def report(name: str, outs: list[dict[str, Any]]) -> None:
    years = sum(o["years"] for o in outs)
    exact = sum(o["exact_years"] for o in outs)
    print(f"\n=== {name}")
    print(f"-- D0 replay from raw inputs: {exact}/{years} trade years reproduce every authoritative transfer bit for bit; "
          f"max static-vs-authoritative donor energetics error {max(o['energy_err'] for o in outs):.3g}")  # fmt: skip
    donors = [r for o in outs for r in o["donor"]]
    recs = [r for o in outs for r in o["recipient"]]
    n = len(donors)
    pop = np.array([r["people"] for r in donors], float)
    off = np.array([r["offer"] for r in donors])
    shp = np.array([r["shipped"] for r in donors])
    states = np.array([r["state"] for r in donors])
    print(f"\n-- A. donor-years (b > 0): {n}; recipient-years (b < 0): {len(recs)}")
    for st in ("exhausted", "partial", "unused"):
        k = states == st
        print(
            f"   offer {st:9s}: unit {k.mean():.3f}  pop {pop[k].sum() / pop.sum():.3f}  offered-kcal {off[k].sum() / off.sum():.3f}  shipped-kcal {shp[k].sum() / max(shp.sum(), 1e-300):.3f}"
        )
    used = shp > DUST_KCAL
    print(f"   shipped/offered where shipped (p10/p50/p90): {np.quantile(shp[used] / off[used], [0.1, 0.5, 0.9]).round(3).tolist()}; "
          f"total shipped/offered {shp.sum() / off.sum():.3f}")  # fmt: skip
    rivals = np.array([r["rivals"] for r in donors])
    unmet_reach = np.array([r["unmet_in_reach"] for r in donors])
    print(
        f"   donors with no recipient in reach: {(rivals == 0).mean():.3f}; contested (>= 2 recipients in reach): {(rivals >= 2).mean():.3f}"
    )
    print(
        f"   unused or partial offers with an unmet recipient still in reach: {((states != 'exhausted') & (unmet_reach > 0)).sum()} (structurally 0: a recipient takes every reachable offer before staying short)"
    )
    print(f"   exhausted offers with an unmet recipient in reach (offer binds): unit {((states == 'exhausted') & (unmet_reach > 0)).mean():.3f} of donor-years, "
          f"{((states == 'exhausted') & (unmet_reach > 0)).sum() / max((states == 'exhausted').sum(), 1):.3f} of exhausted")  # fmt: skip
    rd = np.array([r["deficit"] for r in recs])
    ru = np.array([r["unmet"] for r in recs])
    rn = np.array([r["need"] for r in recs])
    print(f"   recipient-years still short after matching (all reachable offers exhausted): {(ru > 1e-9 * rn).mean():.3f}; "
          f"unmet / pre-trade deficit {ru.sum() / rd.sum():.3f}; no donor in reach {np.mean([r['reach'] == 0 for r in recs]):.3f}")  # fmt: skip
    yb = np.array([v for o in outs for v in o["year_balance"]])
    print(
        f"   years with total offers < total deficits: {(yb[:, 0] < yb[:, 1]).mean():.3f}; total offered / total deficit {yb[:, 0].sum() / yb[:, 1].sum():.2f}"
    )
    # composition of surplus and payment
    sur = np.array([r["surplus"] for r in donors])
    stores = np.array([r["stores"] for r in donors])
    hc = np.array([r["harvest_covers"] for r in donors])
    fs = np.array([r["from_stores"] for r in donors])
    print(f"   harvest alone covers need: {hc.mean():.3f}; stores share of surplus (kcal) {np.minimum(stores, sur).sum() / sur.sum():.3f}; "
          f"shipped kcal paid from stores {fs.sum() / max(shp.sum(), 1e-300):.3f}")  # fmt: skip
    # --- static cost of giving
    giv = [r for r in donors if r["shipped"] > DUST_KCAL]
    carried = np.array([r["carried"] for r in giv])
    sent = np.array([r["shipped"] for r in giv])
    ret = np.array([r["retention"] for r in giv])
    print(f"\n-- static cost of giving (giving donor-years {len(giv)}): carried-into-next-year / shipped = {carried.sum() / sent.sum():.3f} "
          f"(reserve {sum(r['reserve_cost'] for r in giv) / sent.sum():.3f}, stores {sum(r['retained_cost'] for r in giv) / sent.sum():.3f}); lost anyway {1 - carried.sum() / sent.sum():.3f}")  # fmt: skip
    for r_ in sorted(set(ret.round(2).tolist())):
        k = ret.round(2) == r_
        print(
            f"   retention {r_:.2f}: donor-years {k.sum()}, carried/shipped {carried[k].sum() / sent[k].sum():.3f}"
        )
    print(f"   same-year extra energy deficit > 0: {sum(r['d_deficit'] > 0 for r in giv)}; intake after giving < 1: {sum(r['intake_after'] < 1 for r in giv)}; "
          f"food_ratio pushed below 1 (fission/innovation inputs): {np.mean([r['fr_after'] < 1 <= r['harvest'] / r['need'] for r in giv]):.3f}")  # fmt: skip
    # --- later consequences
    later = np.array([v for o in outs for v in o["later"]], dtype=float)
    print(
        "\n-- later shortages after a surplus year (descriptive, authoritative history; alive for the whole window)"
    )
    print("   horizon | gave: short / intake<1 / energy deficit | surplus, nothing shipped: same")
    for h in HORIZONS:
        k = (later[:, 0] == h) & (later[:, 2] == 1)
        g, ng = k & (later[:, 1] == 1), k & (later[:, 1] == 0)
        print(f"   {h:2d} y   | {later[g, 3].mean():.3f} / {later[g, 4].mean():.3f} / {later[g, 5].mean():.3f}  (n {g.sum()}) | "
              f"{later[ng, 3].mean() if ng.any() else float('nan'):.3f} / {later[ng, 4].mean() if ng.any() else float('nan'):.3f} / {later[ng, 5].mean() if ng.any() else float('nan'):.3f}  (n {ng.sum()})")  # fmt: skip
    sh = np.array([v for o in outs for v in o["shadow"]])
    if sh.size:
        print(f"   shadow buffer (donor's own carried cost, decayed with its retention, used first-come): of {sh[:, 0].sum():.3g} kcal carried cost "
              f"({sh[:, 0].sum() / sh[:, 3].sum():.3f} of shipped), would later cover intake gaps {sh[:, 1].sum() / sh[:, 0].sum():.4f} and "
              f"energy deficits {sh[:, 2].sum() / sh[:, 0].sum():.4f}; donors with any covered gap {np.mean(sh[:, 1] > 0):.3f}, deficit {np.mean(sh[:, 2] > 0):.3f}")  # fmt: skip
    # --- information
    rows = [r for r in donors if "future_gap5" in r]
    if rows:
        lab_gap = np.array([r["future_gap5"] for r in rows])
        lab_short = np.array([r["future_short5"] for r in rows])
        print(
            f"\n-- information at the decision (donor-years with a 5-y future: {len(rows)}; future short {lab_short.mean():.3f}, future intake<1 {lab_gap.mean():.3f})"
        )
        print(
            f"   harvest memory available (>= 3 y): {np.mean([r['hist_len'] >= 3 for r in donors]):.3f}"
        )
        feats = {
            "harvest variability (CV of memory)": np.array([r["variability"] for r in rows]),
            "last year's energy deficit": np.array([r["prev_deficit"] for r in rows]),
            "-(surplus / need)": -np.array([r["surplus"] / r["need"] for r in rows]),
            "-(stores / need)": -np.array([r["stores"] / r["need"] for r in rows]),
            "-(harvest / need)": -np.array([r["harvest"] / r["need"] for r in rows]),
        }
        for k, v in feats.items():
            print(
                f"   AUC {k:38s} future short {_auc(v, lab_short):.3f}  future intake<1 {_auc(v, lab_gap):.3f}"
            )
    # --- kin substrate
    kin = np.array([v for o in outs for v in o["kin"]], dtype=float)
    if kin.size:
        print(
            "\n-- kin substrate (fission genealogy; distance = fission links via the nearest common ancestor; descriptive)"
        )
        for label, k in (("parent-daughter (1)", kin[:, 1] == 1), ("siblings/grand (2)", kin[:, 1] == 2),
                         ("3-6", (kin[:, 1] >= 3) & (kin[:, 1] <= 6)), ("unrelated within 6", kin[:, 1] > 6)):  # fmt: skip
            rates = " ".join(
                f"r{rk}:{kin[k & (kin[:, 0] == rk), 2].mean() if (k & (kin[:, 0] == rk)).any() else float('nan'):.3f}"
                for rk in range(4)
            )
            print(
                f"   {label:20s} opportunities {k.mean():.3f}  delivered-kcal share {kin[k, 3].sum() / kin[:, 3].sum():.3f}  transfer rate by cost rank {rates}"
            )
    s1: dict[str, float] = defaultdict(float)
    for o in outs:
        for k, v in o["s1"].items():
            s1[k] += v
    if s1["donors"]:
        print(
            "\n-- S1 illustration (NOT a proposal): offer capped at b - worst remembered shortfall * N / r"
        )
        for key, label in (("s1", "own retention r"), ("s1r1", "r = 1 (perfect storage)")):
            print(f"   {label:24s} offers reduced {s1[key + '_reduced'] / s1['donors']:.3f}, zeroed {s1[key + '_zero'] / s1['donors']:.3f}; "
                  f"delivered {s1[key + '_delivered'] / s1['d0_delivered']:.3f} of D0, unmet {s1[key + '_unmet'] / max(s1['d0_unmet'], 1e-300):.3f} of D0")  # fmt: skip
    # --- sensitivity
    print(
        "\n-- offer-fraction sensitivity (same recorded inputs, full re-matching; phi = 0.3 is D0)"
    )
    agg = {phi: defaultdict(float) for phi in PHIS}
    for o in outs:
        for phi, v in o["sens"].items():
            for k, x in v.items():
                agg[phi][k] += x
    base = agg[0.3]
    print(
        "   phi  | offered/def | shipped | delivered | loss share | unmet/def | short rec | intake | fert | energy-def | gain/loss rec | exhausted | donors used | top share | >50% one donor | eff25 | net full/none | donor carried | donor stores kept | prim changed"
    )
    for phi in PHIS:
        a = agg[phi]
        r_ = a["recipients"] or 1
        s_ = a["served"] or 1
        print(f"   {phi:4.2f} | {a['offered'] / a['deficit']:.3f} | {a['shipped'] / base['shipped']:.3f} | {a['delivered'] / base['delivered']:.3f} | "
              f"{(1 - a['delivered'] / a['shipped']) if a['shipped'] else 0:.3f} | {a['unmet'] / a['deficit']:.3f} | {a['still_short'] / r_:.3f} | "
              f"{a['intake'] / r_:.4f} | {a['fert'] / r_:.4f} | {a['energy_deficit_kcal'] / max(base['energy_deficit_kcal'], 1e-300):.3f} | "
              f"{a['gain'] / r_:.3f}/{a['loss'] / r_:.3f} | {_frac(a['exhausted'], a['n_offers'])} | {a['donors_used'] / max(base['donors_used'], 1):.3f} | "
              f"{a['top_share'] / s_:.3f} | {a['single_dep'] / s_:.3f} | {_frac(a['eff25'], a['decisions'])} | "
              f"{_frac(a['net_full'], a['net_n'])}/{_frac(a['net_none'], a['net_n'])} | {a['donor_carried'] / max(base['donor_carried'], 1e-300):.3f} | "
              f"{a['donor_retained_after'] / max(base['donor_retained_after'], 1e-300):.4f} | {_frac(a['prim_changed'], s_ * 1.0)}")  # fmt: skip
    print(
        f"   (D0 absolute: shipped {base['shipped']:.4g} kcal, delivered {base['delivered']:.4g}, unmet {base['unmet']:.4g}, recipient-years {base['recipients']:.0f})"
    )
    print(
        f"   recipient-years: {q([r['deficit'] / r['need'] for r in recs])} relative pre-trade deficit (p50/p90/p99/max)"
    )


def analyse(load: Path, jobs: int) -> None:
    runs = []
    for path in sorted(load.glob("*.pkl")):
        with path.open("rb") as f:
            runs.append(pickle.load(f))
    print(
        "observer-neutral (physical digest):",
        {f"{r['name']}/{r['seed']}": r["neutral"] for r in runs},
    )
    started = time.perf_counter()
    with Pool(jobs) as pool:
        outs = pool.map(analyse_run, runs)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r, o in zip(runs, outs, strict=True):
        by_name[r["name"]].append(o)
    for name in MVP2_2:
        if by_name[name]:
            report(name, by_name[name])
    print(f"\n(analysis {time.perf_counter() - started:.0f} s)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("record", "analyse"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    args = parser.parse_args()
    if args.command == "record":
        assert args.out is not None
        args.out.mkdir(parents=True, exist_ok=True)
        specs = [(n, s) for n in MVP2_2 for s in args.seeds
                 if not (args.out / f"{n}_{s}.pkl").exists()]  # fmt: skip
        with Pool(args.jobs) as pool:
            for run in pool.imap_unordered(record_job, specs):
                with (args.out / f"{run['name']}_{run['seed']}.pkl").open("wb") as f:
                    pickle.dump(run, f)
                print(
                    f"recorded {run['name']} seed {run['seed']}: {len(run['trade'])} trade years, neutral {run['neutral']}",
                    flush=True,
                )
    else:
        assert args.load is not None
        analyse(args.load, args.jobs)


if __name__ == "__main__":
    main()
