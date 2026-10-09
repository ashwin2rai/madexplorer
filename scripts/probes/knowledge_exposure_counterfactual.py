# The report tables keep one entry per line.
# ruff: noqa: E501
"""Partial knowledge exposure (MVP 3 Stage 5E): observation only. NOT ACTIVE.

Would a technique first known by a few people still be partly unknown when cultivation
needs it? A shadow knowing share ``q`` (``population/knowledge_exposure.py``) is replayed over
the authoritative history of reference runs: per unit-year labor (capacity, clearing debt,
cultivation hours, labor-force entry) recorded at farming, and the event stream (invention,
adoption, loss, cultivation start, fission, fusion, extinction). Every parameter setting
replays the same history; nothing is re-simulated per setting and nothing feeds back
(checked by digest against a plain run).

Shadow year (pipeline order): farming (the constraint is evaluated with the current ``q``)
-> demography (turnover) -> field planning (``cultivation_started``) -> diffusion
(adoption) -> innovation (invention) -> fission -> fusion -> end of year (transmission).

Modes:

``controlled``
    The transmission calibration and trajectories; deterministic synthetic histories for
    the Stage 5E cases.
``record``
    Reference scenarios (neolithic 600 y, pressure + cultivation 400 y; seeds 0-3); one
    file per run.
``replay``
    The parameter sweep over saved histories and the report.

Usage:
    uv run python scripts/probes/knowledge_exposure_counterfactual.py controlled
    uv run python scripts/probes/knowledge_exposure_counterfactual.py record [--jobs 2] [--seeds ...] --out DIR
    uv run python scripts/probes/knowledge_exposure_counterfactual.py replay --load DIR
"""

import argparse
import pickle
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, physical_digest, q, scenario_for

from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import FarmingSubsystem, labor_hours_columns
from madexplorer.population.knowledge_exposure import (
    calibrate_beta,
    fission_expected,
    fission_finite,
    fusion,
    initial_exposure,
    knowledge_constraint,
    min_share,
    transmit,
    turnover,
    years_to,
)

TECH = "plant_cultivation"
SCENARIOS = ("neolithic", "pressure+cult")
HALF_YEARS = (1, 2, 5, 10, 20)  # years to 50 % from one knower in the reference unit
KEPT = {"invention", "technology_adopted", "technology_lost", "cultivation_started",
        "population_split", "population_merge", "unit_extinct"}  # fmt: skip

# ---------------------------------------------------------------- recording


