import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from madexplorer.population.demography import (
    demographic_step,
    fertility_multiplier,
    mortality_hazards,
)
from madexplorer.population.groups import split_cohorts
from madexplorer.species.life_history import LifeTables

cohorts = arrays(np.int64, (2, 91), elements=st.integers(min_value=0, max_value=50))


@settings(max_examples=50)
@given(cohorts, cohorts, st.integers(min_value=0, max_value=2**32 - 1))
def test_demographic_accounting(females: np.ndarray, males: np.ndarray, seed: int) -> None:
    rng = np.random.default_rng(seed)
    death_p = np.full((2, 91), 0.05)
    fertility = np.full((2, 91), 0.1)
    out = demographic_step(females, males, death_p, fertility, 0.5, 1, rng)
    before = females.sum(axis=1) + males.sum(axis=1)
    after = out.females.sum(axis=1) + out.males.sum(axis=1)
    assert (after == before + out.births - out.deaths).all()
    assert (out.females >= 0).all() and (out.males >= 0).all()


@given(
    cohorts,
    cohorts,
    st.floats(min_value=0, max_value=1),
    st.integers(min_value=0, max_value=2**32 - 1),
)
def test_split_conserves_every_cohort(
    females: np.ndarray, males: np.ndarray, fraction: float, seed: int
) -> None:
    kf, km, lf, lm = split_cohorts(females, males, fraction, np.random.default_rng(seed))
    assert np.array_equal(kf + lf, females) and np.array_equal(km + lm, males)
    assert (kf >= 0).all() and (lf >= 0).all()


def test_starvation_raises_mortality(human_tables: LifeTables) -> None:
    hazard, _ = mortality_hazards(human_tables, np.array([0.0, 0.5]), 3.0, np.zeros(2))
    assert (hazard[1] > hazard[0]).all()


def test_fertility_falls_with_food_shortfall() -> None:
    multiplier = fertility_multiplier(np.array([0.4, 0.8, 1.0, 1.5]), midpoint=0.8, scale=0.1)
    assert multiplier[0] < multiplier[1] < multiplier[2] == 1.0
    assert multiplier[3] == 1.0


def test_wellfed_population_grows_on_average(human_tables: LifeTables) -> None:
    """Statistical: under baseline mortality and full fertility, growth is positive but modest."""
    rng = np.random.default_rng(0)
    weights = human_tables.survivorship / human_tables.survivorship.sum()
    females = np.tile(rng.multinomial(5000, weights), (1, 1)).astype(np.int64)
    males = females.copy()
    start = int(females.sum() + males.sum())
    death_p = 1.0 - np.exp(-human_tables.hazard)[None, :]
    for _ in range(25):
        out = demographic_step(
            females, males, death_p, human_tables.fertility[None, :], 0.512, 1, rng
        )
        females, males = out.females, out.males
    annual_growth = (int(females.sum() + males.sum()) / start) ** (1 / 25) - 1
    assert 0.0 < annual_growth < 0.03
