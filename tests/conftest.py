"""Shared fixtures: a tiny deterministic world and the baseline human profile."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from madexplorer.config.loader import Scenario
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile

if TYPE_CHECKING:
    from madexplorer.knowledge.system import KnowledgeModel

ROOT = Path(__file__).resolve().parents[1]


def small_scenario_dict(n_years: int = 40, seed: int = 1) -> dict[str, object]:
    """A 16x16 world with one founding band, small enough for fast tests."""
    return {
        "name": "test_small",
        "simulation": {"n_years": n_years, "seed": seed},
        "world": {"topology": {"seed": 3, "width": 16, "height": 16, "sea_fraction": 0.0}},
        "species": [{"id": "human", "profile": "species/human.yaml"}],
        "initial_populations": [{"species": "human", "cell": [8, 8], "population": 30}],
    }


@pytest.fixture
def small_scenario() -> Scenario:
    """Tiny scenario for integration tests."""
    return Scenario.from_dict(small_scenario_dict(), base_dir=ROOT)


@pytest.fixture
def human() -> SpeciesProfile:
    """Baseline human profile."""
    return Scenario.from_yaml(ROOT / "scenarios" / "mvp1_sandbox.yaml").species["human"]


@pytest.fixture
def human_tables(human: SpeciesProfile) -> LifeTables:
    """Life tables of the baseline human profile."""
    return LifeTables.build(human)


def mvp2_scenario_dict(n_years: int = 60, seed: int = 1) -> dict[str, object]:
    """Small MVP 2 world: knowledge system and all MVP 2 mechanisms on."""
    data = small_scenario_dict(n_years=n_years, seed=seed)
    data["knowledge_system"] = "technologies/neolithic.yaml"
    return data


@pytest.fixture
def knowledge_model() -> "KnowledgeModel":
    """Runtime model of the neolithic knowledge system."""
    from madexplorer.knowledge.system import KnowledgeModel

    scenario = Scenario.from_dict(mvp2_scenario_dict(), base_dir=ROOT)
    assert scenario.knowledge is not None
    return KnowledgeModel(scenario.knowledge)
