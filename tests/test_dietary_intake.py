"""MVP 3 Stage 5I/5J: fertility input, harvest adequacy (H0) vs dietary intake (H1).

``madexplorer.population.dietary_intake`` is used only by MVP 2.2 energetics
(``mechanisms.dietary_intake_fertility``, Stage 5J); the Stage 5I branch in
``scripts/probes/fertility_intake_experiment.py`` stays EXPERIMENTAL / OPT-IN and is the
independent reference the production MVP 2.2 path is checked against.
"""

import importlib.util
import subprocess
import sys
from typing import Any

import numpy as np
import pytest

from madexplorer.core.governance import RULES
from madexplorer.core.simulation import Simulator
from madexplorer.population.demography import DemographySubsystem, fertility_multiplier
from madexplorer.population.dietary_intake import (
    dietary_intake_ratio,
    harvest_adequacy,
    net_sufficiency,
    reserve_drawdown,
    store_withdrawal,
)
from madexplorer.population.energetics import EnergeticsSubsystem, energy_balance_batch
from tests.conftest import ROOT

MID, SCALE = 0.8, 0.1


def arr(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


def fert(x: np.ndarray) -> np.ndarray:
    return fertility_multiplier(x, MID, SCALE)


def test_h0_is_the_authoritative_food_ratio_bit_for_bit() -> None:
    rng = np.random.default_rng(0)
    need = rng.uniform(0, 200, 500)
    need[:5] = 0.0
    harvest, stores = rng.uniform(0, 250, 500), rng.uniform(0, 100, 500)
    reserve, cap = rng.uniform(0, 30, 500), np.full(500, 30.0)
    food_ratio, deficit, _r, stores_out, _s, _sp = energy_balance_batch(
        need, harvest, reserve, cap, stores, np.ones(500, dtype=bool)
    )
    assert np.array_equal(harvest_adequacy(need, harvest), food_ratio)
    short = harvest < need
    # the store withdrawal is the production one; never more than the stores or the gap
    x = store_withdrawal(need, harvest, stores)
    assert np.allclose(x[short], (stores - stores_out)[short], rtol=1e-12, atol=1e-9)
    assert (x <= stores).all()
    assert (harvest + x <= np.maximum(need, harvest) * (1 + 1e-15)).all()  # one rounding step
    assert (dietary_intake_ratio(need, harvest, stores) <= 1.0).all()
    # deficit = gap after stores and reserves
    gap = need - harvest - x - reserve_drawdown(need, harvest, stores, reserve)
    assert np.allclose(
        np.where(short & (need > 0), gap / np.where(need > 0, need, 1), 0.0), deficit
    )


def test_h1_harvest_only_equals_h0_and_fed_units_share_the_multiplier() -> None:
    need, harvest = arr(100, 100, 100), arr(70, 100, 130)
    h0, h1 = harvest_adequacy(need, harvest), dietary_intake_ratio(need, harvest, arr(0, 0, 0))
    assert h1[0] == h0[0]  # short harvest, no stores eaten: identical ratio
    assert h1[1] == h1[2] == 1.0  # consumption capped at the requirement
    assert np.array_equal(fert(h0[1:]), fert(h1[1:]))


def test_stores_count_once_and_reserves_never() -> None:
    need = arr(100, 100, 100)
    # stores cover; reserves cover; partial reserve compensation
    harvest, stores, reserve = arr(70, 80, 60), arr(50, 5, 10), arr(0, 20, 15)
    h1 = dietary_intake_ratio(need, harvest, stores)
    assert h1.tolist() == [1.0, 0.85, 0.7]
    assert reserve_drawdown(need, harvest, stores, reserve).tolist() == [0.0, 15.0, 15.0]
    _fr, deficit, *_ = energy_balance_batch(
        need, harvest, reserve, arr(30, 30, 30), stores, np.ones(3, bool)
    )
    h2 = net_sufficiency(deficit)
    assert h2.tolist() == [1.0, 1.0, 0.85] and (h2 >= h1).all()  # H2 adds reserve energy


def test_equal_intake_from_different_sources_gives_equal_fertility() -> None:
    need = arr(100, 100, 100)
    harvest, stores = arr(100, 60, 10), arr(0, 40, 500)
    h1 = dietary_intake_ratio(need, harvest, stores)
    assert h1.tolist() == [1.0, 1.0, 1.0]
    assert len(set(fert(h1).tolist())) == 1
    assert len(set(fert(harvest_adequacy(need, harvest)).tolist())) == 3  # H0 depends on source


def test_trade_sides() -> None:
    need = arr(100, 100, 100, 100)
    # donor shipped harvest, stores cover; donor shipped and is short; recipient rescued /
    # still short (received food is already in the post-trade harvest, counted once)
    harvest, stores = arr(90, 70, 100, 70), arr(40, 5, 0, 0)
    assert dietary_intake_ratio(need, harvest, stores).tolist() == [1.0, 0.75, 1.0, 0.7]
    # a shipment paid from stores leaves only the post-trade stores to eat
    assert dietary_intake_ratio(arr(100), arr(60), arr(20))[0] == 0.8


def test_zero_and_tiny_need_are_bounded() -> None:
    need, harvest, stores = arr(0, 1e-300, 1e-300), arr(0, 0, 5), arr(5, 5, 0)
    h1 = dietary_intake_ratio(need, harvest, stores)
    assert h1.tolist() == [1.0, 1.0, 1.0]
    m = fert(np.concatenate([h1, harvest_adequacy(need, harvest)]))
    assert ((m >= 0) & (m <= 1)).all()


def test_pure_functions_draw_no_random_numbers() -> None:
    state = np.random.get_state()[1].copy()
    dietary_intake_ratio(arr(100), arr(50), arr(10))
    store_withdrawal(arr(100), arr(50), arr(10))
    assert np.array_equal(np.random.get_state()[1], state)


def test_only_energetics_imports_the_intake_rule_and_it_is_registered() -> None:
    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "population.dietary_intake import", str(ROOT / "src")],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    assert [h.split("/src/")[-1] for h in hits] == ["madexplorer/population/energetics.py"]
    rule = RULES["dietary_intake"]
    assert rule.qualname.endswith("dietary_intake.dietary_intake_ratio")
    assert "MVP 2.2" in rule.rationale


