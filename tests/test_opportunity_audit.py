"""MVP 3 Stage 6B: foraging-patch opportunity diagnostics. READ-ONLY / NOT ACTIVE.

``madexplorer.economy.opportunity_audit`` replays production pooled foraging and compares it
with an independent-satisficing reference and with a unit alone in its cell, on the same
stock, labor, efficiency, targets and harvest function. No simulator path calls it.
"""

import importlib.util
import pickle
import subprocess
import sys
from typing import Any

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.governance import RULES
from madexplorer.economy.agriculture import FieldPlanningSubsystem
from madexplorer.economy.foraging import _harvest
from madexplorer.economy.opportunity_audit import (
    alone_harvest,
    gini,
    independent_harvest,
    labor_elasticity,
    pooled_harvest,
    regrowth_loss,
    remaining_target_met,
    utilization,
)
from madexplorer.experiments.benchmark import synthetic_simulator
from tests.conftest import ROOT, step_context

STOCK = (4.0e6, 2.0e6)  # accessible plant, game kcal
RETURNS = (1000.0, 2500.0)


def test_single_unit_has_no_rivalry() -> None:
    """Negative control: with one unit, all three references coincide."""
    args = (STOCK, RETURNS, [1500.0], [0.8], [9.0e5])
    pooled = pooled_harvest(*args)
    ind, _ = independent_harvest(*args)
    assert pooled[0] == pytest.approx(ind[0], rel=1e-9)
    assert pooled[0] == alone_harvest(STOCK, RETURNS, 1500.0, 0.8, 9.0e5)
    assert pooled[0] == pytest.approx(9.0e5, rel=1e-9)  # target attainable: met exactly


def test_conservation_and_no_double_counting() -> None:
    labor, eff, tgt = [1500.0, 900.0, 2000.0], [0.9, 0.5, 1.0], [8e5, 6e5, 2e6]
    pooled = pooled_harvest(STOCK, RETURNS, labor, eff, tgt)
    ind, effort = independent_harvest(STOCK, RETURNS, labor, eff, tgt)
    for shares in (pooled, ind):
        assert all(x >= 0 for x in shares)
        assert sum(shares) <= sum(STOCK)
    assert sum(ind) == pytest.approx(sum(_harvest(STOCK, RETURNS, sum(effort))))
    assert all(e <= lab * f + 1e-9 for e, lab, f in zip(effort, labor, eff, strict=True))


def test_equal_target_per_effective_hour_makes_pooling_neutral() -> None:
    labor, eff = [1000.0, 2000.0], [1.0, 1.0]
    tgt = [4e5, 8e5]  # proportional to effective labor
    pooled = pooled_harvest(STOCK, RETURNS, labor, eff, tgt)
    ind, _ = independent_harvest(STOCK, RETURNS, labor, eff, tgt)
    assert pooled == pytest.approx(ind, rel=1e-9)
    assert pooled == pytest.approx(tgt, rel=1e-9)


def test_pooling_redistributes_when_targets_differ() -> None:
    labor, eff = [1000.0, 1000.0], [1.0, 1.0]
    tgt = [0.0, 8e5]  # unit 0 is fed by crops but has labor left
    pooled = pooled_harvest(STOCK, RETURNS, labor, eff, tgt)
    ind, effort = independent_harvest(STOCK, RETURNS, labor, eff, tgt)
    assert pooled[0] == pytest.approx(4e5, rel=1e-9) and pooled[1] == pytest.approx(4e5, rel=1e-9)
    assert ind[0] == 0.0 and effort[0] == 0.0 and ind[1] == pytest.approx(8e5, rel=1e-9)
    assert sum(pooled) == pytest.approx(sum(ind), rel=1e-9)  # same total: distribution only


def test_labor_constrained_unit_and_scarce_stock() -> None:
    small = (2.0e5, 1.0e5)
    labor, eff, tgt = [2000.0, 100.0], [1.0, 1.0], [5e5, 5e5]
    ind, effort = independent_harvest(small, RETURNS, labor, eff, tgt)
    assert effort == pytest.approx([2000.0, 100.0])  # nobody can reach its target: all work
    pooled = pooled_harvest(small, RETURNS, labor, eff, tgt)
    assert pooled == pytest.approx(ind, rel=1e-9)  # full effort: both split by effort
    alone = alone_harvest(small, RETURNS, 100.0, 1.0, 5e5)
    assert alone > pooled[1]  # without the co-user the small unit takes far more


