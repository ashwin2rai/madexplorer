# The report tables keep one entry per line.
# ruff: noqa: E501
"""Counterfactual stored-food access (MVP 3 Stage 4C): observation only. NOT ACTIVE.

Evaluates the candidate mechanism of ``madexplorer.population.strata_access`` (access to a
unit's store withdrawal by ``store_claim``, weight a = ``store_access_claim_weight``) on
recorded shortage states. Nothing in the model changes: the probe wraps
``EnergyUpdates.apply`` (to read the year's need) and the engine's ``account_strata`` hook
(to copy each shortage unit's pre-withdrawal shares and store claims before the accounting
and zero-stock rules run), then evaluates several a on the same recorded state.

Modes:

``controlled``
    Deterministic cases on the real rule functions: repeated shortage with positive stores,
    final depletion, need caps, the zero-priority fallback, continuity in a.
``runs``
    Frozen reference scenarios (mvp2_neolithic 600 y, mvp2_pressure + cultivation 400 y;
    seeds 0-3) at ``strata.max_strata`` 16 and 32 (physical state identical), w =
    ``strata.field_output_claim_weight`` 0 (primary) or 1 (``--stress``): prevalence,
    mechanism signal over a, 16-vs-32 resolution (per unit-year population-weighted W1 of
    the access-ratio distribution, |R16 - R32|), association with capacity coalescence,
    repeated shortages, zero-store resets, the D audit, observer neutrality and cost.

Usage:
    uv run python scripts/probes/store_access_counterfactual.py controlled
    uv run python scripts/probes/store_access_counterfactual.py runs [--jobs 2] [--stress] [--out f.pkl]
    uv run python scripts/probes/store_access_counterfactual.py report --load f.pkl
"""

import argparse
import hashlib
import json
import pickle
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from strata_capacity import physical_digest
from strata_review import SEEDS, scenario_for

import madexplorer.core.simulation as simulation
from madexplorer.core.simulation import Simulator
from madexplorer.population.energetics import EnergyUpdates
from madexplorer.population.strata_access import (
    REL_TOL,
    allocate_store_access_counterfactual,
    counterfactual_store_access,
)
from madexplorer.population.strata_accounting import store_claims_after_year

ACCESS_WEIGHTS = (0.0, 0.25, 0.5, 1.0)
CAPACITIES = (16, 32)
SCENARIOS = ("neolithic", "pressure+cult")
NEUTRAL_POSITION = 1e-9  # |store position - 1| above this: non-neutral claims
DUST = 1e-9  # X <= DUST * Need: a rounding remnant of stores (below the allocator's allowance)
ACTIVE = 1e-9  # R / X at a = 1 above this (and X not dust): the weight changes the allocation
WINDOW = 10  # years before a shortage in which a capacity coalescence counts as recent


# ---------------------------------------------------------------- observation


class ShortageObserver:
    """Copies every shortage unit-year's pre-withdrawal state (read-only wrappers)."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.unit_years = 0
        self.deficit_years = 0
        self.reset_checks = 0
        self.reset_failures = 0
        self.seconds = 0.0
        self._need: np.ndarray | None = None
        self._saved: list[tuple[Any, str, Any]] = []

    def install(self) -> "ShortageObserver":
        apply, hook = EnergyUpdates.apply, simulation.account_strata

        def apply_observed(updates: EnergyUpdates, state: Any, ctx: Any) -> None:
            apply(updates, state, ctx)
            self._need = updates.need_kcal.copy()

        def hook_observed(state: Any, ctx: Any) -> None:
            started = time.perf_counter()
            pending = self._capture(state, ctx) if ctx.food_accounts is not None else []
            self.seconds += time.perf_counter() - started
            hook(state, ctx)
            started = time.perf_counter()
            self._check_resets(pending)
            self.seconds += time.perf_counter() - started

        for owner, name, new in (
            (EnergyUpdates, "apply", apply_observed),
            (simulation, "account_strata", hook_observed),
        ):
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, new)
        return self

    def remove(self) -> None:
        for owner, name, original in reversed(self._saved):
            setattr(owner, name, original)
        self._saved.clear()

    def _capture(self, state: Any, ctx: Any) -> list[tuple[Any, dict[str, Any]]]:
        acc, need = ctx.food_accounts, self._need
        assert need is not None and acc.harvest is not None and len(need) == len(acc.units)
        self.unit_years += len(acc.units)
        short = np.flatnonzero(acc.harvest < need)
        self.deficit_years += short.size
        pending = []
        for r in short.tolist():
            x = float(acc.withdrawn[r])
            if x <= 0.0:
                continue
            unit = acc.units[r]
            block = unit.strata
            record = {
                "year": state.year,
                "unit": unit.id,
                "people": int(unit.population),
                "need": float(need[r]),
                "harvest": float(acc.harvest[r]),
                "withdrawn": x,
                "opening": float(acc.opening[r]),
                "closing": float(acc.closing[r]),
                "share": block.columns["share"].copy(),
                "store_claim": block.columns["store_claim"].copy(),
                "ids": block.stratum_id.copy(),
            }
            self.records.append(record)
            if record["closing"] == 0.0:
                pending.append((unit, record))
        self._need = None
        return pending

    def _check_resets(self, pending: list[tuple[Any, dict[str, Any]]]) -> None:
        """After the hook, an emptied store's claims equal shares (zero-stock rule)."""
        for unit, record in pending:
            block = unit.strata
            if record["share"].size == 1:  # single stratum: holds the whole stock either way
                continue
            self.reset_checks += 1
            same = np.array_equal(block.columns["store_claim"], block.columns["share"])
            record["reset_ok"] = same
            self.reset_failures += not same


