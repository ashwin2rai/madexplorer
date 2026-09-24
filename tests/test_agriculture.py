import copy

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.config.schema import AgricultureConfig
from madexplorer.core.simulation import Simulator
from madexplorer.ecology.subsystems import EcologySubsystem
from madexplorer.economy.agriculture import (
    adjusted_fields_ha,
    clearing_hours_per_ha,
    update_soil_nutrients,
)
from madexplorer.economy.trade import delivered_fraction
from madexplorer.metrics.recorder import MetricsRecorder
from tests.conftest import ROOT, mvp2_scenario_dict, step_context


def test_fields_expand_when_farming_beats_foraging() -> None:
    fields, gap = adjusted_fields_ha(10.0, 1e6, 600.0, 0.0, 10, 500.0, 0.3, 2.0, 0.1)
    assert gap > 0 and fields > 10.0


def test_fields_shrink_when_foraging_is_better() -> None:
    fields, gap = adjusted_fields_ha(10.0, 1e5, 600.0, 0.0, 10, 2000.0, 0.3, 2.0, 0.1)
    assert gap < 0 and fields < 10.0


def test_clearing_cost_deters_mobile_groups_but_not_settled_ones() -> None:
    args = dict(
        yield_per_ha=6e5,
        cultivation_hours_per_ha=600.0,
        clearing_hours=1500.0,
        forage_marginal=600.0,
        adjustment_rate=0.3,
        initial_plot_ha=2.0,
        margin=0.1,
    )
    mobile, _ = adjusted_fields_ha(0.0, expected_tenure_years=1, **args)
    settled, _ = adjusted_fields_ha(0.0, expected_tenure_years=10, **args)
    assert mobile == 0.0 and settled > 0.0


def test_forest_clearing_costs_more_and_tools_help() -> None:
    config = AgricultureConfig()
    assert clearing_hours_per_ha(0.7, config, 1.0) > clearing_hours_per_ha(0.1, config, 1.0)
    assert clearing_hours_per_ha(0.7, config, 2.0) < clearing_hours_per_ha(0.7, config, 1.0)


def _soil_after(years: int, cultivated: bool, management: float, start: float = 1.0) -> float:
    config = AgricultureConfig()
    soil = np.array([start])
    for _ in range(years):
        soil = update_soil_nutrients(soil, np.array([cultivated]), np.array([management]), config)
    return float(soil[0])


def test_sustained_cultivation_depletes_toward_low_equilibrium() -> None:
    config = AgricultureConfig()
    levels = [_soil_after(t, cultivated=True, management=0.0) for t in (0, 5, 20, 200)]
    assert levels == sorted(levels, reverse=True) and levels[1] < 1.0
    r, d = config.soil_cultivated_recovery_rate, config.soil_depletion_rate
    assert levels[-1] == pytest.approx(r / (r + d), abs=1e-6)


def test_fallow_land_recovers() -> None:
    assert _soil_after(10, cultivated=False, management=0.0, start=0.3) > 0.3
    assert _soil_after(500, cultivated=False, management=0.0, start=0.3) == pytest.approx(1.0)


def test_soil_management_slows_depletion_and_raises_equilibrium() -> None:
    for years in (5, 200):
        plain = _soil_after(years, cultivated=True, management=0.0)
        managed = _soil_after(years, cultivated=True, management=0.5)
        assert managed > plain


def test_field_fertility_does_not_depend_on_how_much_of_the_cell_is_farmed() -> None:
    small = _farmed_soil_after_one_year(fields_ha=1.0)
    large = _farmed_soil_after_one_year(fields_ha=500.0)
    assert small == pytest.approx(large) and small < 1.0


def _farming_simulator() -> Simulator:
    data = mvp2_scenario_dict(n_years=5)
    data["initial_populations"] = [
        {
            "species": "human",
            "cell": [8, 8],
            "population": 60,
            "technologies": ["plant_cultivation"],
            "initial_knowledge": {"agriculture": 6.0},
        }
    ]
    return Simulator(Scenario.from_dict(data, base_dir=ROOT))


def _farmed_soil_after_one_year(fields_ha: float) -> float:
    sim = _farming_simulator()
    (unit,) = sim.state.units.values()
    unit.fields_ha = fields_ha
    ctx = step_context(sim)
    for proposal in EcologySubsystem().evaluate(sim.state, ctx):
        proposal.apply(sim.state, ctx)
    return float(sim.state.ecology.soil_nutrients[unit.cell])


def test_farming_metrics_do_not_change_when_identical_groups_are_split() -> None:
    sim = _farming_simulator()
    for _ in range(5):
        sim.step()
    farmers = [u for u in sim.state.units.values() if u.fields_ha > 0]
    assert farmers
    unit = farmers[0]
    # One unit of doubled size versus two identical copies of the original.
    double = copy.deepcopy(unit)
    double.females, double.males = unit.females * 2, unit.males * 2
    for name in ("fields_ha", "farm_hours", "stores_kcal"):
        setattr(double, name, getattr(unit, name) * 2)
    twin = copy.deepcopy(unit)
    twin.id = "twin"
    rows = []
    for units in ({unit.id: double}, {unit.id: unit, twin.id: twin}):
        state = copy.copy(sim.state)
        state.units = units
        recorder = MetricsRecorder(sim.scenario, 1000)
        rows.append(recorder.record(state, step_context(sim)))
    keys = [k for k in rows[0] if k.startswith(("farmed_", "arable_", "cultivated_", "farm_"))]
    keys += ["mean_soil_nutrients_farmed", "crop_kcal_per_farm_hour"]
    for key in keys:
        assert rows[0][key] == pytest.approx(rows[1][key], nan_ok=True), key


def test_transport_loss_grows_with_distance() -> None:
    assert delivered_fraction(0.0, 60.0) == 1.0
    assert delivered_fraction(120.0, 60.0) == pytest.approx(np.exp(-2))
