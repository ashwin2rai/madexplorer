"""MVP 3 Stage 5H: donor routing and food accounting. COUNTERFACTUAL / NOT ACTIVE.

``madexplorer.economy.provisioning_counterfactual`` replays the production food matching on
recorded inputs and reorders donors under hypothetical routing rules. No simulator path
calls it.
"""

import importlib.util
import math
import random
import subprocess
import sys
from typing import Any

import pytest

from madexplorer.core.governance import RULES
from madexplorer.economy.provisioning_counterfactual import (
    choice_levels,
    delivered,
    local_replacement,
    match,
    order_key,
    without,
)
from madexplorer.population.energetics import energy_balance
from tests.conftest import ROOT

DECAY = 60.0


def market() -> tuple[list[Any], dict[str, float], dict[str, list[tuple[float, str]]]]:
    """Two recipients reaching three donors; ``r1`` is more severe and is served first."""
    deficits = [(-0.2, "r2", 20.0, 100.0), (-0.5, "r1", 50.0, 100.0)]
    offers = {"a": 30.0, "b": 60.0, "c": 100.0}
    donors_of = {
        "r1": [(10.0, "a"), (20.0, "b"), (50.0, "c")],
        "r2": [(5.0, "b"), (30.0, "a"), (40.0, "c")],
    }
    return deficits, offers, donors_of


def test_recipients_by_severity_then_id_donors_by_cost_then_id() -> None:
    deficits, offers, donors_of = market()
    m = match(deficits, offers, donors_of, DECAY, record=True)
    assert [d.recipient for d in m.decisions] == ["r1", "r2"]
    r1 = [(t[0], t[3]) for t in m.transfers if t[1] == "r1"]
    assert [d for d, _ in r1[:2]] == ["a", "b"]
    # floating-point residue: production keeps serving while ``left > 0``, so a covered
    # deficit can leave a dust transfer to the next donor (reproduced, not repaired)
    assert all(got < 1e-9 for _, got in r1[2:])
    # equal relative deficits: unit id breaks the tie (production sorts the same tuple)
    tie = [(-0.5, "z", 10.0, 20.0), (-0.5, "y", 10.0, 20.0)]
    m2 = match(tie, {"a": 100.0}, {"z": [(0.0, "a")], "y": [(0.0, "a")]}, DECAY, record=True)
    assert [d.recipient for d in m2.decisions] == ["y", "z"]
    assert order_key(5.0, "b", 0.0, 0.0, 60.0) < order_key(5.0, "c", 0.0, 0.0, 60.0)


def test_transport_loss_and_no_food_creation() -> None:
    deficits, offers, donors_of = market()
    m = match(deficits, offers, donors_of, DECAY)
    costs = {(d, r): c for r, v in donors_of.items() for c, d in v}
    for d, r, sent, got in m.transfers:
        assert got == pytest.approx(sent * delivered(costs[(d, r)], DECAY))
        assert got <= sent
    for d, total in m.sent().items():
        assert total <= offers[d] + 1e-12
    deficit = {r: x for _, r, x, _ in deficits}
    for r, total in m.received().items():
        assert total <= deficit[r] + 1e-9
    shipped, arrived = m.totals()
    assert shipped - arrived == pytest.approx(sum(s - g for _, _, s, g in m.transfers))


def test_one_zero_and_exhausted_donors_and_insufficient_supply() -> None:
    one = match([(-0.5, "r", 50.0, 100.0)], {"a": 10.0}, {"r": [(0.0, "a")]}, DECAY, record=True)
    assert one.received() == {"r": 10.0} and len(one.decisions[0].candidates) == 1
    none = match([(-0.5, "r", 50.0, 100.0)], {}, {"r": []}, DECAY, record=True)
    assert none.transfers == [] and none.decisions[0].candidates == ()
    deficits, offers, donors_of = market()
    m = match(deficits, offers, donors_of, DECAY, record=True)
    second = m.decisions[1]  # r2 is served after r1 used up a and part of b
    assert "a" not in {c.donor for c in second.candidates}
    assert {c.donor: c.offer for c in second.candidates}["b"] < 60.0


