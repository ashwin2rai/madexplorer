"""PH4a compiled kernels against their Python references (Level A: bit-identical).

Each kernel is fed the same numeric inputs as the frozen Python rule it transcribes;
floats must be equal bit for bit, not approximately.
"""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.jit import numpy_sum, python_sum
from madexplorer.core.simulation import Simulator
from madexplorer.economy.foraging import (
    CellHarvests,
    ForagingSubsystem,
    cell_harvest,
    single_unit_harvest,
)
from madexplorer.economy.foraging_kernel import forage_groups
from madexplorer.experiments.benchmark import synthetic_simulator
from tests.conftest import ROOT, mvp2_scenario_dict, step_context


@pytest.mark.parametrize("n", [*range(0, 300), 383, 1000, 1031, 4097, 9000, 100_003])
def test_numpy_sum_is_numpys_pairwise_sum(n: int) -> None:
    rng = np.random.default_rng(n)
    for _ in range(3):
        values = rng.lognormal(0.0, 4.0, n) * rng.choice([-1.0, 1.0], n)
        assert numpy_sum(values, 0, n) == values.sum()
        if n > 3:  # an offset slice of a larger buffer, as the kernels use scratch arrays
            assert numpy_sum(values, 2, n - 3) == values[2 : n - 1].sum()


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.sampled_from([0.0, -0.0, 1e308, -1e308, 1e-300, 5e-324]),
        ),
        max_size=40,
    )
)
def test_python_sum_is_the_builtin(values: list[float]) -> None:
    array = np.array(values, dtype=np.float64)
    got, want = python_sum(array, 0, array.size), sum(values)
    assert got == want or (got != got and want != want)  # NaN from overflow cancellation
    assert np.signbit(got) == np.signbit(want)