def drive(scenario: Any, observer: ShortageObserver | None) -> tuple[Simulator, float]:
    if observer is not None:
        observer.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        for _ in range(scenario.config.simulation.n_years):
            sim.step()
            if not sim.state.units:
                break
        return sim, time.perf_counter() - started
    finally:
        if observer is not None:
            observer.remove()


def strata_digest(sim: Simulator) -> str:
    """Strata sidecar (events, flows) and final strata of every unit."""
    population = sim.state.population
    h = hashlib.sha256()
    h.update(json.dumps(population.strata_log, default=repr).encode())
    h.update(json.dumps(population.strata_flows, default=repr).encode())
    for unit in sim.state.units.values():
        for name, values in unit.strata.columns.items():
            h.update(name.encode() + np.ascontiguousarray(values).tobytes())
    return h.hexdigest()


# ---------------------------------------------------------------- evaluation


def weighted_quantiles(
    values: np.ndarray, weights: np.ndarray, qs: tuple[float, ...]
) -> list[float]:
    order = np.argsort(values, kind="stable")
    v, cw = values[order], np.cumsum(weights[order])
    cw = cw / cw[-1]
    return [float(v[min(np.searchsorted(cw, q), v.size - 1)]) for q in qs]


def w1(pa: np.ndarray, wa: np.ndarray, pb: np.ndarray, wb: np.ndarray) -> float:
    """Wasserstein-1 between two weighted point measures (each weight vector sums to 1)."""
    grid = np.unique(np.concatenate([pa, pb]))
    if grid.size < 2:
        return 0.0
    fa = np.array([wa[pa <= g].sum() for g in grid[:-1]]) / wa.sum()
    fb = np.array([wb[pb <= g].sum() for g in grid[:-1]]) / wb.sum()
    return float((np.abs(fa - fb) * np.diff(grid)).sum())


def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    """Every access weight on one recorded state, plus the audits."""
    share, claim = record["share"], record["store_claim"]
    need, harvest, x = record["need"], record["harvest"], record["withdrawn"]
    slack = REL_TOL * max(record["opening"], need)
    out: dict[str, Any] = {
        "position_dev": float(np.abs(claim / share - 1.0).max()),
        "deficit_gap": abs(float((max(need - harvest, 0.0) * share).sum()) - (need - harvest))
        / need,
        "excess": (x - float((max(need - harvest, 0.0) * share).sum()))
        / max(record["opening"], need),
        "pooled_ratio": (harvest + x) / need,
        "per_a": {},
    }
    for a in ACCESS_WEIGHTS:
        result = counterfactual_store_access(share, claim, need, harvest, x, a, slack)
        alloc = result.allocation
        assert (result.counterfactual_store_access_kcal >= 0).all()
        assert (result.counterfactual_store_access_kcal <= result.deficit).all()
        assert abs(result.counterfactual_store_access_kcal.sum() - x) <= REL_TOL * x + slack
        out["per_a"][a] = {
            "R": result.redistribution_kcal,
            "R_fraction": result.redistribution_fraction,
            "ratio": result.counterfactual_external_food_allocation_ratio,
            "unmet": result.counterfactual_unmet_external_need_kcal / (need * share),
            "capped": bool(alloc.capped.any()) and alloc.rounds > 0,
            "fallback": alloc.fallback,
            "complete": alloc.rounds == 0,
            "access": result.counterfactual_store_access_kcal,
        }
    return out


