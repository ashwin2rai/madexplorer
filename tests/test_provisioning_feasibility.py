"""MVP 3 Stage 6B-P3: simultaneous provisioning feasibility. READ-ONLY / NOT ACTIVE.

``madexplorer.economy.provisioning_feasibility`` is the analyst's upper bound on food the
recorded offers can deliver simultaneously; the greedy production matching
(``provisioning_counterfactual.match``) is checked against it on cases with known optima.
"""

import math
import subprocess
import sys
from typing import Any

import pytest

from madexplorer.core.governance import RULES
from madexplorer.economy import provisioning_feasibility as pf
from madexplorer.economy.provisioning_counterfactual import match
from madexplorer.economy.provisioning_feasibility import (
    Allocation,
    FeasibilityError,
    check,
    components,
    edges_from,
    solve,
)
from tests.conftest import ROOT


def delivered(offers: dict[str, float], deficits: dict[str, float], edges: list[Any]) -> float:
    return solve(offers, deficits, edges).delivered


def test_one_donor_one_recipient() -> None:
    assert delivered({"A": 80.0}, {"R": 50.0}, [("A", "R", 1.0)]) == pytest.approx(50.0)
    assert delivered({"A": 30.0}, {"R": 50.0}, [("A", "R", 1.0)]) == pytest.approx(30.0)


def test_one_donor_several_recipients_and_several_donors_one_recipient() -> None:
    star = [("A", "R1", 1.0), ("A", "R2", 1.0), ("A", "R3", 1.0)]
    assert delivered({"A": 100.0}, {"R1": 20.0, "R2": 30.0, "R3": 80.0}, star) == pytest.approx(
        100.0
    )
    fan = [("A", "R", 1.0), ("B", "R", 1.0), ("C", "R", 1.0)]
    assert delivered({"A": 10.0, "B": 20.0, "C": 30.0}, {"R": 45.0}, fan) == pytest.approx(45.0)


def test_shared_donor_greedy_is_suboptimal_and_the_optimum_is_id_independent() -> None:
    """A and B offer 50; R1 reaches A and B, R2 only A; no loss. Optimum 100."""
    for r1, r2 in (("R1", "R2"), ("R2", "R1")):  # exchange the recipients' ids
        edges = [("A", r1, 1.0), ("B", r1, 1.0), ("A", r2, 1.0)]
        best = solve({"A": 50.0, "B": 50.0}, {r1: 50.0, r2: 50.0}, edges)
        assert best.delivered == pytest.approx(100.0)
        assert best.received() == pytest.approx({r1: 50.0, r2: 50.0})
    # production order serves R1 first (more severe) and takes the nearest donor, A
    greedy = match([(-0.6, "R1", 50.0, 80.0), (-0.5, "R2", 50.0, 100.0)], {"A": 50.0, "B": 50.0},
                   {"R1": [(0.0, "A"), (1.0, "B")], "R2": [(0.0, "A")]}, 1e9)  # fmt: skip
    assert greedy.totals()[1] == pytest.approx(50.0)


def test_recipient_without_donor_and_disconnected_networks() -> None:
    offers, deficits = {"A": 50.0, "B": 50.0}, {"R1": 40.0, "R2": 70.0, "R3": 10.0}
    edges = [("A", "R1", 1.0), ("B", "R2", 1.0)]  # R3 reaches nobody
    best = solve(offers, deficits, edges)
    assert best.received() == pytest.approx({"R1": 40.0, "R2": 50.0})
    assert sorted((sorted(d), sorted(r)) for d, r in components(edges)) == [
        (["A"], ["R1"]),
        (["B"], ["R2"]),
    ]


def test_transport_losses_route_by_delivered_fraction() -> None:
    # A delivers 90 %, B 50 %; R needs 45: shipping from A costs 50 kcal, from B 90
    best = solve({"A": 50.0, "B": 100.0}, {"R": 45.0}, [("A", "R", 0.9), ("B", "R", 0.5)])
    assert best.delivered == pytest.approx(45.0)
    assert best.sent()["A"] == pytest.approx(50.0) and best.sent()["B"] == pytest.approx(
        0.0, abs=1e-6
    )
    # scarce supply: each donor serves the recipient it reaches with less loss
    cross = [("A", "R1", 0.9), ("A", "R2", 0.5), ("B", "R1", 0.5), ("B", "R2", 0.9)]
    assert delivered({"A": 10.0, "B": 10.0}, {"R1": 100.0, "R2": 100.0}, cross) == pytest.approx(
        18.0
    )


def test_supply_above_and_below_demand() -> None:
    full = [(d, r, 1.0) for d in "AB" for r in ("R1", "R2")]
    assert delivered({"A": 100.0, "B": 100.0}, {"R1": 30.0, "R2": 40.0}, full) == pytest.approx(
        70.0
    )
    assert delivered({"A": 10.0, "B": 15.0}, {"R1": 30.0, "R2": 40.0}, full) == pytest.approx(25.0)


