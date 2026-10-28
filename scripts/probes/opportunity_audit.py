# The report tables keep one entry per line.
# ruff: noqa: E501
"""Socioecological opportunity structure: resource access, coordination, risk pooling
(MVP 3 Stage 6B). Observation only. READ-ONLY / NOT ACTIVE.

``record`` runs the MVP 2.2 reference scenarios with read-only hooks on the simulator's own
subsystem instances (``_integrity.hook``):

- ``ForagingSubsystem.evaluate``: every cell's wild stocks and capacities before harvest;
  each unit's need, labor, efficiency, foraging target, fields, crop, stores, cell and
  population; each (cell, species) foraging group with its members and the authoritative
  harvest; analyst-computed outside options (true accessible stock per prospective head in
  every reachable cell) and the occupied cells in reach;
- ``TradeSubsystem.evaluate``: the year's authoritative transfers (donor, recipient,
  shipped, delivered, recipient need; an empty list in a year without any), and after each
  step the trade ledger (shipped, transport loss). Joined to the observations above by
  ``(year, unit id)``; unit ids are never reused;
- ``FieldPlanningSubsystem.evaluate``: fields before and after planning (arable sharing) and
  the kernel's desired fields;
- ``MigrationSubsystem.evaluate`` (``migration.gather_candidates`` swapped for that call):
  the cells each unit actually believes in, with believed food and others (actor-known
  outside options).

An uninstrumented twin runs in lockstep and is compared by state fingerprint
(``_integrity.run_observed``). Each recording embeds its provenance and is written
atomically; ``record`` keeps an existing recording only if it is intact and matches (else it
stops; ``--replace`` overwrites), and ``analyse`` loads exactly the requested runs
(``--seeds`` for an explicit subset; ``--legacy-unverified`` for pre-6B-P2 recordings, whose
provenance cannot be checked).

``analyse`` replays pooled foraging exactly (``economy/opportunity_audit.py``) and computes
the pathway measures (pre-registered in the design document §AE): A resource access and
rivalry, B pooled vs independent use, C complementary shortage and surplus; it checks the
recorded transfers' integrity but measures nothing from them (P3, P4).

Usage:
    uv run python scripts/probes/opportunity_audit.py record [--jobs 2] [--seeds 0 1 2 3] [--replace] --out DIR
    uv run python scripts/probes/opportunity_audit.py analyse --load DIR [--jobs 2] [--seeds ...] [--legacy-unverified]
"""

import argparse
import inspect
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from _common import SEEDS
from _integrity import (
    RecordingError,
    hook,
    identity,
    load_data,
    provenance,
    run_observed,
    select_runs,
    swapped,
    to_record,
    write_recording,
)

import madexplorer.economy.agriculture_kernel as agriculture_kernel
import madexplorer.mobility.migration as migration
from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.ecology.resources import logistic_regrowth
from madexplorer.economy.agriculture import HECTARES_PER_KM2, FieldPlanningSubsystem
from madexplorer.economy.foraging import ForagingSubsystem, _harvest
from madexplorer.economy.opportunity_audit import (
    TARGET_REL_TOL,
    alone_harvest,
    gini,
    independent_harvest,
    labor_elasticity,
    pooled_harvest,
    regrowth_loss,
    remaining_target_met,
    utilization,
)
from madexplorer.economy.trade import TradeSubsystem, delivered_fraction
from madexplorer.mobility.migration import MigrationSubsystem
from madexplorer.population.energetics import annual_need_columns

MVP2_2 = {
    "neolithic": ("scenarios/mvp2_2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 400, {"mechanisms.cultivation": True}),
}
LATER = 10  # years ahead for later shortage and assistance
PROBE = "opportunity_audit"
# Recording schema: 1 = Stage 6B-P1 layout (no provenance; legacy); 2 = 6B-P2: provenance
# container, authoritative transfers and the trade ledger.
SCHEMA = 2
DESIRED_ARG = list(
    inspect.signature(
        getattr(agriculture_kernel.plan_fields, "py_func", agriculture_kernel.plan_fields)
    ).parameters
).index("desired")


def scenario(name: str, seed: int) -> Scenario:
    path, horizon, settings = MVP2_2[name]
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=horizon)
    return base.with_settings(settings) if settings else base


# ---------------------------------------------------------------- recording