def coalescence_index(sim: Simulator) -> dict[str, list[tuple[int, float]]]:
    out: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for e in sim.state.population.strata_log or []:
        if e["event"] == "capacity_coalescence":
            out[e["unit_id"]].append((e["year"], e["combined_error"]))
    return out


def recent_coalescence(
    index: dict[str, list[tuple[int, float]]], unit: str, year: int
) -> tuple[bool, float]:
    hits = [err for y, err in index.get(unit, []) if year - WINDOW <= y < year]
    return bool(hits), float(sum(hits))


def one_capacity(name: str, seed: int, weight: float, capacity: int) -> dict[str, Any]:
    scenario = scenario_for(name, seed, weight).with_settings({"strata.max_strata": capacity})
    observer = ShortageObserver()
    sim, seconds = drive(scenario, observer)
    started = time.perf_counter()
    evaluated = [evaluate(r) for r in observer.records]
    eval_seconds = time.perf_counter() - started
    index = coalescence_index(sim)
    keyed = {}
    for record, ev in zip(observer.records, evaluated, strict=True):
        recent, err = recent_coalescence(index, record["unit"], record["year"])
        keyed[(record["year"], record["unit"])] = {
            **record,
            **ev,
            "recent": recent,
            "recent_error": err,
        }
    snapshot_bytes = sum(
        r["share"].nbytes + r["store_claim"].nbytes + r["ids"].nbytes for r in observer.records
    )
    return {
        "keyed": keyed,
        "unit_years": observer.unit_years,
        "deficit_years": observer.deficit_years,
        "reset_checks": observer.reset_checks,
        "reset_failures": observer.reset_failures,
        "seconds": seconds,
        "observer_seconds": observer.seconds,
        "eval_seconds": eval_seconds,
        "evaluations": len(evaluated) * len(ACCESS_WEIGHTS),
        "snapshot_bytes": snapshot_bytes,
        "physical": physical_digest(sim),
        "strata": strata_digest(sim),
    }


