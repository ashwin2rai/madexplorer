import numpy as np
import pytest
from pydantic import ValidationError

from madexplorer.config.loader import Scenario
from madexplorer.knowledge.diffusion import diffusion_gain
from madexplorer.knowledge.innovation import innovation_hazard
from madexplorer.knowledge.learning import learn
from madexplorer.knowledge.system import KnowledgeModel, KnowledgeSystem
from tests.conftest import ROOT, mvp2_scenario_dict


def test_knowledge_system_loads_with_scenario() -> None:
    scenario = Scenario.from_dict(mvp2_scenario_dict(), base_dir=ROOT)
    assert scenario.knowledge is not None
    assert "agriculture" in scenario.knowledge.domains


def test_unknown_technology_prerequisite_is_rejected(knowledge_model: KnowledgeModel) -> None:
    raw = knowledge_model.system.model_dump()
    raw["technologies"][0]["requires"] = ["time_machine"]
    with pytest.raises(ValidationError, match="unknown technologies"):
        KnowledgeSystem.model_validate(raw)


def test_capabilities_add_technology_effects(knowledge_model: KnowledgeModel) -> None:
    base = knowledge_model.capabilities(frozenset())
    farming = knowledge_model.capabilities(frozenset({"plant_cultivation", "seed_selection"}))
    assert base["crop_yield"] == 0.0
    assert farming["crop_yield"] == pytest.approx(0.9)


def test_learning_rises_with_practice_and_group_size(knowledge_model: KnowledgeModel) -> None:
    k0 = np.zeros(len(knowledge_model.domains))
    practice = np.full_like(k0, 0.5)
    small = learn(k0, practice, 20, knowledge_model, 1.0, 1.0)
    large = learn(k0, practice, 200, knowledge_model, 1.0, 1.0)
    idle = learn(k0, np.zeros_like(k0), 200, knowledge_model, 1.0, 1.0)
    assert (large > small).all() and (idle == 0).all()


def test_knowledge_decays_without_practice(knowledge_model: KnowledgeModel) -> None:
    k = np.full(len(knowledge_model.domains), 5.0)
    for _ in range(50):
        k = learn(k, np.zeros_like(k), 50, knowledge_model, 1.0, 1.0)
    assert (k < 5.0).all() and (k >= 0).all()


def test_equilibrium_knowledge_is_higher_in_larger_populations(
    knowledge_model: KnowledgeModel,
) -> None:
    def equilibrium(n: int) -> np.ndarray:
        k = np.zeros(len(knowledge_model.domains))
        for _ in range(2000):
            k = learn(k, np.full_like(k, 0.3), n, knowledge_model, 1.0, 1.0)
        return k

    assert (equilibrium(500) > equilibrium(20)).all()


def test_diffusion_flows_down_gradients_only() -> None:
    mine = np.array([1.0, 3.0])
    gain = diffusion_gain(mine, [(1.0, np.array([2.0, 1.0]))], np.array([0.5, 0.5]), 1.0)
    assert gain[0] == pytest.approx(0.5) and gain[1] == 0.0
    huge = diffusion_gain(mine, [(100.0, np.array([2.0, 1.0]))], np.array([0.5, 0.5]), 1.0)
    assert huge[0] == pytest.approx(1.0)  # never overshoots the best contact


def test_innovation_needs_both_pressure_and_capacity(knowledge_model: KnowledgeModel) -> None:
    spec = knowledge_model.system.innovation
    tech = knowledge_model.technologies["plant_cultivation"]

    def hazard(need: float, ratio: float, instability: float = 0.0) -> float:
        return innovation_hazard(tech, need, ratio, 50, 2.0, 0.2, instability, spec, 0.0)[0]

    assert hazard(1.0, 1.0) > hazard(0.0, 1.0)  # need raises the hazard
    assert hazard(1.0, 2.0) > hazard(1.0, 1.0)  # capacity raises the hazard
    assert hazard(1.0, 1.0, instability=1.0) < hazard(1.0, 1.0)  # instability suppresses it
    assert 0 < hazard(0.0, 0.5) < 1e-3


def test_dependent_technologies_are_kept_while_supported(knowledge_model: KnowledgeModel) -> None:
    held = frozenset({"plant_cultivation", "seed_selection"})
    knowledge = knowledge_model.initial_levels({"agriculture": 5.0, "ecology": 5.0})
    assert knowledge_model.unsupported(held, knowledge, 0.25) == ()
    forgotten = knowledge_model.initial_levels({"agriculture": 0.1, "ecology": 5.0})
    assert knowledge_model.unsupported(held, forgotten, 0.25) == (
        "plant_cultivation",
        "seed_selection",
    )