# ---------------------------------------------------------------- experimental branch


def _experiment() -> Any:
    path = ROOT / "scripts/probes/fertility_intake_experiment.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("fertility_intake_experiment", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def short_runs() -> dict[str, Any]:
    exp = _experiment()
    original = sys.modules["_common"].scenario_for
    exp.scenario_for = lambda n, s, w: original(n, s, w, years=40)
    runs = {m: exp.run_job(("pressure+cult", 2, m)) for m in ("canonical", "h0", "h1")}
    runs["h1_again"] = exp.run_job(("pressure+cult", 2, "h1"))
    runs["exp"] = exp
    return runs


def test_default_pipeline_is_untouched() -> None:
    exp = _experiment()
    scenario = sys.modules["_common"].scenario_for("pressure+cult", 0, 0.0, years=5)
    plain = Simulator(scenario)
    assert any(type(s) is EnergeticsSubsystem for s in plain.pipeline)
    assert any(type(s) is DemographySubsystem for s in plain.pipeline)
    sim, branch = exp.branched_simulator(scenario, "h1")
    assert branch is not None and not any(type(s) is DemographySubsystem for s in sim.pipeline)
    assert any(
        type(s) is DemographySubsystem for s in Simulator(scenario).pipeline
    )  # per instance only
    with pytest.raises(ValueError):
        exp.Branch("h2")


def test_experimental_h0_reproduces_the_canonical_simulator(short_runs: dict[str, Any]) -> None:
    c, h0 = short_runs["canonical"], short_runs["h0"]
    assert c["digest"] == h0["digest"]
    assert c["hashes"] == h0["hashes"]
    assert short_runs["exp"]._rows_equal(c["rows"], h0["rows"])
    assert h0["restore_failures"] == 0


def test_h1_changes_only_the_fertility_input(short_runs: dict[str, Any]) -> None:
    exp = short_runs["exp"]
    c, h0, h1 = short_runs["canonical"], short_runs["h0"], short_runs["h1"]
    assert h1["restore_failures"] == 0  # food_ratio restored bit for bit every year
    first_dm = next((y["year"] for y in h0["years"] if any(u[2] != u[1] for u in y["units"])), None)
    year, parts = exp.first_divergence(c["hashes"], h1["hashes"])
    if year is None:
        assert first_dm is None or first_dm >= len(c["hashes"])
        return
    assert first_dm is not None and year >= first_dm  # nothing changes before fertility does
    # in the divergence year energetics, food and every stream but demography still agree
    assert "food" not in parts
    assert not [p for p in parts if p.startswith("rng:") and p != "rng:demography"]
    assert "cohorts" in parts


def test_branches_are_reproducible(short_runs: dict[str, Any]) -> None:
    assert short_runs["h1"]["digest"] == short_runs["h1_again"]["digest"]
    assert short_runs["h1"]["hashes"] == short_runs["h1_again"]["hashes"]
