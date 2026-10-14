# The report tables keep one entry per line.
# ruff: noqa: E501
"""Fusion-born knowledge heterogeneity (MVP 3 Stage 5F): observation only. NOT ACTIVE.

Does fusion erase meaningful agricultural-knowledge differences by replacing two levels
with their population-weighted mean? A read-only recorder captures, for reference runs,
every fusion's pre-fusion state (both units' knowledge, population, fields, cultivation,
technology), each unit-year's agriculture level around the knowledge steps (before and
after learning, after diffusion and innovation) and the farming inputs. A shadow
distribution of agriculture knowledge (``population/fusion_competence.py``) is then
replayed over that same history under several retention, pooling and resolution settings;
nothing is re-simulated per setting and nothing feeds back (checked by digest against a
plain run).

Shadow year (pipeline order): farming (diagnostics with the current distribution) ->
demography (turnover pooling, sensitivity) -> learning (common slope ``1 - lam``, unit gain)
-> diffusion + innovation (common increment) -> fission (copy) -> fusion (concatenate) ->
pooling delay / resolution.

Modes:

``controlled``
    Deterministic synthetic histories for the Stage 5F cases.
``record``
    Reference scenarios (neolithic 600 y, pressure + cultivation 400 y; seeds 0-3).
``replay``
    Fusion-gap census, the shadow settings and the report.

Usage:
    uv run python scripts/probes/fusion_competence_counterfactual.py controlled
    uv run python scripts/probes/fusion_competence_counterfactual.py record [--jobs 2] [--seeds ...] --out DIR
    uv run python scripts/probes/fusion_competence_counterfactual.py replay --load DIR [--jobs 2]
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
from madexplorer.knowledge.learning import LearningSubsystem
from madexplorer.population.energetics import capability_column
from madexplorer.population.fusion_competence import (
    Metric,
    coalesce,
    compact_exact,
    efficiency,
    fuse,
    learn,
    pool,
    slope,
    summary,
    turnover_pool,
)
from madexplorer.population.groups import FissionSubsystem, Fusion

TECH = "plant_cultivation"
DOMAIN = "agriculture"
SCENARIOS = ("neolithic", "pressure+cult")
HORIZONS = (1, 5, 10, 25, 50)
E_THRESHOLDS = (0.005, 0.01, 0.02, 0.05, 0.1)
KEPT = {"population_split", "population_merge", "unit_extinct"}

# ---------------------------------------------------------------- recording


class Recorder:
    """Read-only hooks: farming inputs, the agriculture level around the knowledge steps,
    and the pre-/post-fusion state of every fusion."""

    def __init__(self) -> None:
        self.farm: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
        self.learn: dict[int, dict[str, tuple[float, float]]] = defaultdict(dict)
        self.end: dict[int, dict[str, float]] = defaultdict(dict)
        self.fusions: dict[tuple[int, str], dict[str, Any]] = {}
        self.domain = -1
        self.half = float("nan")
        self.decay = float("nan")
        self._saved: dict[str, Any] = {}
        self._ramp: dict[int, np.ndarray] = {}

    def install(self) -> None:
        rec = self
        farming0 = FarmingSubsystem.evaluate
        learning0 = LearningSubsystem.evaluate
        fission0 = FissionSubsystem.evaluate
        fusion0 = Fusion.apply

        def farming(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = farming0(sub, state, ctx)
            cols = ctx.columns(state)
            if len(cols) and proposals:
                model = ctx.knowledge
                if rec.domain < 0:
                    rec.domain = model.index[DOMAIN]
                    rec.half = float(model.half_efficiency[rec.domain])
                ids = ctx.compiled.species_ids
                if not rec._ramp:
                    for k, s in enumerate(ids):
                        rec._ramp[k] = np.maximum(np.diff(ctx.tables[s].labor, prepend=0.0), 0.0)
                labor = cols.weighted({k: ctx.tables[s].labor for k, s in enumerate(ids)})
                inflow = cols.weighted(rec._ramp)
                level = cols.knowledge()[:, rec.domain]
                cap = capability_column(cols, ctx, "crop_yield")
                fields = cols.get("fields_ha")
                pop = cols.population()
                hours, harvest = proposals[0].hours, proposals[0].harvest_kcal
                capacity = labor_hours_columns(cols, ctx)
                for k, u in enumerate(cols.units):
                    tau = float(inflow[k] / labor[k]) if labor[k] > 0 else 0.0
                    rec.farm[state.year].append(
                        (u.id, float(level[k]), float(hours[k]), float(harvest[k]),
                         float(fields[k]), bool(cap[k] > 0), float(pop[k]), min(tau, 1.0),
                         float(capacity[k]))
                    )  # fmt: skip
            return proposals

        def learning(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = learning0(sub, state, ctx)
            cols = ctx.columns(state)
            if proposals:
                d = sub.model.index[DOMAIN]
                species = {
                    s: ctx.species(s).cognition.knowledge_retention
                    for s in ctx.compiled.species_ids
                }
                rates = {sub.model.decay_rate[d] / r for r in species.values()}
                assert len(rates) == 1, "one species expected"
                rec.decay = float(rates.pop())
                before = cols.knowledge()[:, d]
                after = proposals[0].knowledge[:, d]
                row = rec.learn[state.year]
                for k, u in enumerate(cols.units):
                    row[u.id] = (float(before[k]), float(after[k]))
            return proposals

        def fission(sub: Any, state: Any, ctx: Any) -> Any:
            cols = ctx.columns(state)
            if len(cols) and rec.domain >= 0:
                level = cols.knowledge()[:, rec.domain]
                row = rec.end[state.year]
                for k, u in enumerate(cols.units):
                    row[u.id] = float(level[k])
            return fission0(sub, state, ctx)

        def fusion(prop: Any, state: Any, ctx: Any) -> None:
            def snap(u: Any) -> dict[str, Any]:
                return {
                    "id": u.id, "population": int(u.population), "knowledge": np.array(u.knowledge),
                    "fields": float(u.fields_ha), "farm_hours": float(u.farm_hours),
                    "farm_harvest": float(u.farm_harvest_kcal), "ever_cultivated": bool(u.ever_cultivated),
                    "tech": TECH in u.technologies, "founded": int(u.founded_year),
                    "parent": u.parent_id,
                }  # fmt: skip

            source, target = state.units[prop.source_id], state.units[prop.target_id]
            pre = {"source": snap(source), "target": snap(target)}
            fusion0(prop, state, ctx)
            pre["post_knowledge"] = np.array(state.units[prop.target_id].knowledge)
            rec.fusions[(state.year, prop.source_id)] = pre

        self._saved = {
            "farming": farming0,
            "learning": learning0,
            "fission": fission0,
            "fusion": fusion0,
        }
        FarmingSubsystem.evaluate = farming  # type: ignore[method-assign]
        LearningSubsystem.evaluate = learning  # type: ignore[method-assign]
        FissionSubsystem.evaluate = fission  # type: ignore[method-assign]
        Fusion.apply = fusion  # type: ignore[method-assign]

    def remove(self) -> None:
        FarmingSubsystem.evaluate = self._saved["farming"]  # type: ignore[method-assign]
        LearningSubsystem.evaluate = self._saved["learning"]  # type: ignore[method-assign]
        FissionSubsystem.evaluate = self._saved["fission"]  # type: ignore[method-assign]
        Fusion.apply = self._saved["fusion"]  # type: ignore[method-assign]


def _events(sim: Simulator) -> list[tuple[int, str, dict[str, Any]]]:
    return [(e.year, e.kind, dict(e.data)) for e in sim.events if e.kind in KEPT]


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
    domains = list(sim.knowledge.domains) if sim.knowledge else []
    return {
        "name": name, "seed": seed, "years": years, "horizon": horizon, "seconds": seconds,
        "farm": dict(rec.farm), "learn": dict(rec.learn), "end": dict(rec.end),
        "fusions": rec.fusions, "events": _events(sim), "domains": domains,
        "half": rec.half, "decay": rec.decay,
        "neutral": physical_digest(sim) == physical_digest(plain),
    }  # fmt: skip


# ---------------------------------------------------------------- fusion census


def _lineage(events: list[tuple[int, str, dict[str, Any]]]) -> dict[str, tuple[str, int]]:
    """daughter -> (parent, split year)."""
    return {e["daughter_id"]: (e["unit_id"], y) for y, k, e in events if k == "population_split"}


def divergence(a: str, b: str, year: int, parent: dict[str, tuple[str, int]]) -> int | None:
    """Years since the two units' ancestral lines separated by fission (None: unrelated
    founders). The separation is the earlier of the two splits off the common ancestor."""

    def path(u: str) -> list[tuple[str, int | None]]:
        out: list[tuple[str, int | None]] = []
        created: int | None = None
        while True:
            out.append((u, created))
            if u not in parent:
                return out
            p, created = parent[u][0], parent[u][1]
            out[-1] = (u, created)
            u = p

    pa, pb = path(a), path(b)
    index_b = {u: j for j, (u, _) in enumerate(pb)}
    for i, (u, _) in enumerate(pa):
        j = index_b.get(u)
        if j is None:
            continue
        splits = [pa[i - 1][1] if i > 0 else None, pb[j - 1][1] if j > 0 else None]
        known = [s for s in splits if s is not None]
        return year - min(known) if known else 0
    return None


def census(history: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per fusion: pre-fusion agriculture levels and efficiencies, weights, the
    variance averaging removes, the static Jensen gap and the fusion's context."""
    d = history["domains"].index(DOMAIN)
    half = history["half"]
    parent = _lineage(history["events"])
    farming = {(y, r[0]) for y, rows in history["farm"].items() for r in rows if r[2] > 0 and r[5]}
    rows = []
    for y, kind, e in history["events"]:
        if kind != "population_merge":
            continue
        rec = history["fusions"][(y, e["unit_id"])]
        s, t = rec["source"], rec["target"]
        ns, nt = s["population"], t["population"]
        ks, kt = float(s["knowledge"][d]), float(t["knowledge"][d])
        ws, wt = ns / (ns + nt), nt / (ns + nt)
        es, et = float(efficiency(ks, half)), float(efficiency(kt, half))
        kbar = wt * kt + ws * ks
        expected = (t["knowledge"] * nt + s["knowledge"] * ns) / (nt + ns)
        div = divergence(s["id"], t["id"], y, parent)
        other = {
            dom: abs(float(s["knowledge"][i]) - float(t["knowledge"][i]))
            for i, dom in enumerate(history["domains"])
        }
        rows.append({
            "year": y, "source": s["id"], "target": t["id"], "ns": ns, "nt": nt,
            "ks": ks, "kt": kt, "es": es, "et": et, "w_minor": min(ws, wt),
            "dk": abs(ks - kt), "de": abs(es - et),
            "wsd_k": (ws * wt) ** 0.5 * abs(ks - kt), "wsd_e": (ws * wt) ** 0.5 * abs(es - et),
            "var_removed": ws * wt * (ks - kt) ** 2, "kbar": kbar,
            "jensen": float(efficiency(kbar, half)) - (wt * et + ws * es),
            "slope_pred": abs(ks - kt) * float(slope(kbar, half)),
            "exact": bool(np.array_equal(expected, rec["post_knowledge"])),
            "post_err": abs(float(rec["post_knowledge"][d]) - kbar),
            "cult": int(s["farm_hours"] > 0) + int(t["farm_hours"] > 0),
            "tech": int(s["tech"]) + int(t["tech"]),
            "divergence": div,
            "farm_after": any((y + h, t["id"]) in farming for h in range(1, 11)),
            "other_dk": other,
        })  # fmt: skip
    return rows


