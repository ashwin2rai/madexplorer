# The report tables keep one entry per line.
# ruff: noqa: E501
"""Participation overhead and practice concentration (MVP 3 Stage 5B): observation only.
NOT ACTIVE.

Shadow per-component agriculture competence under diagnostic practice concentration
``c`` (``population/practice_concentration.py``). The probe reads each unit-year's
authoritative cultivation labor (at farming) and activity shares (at learning), then updates
shadow components with the authoritative learning arithmetic; nothing feeds back (checked by
digest against a plain run). Fission copies a unit's components, fusion concatenates them by
population. A shadow's unit mean competence equals the authoritative unit level at every
``c`` (learning is linear in practice and the hours are conserved), checked every year.

Modes:

``controlled``
    The overhead optimum (corner) over a sweep of ``o``, and deterministic single-unit
    trajectories (low, moderate, near-full and capped demand; no cultivation; start, stop,
    demand rising and falling).
``runs``
    Reference scenarios (neolithic 600 y, pressure + cultivation 400 y; seeds 0-3):
    cultivation opportunity (``f_min``), and shadows: ``c`` in {0, 0.25, 0.5, 0.75, 1} at
    capacity 16 (and 0, 0.5, 1 at 32; continuity assignment, immediate split), plus at ``c = 1``,
    capacity 16: accumulated-divergence merges (tau 0.01 / 0.05 in efficiency), minimum
    duration (3 y), rotation, and competence-based assignment (secondary).

Usage:
    uv run python scripts/probes/practice_concentration_counterfactual.py controlled
    uv run python scripts/probes/practice_concentration_counterfactual.py runs [--jobs 2] [--years N] [--out f.pkl]
    uv run python scripts/probes/practice_concentration_counterfactual.py report --load f.pkl
"""

import argparse
import pickle
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import pairwise
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, drive, physical_digest, q, scenario_for

import madexplorer.core.simulation as simulation
import madexplorer.population.groups as groups
from madexplorer.config.loader import Scenario
from madexplorer.core.exactsum import python_sum_columns
from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import FarmingSubsystem, labor_hours_columns
from madexplorer.knowledge.learning import LearningSubsystem, activity_shares_columns
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.practice_concentration import (
    component_practice,
    diagnostic_share,
    efficiency,
    efficiency_slope,
    learn_components,
    min_participating_share,
    optimal_participating_share,
    participation_labor,
)

SCENARIOS = ("neolithic", "pressure+cult")
CONCENTRATIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
CAPACITIES = (16, 32)
EPS = 1e-12
GAPS = (0.01, 0.05, 0.1)  # efficiency-gap thresholds (sensitivity)
YEARS: int | None = None


# ---------------------------------------------------------------- shadow representation


@dataclass
class Policy:
    concentration: float
    capacity: int = 16
    assignment: str = "continuity"  # continuity | rotation | competence
    merge_tau: float = 0.0  # accumulated divergence: merge same-status within this efficiency
    min_duration: int = 0  # representation lag (years) before the participant share moves

    @property
    def label(self) -> str:
        extra = []
        if self.assignment != "continuity":
            extra.append(self.assignment)
        if self.merge_tau:
            extra.append(f"tau={self.merge_tau}")
        if self.min_duration:
            extra.append(f"dur={self.min_duration}")
        return f"c={self.concentration} cap={self.capacity}" + (
            " " + " ".join(extra) if extra else ""
        )


@dataclass
class Components:
    share: np.ndarray
    k: np.ndarray
    part: np.ndarray
    born: np.ndarray
    rep_target: float = 0.0
    pending: int = 0


@dataclass
class Stats:
    unit_years: int = 0
    farming: int = 0
    comps: list[int] = field(default_factory=list)
    at_cap: int = 0
    splits: int = 0
    compactions: int = 0
    tau_merges: int = 0
    coalescences: int = 0
    coalesce_k_cost: float = 0.0
    coalesce_eff_loss: float = 0.0
    eff_loss_if_eff_metric: float = 0.0
    metric_disagree: int = 0
    rank_corr: list[float] = field(default_factory=list)
    slope_corr: list[float] = field(default_factory=list)
    gaps_e: list[float] = field(default_factory=list)
    gaps_k: list[float] = field(default_factory=list)
    gap_people: list[float] = field(default_factory=list)
    dispersion: list[float] = field(default_factory=list)
    potential: list[float] = field(default_factory=list)
    redundant: int = 0
    lifetimes: list[int] = field(default_factory=list)
    neutral_max: float = 0.0
    shift_max: float = 0.0
    stop_halvings: list[tuple[int, bool]] = field(default_factory=list)
    clearing_dev: list[float] = field(default_factory=list)
    reentries: int = 0
    trace: dict[str, list[float]] = field(default_factory=dict)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return float("nan")
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


