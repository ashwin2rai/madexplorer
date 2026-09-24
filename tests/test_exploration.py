"""Belief sharing: the vectorized merge must equal the reference dictionary merge exactly."""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.mobility.exploration import _BeliefYears, freshest_from_partners
from madexplorer.population.unit import Observation, PopulationUnit

N_CELLS = 60


def _unit(uid: str, beliefs: dict[int, Observation]) -> PopulationUnit:
    cohort = np.zeros(3, dtype=np.int64)
    return PopulationUnit(
        id=uid,
        species_id="human",
        cell=0,
        females=cohort,
        males=cohort,
        reserve_kcal_per_capita=0.0,
        founded_year=0,
        beliefs=beliefs,
    )


def _reference(unit: PopulationUnit, partners: list[PopulationUnit]) -> dict[int, Observation]:
    """The original per-observation merge (first partner wins ties)."""
    received: dict[int, Observation] = {}
    for other in partners:
        for c, obs in other.beliefs.items():
            best = received.get(c) or unit.beliefs.get(c)
            if best is None or obs.year > best.year:
                received[c] = obs
    return received


beliefs_strategy = st.dictionaries(
    st.integers(0, N_CELLS - 1),
    st.integers(-5, 20).map(
        lambda y: Observation(year=y, food_kcal=float(y), water_access=0.0, population=0)
    ),
    max_size=40,
)


@settings(max_examples=200, deadline=None)
@given(own=beliefs_strategy, others=st.lists(beliefs_strategy, min_size=1, max_size=6))
def test_vectorized_sharing_matches_reference(
    own: dict[int, Observation], others: list[dict[int, Observation]]
) -> None:
    unit = _unit("u", own)
    partners = [_unit(f"p{i}", b) for i, b in enumerate(others)]
    got = freshest_from_partners(unit, partners, _BeliefYears(N_CELLS))
    expected = _reference(unit, partners)
    assert got.keys() == expected.keys()
    assert all(got[c] is expected[c] for c in got)