def job(spec: tuple[str, int, float]) -> dict[str, Any]:
    name, seed, weight = spec
    runs = {c: one_capacity(name, seed, weight, c) for c in CAPACITIES}
    # Observer neutrality: the same run without the observer.
    plain = scenario_for(name, seed, weight).with_settings({"strata.max_strata": CAPACITIES[0]})
    sim, plain_seconds = drive(plain, None)
    low, high = (runs[c] for c in CAPACITIES)
    assert low["keyed"].keys() == high["keyed"].keys(), (
        "shortage unit-years differ across capacities"
    )
    rows = []
    for key in sorted(high["keyed"]):
        a16, a32 = low["keyed"][key], high["keyed"][key]
        row: dict[str, Any] = {
            "key": key,
            "people": a32["people"],
            "withdrawn": a32["withdrawn"],
            "depletion": a32["closing"] == 0.0,
            "dust": a32["withdrawn"] <= DUST * a32["need"],
            "nonneutral": a32["position_dev"] > NEUTRAL_POSITION,
            "nonneutral16": a16["position_dev"] > NEUTRAL_POSITION,
            "recent16": a16["recent"],
            "recent32": a32["recent"],
            "recent_error16": a16["recent_error"],
            "n16": a16["share"].size,
            "n32": a32["share"].size,
            "pooled_ratio": a32["pooled_ratio"],
            "per_a": {},
        }
        s16, s32 = a16["share"], a32["share"]
        base = a32["per_a"][0.0]
        for a in ACCESS_WEIGHTS:
            p16, p32 = a16["per_a"][a], a32["per_a"][a]
            ratio = p32["ratio"]
            pooled = row["pooled_ratio"]
            row["per_a"][a] = {
                "R32": p32["R"], "R16": p16["R"],
                "Rf32": p32["R_fraction"], "Rf16": p16["R_fraction"],
                "w1_res": w1(p16["ratio"], s16, ratio, s32),
                "w1_signal": w1(base["ratio"], s32, ratio, s32),
                "w1_unmet_signal": w1(base["unmet"], s32, p32["unmet"], s32),
                "q10_50_90": weighted_quantiles(ratio, s32, (0.1, 0.5, 0.9)),
                "mad": float((s32 * np.abs(ratio - pooled)).sum()),
                "below": float(s32[ratio < pooled * (1 - 1e-12)].sum()),
                "capped": p32["capped"], "fallback": p32["fallback"], "complete": p32["complete"],
                "capped16": p16["capped"], "fallback16": p16["fallback"],
                "ratio": ratio, "share": s32,
            }  # fmt: skip
        rows.append(row)
    sequences = repeated_shortages(high["keyed"])
    audits = {
        c: {
            "deficit_gap": max((v["deficit_gap"] for v in runs[c]["keyed"].values()), default=0.0),
            "excess": max((v["excess"] for v in runs[c]["keyed"].values()), default=0.0),
            "reset_checks": runs[c]["reset_checks"],
            "reset_failures": runs[c]["reset_failures"],
            "depletion_nonneutral": sum(
                v["closing"] == 0.0 and v["position_dev"] > NEUTRAL_POSITION
                for v in runs[c]["keyed"].values()
            ),
        }
        for c in CAPACITIES
    }
    physical = {runs[c]["physical"] for c in CAPACITIES} | {physical_digest(sim)}
    out = {
        "name": name,
        "seed": seed,
        "weight": weight,
        "rows": rows,
        "sequences": sequences,
        "audits": audits,
        "unit_years": high["unit_years"],
        "deficit_years": high["deficit_years"],
        "physical_identical": len(physical) == 1,
        "observer_neutral": runs[CAPACITIES[0]]["strata"] == strata_digest(sim),
        "cost": {
            c: {
                k: runs[c][k]
                for k in (
                    "seconds",
                    "observer_seconds",
                    "eval_seconds",
                    "evaluations",
                    "snapshot_bytes",
                )
            }
            for c in CAPACITIES
        },
        "plain_seconds": plain_seconds,
    }
    print(f"  done {name} seed {seed} w={weight}: {len(rows)} withdrawal unit-years, "
          f"physical identical {out['physical_identical']}, observer neutral {out['observer_neutral']}", flush=True)  # fmt: skip
    return out