class Shadow:
    def __init__(self, policy: Policy, half: float) -> None:
        self.p, self.half = policy, half
        self.units: dict[str, Components] = {}
        self.stats = Stats()
        self.stopped: dict[str, list[Any]] = {}  # unit -> [start year, start gap, years]
        self.year = 0

    # --- structure

    def _split(self, c: Components, i: int, moved: float, to_part: bool) -> None:
        if moved <= EPS * c.share[i]:
            return
        if moved >= c.share[i] * (1 - 1e-15):
            c.part[i] = to_part
            return
        c.share[i] -= moved
        c.share = np.append(c.share, moved)
        c.k = np.append(c.k, c.k[i])
        c.part = np.append(c.part, to_part)
        c.born = np.append(c.born, self.year)
        self.stats.splits += 1

    def _reallocate(self, c: Components, target: float) -> None:
        part_share = float(c.share[c.part].sum())
        if target >= 1 - 1e-15:
            if not c.part.all():
                self.stats.reentries += int((~c.part).sum())
            c.part[:] = True
            return
        if target <= 0:
            c.part[:] = False
            return
        if self.p.assignment == "rotation":
            for i in range(c.share.size):
                was = bool(c.part[i])
                c.part[i] = True
                self._split(c, i, c.share[i] * (1 - target), False)
                del was
            return
        if target > part_share + 1e-15:
            need = target - part_share
            idx = np.flatnonzero(~c.part)
            if self.p.assignment == "competence":
                for i in idx[np.argsort(-c.k[idx], kind="stable")].tolist():
                    take = min(need, float(c.share[i]))
                    self._split(c, i, take, True)
                    need -= take
                    if need <= 1e-15:
                        break
            else:
                pool = float(c.share[idx].sum())
                for i in idx.tolist():
                    self._split(c, i, c.share[i] * need / pool, True)
        elif target < part_share - 1e-15:
            drop = part_share - target
            idx = np.flatnonzero(c.part)
            if self.p.assignment == "competence":
                for i in idx[np.argsort(c.k[idx], kind="stable")].tolist():
                    take = min(drop, float(c.share[i]))
                    self._split(c, i, take, False)
                    drop -= take
                    if drop <= 1e-15:
                        break
            else:
                for i in idx.tolist():
                    self._split(c, i, c.share[i] * drop / part_share, False)

    def _merge(self, c: Components, i: int, j: int) -> None:
        s = c.share[i] + c.share[j]
        k = (c.share[i] * c.k[i] + c.share[j] * c.k[j]) / s
        for arr_end in (i, j):
            self.stats.lifetimes.append(self.year - int(c.born[arr_end]))
        keep = [x for x in range(c.share.size) if x not in (i, j)]
        c.share = np.append(c.share[keep], s)
        c.k = np.append(c.k[keep], k)
        c.part = np.append(c.part[keep], c.part[i])
        c.born = np.append(c.born[keep], self.year)

    def _normalize(self, c: Components) -> None:
        # exact compaction: identical (competence, status)
        changed = True
        while changed and c.share.size > 1:
            changed = False
            for i in range(c.share.size):
                same = np.flatnonzero((c.k == c.k[i]) & (c.part == c.part[i]))
                if same.size > 1:
                    self._merge(c, int(same[0]), int(same[1]))
                    self.stats.compactions += 1
                    changed = True
                    break
        if self.p.merge_tau > 0:
            changed = True
            while changed and c.share.size > 1:
                changed = False
                e = efficiency(c.k, self.half)
                for i in range(c.share.size):
                    near = np.flatnonzero(
                        (np.abs(e - e[i]) < self.p.merge_tau) & (c.part == c.part[i])
                    )
                    near = near[near != i]
                    if near.size:
                        self._merge(c, i, int(near[0]))
                        self.stats.tau_merges += 1
                        changed = True
                        break
        while c.share.size > self.p.capacity:
            self._coalesce(c)

    def _coalesce(self, c: Components) -> None:
        n = c.share.size
        a, b = np.triu_indices(n, 1)
        same = c.part[a] == c.part[b]
        a, b = a[same], b[same]
        w = c.share[a] * c.share[b] / (c.share[a] + c.share[b])
        k_cost = w * (c.k[a] - c.k[b]) ** 2
        e = efficiency(c.k, self.half)
        eff_loss = w * (e[a] - e[b]) ** 2
        mid = 0.5 * (c.k[a] + c.k[b])
        slope_cost = w * (efficiency_slope(mid, self.half) * (c.k[a] - c.k[b])) ** 2
        best = int(np.argmin(k_cost))
        alt = int(np.argmin(eff_loss))
        st = self.stats
        st.coalescences += 1
        st.coalesce_k_cost += float(k_cost[best])
        st.coalesce_eff_loss += float(eff_loss[best])
        st.eff_loss_if_eff_metric += float(eff_loss[alt])
        st.metric_disagree += int(best != alt)
        if st.coalescences % 10 == 1:  # sampled: rank correlations are diagnostic only
            st.rank_corr.append(_spearman(k_cost, eff_loss))
            st.slope_corr.append(_spearman(slope_cost, eff_loss))
        self._merge(c, int(a[best]), int(b[best]))

    # --- yearly update

    def learn(self, uid: str, rec: dict[str, float], k_unit: float, k_new: float) -> None:
        st, p = self.stats, self.p
        c = self.units.get(uid)
        if c is None:
            c = Components(np.ones(1), np.array([k_unit]), np.zeros(1, bool), np.array([self.year]))
            self.units[uid] = c
        st.unit_years += 1
        # Knowledge changes outside learning (diffusion, innovation bonus) are unit-level;
        # carry them to every component alike (neutral convention), so the share-weighted
        # mean stays the authoritative unit level.
        shift = k_unit - float((c.share * c.k).sum())
        if shift != 0.0:
            c.k = np.maximum(c.k + shift, 0.0)
            st.shift_max = max(st.shift_max, abs(shift) / max(abs(k_unit), 1.0))
        farming = rec["hours"] > 0
        f_min = rec["f_min"]
        target = diagnostic_share(p.concentration, f_min) if farming else 0.0
        if p.min_duration and farming:
            if abs(target - c.rep_target) > 1e-12:
                c.pending += 1
                if c.pending >= p.min_duration or c.rep_target < f_min or c.rep_target <= 0:
                    c.rep_target, c.pending = target, 0
            else:
                c.pending = 0
            target = c.rep_target
        elif not farming:
            c.rep_target, c.pending = 0.0, 0
        else:
            c.rep_target = target
        was_stopped = uid in self.stopped
        self._reallocate(c, target)
        participants = float(c.share[c.part].sum()) if farming else 1.0
        practice = component_practice(
            rec["practice"],
            rec["farm"],
            rec["forage"],
            c.part,
            c.share,
            participants,
            rec["w_farm"],
            rec["w_forage"],
        )
        c.k = learn_components(
            c.k,
            practice,
            rec["practitioners"],
            rec["speed"],
            rec["lr"],
            rec["scale"],
            rec["decay"],
            rec["retention"],
        )
        mean = float((c.share * c.k).sum())
        st.neutral_max = max(st.neutral_max, abs(mean - k_new) / max(abs(k_new), 1.0))
        self._normalize(c)
        # diagnostics
        st.comps.append(int(c.share.size))
        st.at_cap += int(c.share.size >= p.capacity)
        e = efficiency(c.k, self.half)
        ebar = float((c.share * e).sum())
        st.dispersion.append(float((c.share * np.abs(e - ebar)).sum()))
        if farming:
            st.farming += 1
        if c.part.any() and (~c.part).any():
            sp, sn = c.share[c.part], c.share[~c.part]
            kp, kn = (
                float((sp * c.k[c.part]).sum() / sp.sum()),
                float((sn * c.k[~c.part]).sum() / sn.sum()),
            )
            gap = float(efficiency(kp, self.half) - efficiency(kn, self.half))
            st.gaps_e.append(gap)
            st.gaps_k.append(kp - kn)
            st.gap_people.append(rec["people"])
            if farming:
                st.potential.append(
                    float(efficiency(kp, self.half) / max(efficiency(k_new, self.half), 1e-300))
                    - 1.0
                )
        for status in (True, False):
            es = np.sort(e[c.part == status])
            st.redundant += int((np.diff(es) < 1e-3).sum())
        # persistence after practice stops (gap at the stop, then decay without cultivation)
        if not farming and not was_stopped and c.share.size > 1:
            spread_e = float(e.max() - e.min())
            if spread_e >= 0.05:
                self.stopped[uid] = [self.year, spread_e, 0]
        elif was_stopped:
            start_year, start_gap, _ = self.stopped[uid]
            spread_e = float(e.max() - e.min()) if c.share.size > 1 else 0.0
            if farming:
                st.stop_halvings.append((self.year - start_year, False))
                del self.stopped[uid]
            elif spread_e <= 0.5 * start_gap:
                st.stop_halvings.append((self.year - start_year, True))
                del self.stopped[uid]

    def fission(self, parent: str, daughter: str) -> None:
        c = self.units.get(parent)
        if c is not None:
            self.units[daughter] = Components(
                c.share.copy(), c.k.copy(), c.part.copy(), c.born.copy(), c.rep_target, c.pending
            )

    def fusion(self, target: str, source: str, n_t: int, n_s: int) -> None:
        a, b = self.units.get(target), self.units.get(source)
        self.units.pop(source, None)
        if a is None or b is None or n_t + n_s == 0:
            return
        wa, wb = n_t / (n_t + n_s), n_s / (n_t + n_s)
        c = Components(
            np.concatenate([a.share * wa, b.share * wb]),
            np.concatenate([a.k, b.k]),
            np.concatenate([a.part, b.part]),
            np.concatenate([a.born, b.born]),
            max(a.rep_target, b.rep_target),
        )
        self.units[target] = c
        self._normalize(c)

    def clearing(self, uid: str, before: float, after: float) -> None:
        c = self.units.get(uid)
        if c is None or after <= before or before <= 0 or not c.part.any() or c.part.all():
            return
        f = float(c.share[c.part].sum())
        n = np.where(c.part, c.share / f, 0.0)  # H2 if participants also clear
        self.stats.clearing_dev.append(
            0.5 * float(np.abs(n - c.share).sum()) * (after - before) / after
        )

    def prune(self, alive: set[str]) -> None:
        for uid in [u for u in self.units if u not in alive]:
            del self.units[uid]
            self.stopped.pop(uid, None)


