# The report tables keep one entry per line.
# ruff: noqa: E501
"""Food provisioning: donor choice, tie information, routing counterfactuals and food-ratio
accounting (MVP 3 Stage 5H). Observation only. COUNTERFACTUAL / NOT ACTIVE.

``record`` installs two read-only hooks on reference runs:

- ``TradeSubsystem.evaluate``: the matching's inputs (deficits in production order, offers,
  reachable offering donors with path costs), the *pre-trade* (lagged) trade ties of every
  recipient, each unit's need / harvest / stores / reserves, and the authoritative transfers;
- ``EnergeticsSubsystem.evaluate``: the authoritative ``food_ratio`` and deficit with their
  inputs (harvest after trade, stores, reserves, need).

``analyse`` replays the matching with the pure helpers in
``economy/provisioning_counterfactual.py`` (H0 must reproduce every transfer exactly), then
measures donor choice, tie information, same-year static rerouting (H1 / H2), reciprocity,
and how often harvest-based ``food_ratio`` departs from the energy actually available.
Nothing is re-simulated per setting and nothing feeds back.

``controlled`` prints the deterministic nutritional-accounting cases.

Usage:
    uv run python scripts/probes/provisioning_counterfactual.py record [--jobs 2] [--seeds 0 1 2 3] [--replace] --out DIR
    uv run python scripts/probes/provisioning_counterfactual.py analyse --load DIR [--jobs 2] [--seeds ...] [--legacy-unverified]
    uv run python scripts/probes/provisioning_counterfactual.py controlled
"""

import argparse
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import REFERENCE, SEEDS, q, scenario_for
from _integrity import (
    RecordingError,
    hook,
    identity,
    load_data,
    provenance,
    run_observed,
    select_runs,
    to_record,
    write_recording,
)

from madexplorer.core.simulation import Simulator
from madexplorer.economy.provisioning_counterfactual import (
    Match,
    choice_levels,
    local_replacement,
    match,
    without,
)
from madexplorer.economy.trade import TradeSubsystem
from madexplorer.population.demography import fertility_multiplier
from madexplorer.population.energetics import (
    EnergeticsSubsystem,
    annual_need_columns,
    capability_column,
    energy_balance,
)

SCENARIOS = ("neolithic", "pressure+cult")  # the MVP 2.1 reference runs (_common.REFERENCE)
WEIGHT = 0.0  # strata.field_output_claim_weight of the recordings (passive strata)
PROBE = "provisioning_counterfactual"
SCHEMA = 1  # 6B-P2 provenance container (earlier recordings: legacy, no provenance)
TIE = 1e-6  # a tie counts as present above this: floating-point "dust" transfers leave ~1e-10 ties
WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
USEFUL = (0.01, 0.05, 0.1, 0.25, 0.5)
MID, SCALE = 0.8, 0.1  # human.yaml fertility_food_midpoint / scale


def fert(ratio: float) -> float:
    return float(fertility_multiplier(np.array([ratio]), MID, SCALE)[0])


# ---------------------------------------------------------------- recording


