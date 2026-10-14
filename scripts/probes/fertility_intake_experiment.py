# The report tables keep one entry per line.
# ruff: noqa: E501
"""Fertility input: harvest adequacy (H0) vs dietary intake (H1). MVP 3 Stage 5I.

EXPERIMENTAL / OPT-IN / NOT CANONICAL.

The canonical simulator is never modified. A branch is one ``Simulator`` whose pipeline has
two subsystem *instances* replaced by subclasses defined here:

- ``BranchEnergetics`` runs the production energetics unchanged and, from the very inputs it
  used (requirement, harvest after trade, stores after trade, reserves), computes dietary
  intake (``population/dietary_intake.py``) and diagnostics. It changes no state.
- ``BranchDemography`` runs the production demography unchanged except for the fertility
  input: for the duration of its ``evaluate`` the ``food_ratio`` column holds the branch's
  input (H0: the authoritative value itself; H1: dietary intake), and the authoritative
  column is restored bit for bit before the proposal is applied. Starvation (deficit),
  fission and innovation keep reading the authoritative ``food_ratio`` / deficit.
- ``ObservingTrade`` records donors and recipients only.

Modes:

``controlled``  deterministic accounting cases;
``run``         canonical, experimental-H0 and experimental-H1 runs of the reference
                scenarios (one file per run), with per-year hashes and diagnostics;
``analyse``     exactness, first divergence, same-state incidence and expected births, and
                the branched outcomes.

Usage:
    uv run python scripts/probes/fertility_intake_experiment.py controlled
    uv run python scripts/probes/fertility_intake_experiment.py run [--jobs 2] [--seeds ...] --out DIR
    uv run python scripts/probes/fertility_intake_experiment.py analyse --load DIR
"""

import argparse
import hashlib
import pickle
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS, physical_digest, q, scenario_for

from madexplorer.core.simulation import Simulator
from madexplorer.economy.trade import TradeSubsystem
from madexplorer.metrics.recorder import MetricsRecorder
from madexplorer.population.demography import (
    DemographySubsystem,
    fertility_multiplier,
    mate_available,
    mortality_hazards,
)
from madexplorer.population.dietary_intake import (
    dietary_intake_ratio,
    harvest_adequacy,
    net_sufficiency,
    reserve_drawdown,
    store_withdrawal,
)
from madexplorer.population.energetics import EnergeticsSubsystem, energy_balance
from madexplorer.population.health import crowding_hazard_columns

SCENARIOS = ("neolithic", "pressure+cult")
MODES = ("canonical", "h0", "h1")
TECH = "plant_cultivation"

# ---------------------------------------------------------------- the branch


class Branch:
    """Per-simulator side channel between the two replaced subsystems (one year at a time)."""

    def __init__(self, mode: str) -> None:
        if mode not in ("h0", "h1"):
            raise ValueError(f"unknown fertility input {mode!r}")
        self.mode = mode
        self.intake: dict[str, float] = {}
        self.energy: dict[str, tuple[float, ...]] = {}
        self.roles: dict[str, str] = {}
        self.years: list[dict[str, Any]] = []
        self.restore_failures = 0


class BranchEnergetics(EnergeticsSubsystem):
    def __init__(self, branch: Branch) -> None:
        self.branch = branch

    def evaluate(self, state: Any, ctx: Any) -> Any:
        proposals = super().evaluate(state, ctx)
        self.branch.intake, self.branch.energy = {}, {}
        if proposals:
            u = proposals[0]
            cols = u.cols
            harvest, stores = cols.get("harvest_kcal"), cols.get("stores_kcal")
            people = cols.population().astype(np.float64)
            reserve = cols.get("reserve_kcal_per_capita") * people
            intake = dietary_intake_ratio(u.need_kcal, harvest, stores)
            withdrawn = store_withdrawal(u.need_kcal, harvest, stores)
            drawn = reserve_drawdown(u.need_kcal, harvest, stores, reserve)
            h0 = harvest_adequacy(u.need_kcal, harvest)
            for k, unit in enumerate(cols.units):
                self.branch.intake[unit.id] = float(intake[k])
                self.branch.energy[unit.id] = (
                    float(u.need_kcal[k]), float(harvest[k]), float(stores[k]), float(withdrawn[k]),
                    float(drawn[k]), float(u.deficit[k]), float(h0[k]), float(intake[k]),
                    float(u.food_ratio[k]), int(people[k]),
                )  # fmt: skip
        return proposals


