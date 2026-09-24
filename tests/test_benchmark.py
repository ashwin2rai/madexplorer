"""The performance benchmark harness builds controlled states and reports timings."""

from madexplorer.config.loader import Scenario
from madexplorer.experiments.benchmark import synthetic_case, synthetic_simulator
from tests.conftest import ROOT, small_scenario_dict


def _scenario() -> Scenario:
    return Scenario.from_dict(small_scenario_dict(), base_dir=ROOT)


def test_synthetic_simulator_places_the_requested_units_on_land() -> None:
    sim = synthetic_simulator(_scenario(), n_units=40)
    assert len(sim.state.units) == 40
    assert all(not sim.world.is_water[u.cell] for u in sim.state.units.values())


def test_synthetic_placement_is_deterministic() -> None:
    a = synthetic_simulator(_scenario(), n_units=25)
    b = synthetic_simulator(_scenario(), n_units=25)
    assert [u.cell for u in a.state.units.values()] == [u.cell for u in b.state.units.values()]


def test_synthetic_case_reports_per_subsystem_timings() -> None:
    case = synthetic_case(_scenario(), n_units=20, ticks=2, warmup_years=2)
    assert case["ticks"] == 2
    assert case["known_cells_after_warmup"] > 0
    assert "perception" in case["subsystem_ms_per_tick"]
    assert "invariants" in case["subsystem_ms_per_tick"]
    assert case["ms_per_tick"] > 0
