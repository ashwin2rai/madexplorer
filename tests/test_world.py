import numpy as np

from madexplorer.config.schema import EcologyConfig, TopologyConfig, WorldConfig
from madexplorer.ecology.resources import logistic_regrowth, miami_npp
from madexplorer.world.generation import generate_world
from madexplorer.world.grid import WorldGrid


def _world(seed: int = 5, sea_fraction: float = 0.3) -> WorldGrid:
    config = WorldConfig(
        topology=TopologyConfig(seed=seed, width=32, height=24, sea_fraction=sea_fraction)
    )
    return generate_world(config, EcologyConfig())


def test_world_generation_is_deterministic() -> None:
    a, b = _world(), _world()
    assert np.array_equal(a.elevation_m, b.elevation_m)
    assert np.array_equal(a.base_rainfall_mm, b.base_rainfall_mm)


def test_sea_fraction_is_respected() -> None:
    world = _world(sea_fraction=0.3)
    assert abs(world.is_water.mean() - 0.3) < 0.02


def test_fields_have_expected_shapes_and_ranges() -> None:
    world = _world()
    land = ~world.is_water
    assert world.elevation_m.shape == (32 * 24,)
    assert (world.water_access >= 0).all() and (world.water_access <= 1).all()
    assert (world.vegetation_density[land] > 0).all() and (world.vegetation_density < 1).all()
    assert (world.base_npp_g_m2[world.is_water] == 0).all()


def test_rivers_form_on_land() -> None:
    world = _world()
    assert world.is_river.any()
    assert not (world.is_river & world.is_water).any()


def test_miami_npp_is_limited_by_the_scarcer_factor() -> None:
    wet_cold = miami_npp(np.array([0.0]), np.array([3000.0]))
    wet_warm = miami_npp(np.array([25.0]), np.array([3000.0]))
    dry_warm = miami_npp(np.array([25.0]), np.array([200.0]))
    assert wet_warm > wet_cold and wet_warm > dry_warm


def test_regrowth_recovers_depleted_stock_and_respects_capacity() -> None:
    capacity = np.array([100.0, 100.0, 100.0, 0.0])
    stock = np.array([0.0, 50.0, 180.0, 0.0])
    regrown = logistic_regrowth(stock, capacity, rate=1.5, recolonization=0.01)
    assert regrown[0] > 0  # recolonization
    assert stock[1] < regrown[1] <= 100
    assert 100 < regrown[2] < 180  # above-capacity stock decays toward capacity
    assert regrown[3] == 0