def test_zero_targets_and_zero_labor() -> None:
    idle = independent_harvest(STOCK, RETURNS, [100.0, 100.0], [1.0, 1.0], [0.0, 0.0])
    assert idle[0] == [0.0, 0.0]
    assert pooled_harvest(STOCK, RETURNS, [0.0], [1.0], [1e5]) == [0.0]


def test_regrowth_loss() -> None:
    assert regrowth_loss(1e6, 4e6, 1.5, 0.01, 0.0) == 0.0
    losses = [regrowth_loss(1e6, 4e6, 1.5, 0.01, x) for x in (1e4, 1e5, 5e5)]
    assert 0 < losses[0] < losses[1] < losses[2]
    # at capacity the stock cannot exceed it: removing from a full stock costs less next year
    assert regrowth_loss(4e6 - 1e5, 4e6, 1.5, 0.01, 1e5) < 1e5


def test_gini() -> None:
    assert gini([1.0, 1.0, 1.0]) == 0.0
    assert gini([0.0, 0.0, 0.0, 4.0]) == pytest.approx(0.75)
    assert gini([]) == 0.0


def test_module_is_not_active() -> None:
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "opportunity_audit", str(ROOT / "src")],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    assert [h for h in hits if not h.endswith("opportunity_audit.py")] == []
    assert not any("opportunity_audit" in r.qualname for r in RULES.values())


# --- Stage 6B-P1 measurement corrections

SURPLUS_TARGET = 0.2  # human foraging.surplus_target


def _remaining(need: float, crop: float) -> float:
    """``ForagingSubsystem._inputs``: the foraging target is net of crops."""
    return max(need * (1.0 + SURPLUS_TARGET) - crop, 0.0)


def test_remaining_target_does_not_count_crops_twice() -> None:
    need, crop = 1.0e6, 5.0e5
    remaining = _remaining(need, crop)  # 7e5 kcal left for foraging
    forage = 4.0e5
    assert crop + forage >= remaining  # the original check: crops counted a second time
    assert remaining_target_met(forage, remaining) is False
    reached = alone_harvest(STOCK, RETURNS, 1500.0, 0.8, remaining)
    assert remaining_target_met(reached, remaining) is True


def test_remaining_target_eligibility_and_attainability() -> None:
    assert remaining_target_met(0.0, _remaining(1.0e6, 2.0e6)) is None  # crops cover it all
    assert remaining_target_met(5.0, 0.0) is None
    target = _remaining(1.0e6, 0.0)  # no crop: the whole target is wild
    attainable = alone_harvest(STOCK, RETURNS, 1500.0, 0.8, target)
    assert attainable == pytest.approx(target, rel=1e-9)
    assert remaining_target_met(attainable, target) is True
    scarce = alone_harvest((2.0e5, 1.0e5), RETURNS, 1500.0, 0.8, target)  # all labor applied
    assert scarce < target and remaining_target_met(scarce, target) is False


def test_collective_utilization_is_not_an_individual_share() -> None:
    stock = (1.0e5, 1.0e5)
    shares = pooled_harvest(stock, RETURNS, [5000.0, 5000.0], [1.0, 1.0], [7.0e4, 7.0e4])
    avail = sum(stock)
    individual = [utilization(x, avail) for x in shares]
    collective = utilization(sum(shares), avail)
    assert all(x is not None and x < 0.5 for x in individual)
    assert collective is not None and collective > 0.5
    assert utilization(1.0, 0.0) is None


def test_labor_elasticity_separates_exhausted_labor_from_a_binding_margin() -> None:
    assert labor_elasticity(STOCK, RETURNS, 1e-3) == pytest.approx(1.0, abs=1e-6)  # scales
    assert labor_elasticity(STOCK, RETURNS, 1e6) == pytest.approx(0.0, abs=1e-6)  # depleted
    middle = labor_elasticity(STOCK, RETURNS, 3000.0)
    assert middle is not None and 0.1 < middle < 0.9  # both labor and stock limit
    assert labor_elasticity((0.0, 0.0), RETURNS, 1500.0) is None


