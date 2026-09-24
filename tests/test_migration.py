"""Mechanism tests for the migration choice (spec §10.2): no best-of-many-noise bias."""

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.mobility.migration import (
    MigrationSubsystem,
    choose_destination,
    destination_components,
)
from madexplorer.population.unit import BeliefMap, Observation, PopulationUnit
from tests.conftest import ROOT, small_scenario_dict, step_context


def _simulator(inertia: float | None = None) -> Simulator:
    data = small_scenario_dict()
    if inertia is not None:
        data["species"] = [
            {
                "id": "human",
                "profile": "species/human.yaml",
                "overrides": {"migration": {"inertia": inertia}},
            }
        ]
    return Simulator(Scenario.from_dict(data, base_dir=ROOT))


def _only_unit(sim: Simulator) -> PopulationUnit:
    (unit,) = sim.state.units.values()
    return unit


def _observation(sim: Simulator, food_kcal: float) -> Observation:
    return Observation(year=sim.state.year, food_kcal=food_kcal, water_access=0.5, population=0)


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
    cells = [unit.cell, *_neighbors_by_cost(sim, unit)[:15]]
    unit.beliefs = BeliefMap.from_observations(
        sim.world.n_cells,
        {
            c: Observation(
                year=sim.state.year - int(rng.integers(0, 15)),
                food_kcal=float(rng.uniform(1e5, 1e7)),
                water_access=float(rng.uniform()),
                population=int(rng.integers(0, 300)),
            )
            for c in cells
        },
    )
    subsystem = MigrationSubsystem()
    prepared = subsystem._prepare(unit, sim.state, step_context(sim))
    assert prepared is not None
    (scores,) = subsystem._scores([prepared], sim.state.year)
    for cell, score in zip(prepared.candidates.tolist(), scores.tolist(), strict=True):
        components = destination_components(
            unit, cell, prepared.costs, sim.state.year, prepared.memory_years, prepared.behavior
        )
        expected = sum(components.values())
        assert score == pytest.approx(expected, rel=1e-9, abs=1e-12)
