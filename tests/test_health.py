"""Mechanism tests for settlement crowding mortality (spec §8.4, §29.1)."""

import numpy as np
import pytest

from madexplorer.population.demography import mortality_probability
from madexplorer.population.health import (
    crowding_hazards,
    sedentism,
    settlement_crowding_pressure,
)
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import Health, SpeciesProfile


def _unit(uid: str, n: int, cell: int = 0, residence: int = 30, groups: int = 1) -> PopulationUnit:
    females = np.zeros(91, dtype=np.int64)
    females[25] = n
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=cell,
        females=females,
        males=np.zeros(91, dtype=np.int64),
        reserve_kcal_per_capita=0.0,
        founded_year=0,
        residence_years=residence,
        groups=groups,
    )


def _hazards(
    units: list[PopulationUnit], health: Health, cell_km: float = 10.0
) -> dict[str, float]:
    return crowding_hazards(units, {"human": health}, cell_km**2)


def test_pressure_and_sedentism_are_monotone() -> None:
    assert settlement_crowding_pressure(0.0, 50) == 0.0
    assert settlement_crowding_pressure(500, 50) > settlement_crowding_pressure(100, 50)
    assert sedentism(0, 5.0) == 0.0
    assert sedentism(20, 5.0) > sedentism(2, 5.0)


def test_concentrated_settlement_has_higher_hazard_than_dispersed(human: SpeciesProfile) -> None:
    concentrated = _hazards([_unit("a", 600)], human.health)["a"]
    dispersed = _hazards([_unit(f"u{i}", 100, cell=i) for i in range(6)], human.health)
    assert concentrated > max(dispersed.values())


def test_more_settled_neighbors_raise_hazard(human: SpeciesProfile) -> None:
    alone = _hazards([_unit("a", 100)], human.health)["a"]
    crowded = _hazards([_unit("a", 100)] + [_unit(f"n{i}", 300) for i in range(5)], human.health)
    assert crowded["a"] > alone


def test_mobile_groups_avoid_most_of_the_penalty(human: SpeciesProfile) -> None:
    hazards = _hazards(
        [_unit("settled", 300, residence=40), _unit("mobile", 300, residence=0)], human.health
    )
    assert hazards["mobile"] == 0.0 < hazards["settled"]
    recent = _hazards([_unit("recent", 300, residence=1)], human.health)["recent"]
    assert 0.0 < recent < hazards["settled"]


def test_crowding_raises_death_probability(human_tables: LifeTables) -> None:
    deficit = np.zeros(2)
    base = mortality_probability(human_tables, deficit, 3.0, np.zeros(2))
    crowded = mortality_probability(human_tables, deficit, 3.0, np.array([0.0, 0.01]))
    assert np.allclose(crowded[0], base[0])
    assert (crowded[1] > base[1]).all()


def test_grid_resolution_barely_changes_the_hazard(human: SpeciesProfile) -> None:
    # Four villages of 100 settled people, 10 km apart: one per 10 km cell, or all in a 20 km cell.
    fine = _hazards([_unit(f"v{i}", 100, cell=i) for i in range(4)], human.health, cell_km=10.0)
    coarse = _hazards([_unit(f"v{i}", 100) for i in range(4)], human.health, cell_km=20.0)
    assert coarse["v0"] == pytest.approx(fine["v0"], rel=0.1)
    # Treating the whole coarse cell as one settlement would nearly double it.
    whole_cell = _hazards([_unit("v", 400)], human.health, cell_km=20.0)["v"]
    assert whole_cell > 1.5 * fine["v0"]


def test_computational_aggregation_does_not_change_the_hazard(human: SpeciesProfile) -> None:
    separate = _hazards([_unit(f"g{i}", 100) for i in range(3)] + [_unit("x", 50)], human.health)
    merged = _hazards([_unit("g", 300, groups=3), _unit("x", 50)], human.health)
    assert merged["g"] == pytest.approx(separate["g0"])
    assert merged["x"] == pytest.approx(separate["x"])