def plan_with_desired(
    evaluate: Any, sub: Any, state: Any, ctx: Any
) -> tuple[Any, np.ndarray | None]:
    """Run field planning once and copy each row's desired fields (before arable sharing).

    Not a second calculation: the production kernel writes them into its ``desired`` scratch
    argument and never rewrites it while sharing arable land, so the array is copied after
    the same call returns. No other interface exposes it. ``None`` when nothing was planned.
    The kernel is replaced only for the duration of this call.
    """
    captured: list[np.ndarray] = []
    kernel0 = agriculture_kernel.plan_fields

    def kernel(*args: Any) -> Any:
        count = kernel0(*args)
        captured.append(np.array(args[DESIRED_ARG], dtype=float))
        return count

    with swapped(agriculture_kernel, "plan_fields", kernel):
        proposals = evaluate(sub, state, ctx)
    assert len(captured) <= 1
    return proposals, captured[0] if captured else None


class Recorder:
    def __init__(self) -> None:
        self.years: list[dict[str, Any]] = []
        self.static: dict[str, Any] = {}
        self.known: dict[int, dict[str, tuple[int, float, float, float]]] = {}
        # Authoritative trade, per year in which trade was evaluated (an empty list: no
        # transfer); None if trade is not in the pipeline.
        self.transfers: dict[int, list[tuple[str, str, float, float, float]]] | None = None
        self.ledger: dict[int, tuple[float, float]] = {}

    def install(self, sim: Simulator) -> None:
        """Read-only hooks on ``sim``'s own subsystem instances (``_integrity.hook``)."""
        rec = self

        def forage(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = ForagingSubsystem.evaluate(sub, state, ctx)
            if not proposals:
                return proposals
            cols = ctx.columns(state)
            inputs = sub._inputs(state, ctx)
            eco = state.ecology
            sid = cols.units[0].species_id
            # Cell totals below (stock, removals, collective utilization) assume one foraging
            # group per cell; with several species, groups forage one stock in sequence.
            assert all(u.species_id == sid for u in cols.units), "single-species scenarios only"
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

        def trade(sub: Any, state: Any, ctx: Any) -> Any:
            proposals = TradeSubsystem.evaluate(sub, state, ctx)
            assert rec.transfers is not None
            rec.transfers[state.year] = [
                (t.donor_id, t.recipient_id, t.sent_kcal, t.received_kcal, t.recipient_need_kcal)
                for p in proposals for t in p.transfers
            ]  # fmt: skip
            return proposals

        def plan(sub: Any, state: Any, ctx: Any) -> Any:
            proposals, captured = plan_with_desired(
                FieldPlanningSubsystem.evaluate, sub, state, ctx
            )
            cols = ctx.columns(state)
            ids = [u.id for u in cols.units]
            before = dict(zip(ids, cols.get("fields_ha").tolist(), strict=True))
            after = dict(before)
            for prop in proposals:
                for r, f in zip(prop.rows.tolist(), prop.fields_ha.tolist(), strict=True):
                    after[prop.cols.units[r].id] = f
            desired = dict(zip(ids, captured.tolist(), strict=True)) if captured is not None else {}
            if rec.years and rec.years[-1]["year"] == state.year:
                rec.years[-1]["fields_plan"] = {
                    u: (before[u], after[u], desired.get(u, float("nan"))) for u in before
                }
            return proposals

        def migrate(sub: Any, state: Any, ctx: Any) -> Any:
            gather0 = migration.gather_candidates

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

            with swapped(migration, "gather_candidates", gather):
                return MigrationSubsystem.evaluate(sub, state, ctx)

        assert hook(sim, ForagingSubsystem, forage)
        if hook(sim, TradeSubsystem, trade):
            rec.transfers = {}
        hook(sim, FieldPlanningSubsystem, plan)
        hook(sim, MigrationSubsystem, migrate)

    def after_step(self, sim: Simulator, ctx: Any) -> None:
        """The step's authoritative trade totals (shipped, transport loss)."""
        if self.transfers is not None:
            self.ledger[sim.state.year] = (
                ctx.ledger.trade_volume_kcal,
                ctx.ledger.transport_loss_kcal,
            )


def ident_of(name: str, seed: int) -> dict[str, Any]:
    """What a recording of ``(name, seed)`` made now would declare (``_integrity``)."""
    path, _, settings = MVP2_2[name]
    return identity(PROBE, SCHEMA, name, scenario(name, seed), path, settings, __file__)


def record_job(spec: tuple[str, int]) -> dict[str, Any]:
    """One instrumented run, its uninstrumented twin compared in lockstep; the data plus
    its ``provenance`` (split off when written)."""
    name, seed = spec
    sc = scenario(name, seed)
    rec = Recorder()
    _sim, years, neutrality = run_observed(sc, rec.install, rec.after_step)
    return {"name": name, "seed": seed, "years": rec.years, "static": rec.static, "known": rec.known,
            "transfers": rec.transfers, "trade_ledger": rec.ledger, "neutral": neutrality["neutral"],
            "provenance": provenance(ident_of(name, seed), sc, years, neutrality)}  # fmt: skip


# ---------------------------------------------------------------- analysis


def _stock(
    y: dict[str, Any], st: dict[str, Any], cell: int
) -> tuple[tuple[float, float], tuple[float, float]]:
    return ((float(y["plant_stock"][cell] * st["plant_access"][cell]), float(y["game_stock"][cell] * st["game_access"][cell])),
            (float(st["plant_return"][cell]), float(st["game_return"][cell])))  # fmt: skip


def balance(u: dict[str, Any]) -> float:
    """Pre-trade food balance: own crop + wild harvest + stores - need (trade's ``b``)."""
    return float(u["farm"] + u["forage"] + u["stores"] - u["need"])


def arable_cell(rows: list[tuple[float, float, float]], arable: float) -> dict[str, Any]:
    """One farming cell-year of field planning: ``rows`` are each unit's (before, after,
    desired) fields. ``rationed``: desired fields exceed the arable cap, so the kernel scaled
    everyone (``plan_fields``); ``at_cap``: planned fields fill the cap. A unit is cut *by
    rationing* when it wanted at least its current fields but was planned below them.
    ``desired`` is this year's planned step toward the unit's target, not the target itself.
    With zero arable land every desired field is rationed to zero (land unavailable, not
    contested); the sharing is pro rata, so no unit is excluded except through the 0.05 ha
    rounding (``zeroed_by_rounding``)."""
    desired = sum(d for _, _, d in rows)
    after = sum(a for _, a, _ in rows)
    rationed = desired > arable
    scale = min(1.0, arable / desired) if desired > 0 else 1.0
    return {
        "n": len(rows), "n_desiring": sum(1 for _, _, d in rows if d > 0),
        "incumbents": sum(1 for b, _, _ in rows if b > 0),
        "desired_ha": desired, "unallocated_ha": max(desired - after, 0.0) if rationed else 0.0,
        "zeroed_by_rounding": sum(1 for _, _, d in rows if rationed and d >= 0.05 and d * scale < 0.05),
        "arable": arable, "desired_ratio": desired / arable if arable > 0 else float("inf"),
        "after_ratio": after / arable if arable > 0 else float("inf"),
        "at_cap": after >= arable * (1 - 1e-9), "rationed": rationed,
        "cut": sum(1 for b, a, _ in rows if a < b and b > 0), "grow": sum(1 for b, a, _ in rows if a > b),
        "rationing_cut": sum(1 for b, a, d in rows if rationed and b > 0 and a < b and d >= b),
        "capture_ok": all(  # the recorded desired fields reproduce the kernel's sharing
            (a == 0.0 and d * s < 0.05) or abs(a - d * s) <= 1e-9 * max(a, 1.0)
            for b, a, d in rows
            for s in [scale]
        ),
    }  # fmt: skip


def neighbours(uid: str, u: dict[str, Any], where: dict[int, list[str]]) -> list[tuple[str, float]]:
    """Other units within one relocation range (the reach trade uses), with path cost.
    Geographic reach only: not contact, and not knowledge of their stores."""
    return [(x, cost) for c, cost in u["occupied_reach"] for x in where[c]] + [
        (x, 0.0) for x in where[u["cell"]] if x != uid
    ]


def potential_role_reversal(
    seq: dict[int, dict[str, tuple[float, int, list[tuple[int, float]]]]], horizon: int
) -> list[tuple[str, int, int, bool, bool]]:
    """``(a, year, delay, formerly_short_has_surplus, any_has_surplus)`` per eligible origin.

    ``seq[year][uid] = (pre-trade balance, cell, occupied cells in reach)``. Origin: unit
    ``a`` has a surplus in ``year`` and at least one *formerly short neighbour* (another unit
    in reach with a negative balance that year; no transfer is required or observed). The
    first year within ``horizon`` in which ``a`` is short is recorded: whether one of those
    formerly short neighbours now has a surplus within ``a``'s reach, and whether any unit
    does. A neighbour that no longer exists counts as not available; the window closes when
    ``a`` disappears or the run ends, and origins without a later shortage are not recorded.
    """
    out = []
    for t in sorted(seq):
        units = seq[t]
        cells_t: dict[int, list[str]] = defaultdict(list)
        for uid, (_b, c, _r) in units.items():
            cells_t[c].append(uid)
        for a, (ba, ca, reach_a) in units.items():
            if ba <= 0:
                continue
            reach_cells = {c for c, _ in reach_a} | {ca}
            formerly_short = [
                b for c in reach_cells for b in cells_t[c] if b != a and units[b][0] < 0
            ]
            if not formerly_short:
                continue
            for k in range(1, horizon + 1):
                later = seq.get(t + k)
                if later is None or a not in later:
                    break
                la, lca, lreach = later[a]
                if la >= 0:
                    continue
                lcells = {c for c, _ in lreach} | {lca}
                specific = any(
                    b in later and later[b][0] > 0 and later[b][1] in lcells for b in formerly_short
                )
                anyone = any(v[0] > 0 and v[1] in lcells for x, v in later.items() if x != a)
                out.append((a, t, k, specific, anyone))
                break
    return out


def transfer_checks(run: dict[str, Any]) -> dict[str, int] | None:
    """Integrity of the recorded authoritative transfers (no behavioural statistics).

    Join key with the opportunity observations: ``(year, unit id)``. Unit ids are never
    reused (``IdAllocator``), so a recorded id names one unit for its whole recorded life.
    """
    transfers = run.get("transfers")
    if transfers is None:
        return None
    by_year = {y["year"]: y["units"] for y in run["years"]}
    decay = run["static"]["decay"]
    c = Counter(years=len(transfers), empty_years=sum(not t for t in transfers.values()))
    for year, ts in transfers.items():
        units = by_year.get(year, {})
        shipped = lost = 0.0
        for donor, recipient, sent, received, need in ts:
            shipped += sent
            lost += sent - received
            c["transfers"] += 1
            if donor not in units or recipient not in units:
                continue
            c["ids_recorded"] += 1
            d, r = units[donor], units[recipient]
            cost = 0.0 if d["cell"] == r["cell"] else dict(r["occupied_reach"]).get(d["cell"])
            c["delivery_exact"] += cost is not None and received == sent * delivered_fraction(
                cost, decay
            )
            c["need_exact"] += need == r["need"]
            c["recipient_short"] += balance(r) < 0 and balance(d) > 0
        c["ledger_exact"] += (shipped, lost) == run["trade_ledger"].get(year)
    span: dict[str, list[int]] = defaultdict(list)
    for y in run["years"]:
        for uid in y["units"]:
            span[uid].append(y["year"])
    c["ids_reappearing"] = sum(v[-1] - v[0] + 1 != len(v) for v in span.values())
    return dict(c)


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
        acc_cap = y["plant_cap"] * st["plant_access"] + y["game_cap"] * st["game_access"]
        out["occupied_frac"].append(len(occupied_cells) / int(land.sum()))
        # --- A + B: foraging groups (one per cell: single species, asserted when recorded)
        members_of_cell: dict[int, list[str]] = {}
        cell_util: dict[int, float | None] = {}
        group_met: dict[int, bool | None] = {}
        for cell, members, plant_rm, game_rm in y["groups"]:
            members_of_cell[cell] = members
            stock, returns = _stock(y, st, cell)
            avail = stock[0] + stock[1]
            removed = float(plant_rm + game_rm)
            shares = [units[m]["forage"] for m in members]
            remaining = sum(units[m]["target"] for m in members)
            cell_util[cell] = utilization(removed, avail)
            group_met[cell] = remaining_target_met(sum(shares), remaining)
            out["cell"].append({
                "n": len(members), "util": cell_util[cell], "removed": removed, "shares": sum(shares),
                "max_share": max((utilization(x, avail) or 0.0) for x in shares), "met": group_met[cell],
            })  # fmt: skip
            if group_met[cell] is False:  # missed => all labor applied (cell_harvest)
                full = sum(units[m]["labor"] * units[m]["eff"] for m in members)
                out["missed"].append((
                    abs(sum(_harvest(stock, returns, full)) - removed) <= 1e-9 * max(removed, 1.0),
                    labor_elasticity(stock, returns, full),
                ))  # fmt: skip
            lab = [units[m]["labor"] for m in members]
            eff = [units[m]["eff"] for m in members]
            tgt = [units[m]["target"] for m in members]
            pooled = pooled_harvest(stock, returns, lab, eff, tgt)
            out["replay_groups"] += 1
            out["replay_exact"] += pooled == shares
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
                "avail": avail, "spread": (max(finite) / min(finite)) if finite and min(finite) > 0 else float("inf"),
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
        # --- A: realized foraging regime and outside options, per unit
        for uid, u in units.items():
            stock, returns = _stock(y, st, u["cell"])
            avail = stock[0] + stock[1]
            out["unit"].append({
                "year": y["year"], "need": u["need"], "remaining_target": u["target"], "forage": u["forage"], "farm": u["farm"],
                "stores": u["stores"], "fields": u["fields"], "people": u["people"],
                "remaining_target_met": remaining_target_met(u["forage"], u["target"]),
                "group_target_met": group_met.get(u["cell"]), "multi": len(members_of_cell.get(u["cell"], [])) >= 2,
                "unit_harvest_share": utilization(u["forage"], avail), "cell_util": cell_util.get(u["cell"]),
                "home": u["home_per_head"], "best": u["best_alt"], "best_cost": u["best_cost"],
                "share_better": u["share_better"], "n_reach": u["n_reach"],
                "known": run["known"].get(y["year"], {}).get(uid),
                "reach_cap_ratio": float(acc_cap[u["cell"]] / np.median(acc_cap[[c for c, _ in u["occupied_reach"]] or [u["cell"]]])),
            })  # fmt: skip
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
        # --- A: arable sharing (cells with planned or desired fields)
        plan = y.get("fields_plan", {})
        if plan:
            per_cell: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
            for uid, row in plan.items():
                if uid in units:
                    per_cell[units[uid]["cell"]].append(row)
            for cell, rows in per_cell.items():
                if sum(a for _, a, _ in rows) <= 0 and sum(d for _, _, d in rows) <= 0:
                    continue
                out["arable"].append(arable_cell(rows, float(st["arable"][cell])))
            out["desiring_unit_years"].append(
                sum(row[2] > 0 for uid, row in plan.items() if uid in units)
            )
            out["zero_arable_desiring"] += [
                (uid, row[2]) for uid, row in plan.items()
                if uid in units and row[2] > 0 and st["arable"][units[uid]["cell"]] <= 0
            ]  # fmt: skip
        # --- C: complementary shortage and surplus (pre-trade balances, units in reach)
        bal = {uid: balance(u) for uid, u in units.items()}
        where: dict[int, list[str]] = defaultdict(list)
        for uid, u in units.items():
            where[u["cell"]].append(uid)
        counted_by: dict[str, int] = defaultdict(int)  # surplus unit -> short units counting it
        for uid, u in units.items():
            nbs = neighbours(uid, u, where)
            if not nbs:
                out["isolated"].append(bal[uid] < 0)
                continue
            short_nb = np.mean([bal[x] < 0 for x, _ in nbs])
            surplus_in = sum(
                bal[x] * delivered_fraction(cost, st["decay"]) for x, cost in nbs if bal[x] > 0
            )
            if bal[uid] < 0:
                for x, _ in nbs:
                    if bal[x] > 0:
                        counted_by[x] += 1
            out["pair"].append((bal[uid] < 0, short_nb, -bal[uid] / u["need"] if bal[uid] < 0 else 0.0,
                                surplus_in / -bal[uid] if bal[uid] < 0 else float("nan"), len(nbs)))  # fmt: skip
        out["counted_by"].extend(counted_by.values())
    # --- C: potential role reversal over time (physical feasibility; no transfer observed)
    seq = {
        y["year"]: {
            uid: (balance(u), u["cell"], u["occupied_reach"]) for uid, u in y["units"].items()
        }
        for y in years
    }
    out["later"] = potential_role_reversal(seq, LATER)
    out["transfer_checks"] = transfer_checks(run)
    return dict(out)


def _q(values: Any, qs: tuple[float, ...] = (0.1, 0.5, 0.9)) -> str:
    a = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    return "/".join(f"{np.quantile(a, x):.3g}" for x in qs) if a.size else "-"


def rate(flags: Any, eligible: Any = None) -> str:
    """``k/n (p %)`` over the eligible observations: exact counts, so a rare nonzero event is
    never shown as 0, and an empty denominator is reported as such (not as a rate)."""
    f = np.asarray(flags, dtype=bool)
    if eligible is not None:
        f = f[np.asarray(eligible, dtype=bool)]
    k, n = int(f.sum()), int(f.size)
    if n == 0:
        return "0/0 (no eligible observations)"
    return f"{k}/{n} ({100.0 * k / n:.4g} %)"


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
    eligible = np.array([r["remaining_target_met"] is not None for r in un])
    met = np.array([bool(r["remaining_target_met"]) for r in un])
    gmet = np.array([bool(r["group_target_met"]) for r in un])
    multi = np.array([r["multi"] for r in un])
    own = np.array([r["farm"] + r["forage"] >= r["need"] for r in un])
    own_st = np.array([r["farm"] + r["forage"] + r["stores"] >= r["need"] for r in un])
    print(
        f"\n-- A2 realized foraging (unit-years {len(un)}; eligible = remaining foraging target > 0, i.e. need x (1 + surplus target) - crop > 0)"
    )
    print(f"   eligible unit-years {rate(eligible)}")
    print(
        f"   remaining_foraging_target_met (wild harvest >= remaining target, rel. tol {TARGET_REL_TOL:g}) {rate(met, eligible)}"
    )
    print(f"     of eligible: unit short but its group met the summed target (effort-proportional split) {rate(~met & gmet, eligible)}; "
          f"group did not meet the summed target, so it applied all its labor (not: labor was the binding margin) {rate(~gmet, eligible)}")  # fmt: skip
    print(
        f"     single-unit cells {rate(met, eligible & ~multi)}; multi-unit cells {rate(met, eligible & multi)}"
    )
    print(
        f"   basic need from own production (crop + wild >= need, before stores and trade): all unit-years {rate(own)}; eligible {rate(own, eligible)}"
    )
    print(
        f"   basic need incl. stores (crop + wild + stores >= need, before trade): all unit-years {rate(own_st)}; eligible {rate(own_st, eligible)}"
    )
    share = np.array(
        [np.nan if r["unit_harvest_share"] is None else r["unit_harvest_share"] for r in un]
    )
    cutil = np.array([np.nan if r["cell_util"] is None else r["cell_util"] for r in un])
    print(
        f"   unit_harvest_share (own wild harvest / cell's accessible stock), eligible p10/p50/p90 {_q(share[eligible])}; > 0.5 {rate(share > 0.5, eligible)}"
    )
    print(
        f"   collective utilization of the unit's cell (all removals / accessible stock), eligible p10/p50/p90 {_q(cutil[eligible])}; > 0.5 {rate(cutil > 0.5, eligible)}"
    )
    print(
        f"     eligible with own share <= 0.5 but cell utilization > 0.5 {rate((share <= 0.5) & (cutil > 0.5), eligible)}"
    )
    print(
        f"     cell utilization of eligible units whose group missed its summed target p10/p50/p90 {_q(cutil[eligible & ~gmet])}"
    )
    cells = [c for o in outs for c in o.get("cell", [])]
    if cells:
        cu = np.array([np.nan if c["util"] is None else c["util"] for c in cells])
        cm = np.array([c["n"] >= 2 for c in cells])
        cmiss = np.array([c["met"] is False for c in cells])
        print(f"   foraging cell-years (one group per cell) {len(cells)}: collective utilization p10/p50/p90 {_q(cu)}; > 0.5 {rate(cu > 0.5)}; "
              f"multi-unit {rate(cm)}, of which > 0.5 {rate(cu > 0.5, cm)}")  # fmt: skip
        print(
            f"     cell-years whose group missed its summed remaining target {rate(cmiss)}; their utilization p10/p50/p90 {_q(cu[cmiss])}"
        )
        print(f"     removal = sum of member harvests (no double counting): max relative difference "
              f"{max(abs(c['removed'] - c['shares']) / max(c['removed'], 1.0) for c in cells):.2g}")  # fmt: skip
    miss = [m for o in outs for m in o.get("missed", [])]
    if miss:
        eps = np.array([np.nan if e is None else e for _, e in miss])
        print(f"   groups that missed their summed target {len(miss)}: harvest at full labor reproduces their removal {rate([ok for ok, _ in miss])}; "
              f"labor elasticity of harvest at full effort p10/p50/p90 {_q(eps)}; >= 0.9 {rate(eps >= 0.9)}; < 0.5 {rate(eps < 0.5)}")  # fmt: skip
        print(
            "     (1: harvest scales with labor; near 0: more labor takes almost nothing more from the stock; between: both limit)"
        )
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
        zero = np.array([a["arable"] <= 0 for a in ar])
        rat = np.array([a["rationed"] for a in ar])
        desiring = sum(x for o in outs for x in o.get("desiring_unit_years", []))
        print(
            f"   field planning (farming cell-years = occupied cells with desired or planned fields {len(ar)}; unit-years with desired fields {desiring};"
            " desired = this year's planned step toward the unit's target, before arable sharing):"
        )
        print(
            f"     allocation constrained by the arable cap (zero-arable or rationed) {rate(rat)} of farming cell-years; units in them {sum(a['n_desiring'] for a in ar if a['rationed'])}/{desiring} unit-years"
        )
        zd = [(i, u, d) for i, o in enumerate(outs) for u, d in o.get("zero_arable_desiring", [])]
        zu = [(i, u) for i, u, _ in zd]
        per_unit = list(Counter(zu).values())
        print(f"     (1) zero arable land, desired fields > 0, all planned to zero: {rate(zero)} of farming cell-years; unit-years {sum(a['n_desiring'] for a in ar if a['arable'] <= 0)}/{desiring}; "
              f"of which held fields before {sum(a['incumbents'] for a in ar if a['arable'] <= 0)}; distinct units {len(per_unit)}, such years per unit p50/p90/max {_q(per_unit, (0.5, 0.9, 1.0))}; "
              f"desired ha per unit p10/p50/p90 {_q([d for _, _, d in zd])}")  # fmt: skip
        ar = [a for a, z in zip(ar, zero, strict=True) if not z]
        at = np.array([a["at_cap"] for a in ar])
        rat = np.array([a["rationed"] for a in ar])
        mul = np.array([a["n_desiring"] >= 2 for a in ar])
        after = np.array([a["after_ratio"] for a in ar])
        print(
            f"     (2) positive arable land (cell-years {len(ar)}; recorded desired fields reproduce the kernel's sharing in {rate([a['capture_ok'] for a in ar])}):"
        )
        print(
            f"       planned fields >= 99 % of cap {rate(after >= 0.99)}; >= 99.9 % {rate(after >= 0.999)}; at cap (>= 1 - 1e-9) {rate(at)}"
        )
        print(f"       rationed (desired > cap: every unit scaled down pro rata) {rate(rat)}: >= 2 cultivators competing {rate(rat & mul)}, one cultivator exceeding the land {rate(rat & ~mul)}; "
              f"desired / cap p50/max {_q([a['desired_ratio'] for a in ar if a['rationed']], (0.5, 1.0))}; unit-years {sum(a['n_desiring'] for a in ar if a['rationed'])}/{desiring}; "
              f"unallocated / desired ha {sum(a['unallocated_ha'] for a in ar):.4g}/{sum(a['desired_ha'] for a in ar if a['rationed']):.4g} in rationed cells, of {sum(a['desired_ha'] for a in ar):.4g} desired overall")  # fmt: skip
        print(
            f"       units cut by rationing (wanted >= current fields, planned below them): cell-years with any {rate([a['rationing_cut'] > 0 for a in ar])}; units {sum(a['rationing_cut'] for a in ar)}; "
            f"zeroed by the 0.05 ha rounding after scaling {sum(a['zeroed_by_rounding'] for a in ar)}"
        )
        print(
            f"       incumbent cut while another expands: any cell {rate([a['cut'] > 0 and a['grow'] > 0 for a in ar])}; rationed cell {rate([a['cut'] > 0 and a['grow'] > 0 for a in ar], rat)}"
        )
        print(
            "     (no rule excludes a cultivator: sharing is pro rata over all units in the cell; competition = rationing with >= 2 cultivators)"
        )
    print(
        "\n-- A4 outside options (units in multi-unit cells; current per-head accessible stock, alternative / home;"
        " a reachable or believed cell, not a realized or costless move)"
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
            print(f"   actor (beliefs; units that evaluated migration {len(kn)}/{len(mem)}): known alternative cells p10/p50/p90 {_q([k[0] for k in kn])}; believed best / believed home p50 {_q(kr, (0.5,))}; "
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
    iso = np.array([x for o in outs for x in o.get("isolated", [])], dtype=bool)
    print(
        "\n-- C complementary shortage (pre-trade balance crop + wild + stores - need; neighbours = other units"
        " within one relocation range, the reach trade uses: geography, not contact or knowledge of stores)"
    )
    if pr or iso.size:
        short = np.array([p[0] for p in pr], dtype=bool)
        nb = np.array([p[1] for p in pr])
        cover = np.array([p[3] for p in pr if p[0]])
        all_short = np.concatenate([short, iso])
        print(
            f"   unit-years {len(all_short)}: with a neighbour {rate(np.r_[np.ones(len(pr)), np.zeros(iso.size)])}; isolated {rate(np.r_[np.zeros(len(pr)), np.ones(iso.size)])}"
        )
        print(
            f"   short: all unit-years {rate(all_short)}; with a neighbour {rate(short)}; isolated {rate(iso)}"
        )
        if short.any() and (~short).any():
            print(
                f"   (units with a neighbour) neighbours short | unit short {nb[short].mean():.3f} vs | unit not short {nb[~short].mean():.3f} (synchrony ratio {nb[short].mean() / max(nb[~short].mean(), 1e-300):.2f})"
            )
        n_short = int(all_short.sum())
        no_surplus = int((cover <= 0).sum())
        print(f"   short units without any surplus unit in reach: of short units with a neighbour {rate(cover <= 0)}; "
              f"of all short units (isolated short counted as without) {no_surplus + int(iso.sum())}/{n_short}")  # fmt: skip
        print(
            f"   hypothetical pre-competition coverage, short units with a neighbour: delivered-equivalent surplus balance in reach / own deficit p10/p50/p90 {_q(cover)}; >= 1 {rate(cover >= 1)}"
        )
        print(
            "     (whole surplus balances after the transport delivery fraction; not offers (phi x b), not allocated: one donor counts for every short unit in its reach)"
        )
        cb = np.array([x for o in outs for x in o.get("counted_by", [])])
        if cb.size:
            print(
                f"     surplus units counted by >= 1 short unit {cb.size}: short units counting the same surplus unit p50/p90/max {_q(cb, (0.5, 0.9, 1.0))}; counted by >= 2 {rate(cb >= 2)}"
            )
    lt = [x for o in outs for x in o.get("later", [])]
    if lt:
        spec = np.array([x[3] for x in lt])
        anyone = np.array([x[4] for x in lt])
        print(
            f"   potential role reversal (origin: a surplus unit with >= 1 short unit in reach; no transfer required or observed; first own shortage within {LATER} y):"
        )
        print(
            f"     per origin year (original weighting) {len(lt)}: a formerly short neighbour now has surplus in reach {rate(spec)}; any unit has surplus in reach {rate(anyone)}; delay p50 {np.median([x[2] for x in lt]):.0f} y"
        )
        first: dict[tuple[int, str, int], tuple[int, bool, bool]] = {}
        for i, o in enumerate(outs):
            for a, t, k, s, n in o.get("later", []):
                key = (i, a, t + k)
                if key not in first or k < first[key][0]:
                    first[key] = (k, s, n)
        ev = np.array(list(first.values()), dtype=float)
        print(
            f"     per distinct later shortage (most recent origin) {len(ev)}: formerly short neighbour {rate(ev[:, 1])}; any unit {rate(ev[:, 2])}; delay p50 {np.median(ev[:, 0]):.0f} y"
        )

    tc = [o["transfer_checks"] for o in outs]
    if any(t is None for t in tc):
        print(
            "\n-- realized transfers: not recorded (legacy recordings, or trade not in the pipeline)"
        )
        return
    t = Counter()
    for x in tc:
        t.update(x)
    n = t["transfers"]
    print(
        "\n-- realized transfers (authoritative TradeSubsystem proposals, joined by (year, unit id); integrity only, no reciprocity measure)"
    )
    print(f"   trade years {t['years']} (without any transfer {t['empty_years']}); transfers {n}; donor and recipient recorded that year {t['ids_recorded']}/{n}; "
          f"delivered = shipped x delivered fraction of the recorded path cost {t['delivery_exact']}/{n}; recipient need = recorded need {t['need_exact']}/{n}")  # fmt: skip
    print(f"   recipient short and donor in surplus by the recorded pre-trade balances {t['recipient_short']}/{n}; "
          f"shipped and transport loss = trade ledger in {t['ledger_exact']}/{t['years']} years; unit ids reappearing after a gap {t['ids_reappearing']}")  # fmt: skip


def _analyse_path(path: Path, legacy: bool) -> tuple[str, int, bool, dict[str, Any]]:
    run = load_data(path, legacy)
    return run["name"], run["seed"], run["neutral"], analyse_run(run)


def analyse(
    load: Path, jobs: int, seeds: list[int], explicit: bool, legacy: bool, mixed: bool = False
) -> None:
    started = time.perf_counter()
    try:
        paths = select_runs(load, list(MVP2_2), seeds, explicit, ident_of, legacy, mixed)
    except RecordingError as error:
        raise SystemExit(str(error)) from None
    with Pool(jobs, maxtasksperchild=1) as pool:  # one recording in memory per worker
        results = pool.starmap(_analyse_path, [(p, legacy) for p in paths], chunksize=1)
    print("observer-neutral:", {f"{n}/{s}": ok for n, s, ok, _ in results})
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
    parser.add_argument(
        "--seeds", type=int, nargs="*", help=f"explicit subset (default {list(SEEDS)})"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="record: overwrite existing recordings that do not match",
    )
    parser.add_argument(
        "--mixed-environments",
        action="store_true",
        help="analyse: explicitly compare runs from different execution environments",
    )
    parser.add_argument("--legacy-unverified", action="store_true",
                        help="analyse: accept pre-6B-P2 recordings without provenance (unverified)")  # fmt: skip
    args = parser.parse_args()
    seeds = list(SEEDS) if args.seeds is None else args.seeds
    if args.command == "record":
        assert args.out is not None
        args.out.mkdir(parents=True, exist_ok=True)
        specs = to_record(args.out, [(n, s) for n in MVP2_2 for s in seeds], ident_of, args.replace)
        with Pool(args.jobs) as pool:
            for run in pool.imap_unordered(record_job, specs):
                path = args.out / f"{run['name']}_{run['seed']}.pkl"
                write_recording(path, run.pop("provenance"), run)
                print(
                    f"recorded {run['name']} seed {run['seed']}: {len(run['years'])} years, neutral {run['neutral']}",
                    flush=True,
                )
    else:
        assert args.load is not None
        analyse(
            args.load,
            args.jobs,
            seeds,
            args.seeds is not None,
            args.legacy_unverified,
            args.mixed_environments,
        )


if __name__ == "__main__":
    main()
