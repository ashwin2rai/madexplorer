"""Leaving fields costs the labor to replace them, not their crop (already in staying)."""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.agriculture import clearing_hours_per_ha
from madexplorer.mobility.migration import MigrationSubsystem, field_replacement_cost
from madexplorer.population.unit import BeliefMap, Observation, PopulationUnit
from tests.conftest import ROOT, mvp2_scenario_dict, step_context


def _farmer() -> tuple[Simulator, PopulationUnit]:
    data = mvp2_scenario_dict()
    data["mechanisms"] = {"direct_observation_shrinkage": False}
    sim = Simulator(Scenario.from_dict(data, base_dir=ROOT))
    (unit,) = sim.state.units.values()
    reachable = sim.movement[unit.species_id].reachable(unit.cell)
    unit.beliefs = BeliefMap.from_observations(
        sim.world.n_cells,
        {c: Observation(year=sim.state.year, food_kcal=3e7, population=0) for c in reachable},
    )
    unit.fields_ha, unit.crop_yield_kcal_per_ha = 4.0, 6e5
    unit.forage_marginal_kcal_per_hour = 500.0
    return sim, unit


def _fields_cost(sim: Simulator, unit: PopulationUnit) -> float:
    prepared = MigrationSubsystem()._prepare(unit, sim.state, step_context(sim))
    assert prepared is not None
    return prepared.costs.fields_cost


def _hazard(sim: Simulator, unit: PopulationUnit) -> float:
    decision = MigrationSubsystem().decide(
        unit, sim.state, step_context(sim), np.random.default_rng(0)
    )
    assert decision is not None
    return decision.hazard


@given(
    fields=st.floats(0.0, 500.0),
    clearing=st.floats(0.0, 5000.0),
    marginal=st.floats(0.0, 3000.0),
    need=st.floats(1e3, 1e8),
)
def test_replacement_cost_is_reclearing_labor_valued_at_the_foraging_return(
    fields: float, clearing: float, marginal: float, need: float
) -> None:
    cost = field_replacement_cost(fields, clearing, marginal, need)
    assert cost >= 0
    assert cost == pytest.approx(fields * clearing * marginal / need, rel=1e-12, abs=1e-300)


def test_replacement_cost_is_zero_without_fields_or_need() -> None:
    assert field_replacement_cost(0.0, 800.0, 500.0, 1e6) == 0.0
    assert field_replacement_cost(3.0, 800.0, 500.0, 0.0) == 0.0


def test_leaving_cost_uses_home_clearing_conditions_and_the_stores_scale() -> None:
    sim, unit = _farmer()
    ctx = step_context(sim)
    per_ha = clearing_hours_per_ha(
        float(sim.world.vegetation_density[unit.cell]),
        sim.scenario.config.agriculture,
        ctx.capabilities(unit)["clearing_efficiency"],
    )
    prepared = MigrationSubsystem()._prepare(unit, sim.state, ctx)
    assert prepared is not None
    weight = prepared.behavior.abandoned_stores_weight
    expected = weight * field_replacement_cost(4.0, per_ha, 500.0, prepared.costs.need_kcal)
    assert prepared.costs.fields_cost == pytest.approx(expected)
    assert prepared.costs.fields_cost > 0


def test_crop_output_is_not_charged_again_when_leaving() -> None:
    sim, unit = _farmer()
    base = _fields_cost(sim, unit)
    unit.crop_yield_kcal_per_ha *= 3  # the crop is valued in the stay term only
    assert _fields_cost(sim, unit) == base


def test_labor_already_spent_clearing_is_sunk() -> None:
    sim, unit = _farmer()
    base = _fields_cost(sim, unit)
    unit.clearing_hours, unit.labor_debt_hours = 1e5, 1e5
    assert _fields_cost(sim, unit) == base


def test_replacement_cost_scales_with_fields_and_the_value_of_labor() -> None:
    sim, unit = _farmer()
    base = _fields_cost(sim, unit)
    unit.fields_ha *= 2
    assert _fields_cost(sim, unit) == pytest.approx(2 * base)
    unit.forage_marginal_kcal_per_hour = 0.0
    assert _fields_cost(sim, unit) == 0.0


def test_fields_still_anchor_a_group() -> None:
    sim, unit = _farmer()
    unit.fields_ha = 0.0
    no_fields = _hazard(sim, unit)
    unit.fields_ha = 4.0
    with_fields = _hazard(sim, unit)
    assert math.isfinite(with_fields) and with_fields < no_fields
