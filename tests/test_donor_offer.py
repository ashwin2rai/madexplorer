"""MVP 3 Stage 6A: donor-side decomposition of food provisioning. COUNTERFACTUAL / NOT ACTIVE.

``madexplorer.economy.donor_offer`` splits production provisioning into surplus, offer,
shipment, delivery and retained food, and prices a shipment for the donor with the
production energy balance. No simulator path calls it.
"""

import importlib.util
import subprocess
import sys
from typing import Any

import pytest

from madexplorer.config.schema import MechanismsConfig
from madexplorer.core.governance import RULES
from madexplorer.economy.donor_offer import (
    DUST_KCAL,
    balances,
    deficits_of,
    donor_payment,
    giving_cost,
    offer_use,
    offers_at,
    unmet,
)
from madexplorer.economy.provisioning_counterfactual import delivered, match
from tests.conftest import ROOT

DECAY = 60.0
PHI = 0.3


def market(
    harvest: dict[str, float], stores: dict[str, float], need: dict[str, float], phi: float = PHI
) -> tuple[dict[str, float], list[Any]]:
    b = balances(harvest, stores, need)
    return offers_at(b, phi), deficits_of(b, need)


# --- 1-6: donors


def test_no_surplus_and_exact_cover_make_neither_offer_nor_request() -> None:
    need = {"a": 100.0, "e": 100.0}
    offers, deficits = market({"a": 80.0, "e": 100.0}, {"a": 10.0, "e": 0.0}, need)
    assert offers == {}  # a: b = -10 is a recipient; e: b = 0 is neither
    assert [r for _, r, _, _ in deficits] == ["a"]


def test_surplus_from_harvest_only() -> None:
    offers, _ = market({"d": 150.0}, {"d": 0.0}, {"d": 100.0})
    assert offers == {"d": PHI * 50.0}
    assert donor_payment(150.0, 0.0, [15.0]) == (135.0, 0.0)
    # reserves full: the shipment would have gone to storage and kept r of it
    c = giving_cost(100.0, 150.0, 0.0, 30.0, 30.0, 0.15, [15.0])
    assert c.reserve == 0.0 and c.retained == pytest.approx(0.15 * 15.0)
    assert c.lost_anyway == pytest.approx(0.85 * 15.0) and c.deficit == 0.0


def test_surplus_partly_in_stores_is_paid_from_harvest_first() -> None:
    offers, _ = market({"d": 90.0}, {"d": 60.0}, {"d": 100.0})
    assert offers == {"d": pytest.approx(15.0)}
    h, s = donor_payment(90.0, 60.0, [15.0])
    assert (h, s) == (75.0, 60.0)  # stores untouched by the shipment itself
    c = giving_cost(100.0, 90.0, 60.0, 30.0, 30.0, 0.5, [15.0])
    assert c.from_stores == 0.0
    assert c.retained == pytest.approx(0.5 * 15.0)  # stores eaten in its place
    assert c.food_ratio_after == 0.75 and c.intake_after == 1.0 and c.deficit == 0.0


def test_genuine_storage_buffer_and_no_storage() -> None:
    granary = giving_cost(100.0, 200.0, 0.0, 30.0, 30.0, 0.8, [30.0])
    assert granary.retained == pytest.approx(0.8 * 30.0) and granary.carried == pytest.approx(24.0)
    none = giving_cost(100.0, 200.0, 0.0, 30.0, 30.0, 0.0, [30.0])
    assert none.carried == 0.0 and none.lost_anyway == 30.0  # it would have spoiled
    # reserves not yet full: giving costs body reserve one for one
    low = giving_cost(100.0, 120.0, 0.0, 0.0, 30.0, 0.0, [10.0])
    assert low.reserve == pytest.approx(10.0) and low.lost_anyway == pytest.approx(0.0)


# --- 7-10: recipients and competition


def test_small_and_large_deficits_against_one_donor() -> None:
    offers, deficits = market(
        {"d": 300.0, "s": 95.0, "l": 40.0}, {"d": 0.0, "s": 0.0, "l": 0.0},
        {"d": 100.0, "s": 100.0, "l": 100.0},
    )  # fmt: skip
    donors_of = {"s": [(0.0, "d")], "l": [(0.0, "d")]}
    m = match(deficits, offers, donors_of, DECAY)
    left = unmet(deficits, m)
    assert [r for _, r, _, _ in sorted(deficits)] == ["l", "s"]  # most severe first
    # 60 offered, l took all of it
    assert left["l"] == pytest.approx(0.0) and left["s"] == pytest.approx(5.0)


def test_recipients_compete_for_one_offer_and_donors_for_one_recipient() -> None:
    offers = {"a": 30.0, "b": 30.0}
    deficits = [(-0.5, "r1", 50.0, 100.0), (-0.2, "r2", 20.0, 100.0)]
    donors_of = {"r1": [(0.0, "a"), (0.0, "b")], "r2": [(0.0, "a")]}
    m = match(deficits, offers, donors_of, DECAY)
    assert m.received() == {"r1": pytest.approx(50.0)}  # r1 exhausts a, r2 gets nothing
    use = offer_use(offers, m)
    assert use["a"].state == "exhausted" and use["b"].state == "partial"
    assert unmet(deficits, m)["r2"] == 20.0


# --- 11-16: offer use, transport, conservation


