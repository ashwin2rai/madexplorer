# The report tables keep one entry per line.
# ruff: noqa: E501
"""Entry costs and participation continuity (MVP 3 Stage 5C): observation only. NOT ACTIVE.

Shadow per-component agriculture competence when this year's cultivation is done by a
participating share chosen by a participation model (``population/entry_cost.py``):

- M0 proportional: everyone participates (today's implicit spread);
- M1 rotation: the smallest feasible share, redrawn in proportion every year;
- M2 entry-cost continuity: the smallest feasible share at minimum entry labor (last
  participants first; equal costs in proportion), or ``retain`` (all zero-cost incumbents
  kept: the other end of the indifference interval);
- M3 competence: the same amount, drawn by descending competence (secondary).

The probe reads each unit-year's authoritative cultivation labor (at farming) and activity
shares (at learning) and updates shadow components with the authoritative learning
arithmetic; nothing feeds back (checked by digest against a plain run). Entry hours go to a
counterfactual ledger only. The shadow unit mean competence equals the authoritative unit
level at every policy, checked every year.

Modes:

``controlled``
    The entry-cost optimum (first entry, incumbents, entrants) over ``e``; deterministic
    single-unit trajectories for the 15 Stage 5C cases and the hysteresis cycle.
``runs``
    Reference scenarios (neolithic 600 y, pressure + cultivation 400 y; seeds 0-3).
``report``
    The tables of a saved ``runs`` directory.

Usage:
    uv run python scripts/probes/entry_cost_counterfactual.py controlled
    uv run python scripts/probes/entry_cost_counterfactual.py runs [--jobs 2] [--years N] [--seeds ...] [--out DIR]
    uv run python scripts/probes/entry_cost_counterfactual.py report --load DIR
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

import madexplorer.population.groups as groups
from madexplorer.config.loader import Scenario
from madexplorer.core.exactsum import python_sum_columns
from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import FarmingSubsystem, labor_hours_columns
from madexplorer.knowledge.learning import LearningSubsystem, activity_shares_columns
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.entry_cost import (
    NEVER,
    Components,
    Memory,
    advance_history,
    allocate,
    entry_factor,
    retain_incumbents,
    split_participation,
    spread_allocation,
    turnover,
)
from madexplorer.population.practice_concentration import (
    component_practice,
    efficiency,
    learn_components,
    min_participating_share,
)

SCENARIOS = ("neolithic", "pressure+cult")
E_RUN = 50.0  # entry hours per entering labor-equivalent in the shadow trajectories
E_SWEEP = (0.0, 1.0, 10.0, 50.0, 200.0)  # ledger sensitivity (not calibration)
EPS = 1e-12
GAPS = (0.01, 0.05, 0.1)
YEARS: int | None = None
PROGRESS_EVERY = 100
HOURS_PER_YEAR = 5.0 * 365.0
W1, W10, H10 = Memory("window", 1), Memory("window", 10), Memory("decay", 10)


# ---------------------------------------------------------------- policies


@dataclass(frozen=True)
class Policy:
    model: str  # M0 | M1 | M2 | M3
    memory: Memory = W1
    retain: bool = False
    capacity: int = 16
    merge_tau: float = 0.0
    entry: float = E_RUN
    turnover: bool = False
    ledger: bool = False

    @property
    def label(self) -> str:
        parts = [self.model]
        if self.model in ("M2", "M3"):
            parts.append("retain" if self.retain else "min")
        if self.model != "M0":
            mem = self.memory
            parts.append(f"W{mem.years:g}" if mem.kind == "window" else f"H{mem.years:g}")
        if self.entry != E_RUN:
            parts.append(f"e={self.entry:g}")
        if self.turnover:
            parts.append("turnover")
        if self.merge_tau:
            parts.append(f"tau={self.merge_tau}")
        if self.capacity != 16:
            parts.append(f"cap={self.capacity}")
        return " ".join(parts)


def policies() -> list[Policy]:
    return [
        Policy("M0", ledger=True),
        Policy("M1", ledger=True),
        Policy("M2", ledger=True),
        Policy("M2", retain=True, ledger=True),
        Policy("M2", memory=W10, ledger=True),
        Policy("M2", memory=H10, ledger=True),
        Policy("M2", turnover=True),
        Policy("M3"),
        Policy("M2", entry=200.0),
        Policy("M2", merge_tau=0.01),
        Policy("M2", merge_tau=0.05),
        Policy("M2", capacity=32),
        Policy("M2", retain=True, capacity=32),
    ]


# ---------------------------------------------------------------- shadow


@dataclass
class Unit:
    c: Components
    born: np.ndarray


@dataclass
class Stats:
    unit_years: int = 0
    farming: int = 0
    comps: list[int] = field(default_factory=list)
    at_cap: int = 0
    splits: int = 0
    turnover_splits: int = 0
    compactions: int = 0
    tau_merges: int = 0
    coalescences: int = 0
    cross_history: int = 0  # forced coalescences that merged different entry-cost classes
    history_mixed: int = 0  # merges of components with different ``since``
    coalesce_k_cost: float = 0.0
    coalesce_eff_loss: float = 0.0
    eff_loss_if_eff_metric: float = 0.0
    metric_disagree: int = 0
    rank_corr: list[float] = field(default_factory=list)
    slope_corr: list[float] = field(default_factory=list)
    dup_diff_history: int = 0  # same status, |dE| < 1e-3, different entry-cost class
    gaps_e: list[float] = field(default_factory=list)
    gaps_k: list[float] = field(default_factory=list)
    dispersion: list[float] = field(default_factory=list)
    potential: list[float] = field(default_factory=list)
    redundant: int = 0
    lifetimes: list[int] = field(default_factory=list)
    neutral_max: float = 0.0
    shift_max: float = 0.0
    stop_halvings: list[tuple[int, bool]] = field(default_factory=list)
    part: list[float] = field(default_factory=list)  # participating share (farming years)
    entrants: list[float] = field(default_factory=list)  # cost-weighted entering share
    retained: list[float] = field(default_factory=list)  # zero-cost incumbents kept / available
    entry_frac: list[float] = field(default_factory=list)  # entry hours / capacity
    free: list[float] = field(default_factory=list)  # share free to join at zero cost
    infeasible: int = 0
    ledger: dict[float, list[float]] = field(
        default_factory=dict
    )  # e -> [entry/C sum, infeasible, years]
    reentries: int = 0  # unit-years resuming cultivation after at least one idle year
    reentry_former: list[float] = field(default_factory=list)  # entrants with phi < 1 / entrants
    tau: list[float] = field(default_factory=list)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if a.size < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return float("nan")
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


ARRAYS = {
    "comps": np.int16,
    "gaps_e": np.float32,
    "gaps_k": np.float32,
    "dispersion": np.float32,
    "potential": np.float32,
    "lifetimes": np.int32,
    "rank_corr": np.float32,
    "slope_corr": np.float32,
    "part": np.float32,
    "entrants": np.float32,
    "retained": np.float32,
    "entry_frac": np.float32,
    "free": np.float32,
    "reentry_former": np.float32,
    "tau": np.float32,
}


def compact(stats: Stats) -> Stats:
    for name, dtype in ARRAYS.items():
        setattr(stats, name, np.asarray(getattr(stats, name), dtype=dtype))
    return stats


class Shadow:
    def __init__(self, policy: Policy, half: float) -> None:
        self.p, self.half = policy, half
        self.units: dict[str, Unit] = {}
        self.stats = Stats()
        self.stopped: dict[str, list[Any]] = {}
        self.last_farm: dict[str, int] = {}
        self.year = 0

    # --- structure

    def _merge(self, u: Unit, i: int, j: int) -> None:
        c = u.c
        s = c.share[i] + c.share[j]
        k = (c.share[i] * c.competence[i] + c.share[j] * c.competence[j]) / s
        since = (c.share[i] * min(c.since[i], 1e6) + c.share[j] * min(c.since[j], 1e6)) / s
        if c.since[i] != c.since[j]:
            self.stats.history_mixed += 1
        else:
            since = c.since[i]
        for end in (i, j):
            self.stats.lifetimes.append(self.year - int(u.born[end]))
        keep = [x for x in range(c.share.size) if x not in (i, j)]
        u.c = Components(
            np.append(c.share[keep], s),
            np.append(c.competence[keep], k),
            np.append(c.since[keep], since if since < 1e6 else NEVER),
            np.append(c.participating[keep], c.participating[i]),
        )
        u.born = np.append(u.born[keep], self.year)

    def _cls(self, c: Components) -> np.ndarray:
        """Entry-cost class next year: zero-cost incumbent or not (merges must respect it)."""
        return entry_factor(c.since, self.p.memory) == 0.0

    def _normalize(self, u: Unit) -> None:
        changed = True
        while changed and u.c.share.size > 1:  # exact compaction: identical state
            changed = False
            c = u.c
            for i in range(c.share.size):
                same = np.flatnonzero(
                    (c.competence == c.competence[i])
                    & (c.participating == c.participating[i])
                    & (c.since == c.since[i])
                )
                if same.size > 1:
                    self._merge(u, int(same[0]), int(same[1]))
                    self.stats.compactions += 1
                    changed = True
                    break
        if self.p.merge_tau > 0:
            changed = True
            while changed and u.c.share.size > 1:
                changed = False
                c = u.c
                e, cls = efficiency(c.competence, self.half), self._cls(c)
                for i in range(c.share.size):
                    near = np.flatnonzero(
                        (np.abs(e - e[i]) < self.p.merge_tau)
                        & (c.participating == c.participating[i])
                        & (cls == cls[i])
                    )
                    near = near[near != i]
                    if near.size:
                        self._merge(u, i, int(near[0]))
                        self.stats.tau_merges += 1
                        changed = True
                        break
        while u.c.share.size > self.p.capacity:
            self._coalesce(u)

    def _coalesce(self, u: Unit) -> None:
        c = u.c
        n = c.share.size
        a, b = np.triu_indices(n, 1)
        same = c.participating[a] == c.participating[b]
        cls = self._cls(c)
        hist = cls[a] == cls[b]
        pool = same & hist
        cross = not pool.any()
        if cross:
            pool = same if same.any() else np.ones(a.size, bool)
            self.stats.cross_history += 1
        a, b = a[pool], b[pool]
        k = c.competence
        w = c.share[a] * c.share[b] / (c.share[a] + c.share[b])
        k_cost = w * (k[a] - k[b]) ** 2
        e = efficiency(k, self.half)
        eff_loss = w * (e[a] - e[b]) ** 2
        mid = 0.5 * (k[a] + k[b])
        slope = self.half / (mid + self.half) ** 2
        slope_cost = w * (slope * (k[a] - k[b])) ** 2
        best, alt = int(np.argmin(k_cost)), int(np.argmin(eff_loss))
        st = self.stats
        st.coalescences += 1
        st.coalesce_k_cost += float(k_cost[best])
        st.coalesce_eff_loss += float(eff_loss[best])
        st.eff_loss_if_eff_metric += float(eff_loss[alt])
        st.metric_disagree += int(best != alt)
        if st.coalescences % 10 == 1:
            st.rank_corr.append(_spearman(k_cost, eff_loss))
            st.slope_corr.append(_spearman(slope_cost, eff_loss))
        self._merge(u, int(a[best]), int(b[best]))

    # --- yearly update

    def allocation(self, c: Components, rec: dict[str, float], entry: float) -> Any:
        phi = entry_factor(c.since, self.p.memory)
        args = (c.share, phi, rec["hours"], rec["capacity"], rec["debt"], rec["m"], entry, rec["L"])
        if self.p.model == "M0":
            return phi, spread_allocation(*args, everyone=True)
        if self.p.model == "M1":
            return phi, spread_allocation(*args, everyone=False)
        rank = -c.competence if self.p.model == "M3" else None
        return phi, allocate(*args, rank=rank)

    def learn(self, uid: str, rec: dict[str, float], k_unit: float, k_new: float) -> None:
        st, p = self.stats, self.p
        u = self.units.get(uid)
        if u is None:
            u = Unit(
                Components(np.ones(1), np.array([k_unit]), np.array([NEVER]), np.zeros(1, bool)),
                np.array([self.year]),
            )
            self.units[uid] = u
        st.unit_years += 1
        c = u.c
        shift = k_unit - float((c.share * c.competence).sum())
        if shift != 0.0:
            c = Components(c.share, np.maximum(c.competence + shift, 0.0), c.since, c.participating)
            st.shift_max = max(st.shift_max, abs(shift) / max(abs(k_unit), 1.0))
        if p.turnover and rec.get("tau", 0.0) > 0:
            before = c.share.size
            c = turnover(c, rec["tau"])
            st.turnover_splits += c.share.size - before
            u.born = np.append(u.born, np.full(c.share.size - before, self.year))
            st.tau.append(rec["tau"])
        farming = rec["hours"] > 0
        was_stopped = uid in self.stopped
        participants = 1.0
        if farming:
            st.farming += 1
            phi, a = self.allocation(c, rec, p.entry)
            take = retain_incumbents(a, c.share, phi) if p.retain else a.take
            zero = phi == 0.0
            inc = float(c.share[zero].sum())
            if inc > 0:
                st.retained.append(float(take[zero].sum()) / inc)
            st.part.append(float(take.sum()))
            st.entrants.append(a.entrants)
            st.entry_frac.append(a.entry_hours / rec["capacity"])
            st.free.append(float((c.share[zero] - take[zero]).sum()))
            st.infeasible += int(not a.feasible)
            last = self.last_farm.get(uid)
            if last is not None and last < self.year - 1:
                st.reentries += 1
                if a.entrants > 0:
                    st.reentry_former.append(float((take * (phi < 1)).sum()) / float(take.sum()))
            self.last_farm[uid] = self.year
            if p.ledger:
                for e in E_SWEEP:
                    _, b = self.allocation(c, rec, e)
                    acc = st.ledger.setdefault(e, [0.0, 0.0, 0.0])
                    acc[0] += b.entry_hours / rec["capacity"]
                    acc[1] += int(not b.feasible)
                    acc[2] += 1
            before = c.share.size
            c = split_participation(c, take)
            st.splits += c.share.size - before
            u.born = np.append(u.born, np.full(c.share.size - before, self.year))
            participants = float(c.share[c.participating].sum())
        else:
            c = Components(c.share, c.competence, c.since, np.zeros(c.share.size, bool))
        part = c.participating if farming else np.zeros(c.share.size, bool)
        practice = component_practice(
            rec["practice"], rec["farm"], rec["forage"], part, c.share, participants,
            rec["w_farm"], rec["w_forage"],
        )  # fmt: skip
        k = learn_components(
            c.competence, practice, rec["practitioners"], rec["speed"], rec["lr"],
            rec["scale"], rec["decay"], rec["retention"],
        )  # fmt: skip
        c = Components(c.share, k, c.since, c.participating)
        mean = float((c.share * k).sum())
        st.neutral_max = max(st.neutral_max, abs(mean - k_new) / max(abs(k_new), 1.0))
        self._diagnose(uid, c, farming, k_new, was_stopped)
        u.c = advance_history(c) if farming else c
        if not farming:  # nobody participated: everyone one year further away
            u.c = Components(c.share, c.competence, c.since + 1.0, c.participating)
        self._normalize(u)

    def _diagnose(
        self, uid: str, c: Components, farming: bool, k_new: float, was_stopped: bool
    ) -> None:
        st, u = self.stats, self.units[uid]
        st.comps.append(int(c.share.size))
        st.at_cap += int(c.share.size >= self.p.capacity)
        e = efficiency(c.competence, self.half)
        ebar = float((c.share * e).sum())
        st.dispersion.append(float((c.share * np.abs(e - ebar)).sum()))
        part = c.participating
        if farming and part.any() and (~part).any():
            sp, sn = c.share[part], c.share[~part]
            kp = float((sp * c.competence[part]).sum() / sp.sum())
            kn = float((sn * c.competence[~part]).sum() / sn.sum())
            st.gaps_e.append(float(efficiency(kp, self.half) - efficiency(kn, self.half)))
            st.gaps_k.append(kp - kn)
            st.potential.append(
                float(efficiency(kp, self.half) / max(float(efficiency(k_new, self.half)), 1e-300))
                - 1.0
            )
        cls = (
            entry_factor(
                np.where(part, 1.0, c.since + 1.0) if farming else c.since + 1.0, self.p.memory
            )
            == 0.0
        )
        for status in (True, False):
            sel = part == status
            order = np.argsort(e[sel])
            es, cs = e[sel][order], cls[sel][order]
            close = np.diff(es) < 1e-3
            st.redundant += int(close.sum())
            st.dup_diff_history += int((close & (cs[1:] != cs[:-1])).sum())
        del u
        if not farming and not was_stopped and c.share.size > 1:
            spread = float(e.max() - e.min())
            if spread >= 0.05:
                self.stopped[uid] = [self.year, spread]
        elif was_stopped:
            start, gap = self.stopped[uid]
            spread = float(e.max() - e.min()) if c.share.size > 1 else 0.0
            if farming:
                st.stop_halvings.append((self.year - start, False))
                del self.stopped[uid]
            elif spread <= 0.5 * gap:
                st.stop_halvings.append((self.year - start, True))
                del self.stopped[uid]

    def fission(self, parent: str, daughter: str) -> None:
        u = self.units.get(parent)
        if u is not None:
            c = u.c
            self.units[daughter] = Unit(
                Components(
                    c.share.copy(), c.competence.copy(), c.since.copy(), c.participating.copy()
                ),
                u.born.copy(),
            )
            if parent in self.last_farm:
                self.last_farm[daughter] = self.last_farm[parent]

    def fusion(self, target: str, source: str, n_t: int, n_s: int) -> None:
        a, b = self.units.get(target), self.units.get(source)
        self.units.pop(source, None)
        self.last_farm.pop(source, None)
        if a is None or b is None or n_t + n_s == 0:
            return
        wa, wb = n_t / (n_t + n_s), n_s / (n_t + n_s)
        u = Unit(
            Components(
                np.concatenate([a.c.share * wa, b.c.share * wb]),
                np.concatenate([a.c.competence, b.c.competence]),
                np.concatenate([a.c.since, b.c.since]),
                np.concatenate([a.c.participating, b.c.participating]),
            ),
            np.concatenate([a.born, b.born]),
        )
        self.units[target] = u
        self._normalize(u)

    def prune(self, alive: set[str]) -> None:
        for uid in [x for x in self.units if x not in alive]:
            del self.units[uid]
            self.stopped.pop(uid, None)
            self.last_farm.pop(uid, None)


# ---------------------------------------------------------------- observation


class Observer:
    def __init__(self, shadows: list[Shadow], model: KnowledgeModel) -> None:
        self.shadows = shadows
        self.model = model
        self.farm: dict[str, dict[str, float]] = {}
        self.opportunity: list[
            tuple[str, int, float, float, float]
        ] = []  # unit, year, f_min, P/(C-D), tau
        self.events = {"fission": 0, "fusion": 0}
        self.seconds = 0.0
        self._saved: list[tuple[Any, str, Any]] = []
        self._ramp: dict[int, np.ndarray] = {}

    def install(self) -> "Observer":
        farm_eval, learn_eval = FarmingSubsystem.evaluate, LearningSubsystem.evaluate
        split, merge = groups.split_unit, groups.merge_units
        obs = self

        def farming(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = farm_eval(sub, state, ctx)
            t = time.perf_counter()
            cols = ctx.columns(state)
            if len(cols) and proposals:
                cap = labor_hours_columns(cols, ctx)
                debt = cols.get("labor_debt_hours")
                m = ctx.compiled.parameter("subsistence.max_farm_labor_share")[cols.species()]
                hpd = ctx.compiled.parameter("foraging.foraging_hours_per_day")[cols.species()]
                labor = cols.weighted(
                    {k: ctx.tables[s].labor for k, s in enumerate(ctx.compiled.species_ids)}
                )
                if not obs._ramp:
                    for k, s in enumerate(ctx.compiled.species_ids):
                        curve = ctx.tables[s].labor
                        obs._ramp[k] = np.maximum(np.diff(curve, prepend=0.0), 0.0)
                inflow = cols.weighted(obs._ramp)
                hours = proposals[0].hours
                for k, u in enumerate(cols.units):
                    h, c, d = float(hours[k]), float(cap[k]), float(debt[k])
                    tau = float(inflow[k] / labor[k]) if labor[k] > 0 else 0.0
                    f_min = min_participating_share(h, c, d, float(m[k]))
                    obs.farm[u.id] = {
                        "hours": h, "capacity": c, "debt": d, "m": float(m[k]),
                        "L": c / (float(hpd[k]) * 365.0), "tau": tau,
                    }  # fmt: skip
                    if h > 0:
                        obs.opportunity.append(
                            (u.id, state.year, f_min, h / max(c - d, 1e-300), tau)
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
            obs.events["fission"] += 1
            for s in obs.shadows:
                s.fission(parent_id, daughter.id)
            return daughter

        def merge_observed(
            population: Any, source_id: str, target_id: str, *args: Any, **kwargs: Any
        ) -> Any:
            n_t = population.units[target_id].population
            n_s = population.units[source_id].population
            out = merge(population, source_id, target_id, *args, **kwargs)
            obs.events["fusion"] += 1
            for s in obs.shadows:
                s.fusion(target_id, source_id, n_t, n_s)
            return out

        for owner, name, new in (
            (FarmingSubsystem, "evaluate", farming),
            (LearningSubsystem, "evaluate", learning),
            (groups, "split_unit", split_observed),
            (groups, "merge_units", merge_observed),
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
        idle = {"hours": 0.0, "capacity": 1.0, "debt": 0.0, "m": 0.9, "L": 0.0, "tau": 0.0}
        for k, u in enumerate(cols.units):
            rec = {
                **base,
                **self.farm.get(u.id, idle),
                "practice": float(practice[k]),
                "farm": float(shares["farming"][k]),
                "forage": float(shares["plant_foraging"][k]),
                "practitioners": float(population[k] * practice[k]),
                "speed": float(speed[k]),
                "retention": float(retention[k]),
            }
            for s in self.shadows:
                s.learn(u.id, rec, float(old[k]), float(new[k]))
        self.farm.clear()


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
        horizon = scenario.config.simulation.n_years
        years = 0
        for years in range(1, horizon + 1):
            sim.step()
            if years % PROGRESS_EVERY == 0:
                print(
                    f"  {name} seed {seed}: year {years}/{horizon}, {len(sim.state.units)} units, {time.perf_counter() - started:.0f} s",
                    flush=True,
                )
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
        "stats": {s.p.label: compact(s.stats) for s in shadows},
        "opportunity": observer.opportunity,
        "events": observer.events,
        "neutral": physical_digest(sim) == physical_digest(plain),
        "years": years,
        "horizon": horizon,
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


def _cat(ss: list[Stats], name: str) -> np.ndarray:
    parts = [np.asarray(getattr(s, name)) for s in ss]
    return np.concatenate(parts) if any(p.size for p in parts) else np.zeros(0)


def _truncated(result: dict[str, Any]) -> str:
    if "years" not in result or result["years"] >= result["horizon"]:
        return ""
    return f"  WARNING: ended at year {result['years']} of {result['horizon']} (no units left)"


def report(results: list[dict[str, Any]]) -> None:
    for name in SCENARIOS:
        rs = [r for r in results if r["name"] == name]
        if not rs:
            continue
        print(
            f"\n=== {name}, seeds {[r['seed'] for r in rs]}; observer neutral: {all(r['neutral'] for r in rs)}"
        )
        for r in rs:
            if _truncated(r):
                print(f"seed {r['seed']}{_truncated(r)}")
        opp = [o for r in rs for o in r["opportunity"]]
        f = np.array([o[2] for o in opp])
        print(
            f"farming unit-years {f.size}; P/(C-D) {q([o[3] for o in opp])}; f_min {q(f)}; turnover tau (new labor share / y) {q([o[4] for o in opp])}"
        )
        print(
            f"cultivation spells per unit (y): {q(spells([(o[0], o[1]) for o in opp]))}; fissions {sum(r['events']['fission'] for r in rs)}, fusions {sum(r['events']['fusion'] for r in rs)}"
        )
        labels = list(rs[0]["stats"])
        print("\nParticipation and the entry ledger (e = 50 h trajectories; farming unit-years)")
        print(
            "| shadow | participating p50/p90 | entrants / unit-year mean (p90) | incumbents kept p50 | free at zero cost mean | entry hours / C mean (p99) | infeasible | re-entries (former share of entrants p50) |"
        )
        print("|---|---|---|---|---|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            part, ent, ret = _cat(ss, "part"), _cat(ss, "entrants"), _cat(ss, "retained")
            ef, fr, rf = _cat(ss, "entry_frac"), _cat(ss, "free"), _cat(ss, "reentry_former")
            fy = max(sum(s.farming for s in ss), 1)
            print(
                f"| {label} | {q(part, (0.5, 0.9))} | {ent.mean() if ent.size else 0:.4f} ({np.quantile(ent, 0.9) if ent.size else 0:.3f}) "
                f"| {np.median(ret) if ret.size else float('nan'):.3f} | {fr.mean() if fr.size else 0:.3f} | {ef.mean() if ef.size else 0:.5f} ({np.quantile(ef, 0.99) if ef.size else 0:.4f}) "
                f"| {sum(s.infeasible for s in ss) / fy:.4f} | {sum(s.reentries for s in ss)} ({np.median(rf) if rf.size else float('nan'):.2f}) |"
            )
        print(
            "\nEntry-cost sensitivity (ledger re-allocated at each e on the same pre-allocation state): mean entry hours / C, infeasible share"
        )
        print("| shadow | " + " | ".join(f"e={e:g}" for e in E_SWEEP) + " |")
        print("|---|" + "---|" * len(E_SWEEP))
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            if not ss[0].ledger:
                continue
            cells = []
            for e in E_SWEEP:
                tot = [sum(s.ledger.get(e, [0, 0, 0])[i] for s in ss) for i in range(3)]
                n = max(tot[2], 1)
                cells.append(f"{tot[0] / n:.5f} / {tot[1] / n:.4f}")
            print(f"| {label} | " + " | ".join(cells) + " |")
        print("\nCompetence and representation")
        print(
            "| shadow | comps mean/p90/max | at cap | splits / unit-year (turnover) | tau merges | coalescences (cross-history) | history-mixed merges | E-gap part-non p50/p90 | share E-gap > 0.01/0.05/0.1 | K-gap p50 | dispersion p50/p90 | potential p50/p90 | redundant / unit-year (different history) | neutral max | lifetime p50/p90 |"
        )
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            comps = _cat(ss, "comps")
            uy = max(sum(s.unit_years for s in ss), 1)
            ge, gk, disp, pot = (
                _cat(ss, "gaps_e"),
                _cat(ss, "gaps_k"),
                _cat(ss, "dispersion"),
                _cat(ss, "potential"),
            )
            frac = " / ".join(f"{(ge > g).sum() / uy:.3f}" for g in GAPS)
            print(
                f"| {label} | {comps.mean():.2f}/{np.quantile(comps, 0.9):.0f}/{comps.max()} | {sum(s.at_cap for s in ss) / uy:.3f} "
                f"| {sum(s.splits for s in ss) / uy:.3f} ({sum(s.turnover_splits for s in ss) / uy:.3f}) | {sum(s.tau_merges for s in ss)} "
                f"| {sum(s.coalescences for s in ss)} ({sum(s.cross_history for s in ss)}) | {sum(s.history_mixed for s in ss)} "
                f"| {q(ge, (0.5, 0.9))} | {frac} | {np.median(gk) if gk.size else float('nan'):.2f} | {np.quantile(disp, 0.5):.3g}/{np.quantile(disp, 0.9):.3g} "
                f"| {q(pot, (0.5, 0.9))} | {sum(s.redundant for s in ss) / uy:.3f} ({sum(s.dup_diff_history for s in ss) / uy:.3f}) "
                f"| {max(s.neutral_max for s in ss):.1e} | {q(_cat(ss, 'lifetimes'), (0.5, 0.9))} |"
            )
        print("\nForced coalescence: K-distance choice vs efficiency choice")
        print(
            "| shadow | coalescences | E-variance loss (K metric) | (E metric) | argmin differs | Spearman(K, E-loss) p50 | Spearman(slope-weighted, E-loss) p50 |"
        )
        print("|---|---|---|---|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            n = sum(s.coalescences for s in ss)
            if not n:
                continue
            rc = [x for s in ss for x in np.asarray(s.rank_corr) if x == x]
            sc = [x for s in ss for x in np.asarray(s.slope_corr) if x == x]
            print(
                f"| {label} | {n} | {sum(s.coalesce_eff_loss for s in ss):.3g} | {sum(s.eff_loss_if_eff_metric for s in ss):.3g} "
                f"| {sum(s.metric_disagree for s in ss) / n:.2f} | {np.median(rc) if rc else float('nan'):.2f} | {np.median(sc) if sc else float('nan'):.2f} |"
            )
        print(
            "\nPersistence after cultivation stops (within-unit E spread >= 0.05): KM share not halved at 5/10/25/50 y"
        )
        print("| shadow | stop episodes | not halved 5/10/25/50 y |")
        print("|---|---|---|")
        for label in labels:
            ss = [r["stats"][label] for r in rs]
            stops = [x for s in ss for x in s.stop_halvings]
            print(
                f"| {label} | {len(stops)} | {' / '.join(f'{x:.2f}' for x in km(stops, (5, 10, 25, 50)))} |"
            )
        print(
            f"\ncost: run {sum(r['seconds'] for r in rs):.0f} s (observer {sum(r['observer_seconds'] for r in rs):.0f} s, {len(labels)} shadows); plain {sum(r['plain_seconds'] for r in rs):.0f} s"
        )


# ---------------------------------------------------------------- controlled


N_PEOPLE, C_TOY = 40, 40 * HOURS_PER_YEAR


def _toy_rec(s: float, model: KnowledgeModel, half: float) -> dict[str, float]:
    i = model.index["agriculture"]
    w = model.system.domains["agriculture"].practice
    p = s * C_TOY
    farm = p / C_TOY
    forage = (1 - farm) * 0.5
    practice = float(w["farming"]) * farm + float(w["plant_foraging"]) * forage
    return {
        "hours": p, "capacity": C_TOY, "debt": 0.0, "m": 0.9, "L": C_TOY / HOURS_PER_YEAR, "tau": 0.0,
        "practice": practice, "farm": farm, "forage": forage, "practitioners": N_PEOPLE * practice,
        "w_farm": float(w["farming"]), "w_forage": float(w["plant_foraging"]), "lr": float(model.learning_rate[i]),
        "scale": float(model.practitioner_scale[i]), "decay": float(model.decay_rate[i]), "speed": 1.0, "retention": 1.0,
    }  # fmt: skip


def _toy(
    policy: Policy,
    pattern: list[float],
    model: KnowledgeModel,
    half: float,
    start: Components | None,
    marks: tuple[int, ...],
) -> list[str]:
    """One 40-person unit through a demand pattern (cultivation share s = P / C per year)."""
    sh = Shadow(policy, half)
    k0 = float(model.initial_levels()[model.index["agriculture"]])
    c = start or Components(np.ones(1), np.array([k0]), np.array([NEVER]), np.zeros(1, bool))
    sh.units["u"] = Unit(c, np.zeros(c.share.size))
    k_unit = float((c.share * c.competence).sum())
    out = []
    for t, s in enumerate(pattern, start=1):
        sh.year = t
        rec = _toy_rec(s, model, half)
        k_new = float(
            learn_components(
                np.array([k_unit]),
                np.array([rec["practice"]]),
                rec["practitioners"],
                1.0,
                rec["lr"],
                rec["scale"],
                rec["decay"],
                1.0,
            )[0]
        )
        n_part = len(sh.stats.part)
        sh.learn("u", rec, k_unit, k_new)
        k_unit = k_new
        if t in marks:
            u = sh.units["u"].c
            e = efficiency(u.competence, half)
            inc = entry_factor(u.since, policy.memory) == 0.0
            ei = (
                float((u.share[inc] * e[inc]).sum() / u.share[inc].sum())
                if inc.any()
                else float("nan")
            )
            eo = (
                float((u.share[~inc] * e[~inc]).sum() / u.share[~inc].sum())
                if (~inc).any()
                else float("nan")
            )
            if len(sh.stats.part) > n_part:
                f, n = sh.stats.part[-1], sh.stats.entrants[-1]
                out.append(f"f{f:.2f} n{n:.2f} E{ei:.2f}/{eo:.2f}")
            else:
                out.append(f"- E{ei:.2f}/{eo:.2f}")
    return out


def controlled() -> None:
    scenario = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml")
    model = knowledge_model(scenario)
    half = float(model.half_efficiency[model.index["agriculture"]])
    budget = 0.9 * C_TOY
    l_toy = C_TOY / HOURS_PER_YEAR
    print(
        "Entry-cost optimum, 40 labor-equivalents, no debt. First entry (no history): f* and entry hours / C; incumbents h = 0.2 / 0.5 with demand s = P/(m C)"
    )
    print(
        "| s | e (h / entrant) | first entry f* (= overhead corner) | entry hours / C | h=0.2: entrants n | h=0.2: entry / C | h=0.5: f range at zero cost |"
    )
    print("|---|---|---|---|---|---|---|")
    for s in (0.1, 0.35, 0.6, 0.9):
        p = s * budget
        for e in E_SWEEP:
            a = allocate(np.ones(1), np.ones(1), p, C_TOY, 0.0, 0.9, e, l_toy)
            b = allocate(np.array([0.2, 0.8]), np.array([0.0, 1.0]), p, C_TOY, 0.0, 0.9, e, l_toy)
            h = allocate(np.array([0.5, 0.5]), np.array([0.0, 1.0]), p, C_TOY, 0.0, 0.9, e, l_toy)
            rng = (
                f"[{h.participating:.3f}, {h.participating + h.free:.3f}]"
                if h.free > 0
                else f"{h.participating:.3f} (n {h.entrants:.3f})"
            )
            fe = (
                f"{a.participating:.3f}"
                + ("" if e > 0 else " (indifferent)")
                + ("" if a.feasible else " INFEASIBLE")
            )
            print(
                f"| {s} | {e:g} | {fe} | {a.entry_hours / C_TOY:.4f} | {b.entrants:.3f}{'' if b.feasible else ' INFEASIBLE'} | {b.entry_hours / C_TOY:.4f} | {rng} |"
            )
    rot = ((0.4, 0.4), (0.4, 0.6), (0.6, 0.4))  # (last year's participants, needed share)
    print(
        "\nRotation vs continuity, entry labor per year (share of C) at e = 50: rotation redraws participants in proportion"
    )
    print(
        "| last year's participants h | needed f | continuity entrants | rotation entrants | continuity entry / C | rotation entry / C |"
    )
    print("|---|---|---|---|---|---|")
    for h, f in rot:
        p = f * budget  # demand that needs share f at e = 0
        a = allocate(np.array([h, 1 - h]), np.array([0.0, 1.0]), p, C_TOY, 0.0, 0.9, 50.0, l_toy)
        r = spread_allocation(
            np.array([h, 1 - h]),
            np.array([0.0, 1.0]),
            p,
            C_TOY,
            0.0,
            0.9,
            50.0,
            l_toy,
            everyone=False,
        )
        print(
            f"| {h} | {f} | {a.entrants:.3f} | {r.entrants:.3f} | {a.entry_hours / C_TOY:.4f} | {r.entry_hours / C_TOY:.4f} |"
        )

    marks = (1, 5, 25, 50, 100)
    k0 = float(model.initial_levels()[model.index["agriculture"]])

    def two(h: float, ka: float, kb: float, since_a: float) -> Components:
        """Two components: a share ``h`` last active ``since_a`` years ago, the rest never."""
        return Components(
            np.array([h, 1 - h]), np.array([ka, kb]), np.array([since_a, NEVER]), np.zeros(2, bool)
        )

    cases: list[tuple[str, list[float], Components | None]] = [
        ("1 homogeneous, no cultivation", [0.0] * 100, None),
        ("2 first encounter, s=0.35", [0.35] * 100, None),
        ("3 existing practitioners (h=0.4), stable s=0.35", [0.35] * 100, two(0.4, 1.0, 1.0, 1.0)),
        (
            "4 demand rises gradually 0.2 -> 0.6 (y1-40)",
            [0.2 + 0.4 * min(t / 40, 1) for t in range(100)],
            None,
        ),
        ("5 demand rises suddenly 0.2 -> 0.6 at y25", [0.2] * 24 + [0.6] * 76, None),
        (
            "6 demand falls gradually 0.6 -> 0.2 (y1-40)",
            [0.6 - 0.4 * min(t / 40, 1) for t in range(100)],
            None,
        ),
        ("7 cultivation stops at y25", [0.35] * 24 + [0.0] * 76, None),
        ("8 returns after 1 idle year (y25)", [0.35] * 24 + [0.0] + [0.35] * 75, None),
        ("9 returns after 30 idle years (y25-54)", [0.35] * 24 + [0.0] * 30 + [0.35] * 46, None),
        ("10 incumbents exceed demand (h=0.8, s=0.2)", [0.2] * 100, two(0.8, 1.0, 1.0, 1.0)),
        ("11 incumbents insufficient (h=0.2, s=0.6)", [0.6] * 100, two(0.2, 1.0, 1.0, 1.0)),
        (
            "12 fusion competence difference, no history (K 3 / 1)",
            [0.35] * 100,
            two(0.5, 3.0, 1.0, NEVER),
        ),
        ("13 equal competence, different histories", [0.35] * 100, two(0.4, k0, k0, 1.0)),
        ("15 zero entry cost (e = 0)", [0.35] * 100, None),
    ]
    pols = [
        Policy("M0"),
        Policy("M1"),
        Policy("M2"),
        Policy("M2", retain=True),
        Policy("M2", memory=W10),
        Policy("M3"),
    ]
    print(
        f"\nSingle-unit trajectories (40 people, e = {E_RUN:g} h unless stated); cells at years {marks}: f participating, n entrants, E incumbents/others (incumbent = zero entry cost next year)"
    )
    for label, pattern, start in cases:
        print(f"\n{label}")
        for pol in pols:
            if label.startswith("15"):
                pol = Policy(pol.model, pol.memory, pol.retain, entry=0.0)
            cells = _toy(pol, pattern, model, half, start, marks)
            print(f"  {pol.label:<16} " + " | ".join(cells))
    print("\n14 high entry cost with insufficient free labor (e = 1500 h, s = 0.85): first entry")
    a = allocate(np.ones(1), np.ones(1), 0.85 * C_TOY, C_TOY, 0.0, 0.9, 1500.0, l_toy)
    print(
        f"  feasible {a.feasible}; shortfall {a.shortfall_hours:.0f} h ({a.shortfall_hours / C_TOY:.3f} of C): entry labor would displace production"
    )

    print(
        "\nHysteresis: demand 0.2 (y1-20) -> 0.6 (y21-40) -> 0.2 (y41-60) -> 0.6 (y61-80); f and entrants at years 20/40/60/80 and at y21/y61 (rises)"
    )
    cycle = [0.2] * 20 + [0.6] * 20 + [0.2] * 20 + [0.6] * 20
    for pol in (
        Policy("M0"),
        Policy("M1"),
        Policy("M2"),
        Policy("M2", retain=True),
        Policy("M2", memory=W10),
        Policy("M2", memory=H10),
    ):
        cells = _toy(pol, cycle, model, half, None, (20, 21, 40, 60, 61, 80))
        print(f"  {pol.label:<16} " + " | ".join(cells))


# ---------------------------------------------------------------- main


def load_results(path: Path) -> list[dict[str, Any]]:
    results = []
    for file in sorted(path.glob("*.pkl")):
        with file.open("rb") as f:
            results.append(pickle.load(f))
    return sorted(results, key=lambda r: (r["name"], r["seed"]))


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
        report(load_results(args.load))
        return
    specs = [(name, seed) for name in SCENARIOS for seed in args.seeds]
    out = args.out
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        specs = [sp for sp in specs if not (out / f"{sp[0]}_{sp[1]}.pkl").exists()]
    started = time.perf_counter()
    results = []
    with Pool(args.jobs, initializer=_set_years, initargs=(args.years,)) as pool:
        for result in pool.imap_unordered(job, specs, chunksize=1):
            print(
                f"done {result['name']} seed {result['seed']} after {time.perf_counter() - started:.0f} s{_truncated(result)}",
                flush=True,
            )
            if out is not None:
                with (out / f"{result['name']}_{result['seed']}.pkl").open("wb") as f:
                    pickle.dump(result, f)
            results.append(result)
    report(load_results(out) if out is not None else results)


if __name__ == "__main__":
    main()
