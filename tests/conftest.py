"""Shared fixtures: a tiny deterministic world and the baseline human profile."""

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from madexplorer.config.loader import Scenario
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile

if TYPE_CHECKING:
    from madexplorer.core.simulation import Simulator
    from madexplorer.core.state import StepContext
    from madexplorer.knowledge.system import KnowledgeModel

ROOT = Path(__file__).resolve().parents[1]


@pytest.hookimpl(tryfirst=True)  # before `-m` deselection, which reads these markers
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify tests by directory: regression/, statistical/, everything else is mechanism."""
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "regression" in parts:
            item.add_marker(pytest.mark.regression)
        elif "statistical" in parts:
            item.add_marker(pytest.mark.statistical)
        else:
            item.add_marker(pytest.mark.mechanism)


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


def step_context(sim: "Simulator") -> "StepContext":
    """A step context for calling one subsystem directly on a simulator's current state."""
    from madexplorer.core.state import StepContext

    return StepContext(
        year=sim.state.year,
        scenario=sim.scenario,
        rng=sim.rng,
        ids=sim.ids,
        events=sim.events,
        tables=sim.tables,
        movement=sim.movement,
        trace_units=frozenset(),
        knowledge=sim.knowledge,
    )


def replay_key(metrics: list[dict[str, float | int]]) -> list[tuple[str, ...]]:
    """Metrics rows in a form where equal runs compare equal (NaN included)."""
    return [tuple(repr(v) for v in row.values()) for row in metrics]