def test_lossless_complete_graph_is_min_of_supply_and_demand() -> None:
    offers = {"A": 13.0, "B": 7.5, "C": 0.0}
    for deficits in ({"R1": 4.0, "R2": 9.0}, {"R1": 40.0, "R2": 9.0}):
        full = [(d, r, 1.0) for d in offers for r in deficits]
        expected = min(sum(offers.values()), sum(deficits.values()))
        assert delivered(offers, deficits, full) == pytest.approx(expected)


def test_zero_supply_zero_demand_and_undeliverable_edges() -> None:
    assert solve({}, {"R": 5.0}, []).delivered == 0.0
    assert solve({"A": 0.0}, {"R": 5.0}, [("A", "R", 1.0)]).edges == ()
    assert solve({"A": 5.0}, {"R": 0.0}, [("A", "R", 1.0)]).edges == ()
    underflow = math.exp(-1e6)  # path cost far beyond the decay length: exactly 0.0
    assert solve({"A": 5.0}, {"R": 5.0}, [("A", "R", underflow)]).delivered == 0.0
    assert edges_from({"R": [(1e6, "A")]}, 1.0)[0][2] == 0.0


def test_solutions_are_feasible_and_certified() -> None:
    offers = {f"D{i}": 10.0 + 7 * i for i in range(6)}
    deficits = {f"R{j}": 5.0 + 11 * j for j in range(5)}
    edges = [(d, r, 0.3 + 0.1 * ((i + j) % 7)) for i, d in enumerate(offers)
             for j, r in enumerate(deficits) if (i * j) % 3 != 1]  # fmt: skip
    best = solve(offers, deficits, edges)
    assert all(x >= 0 for x in best.shipped) and best.gap <= pf.GAP_TOL
    check(offers, deficits, best, edges)
    greedy_like = match(
        [(-1.0, r, x, 100.0) for r, x in deficits.items()], offers,
        {r: [(-math.log(f), d) for d, rr, f in edges if rr == r] for r in deficits}, 1.0,
    )  # fmt: skip
    assert greedy_like.totals()[1] <= best.delivered + 1e-9


def test_check_rejects_infeasible_allocations() -> None:
    offers, deficits, edges = {"A": 10.0}, {"R": 10.0}, [("A", "R", 0.5)]
    for bad in (
        Allocation((("A", "R", 0.5),), (11.0,)),  # over budget
        Allocation((("A", "R", 1.0),), (5.0,)),  # wrong transport fraction
        Allocation((("B", "R", 0.5),), (1.0,)),  # ineligible donor
        Allocation((("A", "R", 0.5),), (-1.0,)),  # negative shipment
    ):
        with pytest.raises(FeasibilityError):
            check(offers, deficits, bad, edges)
    with pytest.raises(FeasibilityError):
        check({"A": 100.0}, deficits, Allocation((("A", "R", 0.5),), (30.0,)), edges)  # > deficit


def test_failed_solver_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import scipy.optimize

    class Failed:
        status, message = 4, "numerical difficulties"

    monkeypatch.setattr(scipy.optimize, "linprog", lambda *a, **k: Failed())
    with pytest.raises(FeasibilityError, match="status 4"):
        solve({"A": 1.0}, {"R": 1.0}, [("A", "R", 1.0)])


def test_priority_only_breaks_ties_among_optima() -> None:
    """R1 and R2 both reach A only: any split of A's 50 kcal is optimal."""
    offers, deficits = {"A": 50.0}, {"R1": 50.0, "R2": 50.0}
    edges = [("A", "R1", 1.0), ("A", "R2", 1.0)]
    first = solve(offers, deficits, edges, priority={"R1": 1.0, "R2": 0.0})
    second = solve(offers, deficits, edges, priority={"R1": 0.0, "R2": 1.0})
    assert first.received() == pytest.approx({"R1": 50.0, "R2": 0.0}, abs=1e-6)
    assert second.received() == pytest.approx({"R1": 0.0, "R2": 50.0}, abs=1e-6)
    assert first.delivered == pytest.approx(second.delivered)


# --- the greedy matcher's sensitivity to order and ids (production semantics unchanged)

TIED = {"R1": [(0.0, "A"), (0.0, "B")], "R2": [(0.0, "B")]}  # R1's donors at equal cost


def test_recipient_ids_decide_who_is_served_at_equal_severity() -> None:
    def served(first: str, second: str) -> dict[str, float]:
        deficits = [(-0.5, first, 50.0, 100.0), (-0.5, second, 50.0, 100.0)]
        return match(
            deficits, {"A": 50.0}, {first: [(0.0, "A")], second: [(0.0, "A")]}, 1e9
        ).received()

    assert served("u1", "u2") == {"u1": 50.0}  # same physical state, the lower id is served
    assert served("u2", "u1") == {"u1": 50.0}  # ...whichever label it carries