class BranchDemography(DemographySubsystem):
    def __init__(self, branch: Branch) -> None:
        self.branch = branch

    def evaluate(self, state: Any, ctx: Any) -> Any:
        cols = ctx.columns(state)
        original = cols.get("food_ratio")  # a copy
        if self.branch.mode == "h1":
            used = np.array(
                [
                    self.branch.intake.get(u.id, f)
                    for u, f in zip(cols.units, original.tolist(), strict=True)
                ]
            )
        else:
            used = original.copy()
        self._diagnose(state, ctx, cols, original, used)
        cols.set("food_ratio", used)
        try:
            proposals = super().evaluate(state, ctx)
        finally:
            cols.set("food_ratio", original)
        if not np.array_equal(cols.get("food_ratio"), original, equal_nan=True):
            self.branch.restore_failures += 1
        return proposals

    def _diagnose(self, state: Any, ctx: Any, cols: Any, h0: np.ndarray, used: np.ndarray) -> None:
        """Same-state expected births under the H0 and H1 inputs (no draws)."""
        branch = self.branch
        intake = np.array(
            [branch.intake.get(u.id, f) for u, f in zip(cols.units, h0.tolist(), strict=True)]
        )
        codes = cols.species()
        crowding_all = (
            crowding_hazard_columns(cols.population().astype(np.float64), cols.get("groups"),
                                    cols.get("residence_years"), cols.get("cell"), codes,
                                    {sid: p.health for sid, p in ctx.scenario.species.items()},
                                    state.world.cell_area_km2)
            if ctx.mechanisms.crowding_mortality else np.zeros(len(cols))
        )  # fmt: skip
        exp0 = exp1 = 0.0
        m0_all, m1_all, fem_all = [], [], []
        for code, species_id in enumerate(ctx.compiled.species_ids):
            rows = np.flatnonzero(codes == code)
            if rows.size == 0:
                continue
            sub = cols.subset(rows) if rows.size < len(cols) else cols
            profile, tables = ctx.species(species_id), ctx.tables[species_id]
            met, lh = profile.metabolism, profile.life_history
            sens = (
                met.starvation_mortality_sensitivity if ctx.mechanisms.starvation_mortality else 0.0
            )
            females, males = sub.cohorts(tables.need_fraction.size)
            hazard, _ = mortality_hazards(
                tables, sub.get("energy_deficit"), sens, crowding_all[rows]
            )
            survive = np.exp(-hazard)
            mate = mate_available(
                males, sub.get("cell"), state.world.n_cells, tables, lh.sexual_reproduction
            )
            m0 = fertility_multiplier(
                h0[rows], met.fertility_food_midpoint, met.fertility_food_scale
            )
            m1 = fertility_multiplier(
                intake[rows], met.fertility_food_midpoint, met.fertility_food_scale
            )
            for m, acc in ((m0, 0), (m1, 1)):
                p = np.clip(tables.fertility[None, :] * (m * mate)[:, None], 0.0, 1.0)
                e = float((females * survive * p).sum()) * lh.offspring_per_birth
                if acc == 0:
                    exp0 += e
                else:
                    exp1 += e
            m0_all += m0.tolist()
            m1_all += m1.tolist()
            fem_all += (females * tables.fertility[None, :]).sum(axis=1).tolist()
        energy = branch.energy
        units = [u.id for u in cols.units]
        branch.years.append({
            "year": state.year, "exp_births_h0": exp0, "exp_births_h1": exp1,
            "units": [(uid, m0_all[k], m1_all[k], fem_all[k], energy.get(uid), branch.roles.get(uid, "none"))
                      for k, uid in enumerate(units)],
        })  # fmt: skip


class ObservingTrade(TradeSubsystem):
    """Production trade; records who gave and who received (no behavior change)."""

    def __init__(self, branch: Branch) -> None:
        self.branch = branch

    def evaluate(self, state: Any, ctx: Any) -> Any:
        proposals = super().evaluate(state, ctx)
        roles: dict[str, str] = {}
        for t in proposals[0].transfers if proposals else ():
            roles[t.donor_id] = "donor" if roles.get(t.donor_id, "donor") == "donor" else "both"
            roles[t.recipient_id] = (
                "recipient" if roles.get(t.recipient_id, "recipient") == "recipient" else "both"
            )
        self.branch.roles = roles
        return proposals