def repeated_shortages(
    keyed: dict[tuple[int, str], dict[str, Any]], gap: int = 2
) -> dict[str, Any]:
    """Chains of withdrawal years of one unit (gaps <= ``gap`` years), at capacity 32."""
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (_, unit), v in sorted(keyed.items()):
        by_unit[unit].append(v)
    chains = []
    for events in by_unit.values():
        chain = [events[0]]
        for v in events[1:]:
            if v["year"] - chain[-1]["year"] <= gap:
                chain.append(v)
            else:
                chains.append(chain)
                chain = [v]
        chains.append(chain)
    multi = [c for c in chains if len(c) > 1]
    # Events inside a chain where claims are non-neutral and stores stay positive.
    positive_nonneutral = [
        v for c in multi for v in c if v["closing"] > 0 and v["position_dev"] > NEUTRAL_POSITION
    ]
    changed_positive = [
        v for v in positive_nonneutral if v["per_a"][1.0]["R"] > REL_TOL * v["withdrawn"]
    ]
    persisting = []  # chains in which non-neutral claims survive at least two withdrawal years
    for c in multi:
        run = [v for v in c if v["position_dev"] > NEUTRAL_POSITION]
        if len(run) >= 2:
            persisting.append(c)
    examples = sorted(persisting, key=len)
    picks = [examples[len(examples) // 2], examples[-1]] if examples else []
    return {
        "chains": len(chains),
        "multi": len(multi),
        "multi_events": sum(len(c) for c in multi),
        "positive_nonneutral": len(positive_nonneutral),
        "changed_positive": len(changed_positive),
        "persisting": len(persisting),
        "ends_in_depletion": sum(c[-1]["closing"] == 0.0 for c in persisting),
        "examples": [[trajectory_row(v) for v in c] for c in picks],
    }


def trajectory_row(v: dict[str, Any]) -> dict[str, Any]:
    share, claim, ids = v["share"], v["store_claim"], v["ids"]
    k = int(np.argmax(claim / share))  # the highest store position this year
    return {
        "year": v["year"],
        "unit": v["unit"],
        "n": share.size,
        "top_id": int(ids[k]),
        "top_share": float(share[k]),
        "top_claim": float(claim[k]),
        "opening": v["opening"],
        "withdrawn": v["withdrawn"],
        "closing": v["closing"],
        "deficit": v["need"] - v["harvest"],
        "top_access_over_pooled": {
            a: float(v["per_a"][a]["access"][k] / (v["withdrawn"] * share[k]))
            for a in ACCESS_WEIGHTS
        },
        "reset_ok": v.get("reset_ok"),
    }


# ---------------------------------------------------------------- report


def q(values: list[float] | np.ndarray, qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> str:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return "-"
    return "/".join(f"{np.quantile(values, x):.3g}" for x in qs) + f"/max {values.max():.3g}"


def report(results: list[dict[str, Any]], label: str) -> None:
    print(f"\n######## {label}")
    print(
        "physical state identical across capacities and observer on/off:",
        all(r["physical_identical"] for r in results),
    )
    print(
        "strata sidecar identical with observer on/off (capacity 16):",
        all(r["observer_neutral"] for r in results),
    )
    for name in SCENARIOS:
        res = [r for r in results if r["name"] == name]
        rows = [row for r in res for row in r["rows"]]
        active = [r for r in rows if not r["dust"] and r["per_a"][1.0]["Rf32"] > ACTIVE]
        dust = [r for r in rows if r["dust"]]
        nonneutral = [row for row in rows if row["nonneutral"]]
        print(f"\n=== {name}, seeds {tuple(r['seed'] for r in res)} ===")
        print("-- prevalence (capacity 32; withdrawal = shortage year with X > 0)")
        print(
            f"unit-years {sum(r['unit_years'] for r in res)}; deficit unit-years {sum(r['deficit_years'] for r in res)}; "
            f"withdrawal unit-years {len(rows)}; with non-neutral claims {len(nonneutral)} (capacity 16: {sum(r['nonneutral16'] for r in rows)})"
        )
        print(
            f"complete satisfaction (X = sum D) {sum(r['per_a'][1.0]['complete'] for r in rows)}; "
            f"total depletion {sum(r['depletion'] for r in rows)}; non-neutral and depletion {sum(r['depletion'] for r in nonneutral)}"
        )
        print(
            f"dust withdrawals (X <= {DUST:g} Need; excluded below) {len(dust)}, max X {max((r['withdrawn'] for r in dust), default=0):.3g} kcal"
        )
        print(
            f"a = 1 changes the allocation (R > {ACTIVE:g} X): {len(active)} unit-years; all of them depletion years: {all(r['depletion'] for r in active)}"
        )
        print(
            f"  people exposed {sum(r['people'] for r in active)} person-years (all withdrawal years: {sum(r['people'] for r in rows)}); "
            f"store kcal withdrawn {sum(r['withdrawn'] for r in active):.3g} (all: {sum(r['withdrawn'] for r in rows):.3g})"
        )
        for a in ACCESS_WEIGHTS[1:]:
            print(
                f"  a={a}: need caps active {sum(r['per_a'][a]['capped'] for r in active)}, zero-priority fallback {sum(r['per_a'][a]['fallback'] for r in active)} of {len(active)}"
            )
        print(
            "-- mechanism signal at capacity 32 (over mechanism-active unit-years; quantiles p50/p90/p99/max)"
        )
        for a in ACCESS_WEIGHTS:
            R = [r["per_a"][a]["R32"] for r in active]
            print(
                f"  a={a:<4}  R total {sum(R):.4g} kcal ({sum(R) / max(sum(r['withdrawn'] for r in active), 1e-300):.3g} of X); "
                f"R {q(R)}; R/X {q([r['per_a'][a]['Rf32'] for r in active])}"
            )
            print(
                f"           W1(a=0, a) of access ratio {q([r['per_a'][a]['w1_signal'] for r in active])}; "
                f"W1 of unmet ratio {q([r['per_a'][a]['w1_unmet_signal'] for r in active])}"
            )
            print(
                f"           pop-weighted MAD from pooled ratio {q([r['per_a'][a]['mad'] for r in active])}; "
                f"pop fraction below pooled {q([r['per_a'][a]['below'] for r in active])}"
            )
        if active:
            for a in (0.0, 1.0):
                ratio = np.concatenate([r["per_a"][a]["ratio"] for r in active])
                people = np.concatenate([r["per_a"][a]["share"] * r["people"] for r in active])
                print(
                    f"  people-weighted access ratio over all active unit-years, a={a}: p10/p50/p90 "
                    + "/".join(
                        f"{v:.3f}" for v in weighted_quantiles(ratio, people, (0.1, 0.5, 0.9))
                    )
                )
        print(
            "-- resolution 16 vs 32 (same year, unit, a; over mechanism-active unit-years at either capacity)"
        )
        either = [
            r
            for r in rows
            if not r["dust"] and max(r["per_a"][1.0]["Rf32"], r["per_a"][1.0]["Rf16"]) > ACTIVE
        ]
        for a in ACCESS_WEIGHTS:
            d = [abs(r["per_a"][a]["R16"] - r["per_a"][a]["R32"]) for r in either]
            df = [abs(r["per_a"][a]["Rf16"] - r["per_a"][a]["Rf32"]) for r in either]
            w = [r["per_a"][a]["w1_res"] for r in either]
            pw = sum(r["people"] * r["per_a"][a]["w1_res"] for r in either) / max(
                sum(r["people"] for r in either), 1
            )
            xw = sum(r["withdrawn"] * r["per_a"][a]["w1_res"] for r in either) / max(
                sum(r["withdrawn"] for r in either), 1e-300
            )
            tot16, tot32 = (
                sum(r["per_a"][a]["R16"] for r in either),
                sum(r["per_a"][a]["R32"] for r in either),
            )
            print(
                f"  a={a:<4}  |R16-R32| {q(d)}; |Rf16-Rf32| {q(df)}; total R 16 {tot16:.4g} vs 32 {tot32:.4g}"
            )
            print(
                f"           W1(16, 32) {q(w)}; people-weighted mean {pw:.3g}; X-weighted mean {xw:.3g}"
            )
        print(
            "-- signal vs resolution uncertainty at a = 1 (per unit-year; mechanism-active at 32)"
        )
        sig = np.array([r["per_a"][1.0]["R32"] for r in active])
        unc = np.array([abs(r["per_a"][1.0]["R16"] - r["per_a"][1.0]["R32"]) for r in active])
        ws = np.array([r["per_a"][1.0]["w1_signal"] for r in active])
        wr = np.array([r["per_a"][1.0]["w1_res"] for r in active])
        if active:
            print(
                f"  R32 total {sig.sum():.4g} kcal vs sum|R16-R32| {unc.sum():.4g} kcal ({unc.sum() / sig.sum():.3g})"
            )
            meaningful = ws > 1e-12
            print(
                f"  |R16-R32| / R32 {q(unc / sig)}; W1 res / W1 signal (where W1 signal > 1e-12, {meaningful.sum()}) {q(wr[meaningful] / ws[meaningful])}"
            )
            print(
                f"  unit-years with |R16-R32| > 0.1 R32: {(unc > 0.1 * sig).sum()} of {sig.size}; W1 res > 0.1 W1 signal: {(wr > 0.1 * ws).sum()}"
            )
        print(f"-- capacity coalescence (prior {WINDOW} years, same unit id)")
        if active:
            rec16 = np.array([r["recent16"] for r in active])
            rec32 = np.array([r["recent32"] for r in active])
            print(
                f"  active unit-years with recent coalescence: capacity 16 {rec16.mean():.3f}, 32 {rec32.mean():.3f}; "
                f"multi-strata units at 16/32: {np.mean([r['n16'] > 1 for r in active]):.3f}/{np.mean([r['n32'] > 1 for r in active]):.3f}"
            )
            order = np.argsort(-unc)
            top = order[: max(1, len(order) // 10)]
            print(
                f"  largest 10% of |R16-R32|: recent coalescence at 16 {rec16[top].mean():.3f} (rest {np.delete(rec16, top).mean() if len(order) > len(top) else float('nan'):.3f}); "
                f"recent coalescence error at 16 p50 {np.median([active[i]['recent_error16'] for i in top]):.3g}"
            )
            no_coal = [i for i in range(len(active)) if not rec16[i]]
            print(
                f"  |R16-R32| without recent coalescence at 16: {q(unc[no_coal])}; with: {q(unc[rec16])}"
            )
        print("-- repeated shortages (capacity 32; chains of withdrawal years with gaps <= 2 y)")
        seq = [r["sequences"] for r in res]
        print(
            f"  chains {sum(s['chains'] for s in seq)}, with >= 2 withdrawals {sum(s['multi'] for s in seq)} ({sum(s['multi_events'] for s in seq)} events)"
        )
        print(
            f"  events in chains with positive closing stores and non-neutral claims {sum(s['positive_nonneutral'] for s in seq)}; "
            f"of which a = 1 changes allocation {sum(s['changed_positive'] for s in seq)}"
        )
        print(
            f"  chains where non-neutral claims persist >= 2 withdrawal years {sum(s['persisting'] for s in seq)}; ending in depletion {sum(s['ends_in_depletion'] for s in seq)}"
        )
        for s, r in zip(seq, res, strict=True):
            for example in s["examples"][:1]:
                print(f"  example (seed {r['seed']}):")
                for t in example:
                    print(
                        f"    y{t['year']} {t['unit']} n={t['n']} top id {t['top_id']} share {t['top_share']:.3f} claim {t['top_claim']:.3f} "
                        f"K0 {t['opening']:.3g} X {t['withdrawn']:.3g} (deficit {t['deficit']:.3g}) K1 {t['closing']:.3g} "
                        f"top access / pooled a=0..1: "
                        + " ".join(f"{v:.3f}" for v in t["top_access_over_pooled"].values())
                        + (f" reset_ok {t['reset_ok']}" if t["reset_ok"] is not None else "")
                    )
        print("-- audits (both capacities)")
        for c in CAPACITIES:
            au = [r["audits"][c] for r in res]
            print(
                f"  capacity {c}: max |sum D - (Need - H)| / Need {max(a['deficit_gap'] for a in au):.3g}; "
                f"max (X - sum D) / max(K0, Need) {max(a['excess'] for a in au):.3g}; "
                f"zero-store resets checked {sum(a['reset_checks'] for a in au)}, failures {sum(a['reset_failures'] for a in au)}; "
                f"non-neutral depletion events (pre-reset claims used) {sum(a['depletion_nonneutral'] for a in au)}"
            )
        print("-- cost")
        for c in CAPACITIES:
            co = [r["cost"][c] for r in res]
            secs, obs, ev, n = (
                sum(x[k] for x in co)
                for k in ("seconds", "observer_seconds", "eval_seconds", "evaluations")
            )
            print(
                f"  capacity {c}: run {secs:.0f} s (observer {obs:.2f} s); evaluation {ev:.2f} s for {n} (state, a) "
                f"= {1e6 * ev / max(n, 1):.0f} us each (incl. audits); snapshots {max(x['snapshot_bytes'] for x in co) / 1e6:.2f} MB max per run"
            )
        print(
            f"  plain run (capacity 16, no observer) {sum(r['plain_seconds'] for r in res):.0f} s"
        )


# ---------------------------------------------------------------- controlled


def controlled() -> None:
    """Deterministic cases on the real rule functions (prescribed flows)."""
    share = np.array([0.8, 0.2])
    claim = np.array([0.5, 0.5])  # the minority controls 2.5x its share of the stores
    need, harvest = 1000.0, 400.0  # deficit 600 per year
    print("== repeated shortage with stores remaining positive (prescribed X < sum D; see note)")
    print(
        "year  K0     X     K1    store_claim       x(a=0)          x(a=0.5)        x(a=1)        claim after"
    )
    stores = 2000.0
    # (harvest, withdrawal): four rationed years, then a bad year that empties the store.
    years = ((harvest, 300.0), (harvest, 300.0), (harvest, 300.0), (harvest, 300.0), (0.0, None))
    for year, (h, x) in enumerate(years, 1):
        x = min(need - h, stores) if x is None else x
        closing = stores - x
        cells = [
            counterfactual_store_access(
                share, claim, need, h, x, a
            ).counterfactual_store_access_kcal
            for a in (0.0, 0.5, 1.0)
        ]
        after = store_claims_after_year(share, claim, stores, 0.0, closing)
        print(
            f"{year:>4}  {stores:5.0f} {x:5.0f} {closing:5.0f}  {claim}  "
            + "  ".join(np.array2string(c, precision=1) for c in cells)
            + f"  {after}"
        )
        claim, stores = after, closing
    print(
        "note: MVP 2.1 energetics withdraws min(Need - H, K0), so X < sum D with stores left over"
    )
    print(
        "      does not occur physically; it would need a rationing rule. Physically, a year either"
    )
    print(
        "      covers sum D (x = D, claims irrelevant) or empties the stores (claims then reset)."
    )
    print("\n== need caps (share, claim, deficit, X, a = 1)")
    cases = {
        "no cap": ([0.5, 0.5], [0.6, 0.4], [100.0, 100.0], 100.0),
        "one saturates": ([0.8, 0.2], [0.5, 0.5], [80.0, 20.0], 60.0),
        "sequential": (
            [0.4, 0.3, 0.2, 0.1],
            [0.05, 0.15, 0.3, 0.5],
            [40.0, 30.0, 20.0, 10.0],
            70.0,
        ),
        "zero-priority fallback": ([0.5, 0.3, 0.2], [1.0, 0.0, 0.0], [50.0, 30.0, 20.0], 80.0),
        "complete": ([0.5, 0.5], [0.9, 0.1], [50.0, 50.0], 100.0),
        "no withdrawal": ([0.5, 0.5], [0.9, 0.1], [50.0, 50.0], 0.0),
    }
    for label, (s, c, d, x) in cases.items():
        r = allocate_store_access_counterfactual(np.array(s), np.array(c), np.array(d), x, 1.0)
        print(
            f"  {label:24} x={r.access} capped={r.capped} fallback={r.fallback} rounds={r.rounds}"
        )
    print("\n== continuity in a (sequential case): x(a) on a fine grid, max jump per step 1e-3")
    s, c, d = (np.array(v) for v in cases["sequential"][:3])
    x = 70.0
    grid = np.linspace(0.0, 1.0, 1001)
    runs = [allocate_store_access_counterfactual(s, c, d, x, a) for a in grid]
    xs = np.array([r.access for r in runs])
    caps = np.array([r.capped for r in runs])
    jumps = np.abs(np.diff(xs, axis=0)).max(axis=1)
    changes = np.flatnonzero((caps[1:] != caps[:-1]).any(axis=1))
    print(
        f"  max |x(a + 0.001) - x(a)| = {jumps.max():.4f} kcal (of X = {x}); cap transitions at a ~ "
        + ", ".join(f"{grid[i + 1]:.3f}" for i in changes)
    )
    for i in changes:  # bisect each transition to 1e-12 and compare both sides
        lo, hi = grid[i], grid[i + 1]
        for _ in range(45):
            mid = (lo + hi) / 2
            same = (allocate_store_access_counterfactual(s, c, d, x, mid).capped == caps[i]).all()
            lo, hi = (mid, hi) if same else (lo, mid)
        left = allocate_store_access_counterfactual(s, c, d, x, lo).access
        right = allocate_store_access_counterfactual(s, c, d, x, hi).access
        print(
            f"    transition at a = {lo:.12f}: max |x(left) - x(right)| = {np.abs(left - right).max():.2e} kcal"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=("controlled", "runs", "report"))
    parser.add_argument("--out", help="runs: pickle the per-job results here")
    parser.add_argument("--load", help="report: a pickle written by runs --out")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--stress", action="store_true", help="field_output_claim_weight = 1")
    parser.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "report":
        with open(args.load, "rb") as f:
            results, label = pickle.load(f)
        report(results, label)
        return
    weight = 1.0 if args.stress else 0.0
    seeds = tuple(int(s) for s in args.seeds.split(","))
    work = [(name, seed, weight) for name in SCENARIOS for seed in seeds]
    with Pool(args.jobs, maxtasksperchild=1) as pool:
        results = pool.map(job, work, chunksize=1)
    label = f"field_output_claim_weight = {weight} ({'stress' if args.stress else 'primary'})"
    if args.out:
        with open(args.out, "wb") as f:
            pickle.dump((results, label), f)
    report(results, label)


if __name__ == "__main__":
    main()