# ---------------------------------------------------------------- shadow replay


@dataclass(frozen=True)
class Config:
    delay: int | None = (
        None  # None: retain; 0: immediate pooling (authoritative); D: pool after D years
    )
    turnover: bool = False  # new workers learn the unit mean
    capacity: int | None = None  # None: unlimited (exact compaction only)
    metric: Metric = "slope"
    detail: bool = False  # keep per farming unit-year E_separate (resolution comparison)

    @property
    def label(self) -> str:
        base = {None: "retain", 0: "pool at fusion (A)"}.get(
            self.delay, f"pool after {self.delay} y"
        )
        if self.turnover:
            base += " + turnover"
        if self.capacity is not None:
            base += f" cap {self.capacity} {self.metric}"
        return base


@dataclass
class Tracer:
    """The two incoming groups of one fusion, followed in the target under common updates."""

    unit: str
    year: int
    gap0: float
    de0: float
    ka: float
    kb: float
    alive: bool = True
    later_fusion: bool = False
    pooled: int | None = None
    halved: int | None = None
    negligible: dict[float, int] = field(default_factory=dict)
    at: dict[int, tuple[float, float, float, float, bool]] = field(default_factory=dict)
    cult_years: int = 0  # farming years (age 1-50) while the pair efficiency gap >= 0.01


