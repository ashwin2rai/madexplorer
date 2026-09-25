"""The static scenario context is exact to reuse: same world, same results, any seed."""

import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.core.static import StaticContext, shared_static_context, static_key
from tests.conftest import ROOT, replay_key, small_scenario_dict


def _scenario(seed: int = 1, n_years: int = 30) -> Scenario:
    return Scenario.from_dict(small_scenario_dict(n_years=n_years, seed=seed), base_dir=ROOT)


def test_static_key_ignores_seed_and_horizon_but_not_species() -> None:
    base = _scenario()
    assert static_key(base) == static_key(base.with_overrides(seed=9, n_years=5))
    changed = base.with_settings({"species.human.movement.annual_relocation_range_km": 80})
    assert static_key(changed) != static_key(base)


def test_reusing_a_static_context_across_seeds_reproduces_fresh_runs() -> None:
    static = StaticContext.build(_scenario())
    for seed in (1, 2, 1):  # reuse after other seeds have filled the lazy caches
        scenario = _scenario(seed=seed)
        fresh = Simulator(scenario).run().metrics
        shared = Simulator(scenario, static=static).run().metrics
        assert replay_key(fresh) == replay_key(shared)


def test_shared_context_is_built_once_per_static_key() -> None:
    assert shared_static_context(_scenario(seed=3)) is shared_static_context(_scenario(seed=4))


def test_a_context_for_another_scenario_is_rejected() -> None:
    other = _scenario().with_settings({"species.human.movement.annual_relocation_range_km": 80})
    with pytest.raises(ValueError):
        Simulator(_scenario(), static=StaticContext.build(other))
