# The report tables keep one entry per line.
# ruff: noqa: E501
"""Counterfactual control over new cultivated capacity (MVP 3 Stage 4E): observation only.
NOT ACTIVE.

Evaluates ``madexplorer.population.field_control`` (H3: new fields are controlled by
``share + p * (field_claim - share)``, p = ``field_claim_continuity``) as a *shadow
socioeconomic trajectory*: the probe substitutes the H3 transition for the authoritative
``field_claims_after_change`` inside the passive strata accounting of a run. Strata feed no
physical mechanism, so fields, crops, food, population, labor, migration, RNG and the
frozen events are identical for every p (checked by digest); only the strata sidecar (claims,
compactions, coalescences) follows the counterfactual. p = 0 must reproduce the
authoritative strata sidecar bit for bit (checked against a plain run without the probe).

Modes:

``controlled``
    Deterministic synthetic trajectories on the pure functions: neutral control, unequal
    control under one expansion, repeated expansion, expansion then shrinkage, zero reset and
    regrowth, the analytical persistence law.
``runs``
    Frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure + cultivation 400 y;
    seeds 0-3), p in {0, 0.25, 0.5, 0.75, 1}, ``strata.max_strata`` 16 and 32, w =
    ``strata.field_output_claim_weight`` 0 (primary) or 1 (``--stress``).

Usage:
    uv run python scripts/probes/field_control_counterfactual.py controlled
    uv run python scripts/probes/field_control_counterfactual.py runs [--jobs 2] [--stress] [--out f.pkl]
    uv run python scripts/probes/field_control_counterfactual.py report --load f.pkl
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

from store_access_counterfactual import strata_digest
from strata_capacity import physical_digest
from strata_review import SEEDS, scenario_for

import madexplorer.core.simulation as simulation
from madexplorer.core.simulation import Simulator
from madexplorer.population import strata_accounting
from madexplorer.population.field_control import (
    control_deviation,
    counterfactual_field_claim_after_expansion,
    field_claim_step,
    retention_factor,
)
from madexplorer.population.unit import belief_slot

CONTINUITIES = (0.0, 0.25, 0.5, 0.75, 1.0)
CAPACITIES = (16, 32)
SCENARIOS = ("neolithic", "pressure+cult")
NEUTRAL = 1e-9  # field-control deviation above this: non-neutral
EPISODE_MIN = 0.01  # a fusion-created episode starts at deviation >= this
AGES = (10, 25, 50, 100)
LEVELS = (0.5, 0.25, 0.1)
WINDOW = 10  # years before a unit-year in which a capacity coalescence counts as recent
YEARS: int | None = None  # horizon override (smoke tests only)


# ---------------------------------------------------------------- shadow run


class ShadowRun:
    """Installs the H3 transition (when ``continuity`` is given) and records every unit-year
    after each step, plus each unit's ordinary field change (F0, F1) of the year."""

    def __init__(self, continuity: float | None) -> None:
        self.continuity = continuity
        self.seconds = 0.0
        self.changes: dict[tuple[int, str], tuple[float, float]] = {}
        self.year = 0
        self._saved: list[tuple[Any, str, Any]] = []
        self.rows: dict[str, list[Any]] = defaultdict(list)
        self.blocks: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    def install(self) -> "ShadowRun":
        hook = simulation.account_strata

        def hook_observed(state: Any, ctx: Any) -> None:
            started = time.perf_counter()
            acc = ctx.field_accounts
            if acc is not None:
                for unit, f0, f1 in zip(
                    acc.units, acc.before.tolist(), acc.after.tolist(), strict=True
                ):
                    self.changes[(state.year, unit.id)] = (f0, f1)
            self.seconds += time.perf_counter() - started
            hook(state, ctx)

        patches: list[tuple[Any, str, Any]] = [(simulation, "account_strata", hook_observed)]
        if self.continuity is not None:
            p = self.continuity

            def transition(share: Any, claim: Any, before: Any, after: Any) -> Any:
                return counterfactual_field_claim_after_expansion(share, claim, before, after, p)

            patches.append((strata_accounting, "field_claims_after_change", transition))
        for owner, name, new in patches:
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, new)
        return self

    def remove(self) -> None:
        for owner, name, original in reversed(self._saved):
            setattr(owner, name, original)
        self._saved.clear()

    def snapshot(self, sim: Simulator) -> None:
        started = time.perf_counter()
        population = sim.state.population
        strata = population.strata
        assert strata is not None
        units = list(sim.state.units.values())
        slots = np.array([belief_slot(u) for u in units], dtype=np.int64)
        share = strata.columns["share"][slots]
        field = strata.columns["field_claim"][slots]
        store = strata.columns["store_claim"][slots]
        n = strata.n_strata[slots].astype(np.int64)
        start = len(self.rows["year"])
        rows = self.rows
        rows["year"] += [sim.state.year] * len(units)
        rows["unit"] += [u.id for u in units]
        rows["people"] += [u.population for u in units]
        rows["fields"] += [u.fields_ha for u in units]
        rows["n"] += n.tolist()
        rows["dev_field"] += (0.5 * np.abs(field - share).sum(axis=1)).tolist()
        rows["dev_store"] += (0.5 * np.abs(store - share).sum(axis=1)).tolist()
        for k in np.flatnonzero(n > 1).tolist():
            m = n[k]
            self.blocks[start + k] = (share[k, :m].copy(), field[k, :m].copy(), store[k, :m].copy())
        self.seconds += time.perf_counter() - started


