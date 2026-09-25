"""Mechanism tests for the migration choice (spec §10.2): no best-of-many-noise bias."""

import math
from dataclasses import replace

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.mobility.exploration import food_prior
from madexplorer.mobility.migration import (
    MigrationSubsystem,
    attention_set,
    choose_destination,
    destination_components,
    direct_confidence,
)
from madexplorer.population.unit import BeliefMap, Observation, PopulationUnit
from tests.conftest import ROOT, small_scenario_dict, step_context


def _simulator(inertia: float | None = None, shrink: bool = False) -> Simulator:
    data = small_scenario_dict()
    if shrink:
        data["mechanisms"] = {"direct_observation_shrinkage": True}
    if inertia is not None:
        data["species"] = [
            {
                "id": "human",
                "profile": "species/human.yaml",
                "overrides": {"migration": {"inertia": inertia}},
            }
        ]
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    # Uniform water access, so alternatives that share a food belief are truly identical.
    sim.state.world = replace(sim.world, water_access=np.full(sim.world.n_cells, 0.5))
    return sim


def _only_unit(sim: Simulator) -> PopulationUnit:
    (unit,) = sim.state.units.values()
    return unit


def _observation(sim: Simulator, food_kcal: float) -> Observation:
    return Observation(year=sim.state.year, food_kcal=food_kcal, population=0)


def _neighbors_by_cost(sim: Simulator, unit: PopulationUnit) -> list[int]:
    reachable = sim.movement[unit.species_id].reachable(unit.cell)
    return sorted((c for c in reachable if c != unit.cell), key=lambda c: (reachable[c], c))


def _hazard(sim: Simulator, beliefs: dict[int, Observation]) -> float:
    unit = _only_unit(sim)
    unit.beliefs = BeliefMap.from_observations(sim.world.n_cells, beliefs)
    decision = MigrationSubsystem().decide(
        unit, sim.state, step_context(sim), np.random.default_rng(0)
    )
    assert decision is not None
    return decision.hazard


def test_identical_alternatives_do_not_raise_move_probability_with_their_number() -> None:
    sim = _simulator()
    unit = _only_unit(sim)
    home = _observation(sim, 5e6)
    options = _neighbors_by_cost(sim, unit)
    assert len(options) >= 16
    hazards = []
    for k in (1, 4, 16, len(options)):
        # Extra options are identical but no closer, so the best option is unchanged.
        beliefs = {unit.cell: home} | {c: _observation(sim, 5e6) for c in options[:k]}
        hazards.append(_hazard(sim, beliefs))
    assert max(hazards) - min(hazards) < 1e-12


def test_better_destination_raises_move_probability() -> None:
    sim = _simulator()
    unit = _only_unit(sim)
    target = _neighbors_by_cost(sim, unit)[0]
    same = _hazard(sim, {unit.cell: _observation(sim, 2e6), target: _observation(sim, 2e6)})
    better = _hazard(sim, {unit.cell: _observation(sim, 2e6), target: _observation(sim, 8e6)})
    assert better > same


def test_higher_inertia_lowers_move_probability() -> None:
    hazards = []
    for inertia in (0.0, 1.0, 3.0):
        sim = _simulator(inertia)
        unit = _only_unit(sim)
        target = _neighbors_by_cost(sim, unit)[0]
        beliefs = {unit.cell: _observation(sim, 2e6), target: _observation(sim, 8e6)}
        hazards.append(_hazard(sim, beliefs))
    assert hazards[0] > hazards[1] > hazards[2]


@pytest.mark.parametrize("k", [2, 30])
def test_moves_are_stochastic_with_frequency_matching_the_hazard(k: int) -> None:
    sim = _simulator()
    unit = _only_unit(sim)
    options = _neighbors_by_cost(sim, unit)[:k]
    unit.beliefs = BeliefMap.from_observations(
        sim.world.n_cells,
        {unit.cell: _observation(sim, 2e6)} | {c: _observation(sim, 4e6) for c in options},
    )
    subsystem, ctx = MigrationSubsystem(), step_context(sim)
    decision = subsystem.decide(unit, sim.state, ctx, np.random.default_rng(0))
    assert decision is not None and 0.1 < decision.hazard < 0.9
    trials = 4000
    moves = sum(len(subsystem.evaluate(sim.state, ctx)) for _ in range(trials))
    se = np.sqrt(decision.hazard * (1 - decision.hazard) / trials)
    assert abs(moves / trials - decision.hazard) < 4 * se


def test_choose_destination_ignores_current_cell_and_breaks_ties_uniformly() -> None:
    rng = np.random.default_rng(0)
    assert choose_destination([1, 2, 3], [9.0, 1.0, 5.0], current=1, rng=rng) == 3
    assert choose_destination([1], [0.0], current=1, rng=rng) is None
    picks = [choose_destination([1, 2, 3], [0.0, 1.0, 1.0], 1, rng) for _ in range(2000)]
    share = picks.count(2) / len(picks)
    assert 0.45 < share < 0.55


