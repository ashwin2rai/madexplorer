"""Integration tests for MVP 2 mechanisms on a small world."""

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.population.groups import merge_into
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, mvp2_scenario_dict, replay_key


def _unit(uid: str, n: int, groups: int = 1) -> PopulationUnit:
    females = np.zeros(91, dtype=np.int64)
    females[20] = n
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=0,
        females=females,
        males=np.zeros(91, dtype=np.int64),
        reserve_kcal_per_capita=100.0,
        founded_year=0,
        groups=groups,
        knowledge=np.array([1.0, 2.0]),
        stores_kcal=50.0,
        fields_ha=3.0,
    )


def test_merge_conserves_people_food_and_fields() -> None:
    a, b = _unit("u1", 30), _unit("u2", 10)
    b.knowledge = np.array([3.0, 2.0])
    merge_into(a, b, combine_groups=True)
    assert a.population == 40 and a.groups == 2
    assert a.stores_kcal == 100.0 and a.fields_ha == 6.0
    assert a.total_reserve_kcal == 40 * 100.0
    assert a.knowledge[0] == (30 * 1.0 + 10 * 3.0) / 40  # population-weighted


def test_population_cache_tracks_cohort_replacement() -> None:
    unit = _unit("u1", 30)
    assert unit.population == 30
    unit.females = unit.females * 2
    assert unit.population == 60


def test_mvp2_run_is_deterministic_and_conserves_population() -> None:
    scenario = Scenario.from_dict(mvp2_scenario_dict(n_years=80), base_dir=ROOT)
    first = replay_key(Simulator(scenario).run().metrics)
    second = replay_key(Simulator(scenario).run().metrics)
    assert first == second  # invariants (population accounting) are checked every step


def test_mvp2_metrics_include_knowledge_and_technology() -> None:
    result = Simulator(Scenario.from_dict(mvp2_scenario_dict(n_years=30), base_dir=ROOT)).run()
    row = result.metrics[-1]
    assert "knowledge_agriculture" in row and "tech_share_plant_cultivation" in row
    assert row["knowledge_ecology"] > 0


def test_starting_technology_enables_cultivation() -> None:
    data = mvp2_scenario_dict(n_years=40)
    data["initial_populations"] = [
        {
            "species": "human",
            "cell": [8, 8],
            "population": 60,
            "technologies": ["plant_cultivation", "seed_selection"],
            "initial_knowledge": {"agriculture": 6.0},
        }
    ]
    data["mechanisms"] = {"migration": False}
    result = Simulator(Scenario.from_dict(data, base_dir=ROOT)).run()
    assert max(r["farm_share_of_harvest"] for r in result.metrics) > 0
    assert any(e.kind == "cultivation_started" for e in result.events)


def test_no_cultivation_without_technology_even_when_enabled() -> None:
    data = mvp2_scenario_dict(n_years=40)
    data["mechanisms"] = {"innovation": False, "knowledge_diffusion": False}
    result = Simulator(Scenario.from_dict(data, base_dir=ROOT)).run()
    assert all(r["cultivated_ha"] == 0 for r in result.metrics)


def test_aggregation_bounds_units_per_cell() -> None:
    data = mvp2_scenario_dict(n_years=150)
    data["resolution"] = {"max_units_per_cell": 1, "max_knowledge_distance": 100.0}
    data["mechanisms"] = {"migration": False}
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    sim.run()
    cells = [u.cell for u in sim.state.units.values()]
    assert len(cells) == len(set(cells))