def branched_simulator(scenario: Any, mode: str) -> tuple[Simulator, Branch | None]:
    """A simulator with the fertility input ``mode`` ("canonical", "h0" or "h1")."""
    sim = Simulator(scenario)
    if mode == "canonical":
        return sim, None
    branch = Branch(mode)
    swaps = {EnergeticsSubsystem: BranchEnergetics, DemographySubsystem: BranchDemography,
             TradeSubsystem: ObservingTrade}  # fmt: skip
    replaced = 0
    for i, sub in enumerate(sim.pipeline):
        cls = swaps.get(type(sub))
        if cls is not None:
            sim.pipeline[i] = cls(branch)
            replaced += 1
    if replaced != len(swaps):
        raise RuntimeError(f"expected to replace {len(swaps)} subsystems, replaced {replaced}")
    return sim, branch


# ---------------------------------------------------------------- runs


def _hashes(sim: Simulator) -> dict[str, str]:
    """Per-year state hashes by component (RNG streams, cohorts, food, the rest)."""
    out = {}
    for name in sorted(sim.rng._streams):
        out[f"rng:{name}"] = hashlib.sha256(
            repr(sim.rng.stream(name).bit_generator.state).encode()
        ).hexdigest()[:16]
    h_coh, h_food, h_rest, h_know = (
        hashlib.sha256(),
        hashlib.sha256(),
        hashlib.sha256(),
        hashlib.sha256(),
    )
    for unit in sim.state.units.values():
        h_coh.update(
            unit.id.encode()
            + np.ascontiguousarray(unit.females).tobytes()
            + np.ascontiguousarray(unit.males).tobytes()
        )
        h_food.update(
            repr(
                (unit.id, unit.stores_kcal, unit.food_ratio, unit.energy_deficit, unit.harvest_kcal)
            ).encode()
        )
        h_rest.update(
            repr((unit.id, unit.cell, unit.fields_ha, sorted(unit.technologies))).encode()
        )
        h_know.update(unit.id.encode() + np.ascontiguousarray(unit.knowledge).tobytes())
    out["cohorts"] = h_coh.hexdigest()[:16]
    out["food"] = h_food.hexdigest()[:16]
    out["rest"] = h_rest.hexdigest()[:16]
    out["knowledge"] = h_know.hexdigest()[:16]
    return out


def run_job(spec: tuple[str, int, str]) -> dict[str, Any]:
    name, seed, mode = spec
    scenario = scenario_for(name, seed, 0.0)
    sim, branch = branched_simulator(scenario, mode)
    recorder = MetricsRecorder(scenario, 10**9, light=False)
    rows, hashes = [], []
    started = time.perf_counter()
    for _ in range(scenario.config.simulation.n_years):
        ctx = sim.step()
        rows.append(recorder.record(sim.state, ctx))
        hashes.append(_hashes(sim))
        if not sim.state.units:
            break
    held = sum(u.population for u in sim.state.units.values() if TECH in u.technologies)
    total = sum(u.population for u in sim.state.units.values())
    first_invention = next(
        (e.year for e in sim.events if e.kind == "invention" and e.data.get("technology") == TECH),
        None,
    )
    first_cultivation = next((e.year for e in sim.events if e.kind == "cultivation_started"), None)
    return {
        "name": name, "seed": seed, "mode": mode, "rows": rows, "hashes": hashes,
        "digest": physical_digest(sim), "seconds": time.perf_counter() - started,
        "years": [] if branch is None else branch.years,
        "restore_failures": 0 if branch is None else branch.restore_failures,
        "final": {"population": total, "units": len(sim.state.units), "tech_share": held / total if total else 0.0,
                  "first_invention": first_invention, "first_cultivation": first_cultivation},
    }  # fmt: skip


# ---------------------------------------------------------------- analysis


MID, SCALE = 0.8, 0.1
FULL = 1.0 - 1e-12  # stores that close the gap exactly can leave (H + X) / N one ulp below 1


def fert(x: np.ndarray | float) -> np.ndarray:
    return fertility_multiplier(np.atleast_1d(np.asarray(x, dtype=float)), MID, SCALE)


def first_divergence(
    a: list[dict[str, str]], b: list[dict[str, str]]
) -> tuple[int | None, list[str]]:
    for k, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return k + 1, sorted(key for key in x if x[key] != y.get(key))
    return None, []