def test_zero_and_equal_ties_and_weight_zero_reproduce_h0() -> None:
    deficits, offers, donors_of = market()
    h0 = match(deficits, offers, donors_of, DECAY)
    zero: dict[str, dict[str, float]] = {"r1": {}, "r2": {}}
    assert match(deficits, offers, donors_of, DECAY, zero, weight=1.0).transfers == h0.transfers
    equal = {"r1": {"a": 0.4, "b": 0.4, "c": 0.4}, "r2": {"a": 0.4, "b": 0.4, "c": 0.4}}
    assert match(deficits, offers, donors_of, DECAY, equal, weight=1.0).transfers == h0.transfers
    strong_c = {"r1": {"c": 2.0}}
    assert match(deficits, offers, donors_of, DECAY, strong_c, weight=0.0).transfers == h0.transfers
    h1 = match(deficits, offers, donors_of, DECAY, strong_c, weight=1.0)
    assert next(t[0] for t in h1.transfers if t[1] == "r1") == "c"
    with pytest.raises(ValueError):
        order_key(1.0, "a", 0.0, 1.5, 60.0)


def test_input_order_neutrality() -> None:
    deficits, offers, donors_of = market()
    h0 = match(deficits, offers, donors_of, DECAY)
    rng = random.Random(3)
    for _ in range(5):
        d2 = deficits[:]
        rng.shuffle(d2)
        o2 = dict(rng.sample(list(offers.items()), len(offers)))
        n2 = {r: rng.sample(v, len(v)) for r, v in donors_of.items()}
        assert match(d2, o2, n2, DECAY).transfers == h0.transfers


def test_donor_removal_and_choice_levels() -> None:
    deficits, offers, donors_of = market()
    m = match(deficits, offers, donors_of, DECAY, record=True)
    alt = match(deficits, without(offers, "a"), donors_of, DECAY)
    assert "a" not in alt.sent() and alt.totals()[0] > 0
    first = m.decisions[0]
    taken = sum(g for d, r, _, g in m.transfers if d == "a" and r == "r1")
    assert 0.0 < local_replacement(first, "a", taken) <= 1.0
    levels = choice_levels(first, 0.1)
    assert levels["nominal"] and levels["effective"]
    assert levels["full"] is False  # no donor alone could deliver all 50


def test_harvest_adequacy_is_not_nutritional_sufficiency() -> None:
    # harvest short, stores cover: food_ratio < 1 but no deficit
    b = energy_balance(100.0, 70.0, 0.0, 30.0, stores_kcal=50.0, can_store=True)
    assert b.food_ratio == 0.7 and b.deficit == 0.0
    # a donor that ships 30 of 120 harvest and covers the gap from stores is fully fed
    donor = energy_balance(100.0, 90.0, 10.0, 30.0, stores_kcal=40.0, can_store=True)
    assert donor.food_ratio == 0.9 and donor.deficit == 0.0
    # a recipient receiving 30 kcal: deficit avoided vs still underfed
    assert energy_balance(100.0, 100.0, 5.0, 30.0).deficit == 0.0
    assert energy_balance(100.0, 70.0, 5.0, 30.0).deficit == pytest.approx(0.25)


def test_module_is_not_active() -> None:
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "provisioning_counterfactual", str(ROOT / "src")],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    assert [h for h in hits if not h.endswith("provisioning_counterfactual.py")] == []
    assert not any("provisioning_counterfactual" in r.qualname for r in RULES.values())


def _probe() -> Any:
    path = ROOT / "scripts/probes/provisioning_counterfactual.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("provisioning_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    probe = _probe()
    common = sys.modules["_common"]
    original = common.scenario_for
    probe.scenario_for = lambda n, s, w: original(n, s, w, years=60)
    run: dict[str, Any] = probe.record_job(("pressure+cult", 1))
    return run


def test_replay_reproduces_authoritative_transfers_and_observer_is_neutral(
    recorded: dict[str, Any],
) -> None:
    assert recorded["neutral"]  # physical digest with and without the hooks
    probe = _probe()
    transfers = 0
    for y in recorded["trade"]:
        h0 = probe._replay(y)
        assert h0.transfers == y["actual"]  # bit for bit: donors, recipients, shipped, delivered
        transfers += len(y["actual"])
    assert transfers > 0


def test_shadow_ties_reproduce_authoritative_ties_at_weight_zero(recorded: dict[str, Any]) -> None:
    probe = _probe()
    res = probe.shadow(recorded, 0.0, 0.7)
    assert res["tie_err"] == 0.0
    # tie-priority shadow changes routing but not physical totals' bounds
    alt = probe.shadow(recorded, 1.0, 0.7)
    assert alt["totals"]["shipped"] > 0 and math.isfinite(alt["totals"]["delivered"])


def test_energetics_recomputation_matches_authoritative(recorded: dict[str, Any]) -> None:
    for units in recorded["energy"].values():
        for need, h, st, reserve, cap, fr, de, _pop in units.values():
            b = energy_balance(need, h, reserve, cap, st, False)
            assert b.food_ratio == fr and b.deficit == de