@dataclass
class Result:
    unit_years: int = 0
    het_unit_years: int = 0
    farm_years: int = 0
    het_farm_years: int = 0
    harvest: float = 0.0
    harvest_rel_jensen: float = 0.0  # sum harvest * (E_pooled / E_separate - 1)
    hours: float = 0.0
    rel_jensen: list[float] = field(default_factory=list)  # heterogeneous farming unit-years
    e_sd: list[float] = field(default_factory=list)
    e_range: list[float] = field(default_factory=list)
    components: list[int] = field(default_factory=list)  # heterogeneous unit-years
    max_components: int = 1
    exact_merges: int = 0
    coalescences: int = 0
    mean_err: float = 0.0
    fusion_err: float = 0.0
    tracers: list[Tracer] = field(default_factory=list)
    detail: dict[tuple[Any, ...], float] = field(default_factory=dict)


def replay(history: dict[str, Any], cfg: Config) -> Result:
    """Replay the shadow over one recorded run. Only heterogeneous units hold components;
    every other unit is a single component at its authoritative level."""
    d = history["domains"].index(DOMAIN)
    half, lam = history["half"], history["decay"]
    res = Result()
    comps: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    tag: dict[str, int] = {}
    tracers: dict[str, list[Tracer]] = defaultdict(list)
    by_year: dict[int, list[tuple[int, str, dict[str, Any]]]] = defaultdict(list)
    for ev in history["events"]:
        by_year[ev[0]].append(ev)
    years = sorted(set(history["farm"]) | set(by_year))

    def retire(t: Tracer) -> None:
        t.alive = False

    for year in years:
        rows = history["farm"].get(year, [])
        taus: dict[str, float] = {}
        # 1. farming: diagnostics with the current distribution
        for uid, level, hours, harvest, _fields, cap, _pop, tau, _c in rows:
            taus[uid] = tau
            res.unit_years += 1
            farming = hours > 0 and cap
            het = uid in comps
            if farming:
                res.farm_years += 1
                res.harvest += harvest
                res.hours += hours
            if het:
                w, k = comps[uid]
                s = summary(w, k, half)
                res.mean_err = max(res.mean_err, abs(s["mean"] - level) / max(level, 1.0))
                res.het_unit_years += 1
                res.components.append(k.size)
                if farming and s["e_separate"] > 0:
                    rel = s["e_pooled"] / s["e_separate"] - 1.0
                    res.het_farm_years += 1
                    res.harvest_rel_jensen += harvest * rel
                    res.rel_jensen.append(rel)
                    res.e_sd.append(s["e_sd"])
                    res.e_range.append(s["e_range"])
                    if cfg.detail:
                        res.detail[(year, uid)] = s["e_separate"]
            elif farming and cfg.detail:
                res.detail[(year, uid)] = float(efficiency(level, half))
            for t in tracers.get(uid, ()):
                age = year - t.year
                gap = abs(t.ka - t.kb)
                de = abs(float(efficiency(t.ka, half)) - float(efficiency(t.kb, half)))
                if t.halved is None and gap <= t.gap0 / 2:
                    t.halved = age
                for eps in E_THRESHOLDS:
                    if eps not in t.negligible and de < eps:
                        t.negligible[eps] = age
                if farming and de >= 0.01:
                    t.cult_years += 1
                if age in HORIZONS:
                    sd = jen = 0.0
                    if het:
                        s = summary(*comps[uid], half)
                        sd, jen = s["sd"], s["jensen"]
                    t.at[age] = (gap, de, sd, jen, bool(farming))
        for uid in list(tracers):
            live = [t for t in tracers[uid] if year - t.year < max(HORIZONS)]
            for t in tracers[uid]:
                if year - t.year >= max(HORIZONS):
                    retire(t)
            tracers[uid] = live
        # 2. demography: new workers learn the unit mean (sensitivity)
        if cfg.turnover:
            for uid, (w, k) in comps.items():
                tau = taus.get(uid, 0.0)
                m = float(np.dot(w, k))
                comps[uid] = (w, turnover_pool(w, k, tau))
                for t in tracers.get(uid, ()):
                    t.ka, t.kb = (1 - tau) * t.ka + tau * m, (1 - tau) * t.kb + tau * m
        # 3. learning (common slope) and 4. diffusion + innovation (common increment)
        learned = history["learn"].get(year, {})
        end = history["end"].get(year, {})
        for uid in set(comps) | set(tracers):
            if uid not in learned:
                continue
            before, after = learned[uid]
            gain = max(after - (1.0 - lam) * before, 0.0)
            extra = end.get(uid, after) - after
            if uid in comps:
                w, k = comps[uid]
                comps[uid] = (w, learn(k, lam, gain) + extra)
            for t in tracers.get(uid, ()):
                t.ka = (1.0 - lam) * t.ka + gain + extra
                t.kb = (1.0 - lam) * t.kb + gain + extra
        # 5. fission, fusion, extinction in event order
        for _, kind, e in by_year.get(year, ()):
            if kind == "population_split":
                p, dau = e["unit_id"], e["daughter_id"]
                if p in comps:
                    w, k = comps[p]
                    comps[dau] = (w.copy(), k.copy())
                    tag[dau] = tag[p]
            elif kind == "unit_extinct":
                comps.pop(e["unit_id"], None)
                for t in tracers.pop(e["unit_id"], []):
                    retire(t)
            elif kind == "population_merge":
                src, tgt = e["unit_id"], e["into_id"]
                rec = history["fusions"][(year, src)]
                parts = []
                levels = {}
                for role, uid in (("target", tgt), ("source", src)):
                    pre = float(rec[role]["knowledge"][d])
                    levels[role] = pre
                    w, k = comps.pop(uid, (np.ones(1), np.array([pre])))
                    res.fusion_err = max(
                        res.fusion_err, abs(float(np.dot(w, k)) - pre) / max(pre, 1.0)
                    )
                    parts.append((w, k, float(rec[role]["population"])))
                w, k = fuse(parts)
                post = float(rec["post_knowledge"][d])
                res.fusion_err = max(
                    res.fusion_err, abs(float(np.dot(w, k)) - post) / max(post, 1.0)
                )
                moved = tracers.pop(src, [])
                for t in tracers.get(tgt, []) + moved:
                    t.later_fusion = True
                tracers[tgt] = tracers.get(tgt, []) + moved
                if cfg.delay == 0:
                    w, k = pool(w, k)
                else:
                    n0 = k.size
                    w, k = compact_exact(w, k)
                    res.exact_merges += n0 - k.size
                    if cfg.capacity is not None and k.size > cfg.capacity:
                        res.coalescences += k.size - cfg.capacity
                        w, k = coalesce(w, k, cfg.capacity, half, cfg.metric)
                    gap = abs(levels["target"] - levels["source"])
                    if gap > 0:
                        de = abs(
                            float(efficiency(levels["target"], half))
                            - float(efficiency(levels["source"], half))
                        )
                        tracers[tgt].append(
                            Tracer(tgt, year, gap, de, levels["target"], levels["source"])
                        )
                        res.tracers.append(tracers[tgt][-1])
                if k.size > 1:
                    comps[tgt] = (w, k)
                    tag[tgt] = year
                    res.max_components = max(res.max_components, k.size)
                tag.pop(src, None)
        # 6. delayed pooling
        if cfg.delay:
            for uid in [u for u in comps if year - tag[u] >= cfg.delay]:
                w, k = comps.pop(uid)
                m = float(np.dot(w, k))
                for t in tracers.get(uid, ()):
                    if t.pooled is None:
                        t.pooled = year - t.year
                    t.ka = t.kb = m
    return res