def observe(runs: list[dict[str, Any]]) -> None:
    """Same-state incidence on the authoritative history (the H0 branch's diagnostics)."""
    rows = []
    exp0 = exp1 = 0.0
    births_actual = 0.0
    for r in runs:
        for y, row in zip(r["years"], r["rows"], strict=False):
            exp0 += y["exp_births_h0"]
            exp1 += y["exp_births_h1"]
            births_actual += row["births"]
            for _uid, m0, m1, fem, energy, role in y["units"]:
                if energy is None:
                    continue
                need, _h, _st, x, drawn, deficit, h0, h1, fr, pop = energy
                if need <= 0:
                    continue
                rows.append(
                    (role, pop, m0, m1, fem, h0, h1, 1.0 - deficit, x / need, drawn / need, fr)
                )
    a = np.array([r[1:] for r in rows], dtype=float)
    role = np.array([r[0] for r in rows])
    pop, m0, m1, fem, h0, h1, h2, xs, rs, fr = a.T
    check = np.max(np.abs(h0 - fr))
    print(
        f"   unit-years {len(rows)}; H0 reconstruction vs authoritative food_ratio: max |diff| {check:.1e}"
    )
    dm = m1 - m0
    print(
        "   group        n        H0==H1  |dm|>0.01  |dm|>0.10  H0<1 & intake>=1  reserves cover a dietary shortfall  stores >= 5% of need  pop share"
    )
    for g in ("all", "donor", "recipient", "both", "none"):
        sel = np.ones(len(role), dtype=bool) if g == "all" else role == g
        if not sel.any():
            continue
        agree = (h0[sel] == h1[sel]).mean()
        print(f"   {g:<12} {sel.sum():<8} {agree:.4f}  {(np.abs(dm[sel]) > 0.01).mean():.4f}     {(np.abs(dm[sel]) > 0.10).mean():.4f}     "
              f"{((h0[sel] < 1) & (h1[sel] >= FULL)).mean():.4f}            {((h1[sel] < FULL) & (rs[sel] > 0)).mean():.4f}                              "
              f"{(xs[sel] >= 0.05).mean():.4f}               {pop[sel].sum() / pop.sum():.3f}")  # fmt: skip
    w = pop / pop.sum()
    print(
        f"   population-weighted: |dm| > 0.01 {np.sum(w * (np.abs(dm) > 0.01)):.4f}; > 0.10 {np.sum(w * (np.abs(dm) > 0.10)):.4f}; H0<1 & intake>=1 {np.sum(w * ((h0 < 1) & (h1 >= FULL))):.4f}"
    )
    big = dm[np.abs(dm) > 0.01]
    print(
        f"   multiplier change where |dm| > 0.01: p50/p90/p99 {q(big)}; never negative: {bool((dm >= -1e-15).all())}"
    )
    print(f"   reconciliation with 5H: H0<1 & deficit=0 {np.mean((h0 < 1) & (h2 >= 1)):.4f}; H0<1 & intake>=1 (stores actually eaten cover) {np.mean((h0 < 1) & (h1 >= FULL)):.4f}; "
          f"H0<1 & intake<1 & deficit=0 (reserves close the gap) {np.mean((h0 < 1) & (h1 < FULL) & (h2 >= 1)):.4f}")  # fmt: skip
    print(
        f"   H2 (1 - deficit) vs H1 (intake): H2 > H1 in {np.mean(h2 > h1 + 1e-12):.4f} of unit-years (reserve compensation)"
    )
    fw = fem / max(fem.sum(), 1e-12)
    print(
        f"   fertility-weighted mean multiplier: H0 {np.sum(fw * m0):.4f} -> H1 {np.sum(fw * m1):.4f}"
    )
    print(
        f"   same-state expected births: H0 {exp0:.0f}, H1 {exp1:.0f} (+{100 * (exp1 / exp0 - 1):.2f} %); realized births on the same history {births_actual:.0f}"
    )


