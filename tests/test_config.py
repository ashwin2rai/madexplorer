import pytest
from pydantic import ValidationError

from madexplorer.config.loader import Scenario
from tests.conftest import ROOT, small_scenario_dict


def test_example_scenario_loads() -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp1_sandbox.yaml")
    assert "human" in scenario.species
    assert len(scenario.config_hash()) == 64


def test_unknown_keys_are_rejected() -> None:
    data = small_scenario_dict()
    data["simulation"] = {"n_years": 10, "sede": 3}
    with pytest.raises(ValidationError):
        Scenario.from_dict(data, base_dir=ROOT)


def test_population_outside_grid_is_rejected() -> None:
    data = small_scenario_dict()
    data["initial_populations"] = [{"species": "human", "cell": [99, 0], "population": 5}]
    with pytest.raises(ValidationError, match="outside the grid"):
        Scenario.from_dict(data, base_dir=ROOT)


def test_species_overrides_are_applied() -> None:
    data = small_scenario_dict()
    data["species"] = [
        {
            "id": "human",
            "profile": "species/human.yaml",
            "overrides": {"life_history": {"total_fertility_rate": 3.0}},
        }
    ]
    scenario = Scenario.from_dict(data, base_dir=ROOT)
    assert scenario.species["human"].life_history.total_fertility_rate == 3.0


def test_config_hash_tracks_changes(small_scenario: Scenario) -> None:
    assert small_scenario.config_hash() != small_scenario.with_overrides(seed=99).config_hash()