# ---------------------------------------------------------------- observation


class Observer:
    def __init__(self, shadows: list[Shadow], model: KnowledgeModel) -> None:
        self.shadows = shadows
        self.model = model
        self.farm: dict[str, dict[str, float]] = {}
        self.opportunity: list[tuple[str, int, float, float]] = []  # unit, year, f_min, s
        self.seconds = 0.0
        self._saved: list[tuple[Any, str, Any]] = []

    def install(self) -> "Observer":
        farm_eval, learn_eval = FarmingSubsystem.evaluate, LearningSubsystem.evaluate
        split, merge, hook = groups.split_unit, groups.merge_units, simulation.account_strata
        obs = self

        def farming(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = farm_eval(sub, state, ctx)
            t = time.perf_counter()
            cols = ctx.columns(state)
            if len(cols) and proposals:
                cap = labor_hours_columns(cols, ctx)
                debt = cols.get("labor_debt_hours")
                m = ctx.compiled.parameter("subsistence.max_farm_labor_share")[cols.species()]
                hours = proposals[0].hours
                for k, u in enumerate(cols.units):
                    h = float(hours[k])
                    f_min = min_participating_share(h, float(cap[k]), float(debt[k]), float(m[k]))
                    obs.farm[u.id] = {"hours": h, "f_min": f_min}
                    if h > 0:
                        obs.opportunity.append(
                            (u.id, state.year, f_min, h / max(float(cap[k] - debt[k]), 1e-300))
                        )
            obs.seconds += time.perf_counter() - t
            return proposals

        def learning(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = learn_eval(sub, state, ctx)
            t = time.perf_counter()
            obs._learn(state, ctx, proposals)
            obs.seconds += time.perf_counter() - t
            return proposals

        def split_observed(population: Any, parent_id: str, *args: Any, **kwargs: Any) -> Any:
            daughter = split(population, parent_id, *args, **kwargs)
            for s in obs.shadows:
                s.fission(parent_id, daughter.id)
            return daughter

        def merge_observed(
            population: Any, source_id: str, target_id: str, *args: Any, **kwargs: Any
        ) -> Any:
            n_t, n_s = (
                population.units[target_id].population,
                population.units[source_id].population,
            )
            out = merge(population, source_id, target_id, *args, **kwargs)
            for s in obs.shadows:
                s.fusion(target_id, source_id, n_t, n_s)
            return out

        def hook_observed(state: Any, ctx: Any) -> None:
            acc = ctx.field_accounts
            if acc is not None:
                for unit, f0, f1 in zip(
                    acc.units, acc.before.tolist(), acc.after.tolist(), strict=True
                ):
                    for s in obs.shadows:
                        s.clearing(unit.id, f0, f1)
            hook(state, ctx)

        for owner, name, new in (
            (FarmingSubsystem, "evaluate", farming),
            (LearningSubsystem, "evaluate", learning),
            (groups, "split_unit", split_observed),
            (groups, "merge_units", merge_observed),
            (simulation, "account_strata", hook_observed),
        ):
            self._saved.append((owner, name, getattr(owner, name)))
            setattr(owner, name, new)
        return self

    def remove(self) -> None:
        for owner, name, original in reversed(self._saved):
            setattr(owner, name, original)
        self._saved.clear()

    def _learn(self, state: Any, ctx: Any, proposals: Any) -> None:
        cols = ctx.columns(state)
        if not len(cols) or not proposals:
            return
        model = self.model
        i = model.index["agriculture"]
        weights = model.system.domains["agriculture"].practice
        shares = activity_shares_columns(cols, labor_hours_columns(cols, ctx))
        zeros = np.zeros(len(cols))
        practice = python_sum_columns([w * shares.get(a, zeros) for a, w in weights.items()])
        population = cols.population()
        old = cols.knowledge()[:, i]
        new = proposals[0].knowledge[:, i]
        species = cols.species()
        compiled = ctx.compiled
        speed = np.array([ctx.species(s).cognition.learning_speed for s in compiled.species_ids])[
            species
        ]
        retention = np.array(
            [ctx.species(s).cognition.knowledge_retention for s in compiled.species_ids]
        )[species]
        base = {
            "w_farm": float(weights.get("farming", 0.0)),
            "w_forage": float(weights.get("plant_foraging", 0.0)),
            "lr": float(model.learning_rate[i]),
            "scale": float(model.practitioner_scale[i]),
            "decay": float(model.decay_rate[i]),
        }
        for s in self.shadows:
            s.year = state.year
        for k, u in enumerate(cols.units):
            farm = self.farm.get(u.id, {"hours": 0.0, "f_min": 0.0})
            rec = {
                **base,
                "hours": farm["hours"],
                "f_min": farm["f_min"],
                "practice": float(practice[k]),
                "farm": float(shares["farming"][k]),
                "forage": float(shares["plant_foraging"][k]),
                "practitioners": float(population[k] * practice[k]),
                "speed": float(speed[k]),
                "retention": float(retention[k]),
                "people": float(population[k]),
            }
            for s in self.shadows:
                s.learn(u.id, rec, float(old[k]), float(new[k]))
        self.farm.clear()


def policies() -> list[Policy]:
    out = [Policy(c, 16) for c in CONCENTRATIONS] + [Policy(c, 32) for c in (0.0, 0.5, 1.0)]
    out += [
        Policy(1.0, 16, merge_tau=0.01),
        Policy(1.0, 16, merge_tau=0.05),
        Policy(1.0, 16, min_duration=3),
        Policy(1.0, 16, assignment="rotation"),
        Policy(1.0, 16, assignment="competence"),
    ]
    return out


def knowledge_model(scenario: Scenario) -> KnowledgeModel:
    assert scenario.knowledge is not None
    return KnowledgeModel(scenario.knowledge)


def job(spec: tuple[str, int]) -> dict[str, Any]:
    name, seed = spec
    scenario = scenario_for(name, seed, 0.0, YEARS)
    model = knowledge_model(scenario)
    half = float(model.half_efficiency[model.index["agriculture"]])
    shadows = [Shadow(p, half) for p in policies()]
    observer = Observer(shadows, model)
    observer.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        for _ in range(scenario.config.simulation.n_years):
            sim.step()
            if not sim.state.units:
                break
            alive = set(sim.state.units)
            for s in shadows:
                s.prune(alive)
        seconds = time.perf_counter() - started
    finally:
        observer.remove()
    plain, plain_seconds = drive(scenario, None)
    return {
        "name": name,
        "seed": seed,
        "stats": {s.p.label: s.stats for s in shadows},
        "opportunity": observer.opportunity,
        "neutral": physical_digest(sim) == physical_digest(plain),
        "seconds": seconds,
        "observer_seconds": observer.seconds,
        "plain_seconds": plain_seconds,
    }


# ---------------------------------------------------------------- report


def spells(keys: list[tuple[str, int]]) -> list[int]:
    out, by = [], defaultdict(list)
    for u, y in keys:
        by[u].append(y)
    for ys in by.values():
        ys.sort()
        run = 1
        for a, b in pairwise(ys):
            if b == a + 1:
                run += 1
            else:
                out.append(run)
                run = 1
        out.append(run)
    return out


def km(durations: list[tuple[int, bool]], ages: tuple[int, ...]) -> list[float]:
    if not durations:
        return [float("nan")] * len(ages)
    t = np.array([d for d, _ in durations])
    e = np.array([x for _, x in durations])
    out = []
    for a in ages:
        s = 1.0
        for x in np.unique(t[e & (t <= a)]):
            s *= 1 - (e & (t == x)).sum() / (t >= x).sum()
        out.append(float(s))
    return out


def report(results: list[dict[str, Any]]) -> None:
    for name in SCENARIOS:
        rs = [r for r in results if r["name"] == name]
        if not rs:
            continue
        print(
            f"\n=== {name}, seeds {[r['seed'] for r in rs]}; observer neutral: {all(r['neutral'] for r in rs)}"
        )
        opp = [o for r in rs for o in r["opportunity"]]
        f = np.array([o[2] for o in opp])
        print(f"farming unit-years {f.size}; P/(C-D) {q([o[3] for o in opp])}")
        print(
            f"f_min = P/(m(C-D)): {q(f)}; everyone needed (f_min = 1): {np.mean(f >= 1):.3f}; < 0.75: {np.mean(f < 0.75):.2f}; < 0.5: {np.mean(f < 0.5):.2f}; < 0.25: {np.mean(f < 0.25):.2f}"
        )
        feasible = [(o[0], o[1]) for r in rs for o in r["opportunity"] if o[2] < 0.75]
        per_run = [
            s for r in rs for s in spells([(o[0], o[1]) for o in r["opportunity"] if o[2] < 0.75])
        ]
        del feasible
        print(f"consecutive years with f_min < 0.75 per unit: {q(per_run)}")
        print(
            "\n| shadow | comps mean/p90/p99/max | at cap | splits / unit-year | compactions | tau merges | coalescences | E-gap part-non p50/p90 (unit-years with both) | share of unit-years with E-gap > 0.01/0.05/0.1 | K-gap p50/p90 | within-unit E dispersion pw p50/p90 | potential practitioner E / unit E - 1 p50/p90 | redundant pairs (|dE|<1e-3) / unit-year | mean-K neutral max | uniform non-learning shift max | re-entries |"
        )
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        labels = list(rs[0]["stats"])
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            comps = np.concatenate([np.array(s.comps) for s in ss])
            uy = sum(s.unit_years for s in ss)
            ge = (
                np.concatenate([np.array(s.gaps_e) for s in ss])
                if any(s.gaps_e for s in ss)
                else np.zeros(0)
            )
            gk = (
                np.concatenate([np.array(s.gaps_k) for s in ss])
                if any(s.gaps_k for s in ss)
                else np.zeros(0)
            )
            disp = np.concatenate([np.array(s.dispersion) for s in ss])
            pot = (
                np.concatenate([np.array(s.potential) for s in ss])
                if any(s.potential for s in ss)
                else np.zeros(0)
            )
            frac = " / ".join(f"{(ge > g).sum() / uy:.3f}" for g in GAPS)
            print(
                f"| {label} | {comps.mean():.2f}/{np.quantile(comps, 0.9):.0f}/{np.quantile(comps, 0.99):.0f}/{comps.max()} | {sum(s.at_cap for s in ss) / uy:.3f} "
                f"| {sum(s.splits for s in ss) / uy:.3f} | {sum(s.compactions for s in ss)} | {sum(s.tau_merges for s in ss)} | {sum(s.coalescences for s in ss)} "
                f"| {q(ge, (0.5, 0.9))} | {frac} | {q(gk, (0.5, 0.9))} | {np.quantile(disp, 0.5):.3g}/{np.quantile(disp, 0.9):.3g} "
                f"| {q(pot, (0.5, 0.9))} | {sum(s.redundant for s in ss) / uy:.3f} | {max(s.neutral_max for s in ss):.1e} | {max(s.shift_max for s in ss):.1e} | {sum(s.reentries for s in ss)} |"
            )
        print(
            "\nForced coalescence and merge metrics (same-status pairs): K-distance choice vs efficiency-variance choice"
        )
        print(
            "| shadow | coalescences | sum K-cost | sum E-variance loss (K metric) | (E metric) | argmin differs | Spearman(K-cost, E-loss) p50 | Spearman(slope-weighted, E-loss) p50 |"
        )
        print("|---|---|---|---|---|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            n = sum(s.coalescences for s in ss)
            if not n:
                continue
            rc = [x for s in ss for x in s.rank_corr if x == x]
            sc = [x for s in ss for x in s.slope_corr if x == x]
            print(
                f"| {label} | {n} | {sum(s.coalesce_k_cost for s in ss):.3g} | {sum(s.coalesce_eff_loss for s in ss):.3g} | {sum(s.eff_loss_if_eff_metric for s in ss):.3g} "
                f"| {sum(s.metric_disagree for s in ss) / n:.2f} | {np.median(rc) if rc else float('nan'):.2f} | {np.median(sc) if sc else float('nan'):.2f} |"
            )
        print(
            "\nPersistence after cultivation stops (within-unit E spread >= 0.05 at the stop): KM share not halved at 5/10/25/50 y; component lifetimes; clearing link"
        )
        print(
            "| shadow | stop episodes | not halved 5/10/25/50 y | component lifetime p50/p90 (merged) | H2-if-participants-clear: field-claim deviation per expansion p50/p90 (n) |"
        )
        print("|---|---|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            stops = [x for s in ss for x in s.stop_halvings]
            life = [x for s in ss for x in s.lifetimes]
            cl = [x for s in ss for x in s.clearing_dev]
            print(
                f"| {label} | {len(stops)} | {' / '.join(f'{x:.2f}' for x in km(stops, (5, 10, 25, 50)))} | {q(life, (0.5, 0.9))} | {q(cl, (0.5, 0.9))} ({len(cl)}) |"
            )
        print(
            f"\ncost: run {sum(r['seconds'] for r in rs):.0f} s (observer {sum(r['observer_seconds'] for r in rs):.0f} s, {len(labels)} shadows); plain {sum(r['plain_seconds'] for r in rs):.0f} s"
        )


# ---------------------------------------------------------------- controlled


def controlled() -> None:
    scenario = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml")
    model = knowledge_model(scenario)
    i = model.index["agriculture"]
    lr, scale, decay = (
        float(x[i]) for x in (model.learning_rate, model.practitioner_scale, model.decay_rate)
    )
    half = float(model.half_efficiency[i])
    w = model.system.domains["agriculture"].practice
    wf, wp = float(w["farming"]), float(w["plant_foraging"])
    C, D, M, H = 40 * 1825.0, 0.0, 0.9, 1825.0  # 40 full-labor adults, no debt
    L = C / H
    print(
        "Participation overhead: total labor P + o f L, feasibility m f (C - D) >= P + o f L (40 labor-equivalents)"
    )
    print(
        "| P / (C - D) | o (h / participant-year) | optimum | f* | overhead hours at f* | overhead / productive | labor saved vs f = 1 |"
    )
    print("|---|---|---|---|---|---|---|")
    for s in (0.1, 0.35, 0.6, 0.9):
        p = s * (C - D)
        for o in (0.0, 1.0, 10.0, 50.0, 200.0):
            opt = optimal_participating_share(p, C, D, M, o, L)
            if opt.indifferent:
                print(f"| {s} | {o} | indifferent on [{opt.minimum:.3f}, 1] | - | 0 | 0 | 0 |")
                continue
            fs = opt.share or 0.0
            over = participation_labor(fs, p, o, L) - p
            print(
                f"| {s} | {o} | corner | {fs:.3f} | {over:.0f} | {over / p:.4f} | {o * L * (1 - fs):.0f} h ({o * L * (1 - fs) / C:.4f} of C) |"
            )

    def run(pattern: list[float], c: float, years_label: tuple[int, ...]) -> list[str]:
        """Two components (participants / not) of one 40-person unit; pattern gives the
        cultivation share s = P/(C - D) per year (forage takes the rest, plant share 0.5)."""
        shares = np.ones(1)
        k = np.array([float(model.initial_levels()[i])])
        part = np.zeros(1, bool)
        out = []
        for t, s in enumerate(pattern, start=1):
            if s > 0:
                f_min = min_participating_share(s * C, C, D, M)
                target = diagnostic_share(c, f_min)
                cur = float(shares[part].sum())
                if part.size == 1 and 0 < target < 1:
                    shares, k, part = (
                        np.array([target, 1 - target]),
                        np.array([k[0], k[0]]),
                        np.array([True, False]),
                    )
                elif part.size == 2 and abs(target - cur) > 1e-12:
                    # continuity: move the marginal share between the two components (population-weighted K)
                    if target > cur:
                        moved = target - cur
                        k_new = (cur * k[0] + moved * k[1]) / target
                        shares, k = np.array([target, 1 - target]), np.array([k_new, k[1]])
                    else:
                        shares = np.array([target, 1 - target])
                        k = np.array(
                            [k[0], ((1 - cur) * k[1] + (cur - target) * k[0]) / (1 - target)]
                        )
                elif part.size == 1:
                    part = np.array([True])
                participants = float(shares[part].sum())
            else:
                participants = 1.0
            forage = (1 - s) * 0.5
            unit = wf * s + wp * forage
            practice = component_practice(
                unit,
                s,
                forage,
                part if s > 0 else np.zeros(part.size, bool),
                shares,
                participants,
                wf,
                wp,
            )
            k = learn_components(k, practice, 40 * unit, 1.0, lr, scale, decay, 1.0)
            if t in years_label:
                e = efficiency(k, half)
                out.append(f"{e.max():.2f}/{e.min():.2f}" if e.size > 1 else f"{e[0]:.2f}")
        return out

    print(
        "\nTwo-component trajectories (40 people), agricultural efficiency practitioners/others at years 1/5/10/25/50/100"
    )
    marks = (1, 5, 10, 25, 50, 100)
    cases = {
        "low demand s=0.1": [0.1] * 100,
        "moderate s=0.35": [0.35] * 100,
        "near-full s=0.85": [0.85] * 100,
        "capped s=0.95": [0.95] * 100,
        "no cultivation": [0.0] * 100,
        "start after 20 y homogeneous (s=0.35 from y21)": [0.0] * 20 + [0.35] * 80,
        "stop after 30 y (s=0.35, then 0)": [0.35] * 30 + [0.0] * 70,
        "demand rises 0.2 -> 0.6 at y30": [0.2] * 30 + [0.6] * 70,
        "demand falls 0.6 -> 0.2 at y30": [0.6] * 30 + [0.2] * 70,
    }
    print("| case | " + " | ".join(f"c={c}" for c in CONCENTRATIONS) + " |")
    print("|---|" + "---|" * len(CONCENTRATIONS))
    for label, pattern in cases.items():
        cells = [" ".join(run(pattern, c, marks)) for c in CONCENTRATIONS]
        print(f"| {label} | " + " | ".join(cells) + " |")
    print(
        f"\nWithout practice both components decay by (1 - {decay}) per year: competence gap half-life {np.log(2) / -np.log(1 - decay):.1f} y."
    )


def _set_years(years: int | None) -> None:
    global YEARS
    YEARS = years


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("controlled", "runs", "report"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--years", type=int)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "report":
        with args.load.open("rb") as f:
            report(pickle.load(f))
        return
    specs = [(name, seed) for name in SCENARIOS for seed in args.seeds]
    with Pool(args.jobs, initializer=_set_years, initargs=(args.years,)) as pool:
        results = pool.map(job, specs, chunksize=1)
    if args.out:
        with args.out.open("wb") as f:
            pickle.dump(results, f)
    report(results)


if __name__ == "__main__":
    main()