def run_shadow(
    name: str, seed: int, weight: float, capacity: int, continuity: float | None, observe: bool
) -> dict[str, Any]:
    scenario = scenario_for(name, seed, weight, YEARS).with_settings(
        {"strata.max_strata": capacity}
    )
    shadow = ShadowRun(continuity)
    if observe or continuity is not None:
        shadow.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        for _ in range(scenario.config.simulation.n_years):
            sim.step()
            if not sim.state.units:
                break
            if observe:
                shadow.snapshot(sim)
        seconds = time.perf_counter() - started
    finally:
        shadow.remove()
    fusions: set[tuple[int, str]] = set()
    coalescences: dict[tuple[int, str], float] = defaultdict(float)
    for e in sim.state.population.strata_log or []:
        if e["event"] == "fusion_inheritance":
            fusions.add((e["year"], e["unit_id"]))
        elif e["event"] == "capacity_coalescence":
            coalescences[(e["year"], e["unit_id"])] += e["field_error"]
    arrays = {k: np.array(v) for k, v in shadow.rows.items()}
    return {
        "arrays": arrays,
        "blocks": shadow.blocks,
        "changes": shadow.changes,
        "fusions": fusions,
        "coalescences": dict(coalescences),
        "physical": physical_digest(sim),
        "strata": strata_digest(sim),
        "seconds": seconds,
        "observer_seconds": shadow.seconds,
        "continuity": 0.0 if continuity is None else continuity,
    }


# ---------------------------------------------------------------- analysis


def weighted_quantiles(
    values: np.ndarray, weights: np.ndarray, qs: tuple[float, ...]
) -> list[float]:
    if values.size == 0:
        return [float("nan")] * len(qs)
    order = np.argsort(values, kind="stable")
    v, cw = values[order], np.cumsum(weights[order])
    cw = cw / cw[-1]
    return [float(v[min(np.searchsorted(cw, q), v.size - 1)]) for q in qs]


def w1(pa: np.ndarray, wa: np.ndarray, pb: np.ndarray, wb: np.ndarray) -> float:
    """Wasserstein-1 between two weighted point measures on the line (weights sum to 1)."""
    points = np.concatenate([pa, pb])
    order = np.argsort(points, kind="stable")
    cum = np.cumsum(np.concatenate([wa, -wb])[order])
    return float((np.abs(cum[:-1]) * np.diff(points[order])).sum())


def field_measure(
    block: tuple[np.ndarray, np.ndarray, np.ndarray] | None,
) -> tuple[np.ndarray, np.ndarray]:
    if block is None:
        return np.ones(1), np.ones(1)
    share, field, _ = block
    return field / share, share


def kaplan_meier(durations: list[tuple[float, bool]], ages: tuple[int, ...]) -> list[float]:
    """Survival S(a) from (time, event) pairs (event False = censored at that time)."""
    if not durations:
        return [float("nan")] * len(ages)
    times = np.array([t for t, _ in durations])
    events = np.array([e for _, e in durations])
    out = []
    for a in ages:
        s = 1.0
        for t in np.unique(times[events & (times <= a)]):
            at_risk = (times >= t).sum()
            s *= 1.0 - (events & (times == t)).sum() / at_risk
        out.append(float(s))
    return out