def test_vectorized_scores_match_the_component_rule() -> None:
    sim = _simulator()
    unit = _only_unit(sim)
    rng = np.random.default_rng(9)
    unit.fields_ha, unit.crop_yield_kcal_per_ha, unit.stores_kcal = 2.0, 8e5, 4e6
    unit.food_log_prior = math.log(3e6)
    cells = [unit.cell, *_neighbors_by_cost(sim, unit)[:15]]
    unit.beliefs = BeliefMap.from_observations(
        sim.world.n_cells,
        {
            c: Observation(
                year=sim.state.year - int(rng.integers(0, 15)),
                food_kcal=float(rng.uniform(1e5, 1e7)),
                population=int(rng.integers(0, 300)),
                hops=0 if c == unit.cell else int(rng.integers(0, 4)),
            )
            for c in cells
        },
    )
    subsystem = MigrationSubsystem()
    prepared = subsystem._prepare(unit, sim.state, step_context(sim))
    assert prepared is not None
    water = rng.uniform(size=sim.world.n_cells)
    (scores,) = subsystem._scores([prepared], sim.state.year, water)
    for cell, score in zip(prepared.candidates.tolist(), scores.tolist(), strict=True):
        components = destination_components(
            unit,
            cell,
            prepared.costs,
            sim.state.year,
            prepared.memory_years,
            prepared.behavior,
            float(water[cell]),
            prepared.confidence_decay,
            prepared.direct_confidence,
        )
        expected = sum(components.values())
        assert score == pytest.approx(expected, rel=1e-9, abs=1e-12)


def test_hearsay_about_a_rich_cell_pulls_less_than_a_direct_observation() -> None:
    sim = _simulator()
    unit = _only_unit(sim)
    target = _neighbors_by_cost(sim, unit)[0]
    unit.food_log_prior = math.log(2e6)
    hazards = []
    for hops in (0, 1, 3):
        rich = Observation(year=sim.state.year, food_kcal=8e6, population=0, hops=hops)
        hazards.append(_hazard(sim, {unit.cell: _observation(sim, 2e6), target: rich}))
    assert hazards[0] > hazards[1] > hazards[2]
    # Shrinkage never makes the report useless: even hearsay beats an average alternative.
    average = Observation(year=sim.state.year, food_kcal=2e6, population=0, hops=3)
    baseline = _hazard(sim, {unit.cell: _observation(sim, 2e6), target: average})
    assert hazards[2] > baseline


def test_direct_confidence_is_precision_weighted_and_off_by_default() -> None:
    assert direct_confidence(0.5, 0.3, enabled=False) == 1.0
    assert direct_confidence(0.5, 0.0, enabled=True) == 1.0
    assert direct_confidence(0.0, 0.3, enabled=True) == 0.0  # differences are all noise
    assert direct_confidence(0.09, 0.3, enabled=True) == pytest.approx(0.5)
    assert direct_confidence(1.0, 0.3, True) > direct_confidence(0.1, 0.3, True)
    assert direct_confidence(0.5, 0.1, True) > direct_confidence(0.5, 0.5, True)


def test_food_prior_recovers_the_true_between_cell_variance() -> None:
    rng = np.random.default_rng(3)
    true = np.exp(12.0 + 0.6 * rng.standard_normal(5000))
    observed = true * np.exp(0.3 * rng.standard_normal(true.size))
    log_prior, signal_var = food_prior(observed, 0.3)
    assert log_prior == pytest.approx(12.0, abs=0.05)
    assert signal_var == pytest.approx(0.36, rel=0.1)
    assert food_prior(np.full(9, 5e6), 0.3)[1] == 0.0  # no spread beyond noise: tau^2 = 0


def _noisy_hazards(shrink: bool, spread: float, seed: int, better: float = 1.0) -> list[float]:
    """Hazards for a unit whose neighborhood is observed with sigma = 0.3 noise.

    True food is lognormal with ``spread`` across cells; the nearest neighbor's true food is
    multiplied by ``better``. The prior is estimated from the observations, as in perception.
    """
    sim = _simulator(shrink=shrink)
    unit = _only_unit(sim)
    rng = np.random.default_rng(seed)
    cells = [unit.cell, *_neighbors_by_cost(sim, unit)[:20]]
    hazards = []
    for _ in range(40):
        true = 3e6 * np.exp(spread * rng.standard_normal(len(cells)))
        true[0] = 3e6
        true[1] = 3e6 * better
        observed = true * np.exp(0.3 * rng.standard_normal(len(cells)))
        unit.food_log_prior, unit.food_log_signal_var = food_prior(observed, 0.3)
        beliefs = {
            c: Observation(year=sim.state.year, food_kcal=float(f), population=0)
            for c, f in zip(cells, observed, strict=True)
        }
        hazards.append(_hazard(sim, beliefs))
    return hazards


def test_shrinkage_damps_moves_driven_only_by_observation_noise() -> None:
    # Every cell is truly identical: any apparent advantage is noise (winner's curse).
    off = np.mean(_noisy_hazards(shrink=False, spread=0.0, seed=1))
    on = np.mean(_noisy_hazards(shrink=True, spread=0.0, seed=1))
    assert on < 0.8 * off


def test_shrinkage_keeps_responding_to_a_genuinely_better_nearby_cell() -> None:
    # Cells differ for real (spread 0.8 >> noise 0.3) and one neighbor is 4x richer.
    better_on = np.mean(_noisy_hazards(shrink=True, spread=0.8, seed=2, better=4.0))
    same_on = np.mean(_noisy_hazards(shrink=True, spread=0.8, seed=2, better=1.0))
    better_off = np.mean(_noisy_hazards(shrink=False, spread=0.8, seed=2, better=4.0))
    assert better_on > same_on
    assert better_on > 0.8 * better_off  # real differences are barely discounted


def test_attention_cap_is_utility_blind_and_keeps_the_current_cell() -> None:
    candidates = np.array([3, 5, 7, 9, 11])
    costs = np.array([10.0, 0.0, 30.0, 5.0, 5.0])
    assert attention_set(candidates, costs, 5, None).tolist() == [0, 1, 2, 3, 4]
    kept = candidates[attention_set(candidates, costs, 5, 3)].tolist()
    assert kept == [5, 9, 11]  # current cell + two nearest (ties by cell id)