class Recorder:
    """Read-only: per unit-year labor inputs at farming (after the authoritative evaluate)."""

    def __init__(self) -> None:
        self.rows: dict[int, list[tuple[str, float, float, float, float, float, float, float]]] = (
            defaultdict(list)
        )
        self._saved: Any = None
        self._ramp: dict[int, np.ndarray] = {}

    def install(self) -> None:
        original = FarmingSubsystem.evaluate
        rec = self

        def farming(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = original(sub, state, ctx)
            cols = ctx.columns(state)
            if len(cols) and proposals:
                ids = ctx.compiled.species_ids
                if not rec._ramp:
                    for k, s in enumerate(ids):
                        rec._ramp[k] = np.maximum(np.diff(ctx.tables[s].labor, prepend=0.0), 0.0)
                cap = labor_hours_columns(cols, ctx)
                debt = cols.get("labor_debt_hours")
                m = ctx.compiled.parameter("subsistence.max_farm_labor_share")[cols.species()]
                hpd = ctx.compiled.parameter("foraging.foraging_hours_per_day")[cols.species()]
                labor = cols.weighted({k: ctx.tables[s].labor for k, s in enumerate(ids)})
                inflow = cols.weighted(rec._ramp)
                pop = cols.population()
                hours = proposals[0].hours
                for k, u in enumerate(cols.units):
                    tau = float(inflow[k] / labor[k]) if labor[k] > 0 else 0.0
                    rec.rows[state.year].append(
                        (u.id, float(hours[k]), float(cap[k]), float(debt[k]), float(m[k]),
                         float(pop[k]), float(cap[k]) / (float(hpd[k]) * 365.0), min(tau, 1.0))
                    )  # fmt: skip
            return proposals

        self._saved = original
        FarmingSubsystem.evaluate = farming  # type: ignore[method-assign]

    def remove(self) -> None:
        FarmingSubsystem.evaluate = self._saved  # type: ignore[method-assign]


def _events(sim: Simulator) -> list[tuple[int, str, dict[str, Any]]]:
    out = []
    for e in sim.events:
        if e.kind not in KEPT:
            continue
        if (
            e.kind in ("invention", "technology_adopted", "technology_lost")
            and e.data.get("technology") != TECH
        ):
            continue
        out.append((e.year, e.kind, dict(e.data)))
    return out


def record_job(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    scenario = scenario_for(name, seed, 0.0)
    rec = Recorder()
    rec.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        horizon = scenario.config.simulation.n_years
        years = 0
        for years in range(1, horizon + 1):  # noqa: B007 (the count is kept after the loop)
            sim.step()
            if not sim.state.units:
                break
        seconds = time.perf_counter() - started
    finally:
        rec.remove()
    plain = Simulator(scenario, record_strata=True)
    for _ in range(years):
        plain.step()
        if not plain.state.units:
            break
    return {
        "name": name, "seed": seed, "years": years, "horizon": horizon, "seconds": seconds,
        "rows": dict(rec.rows), "events": _events(sim),
        "neutral": physical_digest(sim) == physical_digest(plain),
    }  # fmt: skip


# ---------------------------------------------------------------- replay


@dataclass(frozen=True)
class Config:
    k_invention: float = 1.0
    k_adoption: float = 1.0
    beta: float = np.inf
    rate: str = "instant"
    turnover: bool = True
    fission: str = "expected"  # expected | finite
    seed: int = 0

    @property
    def label(self) -> str:
        k = f"k={self.k_invention:g}" + (
            f"/{self.k_adoption:g}" if self.k_adoption != self.k_invention else ""
        )
        extra = "" if self.turnover else " no-turnover"
        fis = "" if self.fission == "expected" else f" finite#{self.seed}"
        return f"{k} {self.rate}{extra}{fis}"


@dataclass
class Lineage:
    origin: str  # invention | adoption
    year: int
    q0: float
    population: float
    first_planned: int | None = None
    q_planned: float | None = None
    first_farm: int | None = None
    q_farm: float | None = None
    first_substantial: int | None = None
    q_substantial: float | None = None
    q_after10: float | None = None
    reach: dict[float, int] = field(default_factory=dict)  # threshold -> years
    ever_binding: bool = False
    ever_material: bool = False
    first_binding: int | None = None
    q_first_binding: float | None = None
    alive: bool = True


@dataclass
class Result:
    farming: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    binding: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    pop_farming: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    pop_binding: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    hours: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    short: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    short_frac: list[float] = field(default_factory=list)  # per binding unit-year
    episodes: list[int] = field(default_factory=list)
    lineages: list[Lineage] = field(default_factory=list)
    knowless_holder_years: int = 0
    holder_years: int = 0
    knowledge_lost: int = 0
    reacquired: int = 0
    repeat_events: int = 0
    final: dict[str, float] = field(default_factory=dict)
    material: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )  # shortfall >= 5 % of P
    trivial: int = 0  # binding only because everyone is needed (f_min ~ 1) and shortfall < 1 %
    near_invention: int = 0  # farming unit-years in an inventing unit within 10 y of invention
    near_invention_material: int = 0


def replay(history: dict[str, Any], cfg: Config) -> Result:
    """Replay the shadow over one recorded run under one configuration."""
    rng = np.random.default_rng(10_000 + cfg.seed)
    res = Result()
    qs: dict[str, float] = {}
    route: dict[str, str] = {}  # how the unit came to know: invention / adoption / fission / fusion
    root: dict[str, Lineage] = {}  # the acquisition lineage a unit descends from
    holders: set[str] = set()
    streak: dict[str, int] = {}
    labor_now: dict[
        str, tuple[float, float]
    ] = {}  # unit -> (population, labor-equivalents) this year
    by_year: dict[int, list[tuple[int, str, dict[str, Any]]]] = defaultdict(list)
    for ev in history["events"]:
        by_year[ev[0]].append(ev)
    years = sorted(set(history["rows"]) | set(by_year))
    for year in years:
        rows = history["rows"].get(year, [])
        seen = set()
        # 1. farming: the constraint under the current q
        for uid, p, c, d, m, n, lab, _tau in rows:
            seen.add(uid)
            labor_now[uid] = (n, lab)
            if uid in holders:
                res.holder_years += 1
                if qs.get(uid, 0.0) == 0.0:
                    res.knowless_holder_years += 1
            if p <= 0.0:
                if uid in streak:
                    res.episodes.append(streak.pop(uid))
                continue
            qv = qs.get(uid, 0.0)
            tag = route.get(uid, "unknown")
            con = knowledge_constraint(qv, p, c, d, m)
            res.farming[tag] += 1
            res.pop_farming[tag] += n
            res.hours[tag] += p
            lin = root.get(uid)
            if (
                lin is not None
                and route.get(uid) in ("invention", "adoption")
                and lin.first_farm is None
            ):
                lin.first_farm, lin.q_farm = year, qv
            f = min_share(p, c, d, m)
            if lin is not None and route.get(uid) in ("invention", "adoption"):
                if lin.first_substantial is None and f >= 0.25:
                    lin.first_substantial, lin.q_substantial = year, qv
                if (
                    lin.first_farm is not None
                    and lin.q_after10 is None
                    and year >= lin.first_farm + 10
                ):
                    lin.q_after10 = qv
            near = lin is not None and tag == "invention" and year - lin.year <= 10
            res.near_invention += int(near)
            if con.binding and con.shortfall_hours >= 0.05 * p:
                res.material[tag] += 1
                res.near_invention_material += int(near)
                if lin is not None:
                    lin.ever_material = True
            if con.binding and f >= 0.999 and con.shortfall_hours < 0.01 * p:
                res.trivial += 1
            if con.binding:
                res.binding[tag] += 1
                res.pop_binding[tag] += n
                res.short[tag] += con.shortfall_hours
                res.short_frac.append(con.shortfall_hours / p)
                streak[uid] = streak.get(uid, 0) + 1
                if lin is not None and not lin.ever_binding:
                    lin.ever_binding, lin.first_binding, lin.q_first_binding = True, year, qv
            elif uid in streak:
                res.episodes.append(streak.pop(uid))
        # 2. demography: new workers do not know
        if cfg.turnover:
            for uid, _p, _c, _d, _m, _n, _lab, tau in rows:
                if qs.get(uid, 0.0) > 0.0:
                    qs[uid] = turnover(qs[uid], tau)
        # 3. the year's events, in emission order
        for _, kind, d in by_year.get(year, []):
            uid = d.get("unit_id")
            if kind == "cultivation_started":
                lin = root.get(uid)
                if (
                    lin is not None
                    and route.get(uid) in ("invention", "adoption")
                    and lin.first_planned is None
                ):
                    lin.first_planned, lin.q_planned = year, qs.get(uid, 0.0)
            elif kind in ("invention", "technology_adopted"):
                n, lab = labor_now.get(uid, (float(d.get("population", 0)), 0.0))
                k = cfg.k_invention if kind == "invention" else cfg.k_adoption
                before = qs.get(uid, 0.0)
                if uid in holders:
                    res.repeat_events += 1
                if before > 0.0:
                    res.reacquired += 1
                qs[uid] = initial_exposure(k, lab if lab > 0 else n, before)
                if np.isinf(cfg.beta):
                    qs[uid] = 1.0
                holders.add(uid)
                origin = "invention" if kind == "invention" else "adoption"
                route[uid] = origin
                lin = Lineage(origin, year, qs[uid], n)
                root[uid] = lin
                res.lineages.append(lin)
            elif kind == "technology_lost":
                holders.discard(uid)
                if qs.pop(uid, 0.0) > 0.0:
                    res.knowledge_lost += 1
            elif kind == "population_split":
                child = d["daughter_id"]
                if uid in holders:
                    holders.add(child)
                    qv = qs.get(uid, 0.0)
                    if cfg.fission == "finite":  # knowing workers, in labor-equivalents
                        n, lab = labor_now.get(uid, (float(d["source_population"]), 0.0))
                        slots = max(round(lab), 1)
                        frac = float(d["moved_population"]) / max(
                            float(d["source_population"]), 1.0
                        )
                        s = fission_finite(qv, slots, min(round(slots * frac), slots), rng)
                    else:
                        s = fission_expected(qv)
                    qs[uid], qs[child] = s.parent, s.daughter
                    route[child] = "fission"
                    if uid in root:
                        root[child] = root[uid]
            elif kind == "population_merge":
                src, dst = uid, d["into_id"]
                n_s = float(d["merged_population"])
                n_t = float(d["resulting_population"]) - n_s
                q_s, q_t = qs.pop(src, 0.0), qs.get(dst, 0.0)
                if src in holders or dst in holders:
                    qs[dst] = fusion(q_t, n_t, q_s, n_s)
                    if dst not in holders:
                        route[dst] = "fusion"
                        if src in root:
                            root[dst] = root[src]
                    holders.add(dst)
                holders.discard(src)
                streak.pop(src, None)
            elif kind == "unit_extinct":
                qs.pop(uid, None)
                holders.discard(uid)
                if uid in streak:
                    res.episodes.append(streak.pop(uid))
        # 4. end of year: transmission
        for uid in list(qs):
            if 0.0 < qs[uid] < 1.0:
                qs[uid] = transmit(qs[uid], cfg.beta)
        for lin_uid, lin in list(root.items()):
            if route.get(lin_uid) in ("invention", "adoption") and root[lin_uid] is lin:
                qv = qs.get(lin_uid)
                if qv is None:
                    continue
                for t in (0.5, 0.9, 0.99):
                    if t not in lin.reach and qv >= t:
                        lin.reach[t] = year - lin.year + 1
        del seen
    res.episodes.extend(streak.values())
    res.final = dict(qs)
    return res


# ---------------------------------------------------------------- calibration and configs


def reference_q0(histories: list[dict[str, Any]]) -> tuple[float, float]:
    """Median labor-equivalents and population at invention across the recorded runs."""
    labs, pops = [], []
    for h in histories:
        rows = h["rows"]
        for year, kind, d in h["events"]:
            if kind != "invention":
                continue
            for uid, _p, _c, _dd, _m, n, lab, _t in rows.get(year, []):
                if uid == d["unit_id"]:
                    labs.append(lab)
                    pops.append(n)
                    break
    return float(np.median(labs)), float(np.median(pops))


def configs(betas: dict[str, float]) -> list[Config]:
    rates = (
        [("instant", np.inf)]
        + [(f"T50={t}y", betas[f"T50={t}y"]) for t in HALF_YEARS]
        + [("none", 0.0)]
    )
    out = []
    for k in (1.0, 2.0, 5.0):
        for name, beta in rates:
            for tv in (True, False):
                out.append(Config(k, k, beta, name, tv))
    for name, beta in rates:
        out.append(Config(1.0, 5.0, beta, name, True))
    for name, beta in rates:
        for s in range(5):
            out.append(Config(1.0, 1.0, beta, name, True, "finite", s))
    return out


def replay_job(args: tuple[dict[str, Any], list[Config]]) -> list[tuple[Config, Result]]:
    history, cfgs = args
    return [(c, replay(history, c)) for c in cfgs]


# ---------------------------------------------------------------- report


def _ratio(a: float, b: float) -> float:
    return a / b if b else float("nan")


def _merge(results: list[Result]) -> Result:
    out = Result()
    for r in results:
        for name in (
            "farming",
            "binding",
            "pop_farming",
            "pop_binding",
            "hours",
            "short",
            "material",
        ):
            for k, v in getattr(r, name).items():
                getattr(out, name)[k] += v
        out.short_frac += r.short_frac
        out.episodes += r.episodes
        out.lineages += r.lineages
        for name in (
            "knowless_holder_years",
            "holder_years",
            "knowledge_lost",
            "reacquired",
            "repeat_events",
            "trivial",
            "near_invention",
            "near_invention_material",
        ):
            setattr(out, name, getattr(out, name) + getattr(r, name))
    return out


def report_scenario(
    name: str,
    results: dict[Config, list[Result]],
    ref: tuple[float, float],
    betas: dict[str, float],
) -> None:
    print(
        f"\n=== {name}: reference unit at invention: {ref[1]:.0f} people, {ref[0]:.1f} labor-equivalents (one knower q0 = {1 / ref[0]:.3f})"
    )
    any_res = _merge(next(iter(results.values())))
    lin = any_res.lineages
    print(
        f"acquisition lineages: invention {sum(x.origin == 'invention' for x in lin)}, adoption {sum(x.origin == 'adoption' for x in lin)}"
    )
    tags = ("invention", "adoption", "fission", "fusion")
    print(
        "\nMaterial binding (shortfall >= 5 % of planned hours) and trivial binding (everyone needed, shortfall < 1 %); expected-value fission"
    )
    print(
        "| config | material share of farming unit-years | material by route inv / adopt / fission / fusion | trivial share | lineages ever material inv / adopt | farming unit-years within 10 y of invention in the inventing unit: share of all (material share of them) |"
    )
    print("|---|---|---|---|---|---|")
    for cfg, rs in results.items():
        if cfg.fission != "expected":
            continue
        r = _merge(rs)
        fy = sum(r.farming.values())
        mat = " / ".join(f"{_ratio(r.material[t], r.farming[t]):.4f}" for t in tags)
        inv = [x for x in r.lineages if x.origin == "invention"]
        ado = [x for x in r.lineages if x.origin == "adoption"]
        lm = f"{_ratio(sum(x.ever_material for x in inv), len(inv)):.2f} / {_ratio(sum(x.ever_material for x in ado), len(ado)):.2f}"
        print(
            f"| {cfg.label} | {_ratio(sum(r.material.values()), fy):.5f} | {mat} | {_ratio(r.trivial, fy):.5f} | {lm} | {_ratio(r.near_invention, fy):.5f} ({_ratio(r.near_invention_material, r.near_invention):.3f}) |"
        )
    print("\nPotential knowledge constraint q < f_min (farming unit-years; expected-value fission)")
    print(
        "| config | binding share (unit-years) | (population-weighted) | hours constrained | shortfall / P p50/p90 (binding) | episode length p50/p90/max | binding share by route inv / adopt / fission / fusion | lineages ever binding inv / adopt |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for cfg, rs in results.items():
        if cfg.fission != "expected":
            continue
        r = _merge(rs)
        fy, by = sum(r.farming.values()), sum(r.binding.values())
        pf, pb = sum(r.pop_farming.values()), sum(r.pop_binding.values())
        hrs, sh = sum(r.hours.values()), sum(r.short.values())
        routes = " / ".join(f"{_ratio(r.binding[t], r.farming[t]):.4f}" for t in tags)
        inv = [x for x in r.lineages if x.origin == "invention"]
        ado = [x for x in r.lineages if x.origin == "adoption"]
        lb = f"{_ratio(sum(x.ever_binding for x in inv), len(inv)):.2f} / {_ratio(sum(x.ever_binding for x in ado), len(ado)):.2f}"
        print(
            f"| {cfg.label} | {_ratio(by, fy):.5f} | {_ratio(pb, pf):.5f} | {_ratio(sh, hrs):.5f} | {q(r.short_frac, (0.5, 0.9))} | {q(r.episodes, (0.5, 0.9))} | {routes} | {lb} |"
        )
    print(
        "\nFinite-knower fission (k = 1, turnover; 5 shadow draws): binding share of farming unit-years, min-max over draws; knowerless holder unit-years"
    )
    print(
        "| rate | binding share (draws) | hours constrained (draws) | knowerless holder share (draws) |"
    )
    print("|---|---|---|---|")
    by_rate: dict[str, list[Result]] = defaultdict(list)
    for cfg, rs in results.items():
        if cfg.fission == "finite":
            by_rate[cfg.rate].append(_merge(rs))
    for rate, rs in by_rate.items():
        b = [_ratio(sum(r.binding.values()), sum(r.farming.values())) for r in rs]
        h = [_ratio(sum(r.short.values()), sum(r.hours.values())) for r in rs]
        z = [_ratio(r.knowless_holder_years, r.holder_years) for r in rs]
        print(
            f"| {rate} | {min(b):.5f}-{max(b):.5f} | {min(h):.5f}-{max(h):.5f} | {min(z):.4f}-{max(z):.4f} |"
        )
    print(
        "\nTiming of acquisition lineages (k = 1, turnover, expected): knowing share at acquisition / first planned fields / first cultivation / first substantial (f_min >= 0.25) / 10 y after first cultivation; years to 50/90/99 %"
    )
    print(
        "| rate | origin | n | q0 p50 | first planned: lag p50 (q p50/p10) | first cultivation: lag p50 (q p50/p10) | substantial: q p50/p10 | +10 y: q p50 | years to 50 / 90 / 99 % p50 | first binding lag p50 (q) |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for cfg, rs in results.items():
        if not (
            cfg.fission == "expected"
            and cfg.turnover
            and cfg.k_invention == 1.0
            and cfg.k_adoption == 1.0
        ):
            continue
        r = _merge(rs)
        for origin in ("invention", "adoption"):
            ls = [x for x in r.lineages if x.origin == origin]
            if not ls:
                continue

            def lagq(attr: str, qattr: str, ls: list[Lineage] = ls) -> str:
                xs = [
                    (getattr(x, attr) - x.year, getattr(x, qattr))
                    for x in ls
                    if getattr(x, attr) is not None
                ]
                if not xs:
                    return "-"
                lags, qv = np.array([a for a, _ in xs]), np.array([b for _, b in xs])
                return f"{np.median(lags):.0f} ({np.median(qv):.2f}/{np.quantile(qv, 0.1):.2f}) n={len(xs)}"

            sub = [x.q_substantial for x in ls if x.q_substantial is not None]
            a10 = [x.q_after10 for x in ls if x.q_after10 is not None]
            reach = " / ".join(
                f"{np.median([x.reach[t] for x in ls if t in x.reach]):.0f}"
                if any(t in x.reach for x in ls)
                else "-"
                for t in (0.5, 0.9, 0.99)
            )
            fb = [
                (x.first_binding - x.year, x.q_first_binding)
                for x in ls
                if x.first_binding is not None
            ]
            fbs = (
                f"{np.median([a for a, _ in fb]):.0f} ({np.median([b for _, b in fb]):.2f})"
                if fb
                else "-"
            )
            print(
                f"| {cfg.rate} | {origin} | {len(ls)} | {np.median([x.q0 for x in ls]):.3f} | {lagq('first_planned', 'q_planned')} | {lagq('first_farm', 'q_farm')} "
                f"| {f'{np.median(sub):.2f}/{np.quantile(sub, 0.1):.2f}' if sub else '-'} | {f'{np.median(a10):.2f}' if a10 else '-'} | {reach} | {fbs} |"
            )
    print(
        f"\nrepeat acquisition events on holders: {any_res.repeat_events}; knowledge lost with the technology: {any_res.knowledge_lost}"
    )


def replay_main(load: Path, jobs: int) -> None:
    histories = []
    for f in sorted(load.glob("*.pkl")):
        with f.open("rb") as fh:
            histories.append(pickle.load(fh))
    for name in SCENARIOS:
        hs = [h for h in histories if h["name"] == name]
        if not hs:
            continue
        print(
            f"\n##### {name}: seeds {[h['seed'] for h in hs]}; observer neutral: {all(h['neutral'] for h in hs)}; full horizon: {all(h['years'] >= h['horizon'] for h in hs)}"
        )
        ref = reference_q0(hs)
        q0 = 1.0 / ref[0]
        betas = {f"T50={t}y": calibrate_beta(q0, t) for t in HALF_YEARS}
        print(
            "calibration (one knower in the reference unit): "
            + ", ".join(f"{k}: beta {v:.3f}" for k, v in betas.items())
        )
        cfgs = configs(betas)
        results: dict[Config, list[Result]] = defaultdict(list)
        with Pool(jobs) as pool:
            for out in pool.imap_unordered(replay_job, [(h, cfgs) for h in hs]):
                for cfg, r in out:
                    results[cfg].append(r)
        ordered = {c: results[c] for c in cfgs}
        report_scenario(name, ordered, ref, betas)


# ---------------------------------------------------------------- controlled


def _hist(
    rows: dict[int, list[tuple[Any, ...]]], events: list[tuple[int, str, dict[str, Any]]]
) -> dict[str, Any]:
    return {"rows": rows, "events": events}


def _unit(uid: str, p: float, n: float = 40.0, tau: float = 0.03) -> tuple[Any, ...]:
    c = n * 0.5 * 1825.0  # half the people are labor-equivalents
    return (uid, p, c, 0.0, 0.9, n, c / 1825.0, tau)


def controlled() -> None:
    lab = 20.0
    q0 = 1.0 / lab
    print(
        f"Transmission q <- q + (1 - q)(1 - exp(-beta q)); reference: one knower among {lab:.0f} labor-equivalents (q0 = {q0:.3f})"
    )
    print(
        "| years to 50 % | beta | q after 1 / 2 / 5 / 10 / 20 / 40 y | years to 90 / 99 % | one knower in 80 labor-eq.: years to 50 % |"
    )
    print("|---|---|---|---|---|")
    for t in HALF_YEARS:
        b = calibrate_beta(q0, t)
        qv, traj = q0, []
        for year in range(1, 41):
            qv = transmit(qv, b)
            if year in (1, 2, 5, 10, 20, 40):
                traj.append(f"{qv:.2f}")
        print(
            f"| {t} | {b:.3f} | {' / '.join(traj)} | {years_to(q0, b, 0.9)} / {years_to(q0, b, 0.99)} | {years_to(1 / 80, b, 0.5)} |"
        )
    b5 = calibrate_beta(q0, 5)
    qv = 1.0
    eq = []
    for year in range(1, 201):
        qv = transmit(turnover(qv, 0.032), b5)
        if year in (10, 50, 200):
            eq.append(f"{qv:.3f}")
    print(
        f"T50 = 5 y with turnover 0.032/y from q = 1: q at 10 / 50 / 200 y = {' / '.join(eq)}; without transmission after 50 y: {(1 - 0.032) ** 50:.3f}"
    )

    def run(label: str, hist: dict[str, Any], cfg: Config) -> None:
        r = replay(hist, cfg)
        lin = r.lineages[0] if r.lineages else None
        fy, by = sum(r.farming.values()), sum(r.binding.values())
        extra = ""
        if lin is not None:
            extra = f"; q0 {lin.q0:.3f}, q at first cultivation {lin.q_farm if lin.q_farm is None else round(lin.q_farm, 3)}"
        print(
            f"  {label:<58} {cfg.label:<28} binding {by}/{fy} unit-years, hours short {sum(r.short.values()):.0f}{extra}"
        )

    def acquire(
        year: int, kind: str = "invention", uid: str = "u"
    ) -> tuple[int, str, dict[str, Any]]:
        return (year, kind, {"unit_id": uid, "technology": TECH, "population": 40})

    demand = 0.3 * 0.9 * 40 * 0.5 * 1825.0  # needs 30 % of labor
    slow, mid = calibrate_beta(q0, 20), calibrate_beta(q0, 5)
    print(
        "\nSynthetic histories (one unit of 40 people, 20 labor-equivalents; cultivation needs 30 % of labor)"
    )
    cases = [
        ("one knower, cultivation the next year", 1, 2, 10, 1.0),
        ("one knower in a larger unit (160 people)", 1, 2, 10, 4.0),
        ("cultivation starts after a ten-year delay", 1, 11, 20, 1.0),
        ("cultivation starts after complete spread (30 y)", 1, 31, 40, 1.0),
    ]
    for label, acq, start, end, scale in cases:
        rows = {
            y: [_unit("u", demand * scale if start <= y <= end else 0.0, 40 * scale)]
            for y in range(1, end + 1)
        }
        hist = _hist(rows, [acquire(acq), (start - 1, "cultivation_started", {"unit_id": "u"})])
        for cfg in (
            Config(beta=np.inf),
            Config(beta=mid, rate="T50=5y"),
            Config(beta=slow, rate="T50=20y"),
            Config(beta=0.0, rate="none"),
            Config(beta=mid, rate="T50=5y", turnover=False),
        ):
            run(label, hist, cfg)
    print("\nInheritance cases")
    rows = {y: [_unit("u", 0.0), _unit("d", 0.0)] for y in range(1, 6)}
    split = (
        2,
        "population_split",
        {"unit_id": "u", "daughter_id": "d", "source_population": 40, "moved_population": 15},
    )
    for cfg in (
        Config(beta=0.0, rate="none"),
        Config(beta=0.0, rate="none", fission="finite", seed=1),
        Config(beta=0.0, rate="none", fission="finite", seed=2),
    ):
        r = replay(_hist(rows, [acquire(1), split]), cfg)
        print(
            f"  fission with one knower: {cfg.label:<28} lineage q0 {r.lineages[0].q0:.3f}; knowerless holder unit-years {r.knowless_holder_years} of {r.holder_years}"
        )
    rows2 = {y: [_unit("a", 0.0), _unit("b", 0.0)] for y in range(1, 4)}
    merge = (
        2,
        "population_merge",
        {"unit_id": "b", "into_id": "a", "merged_population": 40, "resulting_population": 80},
    )
    r = replay(
        _hist(rows2, [acquire(1, uid="a"), merge]), Config(beta=0.0, rate="none", turnover=False)
    )
    print(
        f"  fusion of a knowing (q = {r.lineages[0].q0:.3f}) and an unknowing unit of equal size: fused knowing share {r.final['a']:.4f} (knowers conserved: {r.lineages[0].q0 * 40 / 80:.4f}); the authoritative union gives everyone the technique"
    )
    rows3 = {y: [_unit("u", demand if y >= 4 else 0.0)] for y in range(1, 8)}
    lost = (2, "technology_lost", {"unit_id": "u", "technology": TECH})
    r = replay(_hist(rows3, [acquire(1), lost, acquire(3)]), Config(beta=mid, rate="T50=5y"))
    print(
        f"  knowledge lost then reacquired by a genuine event: lineages {len(r.lineages)}, knowledge lost {r.knowledge_lost}, binding {sum(r.binding.values())} unit-years"
    )
    rows4 = {1: [_unit("u", 0.0)], 2: [_unit("u", 0.0)]}
    r = replay(
        _hist(rows4, [acquire(1), (2, "unit_extinct", {"unit_id": "u"})]),
        Config(beta=mid, rate="T50=5y"),
    )
    print(f"  unit disappears: holder unit-years {r.holder_years}, nothing carried forward")
    r = replay(_hist(rows3, [acquire(1), acquire(2)]), Config(beta=mid, rate="T50=5y"))
    print(
        f"  repeated acquisition event on a holder: lineages {len(r.lineages)}, repeat events {r.repeat_events} (q never lowered)"
    )


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("controlled", "record", "replay"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "replay":
        replay_main(args.load, args.jobs)
        return
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    specs = [(n, s) for n in SCENARIOS for s in args.seeds if not (out / f"{n}_{s}.pkl").exists()]
    started = time.perf_counter()
    with Pool(args.jobs) as pool:
        for h in pool.imap_unordered(record_job, specs, chunksize=1):
            warn = "" if h["years"] >= h["horizon"] else f"  WARNING: ended at year {h['years']}"
            print(
                f"done {h['name']} seed {h['seed']} after {time.perf_counter() - started:.0f} s; neutral {h['neutral']}{warn}",
                flush=True,
            )
            with (out / f"{h['name']}_{h['seed']}.pkl").open("wb") as fh:
                pickle.dump(h, fh)


if __name__ == "__main__":
    main()