def outcomes(name: str, runs: list[dict[str, Any]]) -> None:
    by = defaultdict(dict)
    for r in runs:
        by[r["seed"]][r["mode"]] = r
    print(
        f"\n-- branched outcomes ({name}): EXPERIMENTAL / OPT-IN / NOT CANONICAL; per seed H0 (canonical) -> H1"
    )

    def series(r: dict[str, Any], key: str) -> np.ndarray:
        return np.array([row[key] for row in r["rows"]], dtype=float)

    keys = ("population", "births", "deaths", "units", "mean_group_size", "fissions", "fusions", "extinctions", "migrations",
            "mean_energy_deficit", "mean_food_ratio", "stores_per_capita_kcal", "cultivated_ha", "farm_share_of_harvest",
            "trade_volume_kcal", "trade_share_of_harvest", "inventions", "adoptions", "plant_stock_fraction", "game_stock_fraction",
            "crude_birth_rate", "crude_death_rate", "harvest_to_need", "mean_age", "mean_crowding_hazard")  # fmt: skip
    table: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for seed in sorted(by):
        h0, h1 = by[seed]["canonical"], by[seed]["h1"]
        n = min(len(h0["rows"]), len(h1["rows"]))
        for key in keys:
            if key not in h0["rows"][0]:
                continue
            a, b = series(h0, key)[:n], series(h1, key)[:n]
            if key in (
                "births",
                "deaths",
                "fissions",
                "fusions",
                "extinctions",
                "migrations",
                "inventions",
                "adoptions",
                "trade_volume_kcal",
            ):
                table[f"{key} (cumulative)"].append((a.sum(), b.sum()))
            else:
                table[f"{key} (final 50 y mean)"].append((a[-50:].mean(), b[-50:].mean()))
        for t in (100, 200, 400, 600):
            if t <= n:
                table[f"population at year {t}"].append(
                    (series(h0, "population")[t - 1], series(h1, "population")[t - 1])
                )
        for key in ("first_invention", "first_cultivation", "tech_share"):
            a, b = h0["final"][key], h1["final"][key]
            if a is not None and b is not None:
                table[f"final {key}"].append((float(a), float(b)))
    print(
        "   quantity                                   H0 seeds                          H1 seeds                          paired ratio H1/H0 (min..max)"
    )
    for key, pairs in table.items():
        a = np.array([p[0] for p in pairs])
        b = np.array([p[1] for p in pairs])
        ratio = np.where(a != 0, b / np.where(a != 0, a, 1), np.nan)

        def fmt(v: np.ndarray) -> str:
            return " ".join(f"{x:9.4g}" for x in v)

        print(
            f"   {key:<42} {fmt(a):<33} {fmt(b):<33} {np.nanmedian(ratio):.3f} ({np.nanmin(ratio):.3f}..{np.nanmax(ratio):.3f})"
        )
    # time profile of the population ratio
    print("   population ratio H1/H0 over time (median over seeds): " + ", ".join(
        f"y{t}: {np.median([by[s]['h1']['rows'][t - 1]['population'] / max(by[s]['canonical']['rows'][t - 1]['population'], 1) for s in by if len(by[s]['h1']['rows']) >= t and len(by[s]['canonical']['rows']) >= t]):.3f}"
        for t in (10, 25, 50, 100, 200, 300, 400, 500, 600) if all(len(by[s]["h1"]["rows"]) >= t for s in by)))  # fmt: skip