def unit_series(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Unit-year indices of each unit in chronological order."""
    order = np.lexsort((arrays["year"], arrays["unit"]))
    units = arrays["unit"][order]
    cuts = np.flatnonzero(units[1:] != units[:-1]) + 1
    return {str(arrays["unit"][g[0]]): g for g in np.split(order, cuts)}


def episodes(run: dict[str, Any]) -> list[dict[str, Any]]:
    """Fusion-created non-neutral field-control episodes, followed until each deviation level
    is reached, the unit is lost, fuses again, or the run ends (censored)."""
    a = run["arrays"]
    years, dev, fields = a["year"], a["dev_field"], a["fields"]
    out = []
    for unit, idx in unit_series(a).items():
        k = 0
        while k < idx.size:
            i = idx[k]
            y = int(years[i])
            if (y, unit) not in run["fusions"] or dev[i] < EPISODE_MIN:
                k += 1
                continue
            start, f_start = float(dev[i]), float(fields[i])
            ep: dict[str, Any] = {
                "start": start,
                "year": y,
                "unit": unit,
                "fields": f_start,
                "coalesced": (y, unit) in run["coalescences"],
                "coalescence_error": run["coalescences"].get((y, unit), 0.0),
                "reached": {},
                "end": None,
                "grew": 0,
                "law_error": 0.0,
            }
            growth, previous, predicted = 1.0, start, 1.0
            j = k + 1
            while j < idx.size:
                r = idx[j]
                yr = int(years[r])
                if yr != int(years[idx[j - 1]]) + 1:
                    break  # gap: the id was reused; treat as lost
                if (yr, unit) in run["fusions"]:
                    break  # censored at the next fusion (a new episode may start)
                f0f1 = run["changes"].get((yr, unit))
                if f0f1 is not None and f0f1[1] > f0f1[0] > 0:
                    growth *= f0f1[1] / f0f1[0]
                if f0f1 is not None:
                    predicted *= retention_factor(f0f1[0], f0f1[1], run["continuity"])
                d = float(dev[r])
                if fields[r] > 0:  # the analytical law: D_t = D_0 * prod(p + (1 - p) F0 / F1)
                    ep["law_error"] = max(ep["law_error"], abs(d - start * predicted) / start)
                if d > previous * (1 + 1e-9) + 1e-15:
                    ep["grew"] += 1
                previous = d
                for level in LEVELS:
                    if level not in ep["reached"] and d <= level * start:
                        reset = fields[r] == 0
                        ep["reached"][level] = (
                            yr - y,
                            growth,
                            reset,
                            float(fields[r]) / f_start if f_start > 0 else float("nan"),
                        )
                j += 1
            last = int(years[idx[j - 1]])
            ep["end"] = last - y
            ep["observed_growth"] = growth
            out.append(ep)
            k = j
    return out


def summarize(run: dict[str, Any]) -> dict[str, Any]:
    a, blocks = run["arrays"], run["blocks"]
    n, people, dev = a["n"], a["people"].astype(float), a["dev_field"]
    multi = n > 1
    pos, wts = [], []
    for k, (share, field, _) in blocks.items():
        pos.append(field / share)
        wts.append(share * people[k])
    pos_all = np.concatenate(pos) if pos else np.ones(1)
    w_all = np.concatenate(wts) if wts else np.ones(1)
    eps = episodes(run)
    halving = [
        (e["reached"][0.5][0] if 0.5 in e["reached"] else e["end"], 0.5 in e["reached"])
        for e in eps
    ]
    tenth = [
        (e["reached"][0.1][0] if 0.1 in e["reached"] else e["end"], 0.1 in e["reached"])
        for e in eps
    ]
    # Zero-field resets of non-neutral control: previous year non-neutral, fields now 0.
    resets = 0
    increases_without_fusion = 0
    max_increase = 0.0
    for unit, idx in unit_series(a).items():
        for prev, cur in zip(idx[:-1].tolist(), idx[1:].tolist(), strict=True):
            if a["year"][cur] != a["year"][prev] + 1:
                continue
            if dev[prev] > NEUTRAL and a["fields"][cur] == 0:
                resets += 1
            if (
                dev[cur] > dev[prev] * (1 + 1e-9) + 1e-15
                and (int(a["year"][cur]), unit) not in run["fusions"]
            ):
                increases_without_fusion += 1
                max_increase = max(max_increase, float(dev[cur] - dev[prev]))
    return {
        "unit_years": int(n.size),
        "multi": int(multi.sum()),
        "nonneutral": int((dev > NEUTRAL).sum()),
        "strata_q": [float(n.mean()), *np.quantile(n, (0.5, 0.9, 0.99)).tolist()],
        "dev_pw": float((people * dev).sum() / people.sum()),
        "dev_store_pw": float((people * a["dev_store"]).sum() / people.sum()),
        "pos_q": weighted_quantiles(pos_all, w_all, (0.01, 0.1, 0.5, 0.9, 0.99)),
        "pos_absdev_pw": float(
            (w_all * np.abs(pos_all - 1)).sum() / max((people[multi]).sum(), 1e-300)
        ),
        "episodes": eps,
        "km_half": kaplan_meier(halving, AGES),
        "km_tenth": kaplan_meier(tenth, AGES),
        "resets": resets,
        "increases_without_fusion": increases_without_fusion,
        "max_increase": max_increase,
        "coalescences": len(run["coalescences"]),
        "coalescence_field_error": float(sum(run["coalescences"].values())),
    }


def recent(coalescences: dict[tuple[int, str], float], year: int, unit: str) -> bool:
    return any((y, unit) in coalescences for y in range(year - WINDOW, year + 1))


def compare(low: dict[str, Any], high: dict[str, Any]) -> dict[str, Any]:
    """Same p, capacity 16 vs 32, per unit-year (physical state identical: aligned rows)."""
    a, b = low["arrays"], high["arrays"]
    assert np.array_equal(a["unit"], b["unit"]) and np.array_equal(a["year"], b["year"])
    diff = np.abs(a["dev_field"] - b["dev_field"])
    keys = sorted(set(low["blocks"]) | set(high["blocks"]))
    w1s = np.zeros(a["year"].size)
    for k in keys:
        pa, wa = field_measure(low["blocks"].get(k))
        pb, wb = field_measure(high["blocks"].get(k))
        w1s[k] = w1(pa, wa, pb, wb)
    top = diff >= np.quantile(diff[diff > 0], 0.9) if (diff > 0).any() else diff > 0
    flagged = np.array(
        [
            recent(low["coalescences"], int(y), str(u))
            for y, u in zip(a["year"], a["unit"], strict=True)
        ]
    )
    differs = diff > 1e-12
    return {
        "diff": diff,
        "w1": w1s,
        "top_recent": float(flagged[top].mean()) if top.any() else float("nan"),
        "rest_recent": float(flagged[differs & ~top].mean())
        if (differs & ~top).any()
        else float("nan"),
        "flagged": flagged,
    }


def job(spec: tuple[str, int, float]) -> dict[str, Any]:
    name, seed, weight = spec
    out: dict[str, Any] = {"name": name, "seed": seed, "weight": weight, "per_p": {}}
    kept: dict[float, dict[str, Any]] = {}
    physical = set()
    for p in CONTINUITIES:
        runs = {c: run_shadow(name, seed, weight, c, p, observe=True) for c in CAPACITIES}
        physical |= {runs[c]["physical"] for c in CAPACITIES}
        cmp = compare(runs[16], runs[32])
        out["per_p"][p] = {
            "summary": {c: summarize(runs[c]) for c in CAPACITIES},
            "cmp": {k: v for k, v in cmp.items() if k not in ("diff", "w1", "flagged")},
            "diff16_32": float(cmp["diff"].sum()),
            "w1_16_32": cmp["w1"],
            "diff_q": np.quantile(cmp["diff"], (0.9, 0.99, 1.0)).tolist(),
            "seconds": {c: runs[c]["seconds"] for c in CAPACITIES},
            "observer_seconds": {c: runs[c]["observer_seconds"] for c in CAPACITIES},
            "strata": {c: runs[c]["strata"] for c in CAPACITIES},
        }
        # Long-lived tail: unit-years >= 25 y after the unit's last fusion.
        # Capacity coalescence happens only at a fusion, so a long-lived difference carries
        # coalescence error only through its origin: was the unit's last fusion coalesced?
        a = runs[16]["arrays"]
        fusion_years: dict[str, list[int]] = defaultdict(list)
        for y, u in sorted(runs[16]["fusions"]):
            fusion_years[u].append(y)
        age = np.full(a["year"].size, -1)
        origin = np.zeros(a["year"].size, dtype=bool)
        for k, (y, u) in enumerate(zip(a["year"].tolist(), a["unit"].tolist(), strict=True)):
            ys = fusion_years.get(u)
            if ys:
                i = int(np.searchsorted(ys, y, side="right"))
                if i > 0:
                    age[k] = y - ys[i - 1]
                    origin[k] = (ys[i - 1], u) in runs[16]["coalescences"]
        old = age >= 25
        old_nn = old & (a["dev_field"] > NEUTRAL)
        out["per_p"][p]["tail"] = {
            "old_nonneutral": int(old_nn.sum()),
            "old_diff16_32": float(cmp["diff"][old].sum()),
            "young_diff16_32": float(cmp["diff"][~old].sum()),
            "old_nonneutral_coalesced_origin": float(origin[old_nn].mean())
            if old_nn.any()
            else float("nan"),
            "nonneutral_coalesced_origin": float(origin[a["dev_field"] > NEUTRAL].mean()),
            "old_diff_coalesced_origin": float(cmp["diff"][old & origin].sum()),
            "old_dev_people": float((a["people"][old_nn] * a["dev_field"][old_nn]).sum()),
            "dev_people": float((a["people"] * a["dev_field"]).sum()),
        }
        if p in (0.0, 1.0):
            kept[p] = runs[32]
        del runs, cmp
    assert len(physical) == 1, "physical state differs across p or capacity"
    # Signal p = 0 -> 1 at capacity 32, per unit-year.
    s0, s1 = kept[0.0], kept[1.0]
    signal = np.abs(s0["arrays"]["dev_field"] - s1["arrays"]["dev_field"])
    w1_signal = np.zeros(signal.size)
    for k in sorted(set(s0["blocks"]) | set(s1["blocks"])):
        pa, wa = field_measure(s0["blocks"].get(k))
        pb, wb = field_measure(s1["blocks"].get(k))
        w1_signal[k] = w1(pa, wa, pb, wb)
    out["signal_dev"] = float(signal.sum())
    out["w1_signal"] = w1_signal
    # Observer and authoritative neutrality: a plain run at capacity 16.
    plain = run_shadow(name, seed, weight, 16, None, observe=False)
    out["plain_physical"] = plain["physical"]
    out["physical"] = physical.pop()
    out["plain_strata"] = plain["strata"]
    out["plain_seconds"] = plain["seconds"]
    return out


# ---------------------------------------------------------------- report


def fmt(values: list[float], digits: int = 3) -> str:
    return " / ".join(f"{v:.{digits}g}" for v in values)


def report(results: list[dict[str, Any]]) -> None:
    for name in SCENARIOS:
        rs = [r for r in results if r["name"] == name]
        if not rs:
            continue
        weight = rs[0]["weight"]
        print(f"\n=== {name}, w = {weight}, seeds {[r['seed'] for r in rs]} ===")
        ok_phys = all(r["plain_physical"] == r["physical"] for r in rs)
        ok_p0 = all(r["plain_strata"] == r["per_p"][0.0]["strata"][16] for r in rs)
        print(
            f"physical identical across p, capacity and plain run: {ok_phys}; p=0 strata sidecar == authoritative: {ok_p0}"
        )
        for c in CAPACITIES:
            print(f"\n-- capacity {c}")
            print(
                "| p | unit-years | multi-strata | non-neutral field | strata mean/p50/p90/p99 | dev pw | pos |.-1| pw (multi) | pos p1/p10/p50/p90/p99 | store dev pw | resets | dev up w/o fusion | coalescences / field err |"
            )
            print("|---|---|---|---|---|---|---|---|---|---|---|---|")
            for p in CONTINUITIES:
                ss = [r["per_p"][p]["summary"][c] for r in rs]

                def tot(k: str, ss: list[dict[str, Any]] = ss) -> Any:
                    return sum(s[k] for s in ss)

                py = sum(s["unit_years"] for s in ss)
                strata_q = np.mean([s["strata_q"] for s in ss], axis=0).tolist()
                print(
                    f"| {p} | {py} | {tot('multi')} | {tot('nonneutral')} | {fmt(strata_q)} "
                    f"| {np.mean([s['dev_pw'] for s in ss]):.4f} | {np.mean([s['pos_absdev_pw'] for s in ss]):.4f} "
                    f"| {fmt(np.mean([s['pos_q'] for s in ss], axis=0).tolist())} "
                    f"| {np.mean([s['dev_store_pw'] for s in ss]):.4f} | {tot('resets')} "
                    f"| {tot('increases_without_fusion')} (max {max(s['max_increase'] for s in ss):.2g}) "
                    f"| {tot('coalescences')} / {tot('coalescence_field_error'):.3g} |"
                )
            print(
                "\nepisodes (fusion-created, start dev >= 0.01): KM survival not halved / not below 10% at 10/25/50/100 y; halving by dilution: median years, expansion factor, area ratio; resets"
            )
            print(
                "| p | episodes | S_half(10/25/50/100) | S_10%(10/25/50/100) | halved by dilution: years p50 / growth p10/p50/p90 / area p50 | halved by reset | episodes that grew | max law error |"
            )
            print("|---|---|---|---|---|---|---|---|")
            for p in CONTINUITIES:
                eps = [e for r in rs for e in r["per_p"][p]["summary"][c]["episodes"]]
                halving = [
                    (e["reached"][0.5][0] if 0.5 in e["reached"] else e["end"], 0.5 in e["reached"])
                    for e in eps
                ]
                tenth = [
                    (e["reached"][0.1][0] if 0.1 in e["reached"] else e["end"], 0.1 in e["reached"])
                    for e in eps
                ]
                dil = [
                    e["reached"][0.5]
                    for e in eps
                    if 0.5 in e["reached"] and not e["reached"][0.5][2]
                ]
                reset = sum(1 for e in eps if 0.5 in e["reached"] and e["reached"][0.5][2])
                years = [d[0] for d in dil]
                growth = [d[1] for d in dil]
                area = [d[3] for d in dil if d[3] == d[3]]
                print(
                    f"| {p} | {len(eps)} | {fmt(kaplan_meier(halving, AGES))} | {fmt(kaplan_meier(tenth, AGES))} "
                    f"| {len(dil)}: {np.median(years) if years else float('nan'):.0f} y / "
                    f"{fmt(np.quantile(growth, (0.1, 0.5, 0.9)).tolist()) if growth else '-'} / {np.median(area) if area else float('nan'):.3g} "
                    f"| {reset} | {sum(1 for e in eps if e['grew'])} | {max((e['law_error'] for e in eps), default=0.0):.1e} |"
                )
            print(
                "\nper level: share reached by dilution vs reset; median expansion factor at 50/25/10 %"
            )
            for p in CONTINUITIES:
                eps = [e for r in rs for e in r["per_p"][p]["summary"][c]["episodes"]]
                parts = []
                for level in LEVELS:
                    hit = [e["reached"][level] for e in eps if level in e["reached"]]
                    dil = [h[1] for h in hit if not h[2]]
                    parts.append(
                        f"{int(level * 100)}%: {len(hit)} ({sum(h[2] for h in hit)} reset), growth p50 {np.median(dil) if dil else float('nan'):.3g}"
                    )
                coal = [e for e in eps if e["coalesced"]]
                long = [
                    e
                    for e in eps
                    if e["end"] >= 25 and (0.5 not in e["reached"] or e["reached"][0.5][0] >= 25)
                ]
                print(
                    f"  p={p}: {'; '.join(parts)}; coalesced at start {len(coal) / max(len(eps), 1):.2f}, among episodes not halved by 25 y {sum(e['coalesced'] for e in long) / max(len(long), 1):.2f} (n={len(long)})"
                )
        print("\n-- resolution 16 vs 32 (same p), relative to the p = 0 -> 1 signal at 32")
        signal = sum(r["signal_dev"] for r in rs)
        w1_sig = np.concatenate([r["w1_signal"] for r in rs])
        print(
            f"signal: sum |dev(p=1) - dev(p=0)| = {signal:.4g}; per unit-year W1(p0, p1) of field positions p50/p90/p99 over unit-years with signal: {fmt(np.quantile(w1_sig[w1_sig > 0], (0.5, 0.9, 0.99)).tolist()) if (w1_sig > 0).any() else '-'}"
        )
        print(
            "| p | sum |dev16 - dev32| / signal | |dev16-dev32| p90/p99/max | W1(16,32) p90/p99/max | W1(16,32)/W1 signal p99 | unit-years W1(16,32) > 0.1 signal | top-decile diff with recent coalescence vs rest |"
        )
        print("|---|---|---|---|---|---|---|")
        tails = []
        for p in CONTINUITIES:
            per = [r["per_p"][p] for r in rs]
            w = np.concatenate([x["w1_16_32"] for x in per])
            ratio = w[w1_sig > 0] / w1_sig[w1_sig > 0]
            tail_old = sum(x["tail"]["old_diff16_32"] for x in per)
            tail_all = tail_old + sum(x["tail"]["young_diff16_32"] for x in per)
            print(
                f"| {p} | {sum(x['diff16_32'] for x in per) / signal if signal else float('nan'):.3g} | {fmt(np.max([x['diff_q'] for x in per], axis=0).tolist())} "
                f"| {fmt(np.quantile(w, (0.9, 0.99, 1.0)).tolist())} | {np.quantile(ratio, 0.99) if ratio.size else float('nan'):.3g} "
                f"| {int((w[w1_sig > 0] > 0.1 * w1_sig[w1_sig > 0]).sum())} / {int((w1_sig > 0).sum())} "
                f"| {np.nanmean([x['cmp']['top_recent'] for x in per]):.2f} vs {np.nanmean([x['cmp']['rest_recent'] for x in per]):.2f} |"
            )
            tails.append((p, per, tail_old, tail_all))
        print(
            "\n-- long-lived tail (unit-years >= 25 y after the unit's last fusion; coalesced origin: that fusion needed capacity coalescence, capacity 16)"
        )
        print(
            "| p | non-neutral tail unit-years | share of people-weighted deviation in the tail | coalesced origin: tail / all non-neutral | share of 16v32 diff in the tail | ... of it with coalesced origin |"
        )
        print("|---|---|---|---|---|---|")
        for p, per, tail_old, tail_all in tails:
            t = [x["tail"] for x in per]
            print(
                f"| {p} | {sum(x['old_nonneutral'] for x in t)} | {sum(x['old_dev_people'] for x in t) / max(sum(x['dev_people'] for x in t), 1e-300):.3f} "
                f"| {np.nanmean([x['old_nonneutral_coalesced_origin'] for x in t]):.2f} / {np.nanmean([x['nonneutral_coalesced_origin'] for x in t]):.2f} "
                f"| {tail_old / tail_all if tail_all else float('nan'):.2f} | {sum(x['old_diff_coalesced_origin'] for x in t) / tail_old if tail_old else float('nan'):.2f} |"
            )
        print("\n-- cost")
        for p in CONTINUITIES:
            sec = [r["per_p"][p]["seconds"][c] for r in rs for c in CAPACITIES]
            obs = [r["per_p"][p]["observer_seconds"][c] for r in rs for c in CAPACITIES]
            print(f"p={p}: run {sum(sec):.0f} s, observer+transition {sum(obs):.1f} s")
        print(f"plain (capacity 16, no probe): {sum(r['plain_seconds'] for r in rs):.0f} s")


# ---------------------------------------------------------------- controlled


def controlled() -> None:
    share, claim = np.array([0.8, 0.2]), np.array([0.5, 0.5])
    print(
        "Unequal control share = [0.8, 0.2], field_claim = [0.5, 0.5] (positions 0.625 / 2.5), dev 0.3"
    )
    print("| expansion F1/F0 | " + " | ".join(f"p={p}" for p in CONTINUITIES) + " |")
    print("|---|" + "---|" * len(CONTINUITIES))
    for g in (1.0, 1.1, 2.0, 10.0, 100.0):
        cells = []
        for p in CONTINUITIES:
            c = counterfactual_field_claim_after_expansion(share, claim, 10.0, 10.0 * g, p)
            cells.append(
                f"{c[1]:.4f} (pos {c[1] / 0.2:.3f}, dev {control_deviation(share, c):.4f})"
            )
        print(f"| {g} | " + " | ".join(cells) + " |")
    print(
        "\nNeutral control share = field_claim = [0.8, 0.2], 1000 random expansions: max |claim - share|"
    )
    rng = np.random.default_rng(0)
    for p in CONTINUITIES:
        c, f = share.copy(), 1.0
        for _ in range(1000):
            g = f * (1 + rng.random())
            c, f = counterfactual_field_claim_after_expansion(share, c, f, g, p), g
            if f > 1e6:
                c, f = field_claim_step(share, c, f, 0.5 * f, p), 0.5 * f
        print(f"  p={p}: {np.abs(c - share).max():.2e}")
    print(
        "\nRepeated expansion +3 %/y for 100 y (area x19.2): dev after 25/50/100 y (analytical (F/F0)^-(1-p))"
    )
    for p in CONTINUITIES:
        c, f, out = claim.copy(), 1.0, []
        for t in range(1, 101):
            c, f = counterfactual_field_claim_after_expansion(share, c, f, f * 1.03, p), f * 1.03
            if t in (25, 50, 100):
                out.append(f"{control_deviation(share, c):.4f} ({0.3 * f ** -(1 - p):.4f})")
        print(f"  p={p}: " + " / ".join(out))
    print(
        "\nArea growth needed to halve / quarter / reach 10 % (small steps): 2^(1/(1-p)), 4^(1/(1-p)), 10^(1/(1-p))"
    )
    for p in CONTINUITIES:
        if p == 1.0:
            print("  p=1: never (dev constant under pure expansion)")
            continue
        print(
            f"  p={p}: {2 ** (1 / (1 - p)):.3g} / {4 ** (1 / (1 - p)):.3g} / {10 ** (1 / (1 - p)):.3g}"
        )
    print("\nOne step of factor G retains p + (1-p)/G (>= G^-(1-p), AM-GM): e.g. G=2:")
    for p in CONTINUITIES:
        print(
            f"  p={p}: step {retention_factor(1.0, 2.0, p):.4f}, continuous {2.0 ** -(1 - p):.4f}"
        )
    print("\nExpand x2, shrink x0.5, expand x2: dev")
    for p in CONTINUITIES:
        c1 = counterfactual_field_claim_after_expansion(share, claim, 10.0, 20.0, p)
        c2 = counterfactual_field_claim_after_expansion(share, c1, 20.0, 10.0, p)
        c3 = counterfactual_field_claim_after_expansion(share, c2, 10.0, 20.0, p)
        print(
            f"  p={p}: {control_deviation(share, c1):.4f} -> {control_deviation(share, c2):.4f} -> {control_deviation(share, c3):.4f}"
        )
    print(
        "\nZero fields then regrowth (claim_zero_stock): claim after reset / after regrowth to 5 ha"
    )
    for p in CONTINUITIES:
        c0 = field_claim_step(share, claim, 10.0, 0.0, p)
        c1 = field_claim_step(share, c0, 0.0, 5.0, p)
        print(f"  p={p}: {c0.tolist()} / {c1.tolist()}")


def _set_years(years: int | None) -> None:
    global YEARS
    YEARS = years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("controlled", "runs", "report"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--stress", action="store_true", help="w = 1 instead of 0")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    parser.add_argument("--years", type=int, help="shorter horizon (smoke test)")
    args = parser.parse_args()
    global YEARS
    YEARS = args.years
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "report":
        with args.load.open("rb") as f:
            report(pickle.load(f))
        return
    weight = 1.0 if args.stress else 0.0
    specs = [(name, seed, weight) for name in SCENARIOS for seed in args.seeds]
    started = time.perf_counter()
    with Pool(args.jobs, initializer=_set_years, initargs=(args.years,)) as pool:
        results = pool.map(job, specs, chunksize=1)
    print(f"wall time {time.perf_counter() - started:.0f} s")
    if args.out:
        with args.out.open("wb") as f:
            pickle.dump(results, f)
    report(results)


if __name__ == "__main__":
    main()
