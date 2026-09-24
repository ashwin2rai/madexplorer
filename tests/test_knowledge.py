from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.knowledge.diffusion import diffusion_gain, diffusion_gains
from madexplorer.knowledge.innovation import choose_invention, innovation_hazard
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


def test_competing_risk_choice_is_proportional_to_rates_and_order_free() -> None:
    hazards = [0.05, 0.2, 0.1]
    counts = [0, 0, 0]
    rng = np.random.default_rng(3)
    trials = 60_000
    none = 0
    for _ in range(trials):
        chosen = choose_invention(hazards, rng)
        if chosen is None:
            none += 1
        else:
            counts[chosen] += 1
    p_any = 1.0 - np.prod([1.0 - p for p in hazards])
    assert (trials - none) / trials == pytest.approx(p_any, abs=0.01)
    rates = -np.log1p(-np.array(hazards))
    shares = np.array(counts) / sum(counts)
    assert shares == pytest.approx(rates / rates.sum(), abs=0.01)


def test_no_invention_without_hazard() -> None:
    rng = np.random.default_rng(0)
    assert all(choose_invention([0.0, 0.0], rng) is None for _ in range(100))
    assert choose_invention([], rng) is None


def test_technology_file_order_does_not_change_seeded_results(tmp_path: Path) -> None:
    system = yaml.safe_load((ROOT / "technologies" / "neolithic.yaml").read_text())
    system["innovation"]["baseline_logit"] = -3.0  # frequent inventions, many competing
    runs = []
    for name, technologies in (
        ("given", system["technologies"]),
        ("reversed", list(reversed(system["technologies"]))),
    ):
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(system | {"technologies": technologies}))
        data = mvp2_scenario_dict(n_years=120, seed=2)
        data["knowledge_system"] = str(path)
        data["initial_populations"] = [
            {
                "species": "human",
                "cell": [8, 8],
                "population": 60,
                "initial_knowledge": {"agriculture": 4.5, "storage": 1.2, "construction": 1.0},
            }
        ]
        result = Simulator(Scenario.from_dict(data, base_dir=ROOT)).run()
        runs.append(
            [
                (e.year, e.data["unit_id"], e.data["technology"])
                for e in result.events
                if e.kind == "invention"
            ]
        )
    assert len({tech for _, _, tech in runs[0]}) >= 3
    assert runs[0] == runs[1]


@settings(max_examples=100, deadline=None)
@given(seed=st.integers(0, 10_000), n_units=st.integers(1, 12))
def test_batched_diffusion_equals_per_unit_rule_exactly(seed: int, n_units: int) -> None:
    rng = np.random.default_rng(seed)
    knowledge = rng.uniform(0, 6, (n_units, 4))
    transmissibility = rng.uniform(0, 0.1, 4)
    teaching = rng.uniform(0.5, 1.5, n_units)
    receivers, sources, weights, expected = [], [], [], []
    for i in range(n_units):
        partners = [j for j in range(n_units) if j != i and rng.random() < 0.8]
        strength = [float(rng.uniform(0, 2)) for _ in partners]
        receivers += [i] * len(partners)
        sources += partners
        weights += strength
        levels = [(w, knowledge[j]) for j, w in zip(partners, strength, strict=True)]
        expected.append(diffusion_gain(knowledge[i], levels, transmissibility, teaching[i]))
    got = diffusion_gains(
        knowledge,
        np.array(receivers, dtype=np.int64),
        np.array(sources, dtype=np.int64),
        np.array(weights),
        transmissibility,
        teaching,
    )
    assert np.array_equal(got, np.array(expected))


def test_batched_support_matches_per_unit_loss_check(knowledge_model: KnowledgeModel) -> None:
    rng = np.random.default_rng(1)
    everything = frozenset(knowledge_model.technologies)
    levels = rng.uniform(0, 5, (50, len(knowledge_model.domains)))
    supported = knowledge_model.knowledge_supported(levels, 0.25)
    for row, k in zip(supported, levels, strict=True):
        assert knowledge_model.unsupported_given(everything, row) == (
            knowledge_model.unsupported(everything, k, 0.25)
        )
