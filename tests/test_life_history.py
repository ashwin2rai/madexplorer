import numpy as np

from madexplorer.species.life_history import LifeTables, life_expectancy_at_birth
from madexplorer.species.profile import SpeciesProfile


def test_forager_life_expectancy_is_plausible(human: SpeciesProfile) -> None:
    e0 = life_expectancy_at_birth(human.life_history)
    assert 25 < e0 < 45  # observed forager e0 is roughly 30-37 years


def test_hazard_is_bathtub_shaped(human_tables: LifeTables) -> None:
    hazard = human_tables.hazard
    trough = int(np.argmin(hazard))
    assert 5 <= trough <= 20
    assert hazard[0] > hazard[trough] < hazard[-1]


def test_fertility_sums_to_tfr(human: SpeciesProfile, human_tables: LifeTables) -> None:
    assert np.isclose(human_tables.fertility.sum(), human.life_history.total_fertility_rate)
    lh = human.life_history
    assert human_tables.fertility[: lh.fertility_onset_years].sum() == 0
    assert human_tables.fertility[lh.fertility_end_years :].sum() == 0


def test_need_and_labor_schedules_are_bounded(human_tables: LifeTables) -> None:
    assert (human_tables.need_fraction > 0).all() and (human_tables.need_fraction <= 1).all()
    assert (human_tables.labor >= 0).all() and (human_tables.labor <= 1).all()
    assert human_tables.labor[0] == 0