def _reference_groups(
    sizes: list[int],
    cells: list[int],
    labor: np.ndarray,
    efficiency: np.ndarray,
    target: np.ndarray,
    plant: np.ndarray,
    game: np.ndarray,
    access: tuple[np.ndarray, ...],
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """The Python reference loop of ``ForagingSubsystem._evaluate_reference``."""
    plant_access, game_access, plant_return, game_return = access
    plant, game = plant.copy(), game.copy()
    harvests: list[float] = []
    hours: list[float] = []
    marginals: list[float] = []
    removed_p: list[float] = []
    removed_g: list[float] = []
    start = 0
    target_list = target.tolist()
    for size, cell in zip(sizes, cells, strict=True):
        members = list(range(start, start + size))
        start += size
        if size == 1:
            r = members[0]
            stock = (float(plant[cell] * plant_access[cell]), float(game[cell] * game_access[cell]))
            returns = (float(plant_return[cell]), float(game_return[cell]))
            share, p, g, fraction, marginal = single_unit_harvest(
                stock, returns, float(labor[r]), float(efficiency[r]), 0 + target_list[r]
            )
            harvests.append(share)
            hours.append(float(labor[r]) * fraction)
            marginals.append(marginal * float(efficiency[r]))
        else:
            outcome = cell_harvest(
                np.array([plant[cell] * plant_access[cell], game[cell] * game_access[cell]]),
                np.array([plant_return[cell], game_return[cell]]),
                labor[members],
                efficiency[members],
                sum([target_list[r] for r in members]),
            )
            p, g = float(outcome.removal[0]), float(outcome.removal[1])
            harvests.extend(outcome.shares.tolist())
            hours.extend(x * outcome.effort_fraction for x in labor[members].tolist())
            marginals.extend(
                outcome.marginal_kcal_per_effective_hour * e for e in efficiency[members].tolist()
            )
        plant[cell] -= p
        game[cell] -= g
        removed_p.append(p)
        removed_g.append(g)
    return harvests, hours, marginals, removed_p, removed_g


def _edge_values(rng: np.random.Generator, n: int, scale: float) -> np.ndarray:
    """Positive values with exact zeros and repeated values mixed in."""
    values = rng.lognormal(np.log(scale), 1.5, n)
    values[rng.random(n) < 0.15] = 0.0
    repeat = rng.random(n) < 0.15
    values[repeat] = scale
    return values


@settings(max_examples=40, deadline=None)
@given(st.integers(0, 2**32 - 1))
def test_forage_kernel_equals_the_scalar_rules(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n_cells = 12
    # Group sizes 1-12 and an occasional large group (numpy's pairwise split above 128);
    # several groups per cell deplete the same stocks in order (successive species).
    sizes = [int(rng.integers(1, 13)) for _ in range(int(rng.integers(1, 25)))]
    if rng.random() < 0.2:
        sizes.append(int(rng.integers(129, 300)))
    cells = [int(rng.integers(n_cells)) for _ in sizes]
    n = sum(sizes)
    labor = _edge_values(rng, n, 2000.0)
    efficiency = _edge_values(rng, n, 0.7)
    need = _edge_values(rng, n, 4e5)
    # Targets around the attainable harvest: met, unmet, zero, and boundary cases.
    target = need * rng.choice([0.0, 0.01, 0.5, 1.0, 5.0, 1e3], n)
    plant = _edge_values(rng, n_cells, 3e6)
    game = _edge_values(rng, n_cells, 4e5)
    access = (
        np.clip(rng.uniform(-0.2, 1.0, n_cells), 0.0, 1.0),
        np.ones(n_cells),
        np.full(n_cells, rng.choice([600.0, 900.0])),
        _edge_values(rng, n_cells, 900.0),  # sometimes equal to the plant return
    )
    expected = _reference_groups(sizes, cells, labor, efficiency, target, plant, game, access)

    bounds = np.r_[0, np.cumsum(sizes)].astype(np.int64)
    out = [np.empty(n), np.empty(n), np.empty(n), np.empty(len(sizes)), np.empty(len(sizes))]
    forage_groups(
        np.arange(n, dtype=np.int64),
        bounds,
        np.array(cells, dtype=np.int64),
        np.zeros(len(sizes), dtype=np.int64),
        labor,
        efficiency,
        target,
        plant.copy(),
        game.copy(),
        access[0][None, :].copy(),
        access[1][None, :].copy(),
        access[2][None, :].copy(),
        access[3][None, :].copy(),
        out[0],
        out[1],
        out[2],
        out[3],
        out[4],
        np.empty(max(sizes)),
        np.empty(max(sizes)),
    )
    for got, want in zip(out, expected, strict=True):
        assert got.tolist() == want


def _proposal_state(proposal: CellHarvests) -> tuple[object, ...]:
    return (
        [u.id for u in proposal.cols.units],
        proposal.cells,
        proposal.bounds,
        proposal.rows.tolist(),
        proposal.harvest_kcal.tolist(),
        proposal.hours.tolist(),
        proposal.marginal_kcal_per_hour.tolist(),
        proposal.plant_removed_kcal,
        proposal.game_removed_kcal,
        proposal.learning_rate,
        proposal.familiarity,
    )


def _assert_evaluate_matches_reference(sim: Simulator) -> None:
    subsystem = ForagingSubsystem()
    (fast,) = subsystem.evaluate(sim.state, step_context(sim))
    (reference,) = subsystem._evaluate_reference(sim.state, step_context(sim))
    assert _proposal_state(fast) == _proposal_state(reference)
    assert max(np.diff(fast.bounds)) > 1  # multi-group cells were exercised


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000), st.booleans())
def test_compiled_foraging_equals_the_reference_evaluate(seed: int, farming: bool) -> None:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    sim = synthetic_simulator(scenario, 150, farming=farming)
    for _ in range(4):  # familiarity, depleted stocks, varied knowledge and labor debt
        sim.step()
    units = list(sim.state.units.values())
    rng = np.random.default_rng(seed)
    for unit in units[: len(units) // 2]:  # shared pools: multi-group cells of mixed sizes
        unit.cell = units[-1 - int(rng.integers(8))].cell
    _assert_evaluate_matches_reference(sim)


def test_compiled_foraging_two_species_share_cells_in_species_order() -> None:
    data = mvp2_scenario_dict(n_years=30, seed=2)
    data["species"] = [
        {"id": "human", "profile": "species/human.yaml"},
        {"id": "other", "profile": "species/human.yaml"},
    ]
    data["initial_populations"] = [
        {"species": "human", "cell": [8, 8], "population": 60},
        {"species": "other", "cell": [8, 8], "population": 60},
        {"species": "other", "cell": [8, 9], "population": 40},
    ]
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    for _ in range(12):
        sim.step()
    units = list(sim.state.units.values())
    for unit in units[1:]:  # everyone into one cell: interleaved species, shared stocks
        unit.cell = units[0].cell
    _assert_evaluate_matches_reference(sim)
    (fast,) = ForagingSubsystem().evaluate(sim.state, step_context(sim))
    assert len(fast.cells) == 2 and fast.cells[0] == fast.cells[1]  # two species groups


def _plans_state(plans: object) -> tuple[object, ...]:
    from madexplorer.economy.agriculture import FieldPlans

    assert isinstance(plans, FieldPlans)
    return tuple(
        getattr(plans, name).tolist()
        for name in ("rows", "fields_ha", "clearing_hours", "farm_return", "forage_marginal", "gap")
    )


@settings(max_examples=10, deadline=None)
@given(st.integers(0, 10_000), st.booleans(), st.booleans())
def test_compiled_field_planning_equals_the_reference_evaluate(
    seed: int, expected_tenure: bool, growth_to_target: bool
) -> None:
    from madexplorer.economy.agriculture import FieldPlanningSubsystem

    scenario = (
        Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
        .with_overrides(seed=seed)
        .with_settings(
            {
                "mechanisms.expected_tenure": expected_tenure,
                "mechanisms.field_growth_to_target": growth_to_target,
            }
        )
    )
    sim = synthetic_simulator(scenario, 160, farming=True)
    for _ in range(3):
        sim.step()
    rng = np.random.default_rng(seed)
    units = list(sim.state.units.values())
    crowded = [u.cell for u in units[:4]]
    for unit in units:  # every branch: hazards, tenure, thresholds, arable scarcity
        unit.move_hazard = float(rng.choice([np.nan, 0.0, 1.0, rng.uniform(0, 1)]))
        unit.residence_years = int(rng.integers(0, 40))
        unit.fields_ha = float(rng.choice([0.0, 0.01, rng.uniform(0, 30)]))
        unit.forage_marginal_kcal_per_hour = float(rng.lognormal(np.log(800), 1.0))
        if rng.random() < 0.5:
            unit.cell = crowded[int(rng.integers(len(crowded)))]
    subsystem = FieldPlanningSubsystem()
    (fast,) = subsystem.evaluate(sim.state, step_context(sim))
    (reference,) = subsystem._evaluate_reference(sim.state, step_context(sim))
    assert _plans_state(fast) == _plans_state(reference)
    assert len(fast.rows) > 10  # many plans, including shrinking and expanding ones


@settings(max_examples=300, deadline=None)
@given(st.floats(0.0, 1.0), st.integers(1, 60))
def test_kernel_power_is_pythons_float_power(p: float, horizon: int) -> None:
    from madexplorer.economy.agriculture import expected_tenure_years
    from madexplorer.economy.agriculture_kernel import _expected_tenure

    hazard = 1.0 - p
    assert _expected_tenure(hazard, horizon, 3) == expected_tenure_years(hazard, horizon, 3)
