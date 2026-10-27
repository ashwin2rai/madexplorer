"""MVP 3 Stage 6B: foraging-patch opportunity diagnostics. READ-ONLY / NOT ACTIVE.

``madexplorer.economy.opportunity_audit`` replays production pooled foraging and compares it
with an independent-satisficing reference and with a unit alone in its cell, on the same
stock, labor, efficiency, targets and harvest function. No simulator path calls it.
"""

import importlib.util
import subprocess
import sys
from typing import Any

import pytest

from madexplorer.core.governance import RULES
from madexplorer.economy.foraging import _harvest
from madexplorer.economy.opportunity_audit import (
    alone_harvest,
    gini,
    independent_harvest,
    pooled_harvest,
    regrowth_loss,
)
from tests.conftest import ROOT

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
    probe.MVP2_2 = {"pressure+cult": ("scenarios/mvp2_2_pressure.yaml", 50, cultivation)}
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