def test_donor_ids_at_equal_cost_change_total_delivery() -> None:
    deficits = [(-0.6, "R1", 50.0, 80.0), (-0.5, "R2", 50.0, 100.0)]
    offers = {"A": 50.0, "B": 50.0}
    assert match(deficits, offers, TIED, 1e9).totals()[1] == pytest.approx(100.0)  # R1 takes A
    renamed = {"R1": [(0.0, "Z"), (0.0, "B")], "R2": [(0.0, "B")]}  # A renamed Z: R1 takes B
    assert match(deficits, {"Z": 50.0, "B": 50.0}, renamed, 1e9).totals()[1] == pytest.approx(50.0)


def test_processing_and_donor_order_change_delivery() -> None:
    offers = {"A": 50.0, "B": 50.0}
    reach = {"R1": [(0.0, "A"), (1.0, "B")], "R2": [(0.0, "A")]}
    severe_first = [(-0.6, "R1", 50.0, 80.0), (-0.5, "R2", 50.0, 100.0)]
    reversed_order = [(0.0, "R2", 50.0, 100.0), (1.0, "R1", 50.0, 80.0)]
    assert match(severe_first, offers, reach, 1e9).totals()[1] == pytest.approx(50.0)
    assert match(reversed_order, offers, reach, 1e9).totals()[1] == pytest.approx(100.0)
    farthest = {"R1": {"A": 0.0, "B": 1.0}}  # weight 1 routes by -tie: farthest first here
    assert match(severe_first, offers, reach, 1e9, ties=farthest, weight=1.0).totals()[
        1
    ] == pytest.approx(100.0)


def test_module_is_not_active() -> None:
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "provisioning_feasibility", "src/madexplorer"],
        capture_output=True, text=True, check=False, cwd=ROOT,
    ).stdout.split()  # fmt: skip
    assert hits == []  # no module of the package imports it
    assert not any("provisioning_feasibility" in r.qualname for r in RULES.values())
    probe = (
        "import sys; from madexplorer.config.loader import Scenario; "
        "from madexplorer.core.simulation import Simulator; "
        "Simulator(Scenario.from_yaml('scenarios/mvp2_2_pressure.yaml')).step(); "
        "print('madexplorer.economy.provisioning_feasibility' in sys.modules)"
    )
    loaded = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                            check=True, cwd=ROOT).stdout.strip()  # fmt: skip
    assert loaded == "False"  # the simulator never loads the module
    # SciPy is a development dependency: no model module uses it. (numba imports it at
    # import time, only to check its version, whenever it is installed.)
    grep = ["grep", "-rl", "--include=*.py", "scipy", "src/madexplorer"]
    uses = subprocess.run(
        grep, capture_output=True, text=True, check=False, cwd=ROOT
    ).stdout.split()
    assert uses == ["src/madexplorer/economy/provisioning_feasibility.py"]


# --- the P3 probe on a recorded MVP 2.2 run


@pytest.fixture(scope="module")
def analysed() -> tuple[dict[str, Any], dict[str, Any], bytes]:
    import importlib.util
    import pickle

    path = ROOT / "scripts/probes/provisioning_feasibility.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("feasibility_probe", path)
    assert spec and spec.loader
    probe: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    cultivation = {"mechanisms.cultivation": True}
    probe.DONOR.MVP2_2 = {"pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 80, cultivation)}
    run = probe.DONOR.record_job(("pressure+cult", 1))
    before = pickle.dumps(run)
    out = probe.analyse_run(run)
    assert pickle.dumps(run) == before  # the recording is not modified
    return run, out, pickle.dumps(probe.analyse_run(run))


def test_probe_replays_production_and_orders_the_benchmarks(
    analysed: tuple[dict[str, Any], dict[str, Any], bytes],
) -> None:
    import pickle

    run, out, again = analysed
    assert pickle.dumps(out) == again  # reanalysis is deterministic
    years = out["years"]
    assert len(years) == len(run["trade"]) and all(y["exact"] for y in years)
    tol = 1e-6
    for y in years:
        s = tol * max(y["deficit"], 1.0)
        assert y["A"] <= y["B"] + s and y["B"] <= y["C"] + s and y["C"] <= y["H"] + s
        assert y["B"] <= y["D"] + s and y["D"] <= y["G"] + s and y["G"] <= y["E"] + s
        assert y["C"] <= y["G"] + s and y["H"] <= y["E"] + s and y["A_full"] <= y["D"] + s
        assert y["E"] <= y["deficit"] + s and y["H"] <= y["offered"] + s
        assert y["shipped"] <= y["offered"] + s and y["unused_B"] >= -s
        for r in y["recipients"]:
            for k in ("A", "B", "Bsev", "Banti"):
                assert -s <= r[k] <= r["deficit"] * (1 + 1e-9) + s
    assert sum(y["B"] - y["A"] for y in years) >= 0 and sum(y["deficit"] for y in years) > 0