def test_rare_events_stay_visible_and_empty_denominators_are_explicit() -> None:
    probe = _probe()
    flags = [True] + [False] * 99_999
    assert f"{sum(flags) / len(flags):.3f}" == "0.000"  # how the original report hid it
    assert probe.rate(flags) == "1/100000 (0.001 %)"
    assert probe.rate([True, False], [False, False]) == "0/0 (no eligible observations)"
    assert probe.rate([], []) == "0/0 (no eligible observations)"


def test_arable_cap_use_is_not_rationing() -> None:
    probe = _probe()
    full = probe.arable_cell([(5.0, 5.0, 5.0), (5.0, 5.0, 5.0)], 10.0)  # fills it, nobody cut
    assert full["at_cap"] and not full["rationed"] and full["rationing_cut"] == 0
    assert full["capture_ok"]
    scaled = probe.arable_cell([(6.0, 5.0, 6.0), (2.0, 5.0, 6.0)], 10.0)  # desired 12 > 10
    assert scaled["rationed"] and scaled["at_cap"] and scaled["capture_ok"]
    assert scaled["cut"] == 1 and scaled["grow"] == 1 and scaled["rationing_cut"] == 1
    shrink = probe.arable_cell([(6.0, 4.0, 4.0), (1.0, 3.0, 3.0)], 10.0)  # own choice, no cap
    assert not shrink["rationed"] and shrink["cut"] == 1 and shrink["rationing_cut"] == 0
    assert not probe.arable_cell([(1.0, 1.0, 2.0)], 10.0)["capture_ok"]
    # no arable land: every desired field is rationed to zero (unavailable, not contested)
    none = probe.arable_cell([(0.0, 0.0, 5.0), (0.0, 0.0, 3.0)], 0.0)
    assert none["rationed"] and none["capture_ok"] and none["n_desiring"] == 2
    assert none["unallocated_ha"] == 8.0 and none["incumbents"] == 0
    # pro rata sharing excludes nobody, except through the 0.05 ha rounding
    s = 5.0 / 10.06
    rounded = probe.arable_cell([(0.0, 10.0 * s, 10.0), (0.0, 0.0, 0.06)], 5.0)
    assert rounded["rationed"] and rounded["capture_ok"] and rounded["zeroed_by_rounding"] == 1
    assert full["unallocated_ha"] == 0.0 and shrink["unallocated_ha"] == 0.0


def test_potential_role_reversal_needs_no_transfer() -> None:
    probe = _probe()
    reach = [(1, 10.0)]  # cells 0 and 1 reach each other
    back = [(0, 10.0)]
    # year 0: a (cell 0) has surplus, b (cell 1) is short; no transfer is recorded anywhere
    seq = {
        0: {"a": (5.0, 0, reach), "b": (-3.0, 1, back)},
        1: {"a": (1.0, 0, reach), "b": (-1.0, 1, back)},
        2: {"a": (-2.0, 0, reach), "b": (4.0, 1, back)},
    }
    # both year 0 and year 1 are origins of the same later shortage (per-origin weighting)
    assert probe.potential_role_reversal(seq, 10) == [
        ("a", 0, 2, True, True),
        ("a", 1, 1, True, True),
    ]
    gone = {**seq, 2: {"a": (-2.0, 0, reach), "c": (4.0, 1, back)}}  # b extinct, c arrived
    assert probe.potential_role_reversal(gone, 10)[0] == ("a", 0, 2, False, True)
    vanished = {**seq, 2: {"b": (4.0, 1, back)}}  # a disappears: window closes, no record
    assert probe.potential_role_reversal(vanished, 10) == []
    later = {**seq, 1: {"a": (1.0, 0, reach), "b": (1.0, 1, back)}}  # only year 0 an origin
    assert probe.potential_role_reversal(later, 1) == []  # shortage beyond the horizon
    assert len(probe.potential_role_reversal(later, 2)) == 1
    no_short = {0: {"a": (5.0, 0, reach), "b": (3.0, 1, back)}, 2: seq[2]}
    assert probe.potential_role_reversal(no_short, 10) == []  # origin needs a short neighbour