class Recorder:
    def __init__(self) -> None:
        self.trade: list[dict[str, Any]] = []
        self.energy: dict[int, dict[str, tuple[float, ...]]] = {}

    def install(self, sim: Simulator) -> None:
        """Read-only hooks on ``sim``'s own subsystem instances (``_integrity.hook``)."""
        rec = self

        def trade(sub: Any, state: Any, ctx: Any) -> Any:
            ties = {
                u.id: dict(u.trade_ties) for u in state.units.values()
            }  # before this year's apply
            proposals = TradeSubsystem.evaluate(sub, state, ctx)
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
            rng_km = float(
                ctx.species(cols.units[0].species_id).movement.annual_relocation_range_km
            )
            cells = cols.get("cell").tolist()
            info, offers, offering, deficits = {}, {}, defaultdict(list), []
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
            rec.trade.append({
                "year": state.year, "info": info, "offers": offers, "deficits": deficits,
                "donors_of": donors_of, "decay": config.transport_decay_km, "range": rng_km,
                "ties": {rid: {d: ties[rid].get(d, 0.0) for _, d in donors_of[rid] if d in ties[rid]}
                         for rid in donors_of},
                "actual": [(t.donor_id, t.recipient_id, t.sent_kcal, t.received_kcal)
                           for t in proposals[0].transfers],
            })  # fmt: skip
            return proposals

        def energy(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = EnergeticsSubsystem.evaluate(sub, state, ctx)
            if proposals:
                u = proposals[0]
                cols = u.cols
                people = cols.population().astype(float)
                reserve = cols.get("reserve_kcal_per_capita") * people
                species = cols.species()
                p = ctx.compiled.parameter
                cap = (
                    people
                    * p("metabolism.reserve_days_max")[species]
                    * p("metabolism.adult_daily_kcal")[species]
                )
                h, st = cols.get("harvest_kcal"), cols.get("stores_kcal")
                rec.energy[state.year] = {
                    unit.id: (float(u.need_kcal[k]), float(h[k]), float(st[k]), float(reserve[k]), float(cap[k]),
                              float(u.food_ratio[k]), float(u.deficit[k]), int(people[k]))
                    for k, unit in enumerate(cols.units)
                }  # fmt: skip
            return proposals

        assert hook(sim, TradeSubsystem, trade)
        assert hook(sim, EnergeticsSubsystem, energy)


def ident_of(name: str, seed: int) -> dict[str, Any]:
    """What a recording of ``(name, seed)`` made now would declare (``_integrity``)."""
    path, _, settings = REFERENCE[name]
    settings = {**settings, "strata.field_output_claim_weight": WEIGHT}
    return identity(PROBE, SCHEMA, name, scenario_for(name, seed, WEIGHT), path, settings, __file__)


def record_job(spec: tuple[str, int]) -> dict[str, Any]:
    """One instrumented run, its uninstrumented twin compared in lockstep; the data plus
    its ``provenance`` (split off when written)."""
    name, seed = spec
    scenario = scenario_for(name, seed, WEIGHT)
    rec = Recorder()
    sim, years, neutrality = run_observed(scenario, rec.install)
    events = [(e.year, e.kind, dict(e.data)) for e in sim.events
              if e.kind in ("population_split", "population_merge", "unit_extinct")]  # fmt: skip
    return {"name": name, "seed": seed, "trade": rec.trade, "energy": rec.energy, "events": events,
            "neutral": neutrality["neutral"],
            "provenance": provenance(ident_of(name, seed), scenario, years, neutrality)}  # fmt: skip


# ---------------------------------------------------------------- analysis helpers


def _replay(
    y: dict[str, Any],
    weight: float = 0.0,
    offers: dict[str, float] | None = None,
    record: bool = False,
) -> Match:
    return match(y["deficits"], y["offers"] if offers is None else offers, y["donors_of"], y["decay"],
                 y["ties"], weight, y["range"], record)  # fmt: skip


def _balance(
    i: tuple[Any, ...], harvest: float, stores: float | None = None
) -> tuple[float, float]:
    need, _h, st, reserve, cap, can_store = i[:6]
    b = energy_balance(need, harvest, reserve, cap, st if stores is None else stores, can_store)
    return b.food_ratio, b.deficit


def _after(y: dict[str, Any], m: Match) -> dict[str, tuple[float, float, float, float]]:
    """Static post-trade (harvest, stores) and production energy outcome per affected unit."""
    harvest = {u: i[1] for u, i in y["info"].items()}
    stores = {u: i[2] for u, i in y["info"].items()}
    for d, r, s, got in m.transfers:  # TradeRound.apply: donors pay from harvest, then stores
        take = min(s, harvest[d])
        harvest[d] -= take
        stores[d] = max(stores[d] - (s - take), 0.0)
        harvest[r] += got
    touched = (
        {t[0] for t in m.transfers}
        | {t[1] for t in m.transfers}
        | {r for _, r, _, _ in y["deficits"]}
    )
    out = {}
    for u in touched:
        fr, de = _balance(y["info"][u], harvest[u], stores[u])
        out[u] = (harvest[u], stores[u], fr, de)
    return out


def _hhi(values: list[float]) -> float:
    total = sum(values)
    return sum((v / total) ** 2 for v in values) if total > 0 else 0.0


# ---------------------------------------------------------------- analysis (one run)


def analyse_run(run: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = defaultdict(list)
    out["exact_years"] = out["years"] = 0
    pair_dir: Counter[tuple[str, str]] = Counter()
    prev_pairs: set[tuple[str, str]] = set()
    prev_opps: set[tuple[str, str]] = set()
    ever: set[tuple[str, str]] = set()  # ordered (donor, recipient) pairs with a past transfer
    routing = {w: defaultdict(float) for w in WEIGHTS}
    for y in run["trade"]:
        out["years"] += 1
        h0 = _replay(y, record=True)
        exact = h0.transfers == y["actual"]
        out["exact_years"] += exact
        if not exact:
            continue
        info = y["info"]
        received = h0.received()
        primary = {}
        by_rec: dict[str, dict[str, float]] = defaultdict(dict)
        for d, r, _s, got in h0.transfers:
            by_rec[r][d] = by_rec[r].get(d, 0.0) + got
        for r, by in by_rec.items():
            primary[r] = max(by, key=lambda k: (by[k], k))
        # --- donor choice at each recipient decision (sequential state)
        reach_count: Counter[str] = Counter()
        for _, rid, _, _ in y["deficits"]:
            for _c, did in y["donors_of"][rid]:
                reach_count[did] += 1
        for dec in h0.decisions:
            if dec.recipient not in received:
                out["unserved_with_candidates"].append(len(dec.candidates))
                continue
            got = received[dec.recipient]
            pop = info[dec.recipient][7]
            levels = {u: choice_levels(dec, u) for u in USEFUL}
            prim = primary[dec.recipient]
            taken = by_rec[dec.recipient][prim]
            local = local_replacement(dec, prim, taken)
            costs = [c.cost for c in dec.candidates]
            offers = [c.offer for c in dec.candidates]
            out["choice"].append({
                "n": len(dec.candidates), "pop": pop, "kcal": got, "need": dec.need, "deficit": dec.deficit,
                "levels": levels, "local": local, "prim": prim, "taken": taken, "rid": dec.recipient,
                "cost_spread": (max(costs) - min(costs)) if costs else 0.0,
                "offer_cv": float(np.std(offers) / np.mean(offers)) if len(offers) > 1 else 0.0,
                "competitors": float(np.mean([reach_count[c.donor] for c in dec.candidates])) if dec.candidates else 0.0,
                "start_reach": len(y["donors_of"][dec.recipient]),
            })  # fmt: skip
        # network rematching without each recipient's primary donor
        for r, prim in primary.items():
            alt = _replay(y, offers=without(y["offers"], prim))
            got_alt = alt.received().get(r, 0.0)
            fr0, de0 = _balance(info[r], info[r][1] + received[r])
            fr1, de1 = _balance(info[r], info[r][1] + got_alt)
            out["network"].append({"kept": got_alt / received[r], "replaced": min(max((got_alt - (received[r] - by_rec[r][prim])) / by_rec[r][prim], 0.0), 1.0),
                                   "d_deficit": de1 - de0, "d_fert": fert(fr0) - fert(fr1), "pop": info[r][7], "kcal": received[r]})  # fmt: skip
        # --- tie information: opportunities (recipient, donor in range with an offer at year start)
        pairs_now = {(d, r) for d, r, _, _ in h0.transfers}
        for _, rid, deficit, _ in y["deficits"]:
            cand = y["donors_of"][rid]
            ties = y["ties"].get(rid, {})
            nearer = 0.0  # what nearer offering donors could deliver at year start, / deficit
            for rank, (cost, did) in enumerate(cand):
                tie = ties.get(did, 0.0)
                adequacy = y["offers"][did] * np.exp(-cost / y["decay"]) / deficit
                out["opps"].append((rank, cost, adequacy, tie, (did, rid) in pairs_now,
                                    (did, rid) in prev_pairs, (did, rid) in prev_opps, nearer,
                                    (rid, did) in ever, (did, rid) in ever))  # fmt: skip
                nearer += adequacy
        # decision-state predictor: the nearest candidates until the deficit is covered
        for dec in h0.decisions:
            left, chosen = dec.deficit, set()
            for c in dec.candidates:
                if left <= 0:
                    break
                chosen.add(c.donor)
                left -= (
                    min(c.offer, left / (c.deliverable / c.offer)) * (c.deliverable / c.offer)
                    if c.offer > 0
                    else 0.0
                )
            out["prefix_mismatch"].append(chosen != set(by_rec.get(dec.recipient, {})))
        # decisions with both a tied and an untied feasible candidate: which comes first?
        for dec in h0.decisions:
            tied = [k for k, c in enumerate(dec.candidates) if c.tie > TIE]
            untied = [k for k, c in enumerate(dec.candidates) if c.tie <= TIE]
            if tied and untied:
                out["tied_first"].append(min(tied) < min(untied))
                out["tied_share"].append(len(tied) / len(dec.candidates))
        opps_now = {(did, rid) for _, rid, _, _ in y["deficits"] for _c, did in y["donors_of"][rid]}
        prev_pairs, prev_opps = pairs_now, opps_now
        ever |= pairs_now
        # --- reciprocity
        for d, r, _s, got in h0.transfers:
            pair_dir[(d, r)] += 1
            out["flow"].append((y["year"], d, r, got))
        # --- routing counterfactuals (same year, same inputs)
        base_after = _after(y, h0)
        base_sent, base_rec = h0.sent(), received
        for w in WEIGHTS:
            m = h0 if w == 0.0 else _replay(y, weight=w)
            agg = routing[w]
            s, dl = m.totals()
            agg["shipped"] += s
            agg["delivered"] += dl
            agg["years_changed"] += float({(a, b) for a, b, _, _ in m.transfers} != pairs_now)
            agg["year_count"] += 1
            rec_m, sent_m = m.received(), m.sent()
            after = base_after if w == 0.0 else _after(y, m)
            prim_m = {}
            byr: dict[str, dict[str, float]] = defaultdict(dict)
            for d, r, _s, got in m.transfers:
                byr[r][d] = byr[r].get(d, 0.0) + got
            for r, by in byr.items():
                prim_m[r] = max(by, key=lambda k: (by[k], k))
            for _, rid, deficit, need in y["deficits"]:
                agg["recipients"] += 1
                agg["unmet"] += max(deficit - rec_m.get(rid, 0.0), 0.0)
                agg["deficit_post"] += after[rid][3] * need
                agg["fert_rec"] += fert(after[rid][2])
                agg["prim_changed"] += float(primary.get(rid) != prim_m.get(rid))
                d_rec = rec_m.get(rid, 0.0) - base_rec.get(rid, 0.0)
                agg["rec_gain"] += float(d_rec > 0.01 * need)
                agg["rec_loss"] += float(d_rec < -0.01 * need)
                agg["rec_deficit_gt0"] += float(after[rid][3] > 0)
            for d in set(base_sent) | set(sent_m):
                dn = info[d][0]
                agg["donor_burden_change"] += abs(sent_m.get(d, 0.0) - base_sent.get(d, 0.0))
                agg["donor_more"] += float(sent_m.get(d, 0.0) - base_sent.get(d, 0.0) > 0.01 * dn)
                agg["donor_less"] += float(sent_m.get(d, 0.0) - base_sent.get(d, 0.0) < -0.01 * dn)
                fr = after[d][2] if d in after else info[d][1] / dn
                agg["donor_fert_loss"] += fert(info[d][1] / dn) - fert(fr)
                agg["donor_deficit"] += float(after.get(d, (0, 0, 0, 0.0))[3] > 0)
            agg["donors_used"] += len(sent_m)
            agg["pairs"] += len({(a, b) for a, b, _, _ in m.transfers})
            agg["hhi_donor"] += _hhi(list(sent_m.values())) if sent_m else 0.0
            agg["donors_per_rec"] += float(np.mean([len(v) for v in byr.values()])) if byr else 0.0
    out["routing"] = {w: dict(v) for w, v in routing.items()}
    out["pair_dir"] = dict(pair_dir)
    # --- food-ratio accounting (authoritative energetics)
    roles: dict[int, dict[str, str]] = {}
    for y in run["trade"]:
        r = {}
        for d, rr, _s, _g in y["actual"]:
            r[d] = "donor" if r.get(d) in (None, "donor") else "both"
            r[rr] = "recipient" if r.get(rr) in (None, "recipient") else "both"
        roles[y["year"]] = r
    for year, units in run["energy"].items():
        role = roles.get(year, {})
        for u, (need, h, st, reserve, cap, fr, de, pop) in units.items():
            if need <= 0:
                continue
            from_stores = min(max(need - h, 0.0), st)
            avail = (h + from_stores) / need if h < need else h / need
            suff = 1.0 - de
            b = energy_balance(need, h, reserve, cap, st, False)
            out["energy_check"].append(abs(b.food_ratio - fr) + abs(b.deficit - de))
            out["energy_rows"].append(
                (role.get(u, "none"), fr, avail, suff, from_stores / need, pop)
            )
    return dict(out)


# ---------------------------------------------------------------- report


def report(name: str, outs: list[dict[str, Any]]) -> None:
    years = sum(o["years"] for o in outs)
    exact = sum(o["exact_years"] for o in outs)
    print(f"\n=== {name}")
    print(f"-- H0 replay: {exact}/{years} trade years reproduce every transfer bit for bit")
    ch = [c for o in outs for c in o["choice"]]
    if not ch:
        return
    pop = np.array([c["pop"] for c in ch], dtype=float)
    kcal = np.array([c["kcal"] for c in ch])
    n = np.array([c["n"] for c in ch])
    print("\n-- donor choice at the recipient's decision (candidates still holding offer)")
    print(
        f"   served recipient-years {len(ch)}; candidates p50/p90/p99 {q(n)}; at year start {q([c['start_reach'] for c in ch])}"
    )
    print(
        f"   recipients unserved although in deficit: {sum(len(o['unserved_with_candidates']) for o in outs)} (with >= 1 candidate: {sum(x > 0 for o in outs for x in o['unserved_with_candidates'])})"
    )
    print("   level                         unit-yr  pop-wtd  kcal-wtd")
    nominal = np.array([c["levels"][USEFUL[0]]["nominal"] for c in ch])
    print(
        f"   nominal (>= 2 candidates)      {nominal.mean():.3f}    {np.average(nominal, weights=pop):.3f}    {np.average(nominal, weights=kcal):.3f}"
    )
    for u in USEFUL:
        eff = np.array([c["levels"][u]["effective"] for c in ch])
        print(
            f"   effective (>= 2 deliver >= {u:<4} of deficit) {eff.mean():.3f}    {np.average(eff, weights=pop):.3f}    {np.average(eff, weights=kcal):.3f}"
        )
    full = np.array([c["levels"][USEFUL[0]]["full"] for c in ch])
    print(
        f"   full (>= 2 could each cover the whole deficit) {full.mean():.3f}    {np.average(full, weights=pop):.3f}    {np.average(full, weights=kcal):.3f}"
    )
    local = np.array([c["local"] for c in ch])
    print(
        f"   local replacement of the primary donor (others' remaining deliverable / its delivery): full {float((local >= 0.99).mean()):.3f}, partial {float(((local > 0.01) & (local < 0.99)).mean()):.3f}, none {float((local <= 0.01).mean()):.3f}"
    )
    net = [x for o in outs for x in o["network"]]
    rep = np.array([x["replaced"] for x in net])
    print(
        f"   network rematch without the primary donor: replaced full {float((rep >= 0.99).mean()):.3f}, partial {float(((rep > 0.01) & (rep < 0.99)).mean()):.3f}, none {float((rep <= 0.01).mean()):.3f}; recipient total kept p10/p50 {q([x['kept'] for x in net], (0.1, 0.5))}"
    )
    print(
        f"     static consequence for that recipient: deficit increase p50/p90/p99 {q([x['d_deficit'] for x in net])}; fertility multiplier loss {q([x['d_fert'] for x in net])}"
    )
    print(
        f"   candidate cost spread (km) p50/p90 {q([c['cost_spread'] for c in ch], (0.5, 0.9))}; offer CV p50/p90 {q([c['offer_cv'] for c in ch], (0.5, 0.9))}; recipients reaching the same donor (mean over candidates) p50/p90 {q([c['competitors'] for c in ch], (0.5, 0.9))}"
    )
    # ties
    print(
        "\n-- tie information (lagged pre-trade ties; opportunity = offering donor in range of a deficit unit at year start)"
    )
    opps = [x for o in outs for x in o["opps"]]
    rank = np.array([x[0] for x in opps])
    tie = np.array([x[3] for x in opps])
    took = np.array([x[4] for x in opps])
    prevp = np.array([x[5] for x in opps])
    prevo = np.array([x[6] for x in opps])
    print(
        f"   opportunities {len(opps)}; with a prior tie {float((tie > TIE).mean()):.3f}; transfer rate tie > 1e-6 {took[tie > TIE].mean():.3f} vs none {took[tie <= TIE].mean():.3f}"
    )
    print(
        "   within cost rank (rank 0 = nearest offering donor at year start):   rate tie>0 / tie=0 (n tie>0)"
    )
    diffs, wts = [], []
    for r in range(6):
        sel = rank == r if r < 5 else rank >= 5
        a, b = took[sel & (tie > TIE)], took[sel & (tie <= TIE)]
        if a.size and b.size:
            diffs.append(a.mean() - b.mean())
            wts.append(min(a.size, b.size))
            print(f"     rank {r if r < 5 else '5+'}: {a.mean():.3f} / {b.mean():.3f} ({a.size})")
    print(f"   rank-stratified mean difference (weighted) {np.average(diffs, weights=wts):+.3f}")
    cover = np.array([x[7] for x in opps])
    sev = np.array([x[2] for x in opps])
    diffs, wts = [], []
    print(
        "   within rank x nearer-cover (year-start deliverable of nearer donors / deficit) x own adequacy:"
    )
    for r_lo, r_hi in ((0, 1), (1, 3), (3, 99)):
        for c_lo, c_hi in ((0, 0.5), (0.5, 1.0), (1.0, 1e9)):
            for a_lo, a_hi in ((0, 0.25), (0.25, 1.0), (1.0, 1e9)):
                sel = (
                    (rank >= r_lo)
                    & (rank < r_hi)
                    & (cover >= c_lo)
                    & (cover < c_hi)
                    & (sev >= a_lo)
                    & (sev < a_hi)
                )
                a, b = took[sel & (tie > TIE)], took[sel & (tie <= TIE)]
                if a.size >= 20 and b.size >= 20:
                    diffs.append(a.mean() - b.mean())
                    wts.append(min(a.size, b.size))
    print(
        f"     stratified mean difference tie>0 - tie=0 over {len(diffs)} strata (n >= 20 each): {np.average(diffs, weights=wts):+.3f}; strata range {min(diffs):+.3f} .. {max(diffs):+.3f}"
    )
    mism = [x for o in outs for x in o["prefix_mismatch"]]
    print(
        f"   decision state: 'nearest candidates still holding offer until the deficit is covered' predicts the donor set exactly in {1 - np.mean(mism):.4f} of {len(mism)} decisions; given it, ties carry no allocation information"
    )
    print(
        f"   among last year's opportunities: P(transfer | transferred last year) {took[prevo & prevp].mean():.3f} vs P(transfer | opportunity but no transfer last year) {took[prevo & ~prevp].mean():.3f}"
    )
    for r in (0, 1, 2):
        sel = rank == r
        a, b = took[sel & prevo & prevp], took[sel & prevo & ~prevp]
        if a.size and b.size:
            print(
                f"     same comparison at rank {r}: {a.mean():.3f} vs {b.mean():.3f} (n {a.size} / {b.size})"
            )
    tf = [x for o in outs for x in o["tied_first"]]
    ts = [x for o in outs for x in o["tied_share"]]
    print(
        f"   decisions with tied and untied candidates {len(tf)}: tied donor nearest {np.mean(tf):.3f} vs tied share of candidates {np.mean(ts):.3f} (H0 order ignores ties: any excess is proximity)"
    )
    # reciprocity
    print("\n-- direction")
    pd: Counter[tuple[str, str]] = Counter()
    for o in outs:
        for (d, r), k in o["pair_dir"].items():
            pd[(o["seed_tag"], d, r)] += k
    pairs = {(t, *sorted((d, r))) for t, d, r in pd}
    both = sum(1 for t, a, b in pairs if pd.get((t, a, b)) and pd.get((t, b, a)))
    uni3 = sum(
        1
        for t, a, b in pairs
        if (pd.get((t, a, b), 0) >= 3) != (pd.get((t, b, a), 0) >= 3)
        and min(pd.get((t, a, b), 0), pd.get((t, b, a), 0)) == 0
    )
    print(
        f"   unordered pairs {len(pairs)}; flows in both directions over the run {both / len(pairs):.3f}; one direction only with >= 3 transfers {uni3 / len(pairs):.3f}"
    )
    # direction memory: given an opportunity for donor j -> recipient i at a cost rank, does a
    # past i -> j transfer (or a past j -> i transfer) change the rate?
    rev = np.array([x[8] for x in opps])
    same = np.array([x[9] for x in opps])
    for r in (0, 1, 2):
        sel = rank == r
        a, b = took[sel & rev & ~same], took[sel & ~rev & ~same]
        if a.size and b.size:
            print(
                f"   rank {r}, no past flow j->i: P(transfer | past reverse flow i->j) {a.mean():.3f} vs no past flow either way {b.mean():.3f} (n {a.size} / {b.size})"
            )
    # routing
    print(
        "\n-- same-year static rerouting (COUNTERFACTUAL / NOT ACTIVE); totals over all trade years"
    )
    base = {k: sum(o["routing"][0.0].get(k, 0.0) for o in outs) for k in outs[0]["routing"][0.0]}
    print(
        "   weight  years changed  primary changed  shipped    delivered  loss share  unmet deficit  recip. deficit>0  recip. fert mean  donors used  pairs   donor HHI  donors/recip  recip +/-      donors +/-     donor fert loss"
    )
    for w in WEIGHTS:
        a = {k: sum(o["routing"][w].get(k, 0.0) for o in outs) for k in base}
        print(f"   {w:<6}  {a['years_changed'] / a['year_count']:.3f}          {a['prim_changed'] / a['recipients']:.3f}            "
              f"{a['shipped'] / base['shipped']:.4f}     {a['delivered'] / base['delivered']:.4f}     {1 - a['delivered'] / a['shipped']:.4f}      "
              f"{a['unmet'] / base['unmet'] if base['unmet'] else 0:.4f}         {a['rec_deficit_gt0'] / a['recipients']:.4f}           {a['fert_rec'] / a['recipients']:.4f}            "
              f"{a['donors_used'] / base['donors_used']:.3f}        {a['pairs'] / base['pairs']:.3f}   {a['hhi_donor'] / a['year_count']:.4f}     {a['donors_per_rec'] / a['year_count']:.3f}         "
              f"{a['rec_gain'] / a['recipients']:.3f}/{a['rec_loss'] / a['recipients']:.3f}    {a['donor_more'] / max(a['donors_used'], 1):.3f}/{a['donor_less'] / max(a['donors_used'], 1):.3f}    {a['donor_fert_loss'] / max(a['donors_used'], 1):.5f}")  # fmt: skip
    # food ratio
    print("\n-- food_ratio accounting (authoritative energetics; diagnostics only)")
    check = max(x for o in outs for x in o["energy_check"])
    print(
        f"   energy_balance recomputation vs authoritative food_ratio + deficit: max |diff| {check:.1e}"
    )
    rows = [x for o in outs for x in o["energy_rows"]]
    print(
        "   role        unit-yrs  harvest fr<1  ...with zero deficit  ...with avail>=1  fert(fr) < fert(avail) by >0.01  mean loss  pop share"
    )
    totpop = sum(x[5] for x in rows)
    for role in ("donor", "recipient", "both", "none", "all"):
        sel = [x for x in rows if role == "all" or x[0] == role]
        if not sel:
            continue
        fr = np.array([x[1] for x in sel])
        av = np.array([x[2] for x in sel])
        su = np.array([x[3] for x in sel])
        loss = np.array([fert(a) - fert(b) for b, a in zip(fr, np.minimum(av, 1.0), strict=True)])
        low = fr < 1
        print(
            f"   {role:<10}  {len(sel):<9} {low.mean():.4f}        {(low & (su >= 1)).mean():.4f}                {(low & (av >= 1)).mean():.4f}            {(loss > 0.01).mean():.4f}                       {loss.mean():.5f}   {sum(x[5] for x in sel) / totpop:.3f}"
        )
    sel = [x for x in rows if x[1] < 1 and x[3] >= 1]
    if sel:
        loss = np.array([fert(min(x[2], 1.0)) - fert(x[1]) for x in sel])
        print(
            f"   when fr < 1 but no deficit: fertility multiplier fert(avail) - fert(fr) p50/p90/p99 {q(loss)}; store withdrawal / need p50/p90 {q([x[4] for x in sel], (0.5, 0.9))}"
        )


def analyse_main(load: Path, jobs: int, seeds: list[int], explicit: bool, legacy: bool) -> None:
    try:
        paths = select_runs(load, SCENARIOS, seeds, explicit, ident_of, legacy)
    except RecordingError as error:
        raise SystemExit(str(error)) from None
    runs = [load_data(path, legacy) for path in paths]
    started = time.perf_counter()
    with Pool(jobs) as workers:
        outs = list(workers.imap(analyse_run, runs, chunksize=1))
    for o, r in zip(outs, runs, strict=True):
        o["seed_tag"] = f"{r['name']}#{r['seed']}"
        o["name"] = r["name"]
    print(
        f"analysed {len(runs)} runs in {time.perf_counter() - started:.0f} s; all observer-neutral {all(r['neutral'] for r in runs)}"
    )
    for name in SCENARIOS:
        report(name, [o for o in outs if o["name"] == name])
    with Pool(jobs) as workers:
        shadows = list(workers.imap(shadow_job, runs, chunksize=1))
    for name in SCENARIOS:
        report_shadow(name, [o for o in shadows if o["name"] == name])


# ---------------------------------------------------------------- shadow tie history


PHYSICAL = "PHYSICAL-HISTORY-CONDITIONED SHADOW REPLAY"


def shadow(
    run: dict[str, Any],
    weight: float,
    persistence: float = 0.7,
    switch: int | None = None,
    reset: bool = False,
) -> dict[str, Any]:
    """Shadow ties evolved from shadow transfers with the production update (decay by
    ``persistence``, prune below 1e-3 or dead partners, ``+received/need`` on both sides,
    fusion rewiring, untied daughters) over the authoritative physical history. With
    ``switch``, H0 runs until that year, then ``weight`` applies (ties kept, or emptied when
    ``reset``)."""
    ties: dict[str, dict[str, float]] = defaultdict(dict)
    events: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for year, kind, data in run["events"]:
        events[year].append((kind, data))
    tie_err = 0.0
    flows: list[tuple[int, str, str, float]] = []
    totals = defaultdict(float)
    for y in run["trade"]:
        w = weight if switch is None or y["year"] >= switch else 0.0
        if switch is not None and reset and y["year"] == switch:
            ties = defaultdict(dict)
        present = set(y["info"])
        lag = {
            rid: {d: ties[rid][d] for _, d in y["donors_of"][rid] if d in ties.get(rid, {})}
            for rid in y["donors_of"]
        }
        if weight == 0.0 and persistence == 0.7:
            for rid, rec in y["ties"].items():
                for d in set(rec) | set(lag.get(rid, {})):
                    tie_err = max(tie_err, abs(rec.get(d, -1.0) - lag.get(rid, {}).get(d, -1.0)))
        m = match(y["deficits"], y["offers"], y["donors_of"], y["decay"], lag, w, y["range"])
        ties = defaultdict(dict, {u: {p: v * persistence for p, v in t.items() if p in present and v * persistence > 1e-3}
                                  for u, t in ties.items() if u in present})  # fmt: skip
        need = {rid: n for _, rid, _, n in y["deficits"]}
        for d, r, _sent, got in m.transfers:
            strength = got / need[r] if need[r] > 0 else 0.0
            ties[d][r] = ties[d].get(r, 0.0) + strength
            ties[r][d] = ties[r].get(d, 0.0) + strength
            flows.append((y["year"], d, r, got))
        sh, dl = m.totals()
        totals["shipped"] += sh
        totals["delivered"] += dl
        rec = m.received()
        for _, rid, deficit, _n in y["deficits"]:
            totals["unmet"] += max(deficit - rec.get(rid, 0.0), 0.0)
            totals["recipients"] += 1
            totals["def_gt0"] += float(
                _balance(y["info"][rid], y["info"][rid][1] + rec.get(rid, 0.0))[1] > 0
            )
        for kind, data in events.get(y["year"], ()):
            if kind == "population_split":
                ties[data["daughter_id"]] = {}
            elif kind == "population_merge":
                src, tgt = data["unit_id"], data["into_id"]
                source = ties.pop(src, {})
                for partner, t in source.items():
                    if partner != tgt:
                        ties[tgt][partner] = ties[tgt].get(partner, 0.0) + t
                ties[tgt].pop(src, None)
                for partner in source:
                    if partner != tgt and src in ties.get(partner, {}):
                        t = ties[partner].pop(src)
                        ties[partner][tgt] = ties[partner].get(tgt, 0.0) + t
    return {"flows": flows, "totals": dict(totals), "tie_err": tie_err}


def flow_structure(flows: list[tuple[int, str, str, float]], start: int = 0) -> dict[str, float]:
    """Pair duration (consecutive-year runs), primary-donor recurrence and pair concentration."""
    by_year: dict[int, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
    volume: Counter[tuple[str, str]] = Counter()
    for year, d, r, got in flows:
        if year < start:
            continue
        by_year[year][r][d] = by_year[year][r].get(d, 0.0) + got
        volume[(d, r)] += got
    runs, current = [], {}
    recur = []
    prev_primary: dict[str, str] = {}
    for year in sorted(by_year):
        pairs = {(d, r) for r, ds in by_year[year].items() for d in ds}
        for pair in list(current):
            if pair not in pairs:
                runs.append(current.pop(pair))
        for pair in pairs:
            current[pair] = current.get(pair, 0) + 1
        primary = {r: max(ds, key=lambda k: (ds[k], k)) for r, ds in by_year[year].items()}
        recur += [prev_primary[r] == p for r, p in primary.items() if r in prev_primary]
        prev_primary = primary
    runs += list(current.values())
    per_rec: dict[str, list[float]] = defaultdict(list)
    for (_d, r), v in volume.items():
        per_rec[r].append(v)
    return {
        "pairs": len(volume), "dur_p50": float(np.median(runs)) if runs else 0.0,
        "dur_p90": float(np.quantile(runs, 0.9)) if runs else 0.0, "dur_ge5": float(np.mean([x >= 5 for x in runs])) if runs else 0.0,
        "recur": float(np.mean(recur)) if recur else 0.0,
        "rec_hhi": float(np.mean([_hhi(v) for v in per_rec.values()])) if per_rec else 0.0,
    }  # fmt: skip


SHADOWS = (
    ("H0 (= authoritative)", 0.0, 0.7, None, False),
    ("H2 weight 0.5", 0.5, 0.7, None, False),
    ("H1 tie priority", 1.0, 0.7, None, False),
    ("H1, persistence 0.5", 1.0, 0.5, None, False),
    ("H1, persistence 0.9", 1.0, 0.9, None, False),
    ("H0 -> H1 at midpoint, ties kept", 1.0, 0.7, "mid", False),
    ("H0 -> H1 at midpoint, ties emptied", 1.0, 0.7, "mid", True),
)


def shadow_job(run: dict[str, Any]) -> dict[str, Any]:
    mid = run["trade"][len(run["trade"]) // 2]["year"] + 5
    out = {}
    for label, w, pers, switch, reset in SHADOWS:
        sw = run["trade"][len(run["trade"]) // 2]["year"] if switch == "mid" else None
        res = shadow(run, w, pers, sw, reset)
        out[label] = {**res["totals"], **flow_structure(res["flows"], mid if switch == "mid" else 0),
                      "tie_err": res["tie_err"]}  # fmt: skip
        if switch == "mid":
            base = shadow(run, 0.0, 0.7)
            out.setdefault("H0 second half", flow_structure(base["flows"], mid))
    return {"name": run["name"], "shadow": out}


def report_shadow(name: str, outs: list[dict[str, Any]]) -> None:
    print(
        f"\n-- {PHYSICAL} ({name}): ties evolve from shadow transfers; food, population, places and events stay authoritative"
    )
    print(
        "   setting                               shipped   delivered  unmet    recip def>0  pairs   pair dur p50/p90  >=5y   primary recurs  per-recipient HHI  max tie err"
    )
    labels = list(outs[0]["shadow"])
    base = outs[0]["shadow"]["H0 (= authoritative)"]
    for label in labels:
        rows = [o["shadow"][label] for o in outs]
        agg = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
        tb = {
            k: float(np.mean([o["shadow"]["H0 (= authoritative)"].get(k, 0.0) for o in outs]))
            for k in base
        }

        def tot(k: str, agg: dict[str, float] = agg, tb: dict[str, float] = tb) -> str:
            return f"{agg[k] / tb[k]:.4f}" if k in agg and tb.get(k) else "  -   "

        def0 = f"{agg['def_gt0'] / agg['recipients']:.4f}" if "def_gt0" in agg else "  -   "
        print(
            f"   {label:<37} {tot('shipped')}    {tot('delivered')}     {tot('unmet')}   {def0}       {agg['pairs']:<7.0f} {agg['dur_p50']:.1f} / {agg['dur_p90']:.1f}        {agg['dur_ge5']:.3f}  {agg['recur']:.3f}           {agg['rec_hhi']:.3f}              {agg.get('tie_err', 0.0):.1e}"
        )


# ---------------------------------------------------------------- controlled nutritional cases


def controlled() -> None:
    need, cap = 100.0, 30.0
    cases = [
        ("1. harvest alone covers need", 110.0, 0.0, 10.0),
        ("2. harvest short, stores cover", 70.0, 50.0, 10.0),
        ("3. harvest short, reserves cover", 85.0, 0.0, 20.0),
        ("4. donor ships 30 of 120, stores cover", 90.0, 40.0, 10.0),
        ("5. donor ships, genuine deficit", 70.0, 5.0, 5.0),
        ("6. recipient receives 30, no deficit", 100.0, 0.0, 5.0),
        ("7. recipient receives 30, still short", 70.0, 0.0, 5.0),
        ("8a. same intake: all harvest", 100.0, 0.0, 0.0),
        ("8b. same intake: 60 harvest + 40 stores", 60.0, 40.0, 0.0),
        ("9. trade moves 20 harvest -> stores cover", 80.0, 20.0, 0.0),
        ("10. abundant stores, low harvest", 30.0, 500.0, 0.0),
    ]
    print(
        "case                                         food_ratio  avail  deficit  fert(food_ratio)  fert(avail)  starvation hazard x (adult)"
    )
    for label, harvest, stores, reserve in cases:
        b = energy_balance(need, harvest, reserve, cap, stores, True)
        from_stores = min(max(need - harvest, 0.0), stores)
        avail = (harvest + from_stores) / need if harvest < need else harvest / need
        print(
            f"{label:<44} {b.food_ratio:<11.2f} {avail:<6.2f} {b.deficit:<8.2f} {fert(b.food_ratio):<17.3f} {fert(min(avail, 1.0)):<12.3f} {np.exp(3.0 * b.deficit):.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("record", "analyse", "controlled"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--seeds", type=int, nargs="*", help=f"explicit subset (default {list(SEEDS)})"
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="record: overwrite existing recordings that do not match",
    )
    parser.add_argument("--legacy-unverified", action="store_true",
                        help="analyse: accept pre-6B-P2 recordings without provenance (unverified)")  # fmt: skip
    args = parser.parse_args()
    seeds = list(SEEDS) if args.seeds is None else args.seeds
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "analyse":
        analyse_main(args.load, args.jobs, seeds, args.seeds is not None, args.legacy_unverified)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    specs = to_record(args.out, [(n, s) for n in SCENARIOS for s in seeds], ident_of, args.replace)
    started = time.perf_counter()
    with Pool(args.jobs) as workers:
        for h in workers.imap_unordered(record_job, specs, chunksize=1):
            print(
                f"done {h['name']} seed {h['seed']} after {time.perf_counter() - started:.0f} s; trade years {len(h['trade'])}; neutral {h['neutral']}",
                flush=True,
            )
            write_recording(args.out / f"{h['name']}_{h['seed']}.pkl", h.pop("provenance"), h)


if __name__ == "__main__":
    main()
