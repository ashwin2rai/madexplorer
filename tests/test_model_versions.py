"""MVP 2.1 vs MVP 2.2 (Stage 5J): the fertility-input version boundary.

MVP 2.1 (``mechanisms.dietary_intake_fertility`` off, the default): nutritional fertility
reads harvest adequacy (``food_ratio``). MVP 2.2 candidate (``scenarios/mvp2_2_*.yaml``):
it reads dietary intake. Nothing else differs between the versions.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import MechanismsConfig
from madexplorer.core.simulation import Simulator
from madexplorer.population.demography import fertility_input, fertility_multiplier
from madexplorer.population.dietary_intake import dietary_intake_ratio, harvest_adequacy
from madexplorer.population.energetics import EnergeticsSubsystem
from tests.conftest import ROOT

PAIRS = (("mvp2_neolithic", "mvp2_2_neolithic"), ("mvp2_pressure", "mvp2_2_pressure"))


def _load(name: str, **overrides: Any) -> Scenario:
    return Scenario.from_yaml(ROOT / "scenarios" / f"{name}.yaml").with_overrides(**overrides)


def test_legacy_default_is_mvp2_1() -> None:
    assert MechanismsConfig().dietary_intake_fertility is False
    for old, new in PAIRS:
        assert _load(old).config.mechanisms.dietary_intake_fertility is False
        assert _load(new).config.mechanisms.dietary_intake_fertility is True


@pytest.mark.parametrize(("old", "new"), PAIRS)
def test_versioned_scenarios_differ_only_in_name_and_switch(old: str, new: str) -> None:
    a, b = _load(old).to_dict(), _load(new).to_dict()
    assert a["scenario"]["name"] == old and b["scenario"]["name"] == new
    for d in (a, b):
        d["scenario"]["name"] = "x"
        d["scenario"]["mechanisms"]["dietary_intake_fertility"] = None
    assert a == b


class _Cols:
    """Minimal column view for :func:`fertility_input`."""

    def __init__(self, ids: list[str], food: list[float], population: list[int]) -> None:
        self.units = [type("U", (), {"id": i})() for i in ids]
        self._food, self._pop = np.array(food), np.array(population)

    def get(self, name: str) -> np.ndarray:
        assert name == "food_ratio"
        return self._food.copy()

    def population(self) -> np.ndarray:
        return self._pop


class _Ctx:
    def __init__(self, on: bool, intake: dict[str, float] | None) -> None:
        self.mechanisms = MechanismsConfig(dietary_intake_fertility=on)
        self.dietary_intake = intake


def test_fertility_input_selects_one_quantity_per_version() -> None:
    cols = _Cols(["a", "b", "c"], [0.6, 1.2, 0.9], [10, 5, 0])
    intake = {"a": 1.0, "b": 1.0}  # c has no members: energetics skipped it
    off = fertility_input(cols, _Ctx(False, intake))  # type: ignore[arg-type]
    assert off.tolist() == [0.6, 1.2, 0.9]  # MVP 2.1 ignores any intake values
    on = fertility_input(cols, _Ctx(True, intake))  # type: ignore[arg-type]
    assert on.tolist() == [1.0, 1.0, 0.9]
    with pytest.raises(RuntimeError):  # MVP 2.2 never silently falls back to food_ratio
        fertility_input(cols, _Ctx(True, None))  # type: ignore[arg-type]
    empty = _Cols(["c"], [0.9], [0])
    assert fertility_input(empty, _Ctx(True, None)).tolist() == [0.9]  # type: ignore[arg-type]


def test_h1_never_lowers_the_multiplier_and_agrees_without_stores() -> None:
    rng = np.random.default_rng(4)
    need = rng.uniform(1, 200, 2000)
    harvest, stores = rng.uniform(0, 250, 2000), rng.uniform(0, 100, 2000)
    stores[:500] = 0.0
    m0 = fertility_multiplier(harvest_adequacy(need, harvest), 0.8, 0.1)
    m1 = fertility_multiplier(dietary_intake_ratio(need, harvest, stores), 0.8, 0.1)
    assert (m1 >= m0).all() and ((m1 >= 0) & (m1 <= 1)).all()
    assert np.array_equal(m0[:500], m1[:500])  # no stores eaten: identical multiplier


def _first_step(name: str) -> tuple[Simulator, Any]:
    sim = Simulator(_load(name, seed=3, n_years=5))
    ctx = sim.step()
    return sim, ctx


@pytest.mark.parametrize(("old", "new"), PAIRS)
def test_only_the_fertility_input_differs_in_the_first_year(old: str, new: str) -> None:
    """Energetics outputs (food_ratio, deficit, reserves, stores) and every other reader's
    input are identical; MVP 2.2 adds only the transient intake, which equals the rule."""
    s21, c21 = _first_step(old)
    s22, c22 = _first_step(new)
    assert c21.dietary_intake is None and c22.dietary_intake is not None
    fields = ("food_ratio", "energy_deficit", "reserve_kcal_per_capita", "stores_kcal")
    for u21, u22 in zip(s21.state.units.values(), s22.state.units.values(), strict=True):
        assert [getattr(u21, f) for f in fields] == [getattr(u22, f) for f in fields]
        assert 0.0 <= c22.dietary_intake[u22.id] <= 1.0


def test_energetics_passes_the_rule_value_computed_from_its_own_inputs() -> None:
    sim = Simulator(_load("mvp2_2_pressure", seed=1, n_years=3))
    for _ in range(2):
        sim.step()
    ctx = sim.context()
    subsystem = next(s for s in sim.pipeline if isinstance(s, EnergeticsSubsystem))
    (update,) = subsystem.evaluate(sim.state, ctx)
    cols = update.cols
    expected = dietary_intake_ratio(
        update.need_kcal, cols.get("harvest_kcal"), cols.get("stores_kcal")
    )
    assert update.dietary_intake is not None and np.array_equal(update.dietary_intake, expected)


def _experiment() -> Any:
    path = ROOT / "scripts/probes/fertility_intake_experiment.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("fertility_intake_experiment_v", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trajectory(sim: Simulator, exp: Any, years: int) -> list[dict[str, str]]:
    out = []
    for _ in range(years):
        sim.step()
        out.append(exp._hashes(sim))
    return out


def test_production_versions_match_the_independent_experimental_branch() -> None:
    """MVP 2.1 = experimental H0 and MVP 2.2 = experimental H1, year by year (40 years of
    pressure with cultivation, where the fertility inputs differ from year 2)."""
    exp = _experiment()
    settings = {"mechanisms.cultivation": True}
    for version, mode in (("mvp2_pressure", "h0"), ("mvp2_2_pressure", "h1")):
        prod = Simulator(_load(version, seed=2, n_years=40).with_settings(settings))
        branch_sim, _ = exp.branched_simulator(
            _load("mvp2_pressure", seed=2, n_years=40).with_settings(settings), mode
        )
        assert _trajectory(prod, exp, 40) == _trajectory(branch_sim, exp, 40)


def test_versions_diverge_only_through_births() -> None:
    exp = _experiment()
    settings = {"mechanisms.cultivation": True}
    a = Simulator(_load("mvp2_pressure", seed=0, n_years=10).with_settings(settings))
    b = Simulator(_load("mvp2_2_pressure", seed=0, n_years=10).with_settings(settings))
    year, parts = exp.first_divergence(_trajectory(a, exp, 10), _trajectory(b, exp, 10))
    assert year is not None  # pressure seed 0 diverges in year 3 (Stage 5I)
    assert "cohorts" in parts and "food" not in parts
    assert not [p for p in parts if p.startswith("rng:") and p != "rng:demography"]


def test_oracle_tool_defaults_to_mvp2_1() -> None:
    text = Path(ROOT / "scripts/perf/exactness_oracle.py").read_text()
    assert 'MODEL = "mvp2"' in text and '"mvp2_2": "mvp2_2"' in text