CONFIGS = (
    Config(delay=0),
    Config(detail=True),
    Config(turnover=True),
    *(Config(delay=dd) for dd in (1, 2, 5, 10, 25)),
    *(Config(capacity=c, metric=m, detail=True) for c in (16, 32) for m in ("k", "slope", "e")),
    Config(capacity=4, metric="k", detail=True),
    Config(capacity=4, metric="slope", detail=True),
)  # fmt: skip


def replay_job(history: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    out = {cfg: replay(history, cfg) for cfg in CONFIGS}
    rows = census(history)
    # Ordinary variation of agriculture efficiency among farming units (authoritative).
    half = history["half"]
    spread, step = [], []
    last: dict[str, float] = {}
    for year in sorted(history["farm"]):
        es = []
        now: dict[str, float] = {}
        for uid, level, hours, _h, _f, cap, *_ in history["farm"][year]:
            if hours > 0 and cap:
                e = float(efficiency(level, half))
                es.append(e)
                now[uid] = e
                if uid in last:
                    step.append(abs(e - last[uid]))
        if len(es) >= 2:
            spread.append(float(np.std(es)))
        last = now
    return {
        "name": history["name"], "seed": history["seed"], "results": out, "census": rows,
        "spread": spread, "step": step, "seconds": time.perf_counter() - started,
        "neutral": history["neutral"],
    }  # fmt: skip


# ---------------------------------------------------------------- report


def _frac(x: float, n: float) -> str:
    return f"{x / n:.4f}" if n else "-"


def _merge(results: list[Result]) -> Result:
    total = Result()
    for i, r in enumerate(results):
        total.detail.update({(i, *key): v for key, v in r.detail.items()})
        for name in ("unit_years", "het_unit_years", "farm_years", "het_farm_years", "harvest",
                     "harvest_rel_jensen", "hours", "exact_merges", "coalescences"):  # fmt: skip
            setattr(total, name, getattr(total, name) + getattr(r, name))
        for name in ("rel_jensen", "e_sd", "e_range", "components", "tracers"):
            getattr(total, name).extend(getattr(r, name))
        total.max_components = max(total.max_components, r.max_components)
        total.mean_err = max(total.mean_err, r.mean_err)
        total.fusion_err = max(total.fusion_err, r.fusion_err)
    return total


def report_census(rows: list[dict[str, Any]]) -> None:
    n = len(rows)
    a = {k: np.array([r[k] for r in rows], dtype=float) for k in
         ("dk", "de", "wsd_k", "wsd_e", "w_minor", "jensen", "var_removed", "kbar", "slope_pred")}  # fmt: skip
    print(
        f"  fusions {n}; formula bit-exact {sum(r['exact'] for r in rows)}; max |post - mean| {max(r['post_err'] for r in rows):.2e}"
    )
    print(
        f"  people in the smaller unit: total {sum(min(r['ns'], r['nt']) for r in rows)}; minority weight p50/p90 {np.quantile(a['w_minor'], 0.5):.3f}/{np.quantile(a['w_minor'], 0.9):.3f}"
    )
    print(f"  identical levels (dK = 0): {_frac(float((a['dk'] == 0).sum()), n)}")
    print(f"  dK p50/p90/p99/max      {q(a['dk'])}")
    print(f"  dE p50/p90/p99/max      {q(a['de'])}")
    print(f"  weighted sd(K) = sqrt(wAwB) dK    {q(a['wsd_k'])}")
    print(f"  weighted sd(E) = sqrt(wAwB) dE    {q(a['wsd_e'])}")
    print(
        f"  Jensen gap at fusion    {q(a['jensen'])}; relative to E(mean) {q(a['jensen'] / np.maximum(efficiency(a['kbar'], 2.0), 1e-12))}"
    )
    print(f"  K variance removed      {q(a['var_removed'])}")
    print("  share of fusions above a threshold (dE / weighted sd(E)):")
    for eps in E_THRESHOLDS:
        print(
            f"    {eps:<6} {_frac(float((a['de'] >= eps).sum()), n)} / {_frac(float((a['wsd_e'] >= eps).sum()), n)}"
        )
    # slope-weighted predictor of the efficiency gap
    nz = a["de"] > 0
    ratio = a["slope_pred"][nz] / a["de"][nz]
    rho_k = _spearman(a["dk"][nz], a["de"][nz])
    rho_s = _spearman(a["slope_pred"][nz], a["de"][nz])
    print(
        f"  slope-weighted |dK|E'(mean) / |dE|: {q(ratio, (0.1, 0.5, 0.9))}; Spearman with dE: plain dK {rho_k:.3f}, slope-weighted {rho_s:.3f}"
    )
    top = a["de"] >= np.quantile(a["de"], 0.9)
    print(
        f"  top-decile dE fusions that are top-decile dK: {float((top & (a['dk'] >= np.quantile(a['dk'], 0.9))).sum() / max(top.sum(), 1)):.2f}"
    )
    # contexts
    print(
        "  context                          n      share  dE p50/p90/p99/max          share dE>=0.01  weighted sd(E)>=0.01"
    )
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[f"cultivating: {('neither', 'one', 'both')[r['cult']]}"].append(r)
        groups[f"plant_cultivation: {('neither', 'one', 'both')[r['tech']]}"].append(r)
        mw = r["w_minor"]
        groups[
            "minority < 0.1"
            if mw < 0.1
            else "minority 0.1-0.25"
            if mw < 0.25
            else "minority 0.25-0.5"
        ].append(r)
        dv = r["divergence"]
        groups["kin, split this year" if dv == 0 else "kin, split 1-10 y ago" if dv is not None and dv <= 10
               else "kin, split > 10 y ago" if dv is not None else "unrelated founders"].append(r)  # fmt: skip
        groups[f"target farms within 10 y: {r['farm_after']}"].append(r)
    for key in sorted(groups):
        g = groups[key]
        de = np.array([r["de"] for r in g])
        ws = np.array([r["wsd_e"] for r in g])
        print(
            f"  {key:<32} {len(g):<6} {len(g) / n:.3f}  {q(de):<27} {float((de >= 0.01).mean()):.3f}           {float((ws >= 0.01).mean()):.3f}"
        )
    other = defaultdict(list)
    for r in rows:
        for dom, v in r["other_dk"].items():
            other[dom].append(v)
    print(
        "  other domains, dK p50/p90/p99/max: "
        + "; ".join(f"{dom} {q(v)}" for dom, v in other.items())
    )


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 3:
        return float("nan")
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def report_shadow(results: dict[Config, Result]) -> None:
    print(
        "  setting                    het unit-yrs  het farm-yrs  harvest-wtd E_pool/E_sep-1  rel gap p50/p90/p99/max (het farming)   E sd p50/p90   comps p50/p99/max"
    )
    for cfg, r in results.items():
        if cfg.capacity is not None:
            continue
        hw = r.harvest_rel_jensen / r.harvest if r.harvest else 0.0
        esd = q(r.e_sd, (0.5, 0.9)) if r.e_sd else "-"
        comps = q(r.components, (0.5, 0.99)) if r.components else "-"
        print(
            f"  {cfg.label:<26} {_frac(r.het_unit_years, r.unit_years):<13} {_frac(r.het_farm_years, r.farm_years):<13} {hw:<27.2e} {q(r.rel_jensen) if r.rel_jensen else '-':<40} {esd:<14} {comps}"
        )
    base = next(r for c, r in results.items() if c == Config(detail=True))
    rel = np.array(base.rel_jensen) if base.rel_jensen else np.zeros(1)
    print("  retain: share of farming unit-years with relative gap >= x: "
          + ", ".join(f"{x:g} {float((rel >= x).sum()) / max(base.farm_years, 1):.5f}" for x in (1e-4, 1e-3, 0.01, 0.05)))  # fmt: skip
    print(
        f"  shadow mean vs authoritative: max relative error at farming {base.mean_err:.1e}, at fusion {base.fusion_err:.1e}"
    )


def report_persistence(results: dict[Config, Result]) -> None:
    for cfg in (Config(detail=True), Config(turnover=True), Config(delay=5)):
        tr = results[cfg].tracers
        for eps_label, sel in (("all dK > 0", [t for t in tr]),
                               ("dE0 >= 0.01", [t for t in tr if t.de0 >= 0.01]),
                               ("dE0 >= 0.05", [t for t in tr if t.de0 >= 0.05])):  # fmt: skip
            if not sel:
                continue
            line = f"  {cfg.label:<20} {eps_label:<12} n {len(sel):<6}"
            for h in HORIZONS:
                obs = [t for t in sel if h in t.at]
                if not obs:
                    line += f" | {h}y -"
                    continue
                ratio = np.array([t.at[h][0] / t.gap0 for t in obs])
                de = np.array([t.at[h][1] for t in obs])
                line += f" | {h}y n{len(obs)} gap/gap0 {np.median(ratio):.2f} dE>=.01 {float((de >= 0.01).mean()):.2f}"
            halved = [t.halved for t in sel if t.halved is not None]
            line += f" | halved by 50y {len(halved) / len(sel):.2f} (p50 {np.median(halved) if halved else float('nan'):.0f} y)"
            neg = [t.negligible.get(0.01) for t in sel]
            hit = [x for x in neg if x is not None]
            line += f" | dE<0.01 reached {len(hit) / len(sel):.2f} (p50 {np.median(hit) if hit else float('nan'):.0f} y)"
            print(line)
    tr = results[Config(detail=True)].tracers
    sel = [t for t in tr if t.de0 >= 0.01]
    if sel:
        cens = sum(not t.alive and len(t.at) < len(HORIZONS) for t in sel)
        print(f"  retain, dE0 >= 0.01: later fusion into the same unit {np.mean([t.later_fusion for t in sel]):.2f}; "
              f"farming years with pair dE >= 0.01 within 50 y: p50 {np.median([t.cult_years for t in sel]):.0f}, "
              f"mean {np.mean([t.cult_years for t in sel]):.1f}, zero {np.mean([t.cult_years == 0 for t in sel]):.2f}; censored before 50 y {cens / len(sel):.2f}")  # fmt: skip
        sd = {h: [t.at[h][2] for t in sel if h in t.at] for h in HORIZONS}
        print(
            "  retain, dE0 >= 0.01: unit sd(K) p50 at horizon "
            + ", ".join(f"{h}y {np.median(v):.3f}" for h, v in sd.items() if v)
        )
    print("  delayed pooling (D): harvest-weighted E_pool/E_sep-1 and het farming unit-years")
    for cfg, r in results.items():
        if cfg.capacity is None and not cfg.turnover:
            hw = r.harvest_rel_jensen / r.harvest if r.harvest else 0.0
            print(f"    {cfg.label:<22} {hw:.2e}  {_frac(r.het_farm_years, r.farm_years)}")


def report_resolution(results: dict[Config, Result]) -> None:
    ref = results[Config(detail=True)]
    print(
        f"  unlimited: max components {ref.max_components}; components p50/p99/max over het unit-years {q(ref.components, (0.5, 0.99)) if ref.components else '-'}; exact merges {ref.exact_merges}"
    )
    for cfg, r in results.items():
        if cfg.capacity is None:
            continue
        err = [abs(r.detail[k] - v) for k, v in ref.detail.items() if k in r.detail]
        reached = float(np.mean([c >= cfg.capacity for c in r.components])) if r.components else 0.0
        hw_ref = ref.harvest_rel_jensen / ref.harvest if ref.harvest else 0.0
        hw = r.harvest_rel_jensen / r.harvest if r.harvest else 0.0
        print(
            f"  {cfg.label:<26} at capacity {reached:.4f} of het unit-yrs; coalescences {r.coalescences}; |E_sep - ref| p99/max {np.quantile(err, 0.99) if err else 0:.1e}/{max(err) if err else 0:.1e}; harvest-wtd gap {hw:.3e} vs {hw_ref:.3e}"
        )


def replay_main(load: Path, jobs: int) -> None:
    histories = []
    for path in sorted(load.glob("*.pkl")):
        with path.open("rb") as fh:
            histories.append(pickle.load(fh))
    started = time.perf_counter()
    with Pool(jobs) as workers:
        outs = list(workers.imap(replay_job, histories, chunksize=1))
    print(
        f"replayed {len(outs)} histories x {len(CONFIGS)} settings in {time.perf_counter() - started:.0f} s; all neutral {all(o['neutral'] for o in outs)}"
    )
    for name in SCENARIOS:
        group = [o for o in outs if o["name"] == name]
        if not group:
            continue
        print(f"\n=== {name} (seeds {sorted(o['seed'] for o in group)})")
        print("\n-- fusion census (agriculture)")
        report_census([r for o in group for r in o["census"]])
        merged = {cfg: _merge([o["results"][cfg] for o in group]) for cfg in CONFIGS}
        print("\n-- static relevance and sharing sensitivity (farming unit-years)")
        report_shadow(merged)
        print(
            "\n-- persistence of fusion-born gaps (pair tracers; age = years after fusion at the farming check)"
        )
        report_persistence(merged)
        print("\n-- resolution (capacity and merge metric vs unlimited retention)")
        report_resolution(merged)
        spread = [x for o in group for x in o["spread"]]
        step = [x for o in group for x in o["step"]]
        print("\n-- ordinary variation (authoritative)")
        print(
            f"  across farming units, per-year sd of E: p50/p90 {q(spread, (0.5, 0.9))}; year-to-year |dE| of a farming unit: {q(step)}"
        )


# ---------------------------------------------------------------- controlled cases

HALF, LAM = 2.0, 0.02  # technologies/neolithic.yaml agriculture; human knowledge_retention 1


def _gain(k_star: float) -> float:
    """The unit gain whose fixed point is ``k_star`` (``K* = g / lam``)."""
    return LAM * k_star


def _trajectory(
    w: np.ndarray, k: np.ndarray, gains: list[float], tau: float = 0.0
) -> list[dict[str, float]]:
    out = [summary(w, k, HALF)]
    for g in gains:
        if tau:
            k = turnover_pool(w, k, tau)
        k = learn(k, LAM, g)
        out.append(summary(w, k, HALF))
    return out


def _synthetic(
    fusions: list[tuple[int, str, str, int, int]],
    levels: dict[str, list[float]],
    splits: list[tuple[int, str, str]],
    years: int,
    gain: float,
) -> dict[str, Any]:
    """A recorded-history stand-in: units learn with a common gain; scripted fissions and
    fusions (year, source, target, n_source, n_target) at the recorded authoritative mean."""
    hist: dict[str, Any] = {"farm": {}, "learn": {}, "end": {}, "fusions": {}, "events": [],
                            "domains": [DOMAIN], "half": HALF, "decay": LAM, "name": "synthetic"}  # fmt: skip
    k = {u: v[0] for u, v in levels.items()}
    for y in range(years):
        hist["farm"][y] = [(u, k[u], 100.0, 1000.0, 1.0, True, 30.0, 0.03, 1e4) for u in k]
        hist["learn"][y] = {u: (k[u], (1 - LAM) * k[u] + gain) for u in k}
        k = {u: (1 - LAM) * v + gain for u, v in k.items()}
        hist["end"][y] = dict(k)
        for ys, p, dau in splits:
            if ys == y:
                k[dau] = k[p]
                hist["events"].append((y, "population_split", {"unit_id": p, "daughter_id": dau}))
        for yf, s, t, ns, nt in fusions:
            if yf == y:
                post = (k[t] * nt + k[s] * ns) / (nt + ns)
                hist["fusions"][(y, s)] = {
                    "source": {"knowledge": np.array([k[s]]), "population": ns},
                    "target": {"knowledge": np.array([k[t]]), "population": nt},
                    "post_knowledge": np.array([post]),
                }
                hist["events"].append((y, "population_merge", {"unit_id": s, "into_id": t}))
                k[t] = post
                del k[s]
    return hist


def controlled() -> None:
    half_life = np.log(0.5) / np.log(1 - LAM)
    print(f"agriculture: E = K/(K+{HALF:g}); decay lam = {LAM}; deviation half-life ln2/-ln(1-lam) = {half_life:.1f} y; "
          f"after 50 y {(1 - LAM) ** 50:.3f} of the gap remains")  # fmt: skip
    print(
        f"with pooled teaching of new workers (tau = 0.032): half-life {np.log(0.5) / np.log((1 - LAM) * (1 - 0.032)):.1f} y"
    )

    def show(label: str, w: list[float], k: list[float]) -> None:
        wa, ka = np.array(w), np.array(k)
        wc, kc = compact_exact(wa, ka)
        s = summary(wc, kc, HALF)
        print(f"{label:<44} comps {kc.size}  mean {s['mean']:.3f}  E_pool {s['e_pooled']:.4f}  E_sep {s['e_separate']:.4f}  "
              f"Jensen {s['jensen']:.2e}  E_pool/E_sep-1 {s['e_pooled'] / s['e_separate'] - 1 if s['e_separate'] else 0:.2e}")  # fmt: skip

    print("\nstatic cases (fusion, before any later year)")
    show("1. equal K (3, 3)", [0.5, 0.5], [3.0, 3.0])
    show("2/3. very different K, equal sizes (0.4, 9)", [0.5, 0.5], [0.4, 9.0])
    show("4. large absorbs small (95 % at 9, 5 % at 0.4)", [0.95, 0.05], [9.0, 0.4])
    show("5. cultivator 6 + forager 0.4, equal", [0.5, 0.5], [6.0, 0.4])
    show("6. different K, same technology (2.2, 4)", [0.5, 0.5], [2.2, 4.0])
    show("7. both without competence (0, 0)", [0.5, 0.5], [0.0, 0.0])
    w8, k8 = fuse([(*fuse([(np.ones(1), np.array([1.0]), 20), (np.ones(1), np.array([5.0]), 10)]), 30),
                   (np.ones(1), np.array([9.0]), 15)])  # fmt: skip
    show("8. repeated fusion (1 x20, 5 x10, then 9 x15)", list(w8), list(k8))
    print(
        f"   mean {np.dot(w8, k8):.6f} vs authoritative two-step mean {((1 * 20 + 5 * 10) / 30 * 30 + 9 * 15) / 45:.6f}"
    )
    w8r, k8r = fuse([(np.ones(1), np.array([9.0]), 15),
                     (*fuse([(np.ones(1), np.array([5.0]), 10), (np.ones(1), np.array([1.0]), 20)]), 30)])  # fmt: skip
    a, b = summary(*compact_exact(w8, k8), HALF), summary(*compact_exact(w8r, k8r), HALF)
    print(
        f"   input-order invariance: |dE_sep| {abs(a['e_separate'] - b['e_separate']):.1e}, |dmean| {abs(a['mean'] - b['mean']):.1e}"
    )

    print(
        "\ntrajectories after an equal-size fusion of K = 0.4 and K = 9 (gap, E gap, Jensen at years 0/5/10/25/50)"
    )

    def traj(
        label: str, gains: list[float], tau: float = 0.0, k0: tuple[float, float] = (0.4, 9.0)
    ) -> None:
        t = _trajectory(np.array([0.5, 0.5]), np.array(k0), gains, tau)
        cells = " | ".join(
            f"{y}: {t[y]['range']:.2f} {t[y]['e_range']:.3f} {t[y]['jensen']:.1e}"
            for y in (0, 5, 10, 25, 50)
        )
        print(f"{label:<44} {cells}")

    traj("10. no cultivation afterwards (gain 0)", [0.0] * 50)
    traj("11. identical ongoing practice (K* = 9)", [_gain(9.0)] * 50)
    traj("11b. identical ongoing practice (K* = 20)", [_gain(20.0)] * 50)
    traj("12. practice 10 y, then cessation", [_gain(9.0)] * 10 + [0.0] * 40)
    traj("15. turnover pooling tau 0.032, K* = 9", [_gain(9.0)] * 50, tau=0.032)
    traj("16. long-term decay, forager-level (0.2, 0.6)", [_gain(0.4)] * 50, k0=(0.2, 0.6))

    print(
        "\n9/13/14. replayed synthetic history (u1 = 0.4 x20, u2 = 9 x20 fuse at year 2; u2 splits at year 5; u3 joins u2 at year 8)"
    )
    hist = _synthetic([(2, "u1", "u2", 20, 20), (8, "u3", "u2", 10, 25)], {"u1": [0.4], "u2": [9.0], "u3": [3.0]},
                      [(5, "u2", "u4")], 40, _gain(9.0))  # fmt: skip
    for cfg in (
        Config(delay=0),
        Config(),
        Config(delay=5),
        Config(turnover=True),
        Config(capacity=2, metric="slope"),
    ):
        r = replay(hist, cfg)
        print(f"   {cfg.label:<24} het unit-years {r.het_unit_years:<4} max comps {r.max_components}  rel gap p50/max "
              f"{q(r.rel_jensen, (0.5,)) if r.rel_jensen else '-'}  mean err {r.mean_err:.1e} fusion err {r.fusion_err:.1e}")  # fmt: skip
    homog = replay(_synthetic([], {"u1": [0.4], "u2": [9.0]}, [], 30, _gain(9.0)), Config())
    print(
        f"   homogeneous history: het unit-years {homog.het_unit_years}, harvest-weighted gap {homog.harvest_rel_jensen}"
    )

    print(
        "\n17. nonlinear averaging: Jensen >= 0 on 10,000 random distributions; second-order approximation"
    )
    rng = np.random.default_rng(5)
    worst, approx = np.inf, []
    for _ in range(10_000):
        n = int(rng.integers(2, 6))
        w = rng.dirichlet(np.ones(n))
        k = rng.exponential(4.0, n)
        j = summary(w, k, HALF)["jensen"]
        worst = min(worst, j)
        m = float(np.dot(w, k))
        approx.append(
            HALF / (m + HALF) ** 3 * float(np.dot(w, (k - m) ** 2)) / j if j > 1e-12 else 1.0
        )
    print(
        f"   min Jensen {worst:.2e}; (h/(m+h)^3 Var) / Jensen p10/p50/p90 {np.quantile(approx, [0.1, 0.5, 0.9]).round(3)}"
    )

    print(
        "\n18. capacity: 40 random components (K ~ Exp(4)) to capacity 16 / 4 by metric; E_sep error vs exact"
    )
    errs: dict[tuple[int, str], list[float]] = defaultdict(list)
    for _ in range(200):
        w = rng.dirichlet(np.ones(40))
        k = rng.exponential(4.0, 40)
        exact = summary(w, k, HALF)["e_separate"]
        for cap in (16, 4):
            for metric in ("k", "slope", "e"):
                wc, kc = coalesce(w, k, cap, HALF, metric)  # type: ignore[arg-type]
                errs[(cap, metric)].append(abs(summary(wc, kc, HALF)["e_separate"] - exact))
    for key, v in errs.items():
        print(f"   capacity {key[0]:<3} {key[1]:<6} |E_sep error| p50/p90/max {q(v, (0.5, 0.9))}")


# ---------------------------------------------------------------- entry point


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
    with Pool(args.jobs) as workers:
        for h in workers.imap_unordered(record_job, specs, chunksize=1):
            warn = "" if h["years"] >= h["horizon"] else f"  WARNING: ended at year {h['years']}"
            print(
                f"done {h['name']} seed {h['seed']} after {time.perf_counter() - started:.0f} s; "
                f"fusions {len(h['fusions'])}; neutral {h['neutral']}{warn}",
                flush=True,
            )
            with (out / f"{h['name']}_{h['seed']}.pkl").open("wb") as fh:
                pickle.dump(h, fh)


if __name__ == "__main__":
    main()