def _rows_equal(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """Metric rows equal, NaN equal to NaN."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b, strict=True):
        if x.keys() != y.keys():
            return False
        for k in x:
            u, v = x[k], y[k]
            if u != v and not (
                isinstance(u, float) and isinstance(v, float) and np.isnan(u) and np.isnan(v)
            ):
                return False
    return True


def analyse_main(load: Path) -> None:
    runs = []
    for path in sorted(load.glob("*.pkl")):
        with path.open("rb") as fh:
            runs.append(pickle.load(fh))
    print(f"loaded {len(runs)} runs")
    for name in SCENARIOS:
        group = [r for r in runs if r["name"] == name]
        if not group:
            continue
        print(f"\n=== {name} (seeds {sorted({r['seed'] for r in group})})")
        by = defaultdict(dict)
        for r in group:
            by[r["seed"]][r["mode"]] = r
        print("-- experimental H0 vs canonical (exactness)")
        for seed, m in sorted(by.items()):
            c, h0 = m["canonical"], m["h0"]
            div, parts = first_divergence(c["hashes"], h0["hashes"])
            same_rows = _rows_equal(c["rows"], h0["rows"])
            print(f"   seed {seed}: final physical digest identical {c['digest'] == h0['digest']}; per-year hashes identical {div is None}; metrics rows identical {same_rows}; "
                  f"column restore failures {h0['restore_failures']}")  # fmt: skip
        print("-- first H1 divergence from canonical")
        for seed, m in sorted(by.items()):
            c, h1, h0 = m["canonical"], m["h1"], m["h0"]
            div, parts = first_divergence(c["hashes"], h1["hashes"])
            first_dm = next(
                (y["year"] for y in h0["years"] if any(abs(u[2] - u[1]) > 0 for u in y["units"])),
                None,
            )
            print(f"   seed {seed}: first year with any H1 != H0 multiplier {first_dm}; first state divergence year {div}; components differing then: {parts}; "
                  f"H1 column restore failures {h1['restore_failures']}")  # fmt: skip
        print("-- same-state incidence and direct effect (authoritative history)")
        observe([m["h0"] for m in by.values()])
        outcomes(name, group)


# ---------------------------------------------------------------- controlled cases


def controlled() -> None:
    need, cap = 100.0, 30.0
    # (label, harvest after trade, stores after trade, reserve)
    cases = [
        ("1 adequate current harvest", 110.0, 0.0, 10.0),
        ("2 stores cover a short harvest", 70.0, 50.0, 10.0),
        ("3 body reserves cover a shortfall", 80.0, 5.0, 20.0),
        ("4 donor ships 30 of 120, stores cover", 90.0, 40.0, 10.0),
        ("5 donor ships, genuine dietary shortage", 70.0, 5.0, 5.0),
        ("6 recipient rescued (70 own + 30 received)", 100.0, 0.0, 5.0),
        ("7 recipient still underfed (50 + 20 received)", 70.0, 0.0, 5.0),
        ("8a equal intake: all harvest", 100.0, 0.0, 0.0),
        ("8b equal intake: 60 harvest + 40 stores", 60.0, 40.0, 0.0),
        ("9 adequate stores, very low harvest", 10.0, 500.0, 0.0),
        ("10 shipment partly from stores (stores 50 -> 20)", 60.0, 20.0, 30.0),
        ("12 partial reserve compensation", 60.0, 10.0, 15.0),
    ]
    print(
        "case                                              H0 ratio  H1 intake  H2 1-def  X/N    R/N    deficit  fert H0  fert H1"
    )
    for label, h, s, r in cases:
        n, hh, ss, rr = (np.array([v]) for v in (need, h, s, r))
        b = energy_balance(need, h, r, cap, s, True)
        h0, h1 = harvest_adequacy(n, hh)[0], dietary_intake_ratio(n, hh, ss)[0]
        x, d = store_withdrawal(n, hh, ss)[0], reserve_drawdown(n, hh, ss, rr)[0]
        assert abs((s - b.stores_kcal) - x) < 1e-12 if h < need else True
        print(
            f"{label:<49} {h0:<9.3f} {h1:<10.3f} {net_sufficiency(np.array([b.deficit]))[0]:<9.3f} {x / need:<6.2f} {d / need:<6.2f} {b.deficit:<8.3f} {fert(h0)[0]:<8.3f} {fert(h1)[0]:.3f}"
        )
    for n in (0.0, 1e-300):
        print(
            f"11 need {n:g}: H0 {harvest_adequacy(np.array([n]), np.array([0.0]))[0]:.3f}, H1 {dietary_intake_ratio(np.array([n]), np.array([0.0]), np.array([5.0]))[0]:.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("controlled", "run", "analyse"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--seeds", type=int, nargs="*", default=list(SEEDS))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--load", type=Path)
    args = parser.parse_args()
    if args.mode == "controlled":
        controlled()
        return
    if args.mode == "analyse":
        analyse_main(args.load)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    specs = [
        (n, s, m)
        for n in SCENARIOS
        for s in args.seeds
        for m in MODES
        if not (args.out / f"{n}_{s}_{m}.pkl").exists()
    ]
    started = time.perf_counter()
    with Pool(args.jobs) as workers:
        for r in workers.imap_unordered(run_job, specs, chunksize=1):
            print(
                f"done {r['name']} seed {r['seed']} {r['mode']} after {time.perf_counter() - started:.0f} s ({r['seconds']:.0f} s); final population {r['final']['population']}",
                flush=True,
            )
            with (args.out / f"{r['name']}_{r['seed']}_{r['mode']}.pkl").open("wb") as fh:
                pickle.dump(r, fh)


if __name__ == "__main__":
    main()