def test_offer_used_partially_unused_and_without_recipient() -> None:
    offers = {"a": 10.0, "b": 100.0, "c": 50.0}
    deficits = [(-0.3, "r", 30.0, 100.0)]
    m = match(deficits, offers, {"r": [(0.0, "a"), (0.0, "b")]}, DECAY)
    use = offer_use(offers, m)
    assert use["a"].state == "exhausted" and use["a"].unused == 0.0
    assert use["b"].state == "partial" and use["b"].unused == pytest.approx(80.0)
    assert use["c"].state == "unused" and use["c"].shipped == 0.0  # no recipient in reach
    assert giving_cost(100.0, 300.0, 0.0, 30.0, 30.0, 0.5, use["c"].shipments).carried == 0.0


def test_transport_loss_and_conservation() -> None:
    harvest, stores = {"d": 120.0, "r": 50.0}, {"d": 200.0, "r": 0.0}
    need = {"d": 100.0, "r": 100.0}
    offers, deficits = market(harvest, stores, need)
    m = match(deficits, offers, {"r": [(30.0, "d")]}, DECAY)
    use = offer_use(offers, m)["d"]
    assert use.delivered == pytest.approx(use.shipped * delivered(30.0, DECAY))
    assert use.delivered < use.shipped
    assert use.shipped == pytest.approx(offers["d"])  # 0.3 * 220 = 66 < 50 / f
    h, s = donor_payment(harvest["d"], stores["d"], use.shipments)
    assert harvest["d"] + stores["d"] - (h + s) == pytest.approx(use.shipped)
    assert h == pytest.approx(54.0) and s == 200.0  # harvest pays the whole shipment
    c = giving_cost(need["d"], harvest["d"], stores["d"], 30.0, 30.0, 0.5, use.shipments)
    assert c.carried + c.lost_anyway == pytest.approx(use.shipped)
    assert c.deficit == 0.0 and c.intake_after == 1.0


def test_sequential_payment_matches_production_order() -> None:
    # several shipments are paid one at a time, harvest first then stores, as TradeRound.apply
    h, s = donor_payment(10.0, 100.0, [6.0, 6.0, 6.0])
    assert (h, s) == (0.0, 92.0)


# --- 17-18: when the offer fraction matters


def test_offer_fraction_irrelevant_when_supply_is_ample() -> None:
    harvest, stores, need = {"d": 1000.0, "r": 90.0}, {"d": 0.0, "r": 0.0}, {"d": 100.0, "r": 100.0}
    donors_of = {"r": [(10.0, "d")]}
    results = []
    for phi in (0.1, 0.3, 1.0):
        offers, deficits = market(harvest, stores, need, phi)
        results.append(match(deficits, offers, donors_of, DECAY).transfers)
    assert results[0] == results[1] == results[2]


def test_offer_fraction_binds_under_scarcity() -> None:
    harvest = {"d": 130.0, "r1": 40.0, "r2": 60.0}
    stores, need = dict.fromkeys(harvest, 0.0), dict.fromkeys(harvest, 100.0)
    donors_of = {"r1": [(0.0, "d")], "r2": [(0.0, "d")]}
    got = {}
    for phi in (0.0, 0.3, 1.0):
        offers, deficits = market(harvest, stores, need, phi)
        got[phi] = sum(match(deficits, offers, donors_of, DECAY).received().values())
    assert got[0.0] == 0.0 and got[0.3] == pytest.approx(9.0) and got[1.0] == pytest.approx(30.0)


# --- 19-20: information and inactivity


def test_offers_read_only_the_donors_current_balance() -> None:
    b = balances({"d": 150.0}, {"d": 20.0}, {"d": 100.0})
    assert offers_at(b, PHI) == offers_at({"d": 70.0}, PHI) == {"d": PHI * 70.0}
    assert offers_at(b, {"d": 0.5}) == {"d": 35.0}
    assert DUST_KCAL < 1e-3


def test_module_is_not_active() -> None:
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "donor_offer", str(ROOT / "src")],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    assert [h for h in hits if not h.endswith("donor_offer.py")] == []
    assert not any("donor_offer" in r.qualname for r in RULES.values())
    assert not any("donor" in name or "offer" in name for name in MechanismsConfig.model_fields)


# --- replay on a recorded MVP 2.2 run


def _probe() -> Any:
    path = ROOT / "scripts/probes/donor_offer_audit.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("donor_offer_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    probe = _probe()
    cultivation = {"mechanisms.cultivation": True}
    probe.MVP2_2 = {"pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 60, cultivation)}
    run: dict[str, Any] = probe.record_job(("pressure+cult", 1))
    return run


def test_d0_rebuilt_from_raw_inputs_reproduces_mvp2_2_transfers(recorded: dict[str, Any]) -> None:
    assert recorded["neutral"]  # physical digest with and without the hooks
    probe = _probe()
    transfers = 0
    for y in recorded["trade"]:
        b, share, deficits = probe.inputs(y)
        m = probe._replay(y, offers_at(b, share), deficits)
        assert m.transfers == y["actual"]  # bit for bit
        transfers += len(y["actual"])
    assert transfers > 0


def test_donor_inputs_precede_the_years_outcome(recorded: dict[str, Any]) -> None:
    """Harvest memory at the trade decision ends with last year's post-trade harvest."""
    energy = recorded["energy"]
    checked = same = 0
    for y in recorded["trade"]:
        last = energy.get(y["year"] - 1, {})
        for uid, i in y["info"].items():
            if uid in last and i["history"]:
                h, people = last[uid][1], last[uid][7]
                same += i["history"][-1] == pytest.approx(h / people)
                checked += 1
    assert checked > 0 and same / checked > 0.9  # fusion blends the target's memory
    # the giving cost the probe prices equals the authoritative donor energetics
    out = probe_analysis(recorded)
    assert out["energy_err"] == 0.0 and out["exact_years"] == out["years"]


def probe_analysis(run: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = _probe().analyse_run(run)
    return result