def test_isolated_units_have_no_neighbours() -> None:
    probe = _probe()
    where = {0: ["a", "b"], 5: ["c"]}
    assert probe.neighbours("c", {"cell": 5, "occupied_reach": []}, where) == []
    assert probe.neighbours("a", {"cell": 0, "occupied_reach": [(5, 7.0)]}, where) == [
        ("c", 7.0),
        ("b", 0.0),
    ]


def test_desired_capture_agrees_with_production_planning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The captured desired fields are the production kernel's, and reproduce its plans with
    zero, limited and ample arable land, several cultivators and incumbent changes."""
    probe = _probe()
    sc = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(seed=2)
    sim = synthetic_simulator(sc, 40, farming=True)
    for _ in range(3):
        sim.step()
    units = sorted(sim.state.units.values(), key=lambda u: u.id)
    zero, scarce, ample = list(dict.fromkeys(u.cell for u in units))[:3]
    for unit, cell in zip(units, (zero, zero, scarce, scarce, scarce, ample), strict=False):
        unit.cell, unit.fields_ha, unit.forage_marginal_kcal_per_hour = cell, 0.0, 1.0  # expand
    contracting = units[5]  # incumbent whose foraging pays better: shrinks by its own choice
    contracting.fields_ha, contracting.forage_marginal_kcal_per_hour = 10.0, 1e7
    subsystem = FieldPlanningSubsystem()
    base = np.asarray(step_context(sim).arable_ha, dtype=float)

    def run(arable: np.ndarray) -> tuple[Any, ...]:
        monkeypatch.setattr(type(step_context(sim)), "arable_ha", property(lambda _: arable))
        ctx = step_context(sim)
        (plain,) = subsystem.evaluate(sim.state, ctx)
        (wrapped,), desired = probe.plan_with_desired(
            FieldPlanningSubsystem.evaluate, subsystem, sim.state, ctx
        )
        (reference,) = subsystem._evaluate_reference(sim.state, ctx)
        state = [tuple(getattr(p, k).tolist() for k in ("rows", "fields_ha", "clearing_hours"))
                 for p in (plain, wrapped, reference)]  # fmt: skip
        assert state[0] == state[1] == state[2]  # capturing changes nothing; kernel = reference
        now = ctx.columns(sim.state).get("fields_ha")
        after = now.copy()
        after[wrapped.rows] = wrapped.fields_ha
        return ctx.columns(sim.state), now, after, desired

    # unlimited land: the authoritative Python path plants exactly the captured desired fields
    incumbent = units[4]
    cols, _, _, first = run(np.full_like(base, np.inf))
    row = [u.id for u in cols.units].index(incumbent.id)
    incumbent.fields_ha = float(first[row])  # wants to keep and grow these fields
    fingerprint = sys.modules["_integrity"].fingerprint
    digest = fingerprint(sim)
    cols, now, after, desired = run(np.full_like(base, np.inf))
    assert np.array_equal(after, np.where(desired < 0.05, 0.0, desired))
    cell_of = cols.get("cell")
    arable = base.copy()
    arable[zero], arable[ample] = 0.0, np.inf
    arable[scarce] = 0.1 * desired[cell_of == scarce].sum()
    cols, now, after, again = run(arable)
    assert np.array_equal(again, desired)  # desired fields do not depend on arable land
    assert fingerprint(sim) == digest  # no state or RNG change (every component)
    ids = [u.id for u in cols.units]
    out = {}
    for c in set(cell_of.tolist()):
        rows = np.flatnonzero(cell_of == c)
        out[c] = probe.arable_cell([(now[r], after[r], desired[r]) for r in rows], float(arable[c]))
        assert out[c]["capture_ok"]
    in_zero = [ids.index(u.id) for u in units[:2]]
    assert all(desired[r] > 0 and after[r] == 0.0 for r in in_zero)
    assert out[zero]["rationed"] and out[zero]["n_desiring"] >= 2
    assert out[scarce]["rationed"] and out[scarce]["n_desiring"] >= 3
    assert out[scarce]["rationing_cut"] >= 1  # the incumbent, cut by the shared cap
    r = ids.index(contracting.id)
    assert after[r] < now[r] and not out[ample]["rationed"] and out[ample]["rationing_cut"] == 0


# --- replay on a recorded MVP 2.2 run


def _probe() -> Any:
    path = ROOT / "scripts/probes/opportunity_audit.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("opportunity_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    probe = _probe()
    cultivation = {"mechanisms.cultivation": True}
    probe.MVP2_2 = {"pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 100, cultivation)}
    run: dict[str, Any] = probe.record_job(("pressure+cult", 1))
    return run


def test_replay_is_exact_and_observer_is_neutral(recorded: dict[str, Any]) -> None:
    assert recorded["neutral"]  # physical digest with and without the hooks
    out = _probe().analyse_run(recorded)
    assert out["replay_groups"] > 0 and out["replay_exact"] == out["replay_groups"]
    assert out["regrowth_checked"] > 0 and out["regrowth_err"] == 0.0


def test_outside_options_use_current_state_only(recorded: dict[str, Any]) -> None:
    for y in recorded["years"]:
        for uid, u in y["units"].items():
            assert u["best_alt"] >= 0 and 0 <= u["share_better"] <= 1
            known = recorded["known"].get(y["year"], {}).get(uid)
            if known is not None:  # believed cells are a subset of the reachable ones
                assert known[0] <= u["n_reach"]


def test_recorded_target_is_net_of_crops(recorded: dict[str, Any]) -> None:
    path = "scenarios/mvp2_2_pressure.yaml"
    surplus = Scenario.from_yaml(path).species["human"].foraging.surplus_target
    checked = 0
    for y in recorded["years"]:
        for u in y["units"].values():
            assert u["target"] == pytest.approx(
                max(u["need"] * (1.0 + surplus) - u["farm"], 0.0), rel=1e-12, abs=1e-6
            )
            checked += u["farm"] > 0
    assert checked > 0  # crops were present in the recording


def test_analysis_measures_and_denominators(recorded: dict[str, Any]) -> None:
    probe = _probe()
    before = pickle.dumps(recorded)
    out = probe.analyse_run(recorded)
    assert pickle.dumps(recorded) == before  # the analysis does not modify the recording
    unit_years = sum(len(y["units"]) for y in recorded["years"])
    assert len(out["pair"]) + len(out["isolated"]) == unit_years
    assert len(out["unit"]) == unit_years
    for c in out["cell"]:  # collective removal is the sum of members' harvests
        assert c["removed"] == pytest.approx(c["shares"], rel=1e-12)
        if c["util"] is not None:
            assert c["util"] >= c["max_share"] * (1 - 1e-12)
    assert all(a["capture_ok"] for a in out["arable"])
    assert out["missed"] and all(ok for ok, _ in out["missed"])  # missed => all labor applied


def test_recorded_transfers_are_authoritative_and_joinable(recorded: dict[str, Any]) -> None:
    checks = _probe().transfer_checks(recorded)
    assert checks is not None
    n, years = checks["transfers"], checks["years"]
    assert n > 0 and years == recorded["provenance"]["years_completed"]  # every trade year
    assert checks["ids_recorded"] == n  # donor and recipient known that year by unit id
    assert checks["delivery_exact"] == n  # delivered = shipped x exp(-path cost / decay)
    assert checks["need_exact"] == n and checks["recipient_short"] == n
    assert checks["ledger_exact"] == years  # shipped and transport loss = authoritative ledger
    assert checks["ids_reappearing"] == 0  # ids name one unit for its recorded life
    assert sum(not ts for ts in recorded["transfers"].values()) == checks["empty_years"]


def test_transfer_capture_agrees_with_an_independent_observer(recorded: dict[str, Any]) -> None:
    path = ROOT / "scripts/probes/donor_offer_audit.py"
    spec = importlib.util.spec_from_file_location("donor_offer_probe_check", path)
    assert spec and spec.loader
    donor: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(donor)
    cultivation = {"mechanisms.cultivation": True}
    donor.MVP2_2 = {"pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 100, cultivation)}
    other = donor.record_job(("pressure+cult", 1))  # a separate run, observed by another probe
    ours = {y: [t[:4] for t in ts] for y, ts in recorded["transfers"].items()}
    assert ours == {y["year"]: y["actual"] for y in other["trade"]}
