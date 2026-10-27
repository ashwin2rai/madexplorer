# The report tables keep one entry per line.
# ruff: noqa: E501
"""Socioecological opportunity structure: resource access, coordination, risk pooling
(MVP 3 Stage 6B). Observation only. READ-ONLY / NOT ACTIVE.

``record`` runs the MVP 2.2 reference scenarios with three read-only hooks:

- ``ForagingSubsystem.evaluate``: every cell's wild stocks and capacities before harvest;
  each unit's need, labor, efficiency, foraging target, fields, crop, stores, cell and
  population; each (cell, species) foraging group with its members and the authoritative
  harvest; analyst-computed outside options (true accessible stock per prospective head in
  every reachable cell) and the occupied cells in reach;
- ``FieldPlanningSubsystem.evaluate``: fields before and after planning (arable sharing);
- ``migration.gather_candidates``: the cells each unit actually believes in, with believed
  food and others (actor-known outside options).

``analyse`` replays pooled foraging exactly (``economy/opportunity_audit.py``) and computes
the pathway measures (pre-registered in the design document §AE): A resource access and
rivalry, B pooled vs independent use, C complementary shortage and surplus.

Usage:
    uv run python scripts/probes/opportunity_audit.py record [--jobs 2] [--seeds 0 1 2 3] --out DIR
    uv run python scripts/probes/opportunity_audit.py analyse --load DIR [--jobs 2]
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

from _common import SEEDS, physical_digest

import madexplorer.mobility.migration as migration
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.ecology.resources import logistic_regrowth
from madexplorer.economy.agriculture import HECTARES_PER_KM2, FieldPlanningSubsystem
from madexplorer.economy.foraging import ForagingSubsystem
from madexplorer.economy.opportunity_audit import (
    alone_harvest,
    gini,
    independent_harvest,
    pooled_harvest,
    regrowth_loss,
)
from madexplorer.economy.trade import delivered_fraction
from madexplorer.population.energetics import annual_need_columns

MVP2_2 = {
    "neolithic": ("scenarios/mvp2_2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 400, {"mechanisms.cultivation": True}),
}
LATER = 10  # years ahead for later shortage and assistance


def scenario(name: str, seed: int) -> Scenario:
    path, horizon, settings = MVP2_2[name]
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=horizon)
    return base.with_settings(settings) if settings else base


# ---------------------------------------------------------------- recording


class Recorder:
    def __init__(self) -> None:
        self.years: list[dict[str, Any]] = []
        self.static: dict[str, Any] = {}
        self.known: dict[int, dict[str, tuple[int, float, float, float]]] = {}
        self._saved: dict[str, Any] = {}

    def install(self) -> None:
        rec = self
        forage0 = ForagingSubsystem.evaluate
        plan0 = FieldPlanningSubsystem.evaluate
        gather0 = migration.gather_candidates

        def forage(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = forage0(sub, state, ctx)
            if not proposals:
                return proposals
            cols = ctx.columns(state)
            inputs = sub._inputs(state, ctx)
            eco = state.ecology
            sid = cols.units[0].species_id
            pa, ga, pr, gr = ctx.forage[sid].as_tuple()
            if not rec.static:
                cfg = ctx.scenario.config
                rec.static = {
                    "plant_access": pa.copy(), "game_access": ga.copy(), "plant_return": pr.copy(),
                    "game_return": gr.copy(), "arable": np.asarray(ctx.arable_ha, dtype=float).copy(),
                    "land": ~state.world.is_water, "cell_ha": state.world.cell_area_km2 * HECTARES_PER_KM2,
                    "plant_rate": cfg.ecology.plant_regrowth_rate_per_year,
                    "game_rate": cfg.ecology.game_regrowth_rate_per_year,
                    "recol": cfg.ecology.recolonization_fraction,
                    "plant_disp": cfg.agriculture.wild_plant_displacement,
                    "game_disp": cfg.agriculture.wild_game_displacement,
                    "decay": cfg.trade.transport_decay_km,
                }  # fmt: skip
            accessible = eco.plant_stock_kcal * pa + eco.game_stock_kcal * ga
            need = annual_need_columns(cols, state, ctx).tolist()
            people = cols.population().astype(float)
            cells = cols.get("cell").tolist()
            ids = [u.id for u in cols.units]
            occupants: dict[int, float] = defaultdict(float)
            for c, n in zip(cells, people.tolist(), strict=True):
                occupants[c] += n
            p = proposals[0]
            harvest = dict.fromkeys(ids, 0.0)
            rows = p.rows.tolist()
            for k, r in enumerate(rows):
                harvest[ids[r]] = float(p.harvest_kcal[k])
            groups = []
            for g, cell in enumerate(p.cells):
                members = [ids[r] for r in rows[p.bounds[g] : p.bounds[g + 1]]]
                groups.append((cell, members, p.plant_removed_kcal[g], p.game_removed_kcal[g]))
            units = {}
            farm = cols.get("farm_harvest_kcal").tolist()
            stores = cols.get("stores_kcal").tolist()
            fields = cols.get("fields_ha").tolist()
            for k, uid in enumerate(ids):
                reach = ctx.movement[cols.units[k].species_id].reachable(cells[k])
                rc = np.fromiter(reach.keys(), dtype=np.int64)
                cost = np.fromiter(reach.values(), dtype=np.float64)
                own = people[k]
                home_heads = occupants[cells[k]]
                alt = rc != cells[k]
                heads = np.array([occupants.get(c, 0.0) for c in rc.tolist()]) + own
                per_head = accessible[rc] / np.maximum(heads, 1.0)
                home = accessible[cells[k]] / max(home_heads, 1.0)
                if alt.any():
                    j = int(np.argmax(np.where(alt, per_head, -1.0)))
                    best, best_cost = float(per_head[j]), float(cost[j])
                    better = float((per_head[alt] >= home).mean())
                else:
                    best, best_cost, better = 0.0, 0.0, 0.0
                occupied = [(int(c), float(x)) for c, x in zip(rc.tolist(), cost.tolist(), strict=True)
                            if c != cells[k] and c in occupants]  # fmt: skip
                units[uid] = {
                    "cell": cells[k], "people": own, "need": need[k], "labor": float(inputs.labor[k]),
                    "eff": float(inputs.efficiency[k]), "target": float(inputs.target_share[k]),
                    "farm": farm[k], "forage": harvest[uid], "stores": stores[k], "fields": fields[k],
                    "home_per_head": float(home), "best_alt": best, "best_cost": best_cost,
                    "share_better": better, "n_reach": int(alt.sum()), "occupied_reach": occupied,
                }  # fmt: skip
            rec.years.append({
                "year": state.year, "units": units, "groups": groups,
                "plant_stock": eco.plant_stock_kcal.copy(), "game_stock": eco.game_stock_kcal.copy(),
                "plant_cap": eco.plant_capacity_kcal.copy(), "game_cap": eco.game_capacity_kcal.copy(),
            })  # fmt: skip
            return proposals

        def plan(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = plan0(sub, state, ctx)
            cols = ctx.columns(state)
            before = dict(
                zip([u.id for u in cols.units], cols.get("fields_ha").tolist(), strict=True)
            )
            after = dict(before)
            for prop in proposals:
                for r, f in zip(prop.rows.tolist(), prop.fields_ha.tolist(), strict=True):
                    after[prop.cols.units[r].id] = f
            if rec.years and rec.years[-1]["year"] == state.year:
                rec.years[-1]["fields_plan"] = {u: (before[u], after[u]) for u in before}
            return proposals

        def gather(
            cols: Any, species: Any, store: Any, memory: Any, reachable: Any, year: int
        ) -> Any:
            found = gather0(cols, species, store, memory, reachable, year)
            if found is not None:
                out = {}
                population = cols.population().astype(float)
                start = 0
                for k, row in enumerate(found.index.tolist()):
                    n = int(found.counts[k])
                    sl = slice(start, start + n)
                    start += n
                    pop = population[row]
                    per_head = found.food[sl] / np.maximum(pop + found.others[sl], 1.0)
                    stay = found.staying[sl]
                    home = float(per_head[stay][0]) if stay.any() else float("nan")
                    alts = per_head[~stay]
                    out[cols.units[row].id] = (n - int(stay.sum()), home,
                                               float(alts.max()) if alts.size else float("nan"),
                                               float((alts >= home).mean()) if alts.size else 0.0)  # fmt: skip
                rec.known[year] = out
            return found

        self._saved = {"forage": forage0, "plan": plan0, "gather": gather0}
        ForagingSubsystem.evaluate = forage  # type: ignore[method-assign]
        FieldPlanningSubsystem.evaluate = plan  # type: ignore[method-assign]
        migration.gather_candidates = gather

    def remove(self) -> None:
        ForagingSubsystem.evaluate = self._saved["forage"]  # type: ignore[method-assign]
        FieldPlanningSubsystem.evaluate = self._saved["plan"]  # type: ignore[method-assign]
        migration.gather_candidates = self._saved["gather"]


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
    return {"name": name, "seed": seed, "years": rec.years, "static": rec.static, "known": rec.known,
            "neutral": physical_digest(sim) == physical_digest(plain)}  # fmt: skip


# ---------------------------------------------------------------- analysis


def _stock(
    y: dict[str, Any], st: dict[str, Any], cell: int
) -> tuple[tuple[float, float], tuple[float, float]]:
    return ((float(y["plant_stock"][cell] * st["plant_access"][cell]), float(y["game_stock"][cell] * st["game_access"][cell])),
            (float(st["plant_return"][cell]), float(st["game_return"][cell])))  # fmt: skip


def analyse_run(run: dict[str, Any]) -> dict[str, Any]:
    st, years = run["static"], run["years"]
    out: dict[str, Any] = defaultdict(list)
    out["replay_groups"] = out["replay_exact"] = out["regrowth_checked"] = 0
    out["regrowth_err"] = 0.0
    land = st["land"]
    cap_series = np.array(
        [
            (y["plant_cap"] * st["plant_access"] + y["game_cap"] * st["game_access"])[land]
            for y in years
        ]
    )
    out["cap_series"] = cap_series.astype(np.float32)
    by_year = {y["year"]: y for y in years}
    for y in years:
        units = y["units"]
        occupied_cells = {u["cell"] for u in units.values()}
        # --- A: concentration of potential within each unit's reach (true capacity)
        acc_cap = y["plant_cap"] * st["plant_access"] + y["game_cap"] * st["game_access"]
        out["occupied_frac"].append(len(occupied_cells) / int(land.sum()))
        for uid, u in units.items():
            # --- A: realized foraging regime and outside options
            stock, returns = _stock(y, st, u["cell"])
            avail = stock[0] + stock[1]
            out["unit"].append({
                "year": y["year"], "need": u["need"], "target": u["target"], "forage": u["forage"], "farm": u["farm"],
                "fields": u["fields"], "people": u["people"], "depletion": u["forage"] / avail if avail > 0 else 0.0,
                "cap_ratio": u["labor"] * u["eff"] * max(returns) / avail if avail > 0 else float("inf"),
                "home": u["home_per_head"], "best": u["best_alt"], "best_cost": u["best_cost"],
                "share_better": u["share_better"], "n_reach": u["n_reach"],
                "known": run["known"].get(y["year"], {}).get(uid),
                "reach_cap_ratio": float(acc_cap[u["cell"]] / np.median(acc_cap[[c for c, _ in u["occupied_reach"]] or [u["cell"]]])),
            })  # fmt: skip
        # --- A + B: foraging groups
        members_of_cell: dict[int, list[str]] = {}
        for cell, members, plant_rm, game_rm in y["groups"]:
            members_of_cell[cell] = members
            stock, returns = _stock(y, st, cell)
            lab = [units[m]["labor"] for m in members]
            eff = [units[m]["eff"] for m in members]
            tgt = [units[m]["target"] for m in members]
            pooled = pooled_harvest(stock, returns, lab, eff, tgt)
            out["replay_groups"] += 1
            out["replay_exact"] += pooled == [units[m]["forage"] for m in members]
            if len(members) < 2:
                continue
            ind, _e = independent_harvest(stock, returns, lab, eff, tgt)
            ratio = [
                t / (lab_ * e) if lab_ * e > 0 else float("inf")
                for t, lab_, e in zip(tgt, lab, eff, strict=True)
            ]
            finite = [r for r in ratio if np.isfinite(r)]
            out["group"].append({
                "n": len(members), "pooled_total": sum(pooled), "ind_total": sum(ind), "target": sum(tgt),
                "avail": stock[0] + stock[1], "spread": (max(finite) / min(finite)) if finite and min(finite) > 0 else float("inf"),
            })  # fmt: skip
            for k, m in enumerate(members):
                u = units[m]
                alone = alone_harvest(stock, returns, lab[k], eff[k], tgt[k])
                out["member"].append({
                    "need": u["need"], "target": tgt[k], "pooled": pooled[k], "ind": ind[k], "alone": alone,
                    "farm": u["farm"], "stores": u["stores"], "fields": u["fields"],
                    "short_pooled": u["farm"] + pooled[k] + u["stores"] < u["need"],
                    "short_ind": u["farm"] + ind[k] + u["stores"] < u["need"],
                    "home": u["home_per_head"], "best": u["best_alt"], "share_better": u["share_better"],
                    "best_cost": u["best_cost"], "known": run["known"].get(y["year"], {}).get(m),
                })  # fmt: skip
            # --- A: intertemporal rivalry (exact one-step regrowth; next year's capacity)
            nxt = by_year.get(y["year"] + 1)
            if nxt is not None:
                end_p = float(y["plant_stock"][cell]) - plant_rm
                end_g = float(y["game_stock"][cell]) - game_rm
                got_p = logistic_regrowth(
                    np.array([max(end_p, 0.0)]),
                    np.array([nxt["plant_cap"][cell]]),
                    st["plant_rate"],
                    st["recol"],
                )[0]
                out["regrowth_err"] = max(
                    out["regrowth_err"], abs(got_p - nxt["plant_stock"][cell])
                )
                out["regrowth_checked"] += 1
                for k, m in enumerate(members):
                    share = pooled[k] / sum(pooled) if sum(pooled) > 0 else 0.0
                    lost = (regrowth_loss(max(end_p, 0.0), float(nxt["plant_cap"][cell]), st["plant_rate"], st["recol"], plant_rm * share)
                            + regrowth_loss(max(end_g, 0.0), float(nxt["game_cap"][cell]), st["game_rate"], st["recol"], game_rm * share))  # fmt: skip
                    others_next = [
                        x for x, v in nxt["units"].items() if v["cell"] == cell and x != m
                    ]
                    out["carry"].append((pooled[k], lost, bool(others_next),
                                         sum(nxt["units"][x]["need"] for x in others_next)))  # fmt: skip
        # --- A: farming displaces co-users' wild capacity
        fields_by_cell: dict[int, list[tuple[str, float]]] = defaultdict(list)
        for uid, u in units.items():
            if u["fields"] > 0:
                fields_by_cell[u["cell"]].append((uid, u["fields"]))
        for cell, owners in fields_by_cell.items():
            total = sum(f for _, f in owners)
            frac = min(total / st["cell_ha"], 1.0)
            base_p = (
                y["plant_cap"][cell] / (1 - st["plant_disp"] * frac)
                if st["plant_disp"] * frac < 1
                else 0.0
            )
            base_g = y["game_cap"][cell] / (1 - st["game_disp"] * frac)
            for uid in members_of_cell.get(cell, []):
                own = units[uid]["fields"]
                others = (total - own) / st["cell_ha"]
                if others <= 0:
                    continue
                lost = (base_p * st["plant_disp"] * others * st["plant_access"][cell]
                        + base_g * st["game_disp"] * others * st["game_access"][cell])  # fmt: skip
                out["displaced"].append((lost / units[uid]["need"], units[uid]["fields"] > 0))
        # --- A: arable sharing
        plan = y.get("fields_plan", {})
        if plan:
            per_cell: dict[int, list[tuple[float, float]]] = defaultdict(list)
            for uid, (before, after) in plan.items():
                if uid in units:
                    per_cell[units[uid]["cell"]].append((before, after))
            for cell, rows in per_cell.items():
                total_after = sum(a for _, a in rows)
                if total_after <= 0:
                    continue
                binding = total_after >= st["arable"][cell] * (1 - 1e-9)
                cut = sum(1 for b, a in rows if a < b and b > 0)
                grow = sum(1 for b, a in rows if a > b)
                out["arable"].append(
                    (binding, len(rows), cut, grow, total_after / st["arable"][cell])
                )
        # --- C: complementary shortage and surplus (pre-trade balances, units in reach)
        bal = {uid: u["farm"] + u["forage"] + u["stores"] - u["need"] for uid, u in units.items()}
        where: dict[int, list[str]] = defaultdict(list)
        for uid, u in units.items():
            where[u["cell"]].append(uid)
        for uid, u in units.items():
            neighbors = [(x, cost) for c, cost in u["occupied_reach"] for x in where[c]] + [
                (x, 0.0) for x in where[u["cell"]] if x != uid
            ]
            if not neighbors:
                out["isolated"].append(bal[uid] < 0)
                continue
            short_nb = np.mean([bal[x] < 0 for x, _ in neighbors])
            surplus_in = sum(
                bal[x] * delivered_fraction(cost, st["decay"])
                for x, cost in neighbors
                if bal[x] > 0
            )
            out["pair"].append((bal[uid] < 0, short_nb, -bal[uid] / u["need"] if bal[uid] < 0 else 0.0,
                                surplus_in / -bal[uid] if bal[uid] < 0 else float("nan"), len(neighbors)))  # fmt: skip
    # --- C: bilateral vs network assistance over time (physical feasibility, not willingness)
    seq = {
        y["year"]: {
            uid: (u["farm"] + u["forage"] + u["stores"] - u["need"], u["cell"], u["occupied_reach"])
            for uid, u in y["units"].items()
        }
        for y in years
    }
    for y in years:
        t = y["year"]
        units = seq[t]
        cells_t: dict[int, list[str]] = defaultdict(list)
        for uid, (_b, c, _r) in units.items():
            cells_t[c].append(uid)
        for a, (ba, ca, reach_a) in units.items():
            if ba <= 0:
                continue
            reach_cells = {c for c, _ in reach_a} | {ca}
            helped = [b for c in reach_cells for b in cells_t[c] if b != a and units[b][0] < 0]
            if not helped:
                continue
            for k in range(1, LATER + 1):
                later = seq.get(t + k)
                if later is None or a not in later:
                    break
                la, lca, lreach = later[a]
                if la >= 0:
                    continue
                lcells = {c for c, _ in lreach} | {lca}
                bil = any(b in later and later[b][0] > 0 and later[b][1] in lcells for b in helped)
                net = any(v[0] > 0 and v[1] in lcells for x, v in later.items() if x != a)
                out["later"].append((k, bil, net))
                break
    return dict(out)


def _q(values: Any, qs: tuple[float, ...] = (0.1, 0.5, 0.9)) -> str:
    a = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    return "/".join(f"{np.quantile(a, x):.3g}" for x in qs) if a.size else "-"


def report(name: str, outs: list[dict[str, Any]]) -> None:
    print(f"\n=== {name}")
    g = sum(o["replay_groups"] for o in outs)
    print(f"-- pooled foraging replay: {sum(o['replay_exact'] for o in outs)}/{g} groups bit for bit; "
          f"regrowth replay max error {max(o['regrowth_err'] for o in outs):.3g} kcal over {sum(o['regrowth_checked'] for o in outs)} cell-years")  # fmt: skip
    # ---- A
    cs = outs[0][
        "cap_series"
    ]  # the world is the scenario's (topology seed); run seeds change climate only
    mean_cap = cs.mean(axis=0)
    cv = cs.std(axis=0) / np.maximum(mean_cap, 1e-300)
    ranks = [
        np.corrcoef(np.argsort(np.argsort(cs[t])), np.argsort(np.argsort(cs[t + 1])))[0, 1]
        for t in range(0, cs.shape[0] - 1, 10)
    ]
    print("\n-- A1 potential (accessible wild capacity per land cell; seed 0 world)")
    print(f"   Gini across land cells {gini(mean_cap):.3f}; p90/p10 {np.quantile(mean_cap, 0.9) / max(np.quantile(mean_cap, 0.1), 1e-300):.2f}; "
          f"interannual CV per cell p10/p50/p90 {_q(cv)}; year-to-year rank correlation {np.mean(ranks):.3f}")  # fmt: skip
    print(
        f"   occupied share of land cells (mean over years) {np.mean([x for o in outs for x in o['occupied_frac']]):.3f}"
    )
    un = [r for o in outs for r in o.get("unit", [])]
    rc = np.array([r["reach_cap_ratio"] for r in un])
    print(f"   home capacity / median capacity of occupied cells in reach: p10/p50/p90 {_q(rc)}")
    dep = np.array([r["depletion"] for r in un])
    met = np.array([r["farm"] + r["forage"] >= r["target"] / 1.0 - 1e-6 for r in un])
    forager = np.array([r["target"] > 0 for r in un])
    print(
        f"\n-- A2 realized foraging (unit-years {len(un)}; with a foraging target {forager.mean():.3f})"
    )
    print(f"   target met by own production {met[forager].mean():.3f}; harvest / accessible stock p10/p50/p90 {_q(dep[forager])}; "
          f"stock-limited (> 50 % of accessible taken) {(dep[forager] > 0.5).mean():.3f}")  # fmt: skip
    mem = [m for o in outs for m in o.get("member", [])]
    grp = [x for o in outs for x in o.get("group", [])]
    print(
        f"\n-- A3 rivalry: foraging unit-years in multi-unit cells {len(mem)} ({len(mem) / max(len(un), 1):.3f} of unit-years), groups {len(grp)}"
    )
    if mem:
        need = np.array([m["need"] for m in mem])
        gain_alone = (
            np.array([m["alone"] for m in mem]) - np.array([m["pooled"] for m in mem])
        ) / need
        print(
            f"   harvest gain if co-users were absent (alone - pooled) / need: p10/p50/p90 {_q(gain_alone)}; > 1 % {np.mean(gain_alone > 0.01):.3f}; > 10 % {np.mean(gain_alone > 0.1):.3f}"
        )
        avail = np.array([x["avail"] for x in grp])
        tgt = np.array([x["target"] for x in grp])
        print(
            f"   group target / accessible stock p10/p50/p90 {_q(tgt / avail)}; groups whose summed target exceeds what full effort can take: {np.mean([x['pooled_total'] < x['target'] * (1 - 1e-9) for x in grp]):.3f}"
        )
    carry = np.array([c for o in outs for c in o.get("carry", [])], dtype=float)
    if carry.size:
        print(f"   intertemporal: next-year stock lost per kcal removed {carry[:, 1].sum() / carry[:, 0].sum():.3f}; removals followed by another unit in the cell next year {carry[:, 2].mean():.3f}; "
              f"lost / co-users' next-year need {carry[carry[:, 2] == 1, 1].sum() / max(carry[carry[:, 2] == 1, 3].sum(), 1e-300):.4f}")  # fmt: skip
    disp = np.array([d for o in outs for d in o.get("displaced", [])], dtype=float)
    if disp.size:
        print(
            f"   wild capacity displaced by co-residents' fields / own need: unit-years {len(disp)}, p50/p90 {_q(disp[:, 0], (0.5, 0.9))}; of which the unit also farms {disp[:, 1].mean():.3f}"
        )
    ar = [a for o in outs for a in o.get("arable", [])]
    if ar:
        b = np.array([a[0] for a in ar])
        multi = np.array([a[1] >= 2 for a in ar])
        print(f"   arable: farming cell-years {len(ar)}, cap binding {b.mean():.3f}, binding with >= 2 farming units {(b & multi).mean():.3f}; "
              f"incumbents cut while another expands in a binding cell {np.mean([a[0] and a[2] > 0 and a[3] > 0 for a in ar]):.4f}")  # fmt: skip
    print(
        "\n-- A4 outside options (units in multi-unit cells; per-head accessible stock, alternative / home)"
    )
    if mem:
        home = np.array([m["home"] for m in mem])
        best = np.array([m["best"] for m in mem])
        ratio = best / np.maximum(home, 1e-300)
        print(f"   analyst (true stocks): best alternative / home p10/p50/p90 {_q(ratio)}; share with an alternative >= home {(ratio >= 1).mean():.3f}; "
              f"share of reachable cells >= home p50 {_q([m['share_better'] for m in mem], (0.5,))}; path cost of best p50 {_q([m['best_cost'] for m in mem], (0.5,))} km")  # fmt: skip
        kn = [m["known"] for m in mem if m["known"] is not None]
        if kn:
            kr = np.array([k[2] / k[1] if k[1] > 0 else np.nan for k in kn])
            print(f"   actor (beliefs): known alternative cells p10/p50/p90 {_q([k[0] for k in kn])}; believed best / believed home p50 {_q(kr, (0.5,))}; "
                  f"share with a believed alternative >= home {np.nanmean(kr >= 1):.3f}; units with no known alternative {np.mean([k[0] == 0 for k in kn]):.3f}")  # fmt: skip
    # ---- B
    print(
        "\n-- B pooled (production) vs independent satisficing in multi-unit cells (same stock, labor, targets)"
    )
    if mem:
        pt = np.array([x["pooled_total"] for x in grp])
        it = np.array([x["ind_total"] for x in grp])
        d = (np.array([m["pooled"] for m in mem]) - np.array([m["ind"] for m in mem])) / need
        sp, si = np.array([m["short_pooled"] for m in mem]), np.array([m["short_ind"] for m in mem])
        zero = np.array([m["target"] <= 0 for m in mem])
        print(
            f"   total harvest pooled / independent {pt.sum() / it.sum():.4f}; groups differing by > 1 % of target {np.mean(np.abs(pt - it) > 0.01 * np.maximum([x['target'] for x in grp], 1e-300)):.3f}"
        )
        print(
            f"   member (pooled - independent) / need p10/p50/p90 {_q(d)}; |diff| > 1 % {np.mean(np.abs(d) > 0.01):.3f}; > 10 % {np.mean(np.abs(d) > 0.1):.3f}"
        )
        print(
            f"   members short of need (harvest + stores, before trade): pooled {sp.mean():.4f}, independent {si.mean():.4f}; short only under pooling {np.mean(sp & ~si):.4f}, only under independent {np.mean(si & ~sp):.4f}"
        )
        print(
            f"   members with zero foraging target (fed by crops) {zero.mean():.3f}; wild kcal they receive under pooling / group harvest {sum(m['pooled'] for m, z in zip(mem, zero, strict=True) if z) / max(pt.sum(), 1e-300):.4f}"
        )
        print(
            f"   heterogeneity of target per effective hour within groups (max/min) p50/p90 {_q([x['spread'] for x in grp], (0.5, 0.9))}"
        )
    # ---- C
    pr = [p for o in outs for p in o.get("pair", [])]
    if pr:
        short = np.array([p[0] for p in pr])
        nb = np.array([p[1] for p in pr])
        cover = np.array([p[3] for p in pr if p[0]])
        print(
            "\n-- C complementary shortage (pre-trade balance; neighbors = units in one relocation range)"
        )
        print(
            f"   short unit-years {short.mean():.3f}; neighbors short | unit short {nb[short].mean():.3f} vs | unit not short {nb[~short].mean():.3f} (synchrony ratio {nb[short].mean() / max(nb[~short].mean(), 1e-300):.2f})"
        )
        print(
            f"   short units with no surplus neighbor {np.mean(cover <= 0):.3f}; delivered-equivalent neighbor surplus / own deficit p10/p50/p90 {_q(cover)} (all surplus, before competition)"
        )
        iso = [x for o in outs for x in o.get("isolated", [])]
        print(
            f"   isolated unit-years (no other unit in reach) {len(iso)} ({len(iso) / (len(iso) + len(pr)):.3f}), of which short {np.mean(iso) if iso else 0:.3f}"
        )
    lt = np.array([x for o in outs for x in o.get("later", [])], dtype=float)
    if lt.size:
        print(f"   surplus units that had a short neighbor and fall short within {LATER} y: {len(lt)}; when they do, a former short neighbor now has surplus in reach (bilateral) {lt[:, 1].mean():.3f}; "
              f"any neighbor has surplus in reach (network) {lt[:, 2].mean():.3f}; delay p50 {np.median(lt[:, 0]):.0f} y")  # fmt: skip


def _analyse_path(path: Path) -> tuple[str, int, bool, dict[str, Any]]:
    with path.open("rb") as f:
        run = pickle.load(f)
    return run["name"], run["seed"], run["neutral"], analyse_run(run)


def analyse(load: Path, jobs: int) -> None:
    started = time.perf_counter()
    with Pool(jobs, maxtasksperchild=1) as pool:  # one recording in memory per worker
        results = pool.map(_analyse_path, sorted(load.glob("*.pkl")), chunksize=1)
    print("observer-neutral (physical digest):", {f"{n}/{s}": ok for n, s, ok, _ in results})
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name, _seed, _ok, out in results:
        by_name[name].append(out)
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
        specs = [
            (n, s) for n in MVP2_2 for s in args.seeds if not (args.out / f"{n}_{s}.pkl").exists()
        ]
        with Pool(args.jobs) as pool:
            for run in pool.imap_unordered(record_job, specs):
                with (args.out / f"{run['name']}_{run['seed']}.pkl").open("wb") as f:
                    pickle.dump(run, f)
                print(
                    f"recorded {run['name']} seed {run['seed']}: {len(run['years'])} years, neutral {run['neutral']}",
                    flush=True,
                )
    else:
        assert args.load is not None
        analyse(args.load, args.jobs)


if __name__ == "__main__":
    main()
