import numpy as np

from madexplorer.config.schema import EcologyConfig, TopologyConfig, WorldConfig
from madexplorer.mobility.movement import MovementModel, cell_friction
from madexplorer.species.profile import SpeciesProfile
from madexplorer.world.generation import generate_world
from madexplorer.world.grid import WorldGrid


def _world() -> WorldGrid:
    return generate_world(
        WorldConfig(topology=TopologyConfig(seed=2, width=24, height=24)), EcologyConfig()
    )


def test_friction_increases_with_vegetation_and_slope(human: SpeciesProfile) -> None:
    world = _world()
    friction = cell_friction(world, human.movement)
    land = ~world.is_water
    veg_corr = np.corrcoef(world.vegetation_density[land], friction[land])[0, 1]
    assert veg_corr > 0
    assert (friction[land] >= 1).all()


def test_walkers_cannot_cross_water_but_fliers_can(human: SpeciesProfile) -> None:
    world = _world()
    walker = cell_friction(world, human.movement)
    assert np.isinf(walker[world.is_water]).all()
    flier = human.movement.model_copy(update={"can_fly": True, "flight_terrain_factor": 0.1})
    flying = cell_friction(world, flier)
    assert np.isfinite(flying).all()
    land = ~world.is_water
    assert (flying[land] <= walker[land]).all()  # flight reduces slope and vegetation penalties


def test_reachability_is_bounded_by_range(human: SpeciesProfile) -> None:
    world = _world()
    origin = int(np.flatnonzero(~world.is_water)[0])
    reachable = MovementModel(world, human.movement).reachable(origin)
    assert reachable[origin] == 0
    assert max(reachable.values()) <= human.movement.annual_relocation_range_km
    assert all(not world.is_water[c] for c in reachable)
