"""Belief sharing: the vectorized merge must equal the reference dictionary merge exactly."""

from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.mobility.exploration import freshest_from_partners
from madexplorer.population.unit import BeliefMap, Observation

N_CELLS = 60


def _reference(
    own: dict[int, Observation], partners: list[dict[int, Observation]]
) -> dict[int, Observation]:
    """The original dictionary merge (first partner wins ties), applied to ``own``."""
    received: dict[int, Observation] = {}
    for other in partners:
        for c, obs in other.items():
            best = received.get(c) or own.get(c)
            if best is None or obs.year > best.year:
                received[c] = obs
    return own | received


beliefs_strategy = st.dictionaries(
    st.integers(0, N_CELLS - 1),
    st.tuples(st.integers(-5, 20), st.floats(0, 1e6), st.integers(0, 500)).map(
        lambda t: Observation(year=t[0], food_kcal=t[1], water_access=t[1] / 1e6, population=t[2])
    ),
    max_size=40,
)


@settings(max_examples=200, deadline=None)
@given(own=beliefs_strategy, others=st.lists(beliefs_strategy, min_size=1, max_size=6))
def test_vectorized_sharing_matches_reference(
    own: dict[int, Observation], others: list[dict[int, Observation]]
) -> None:
    merged = freshest_from_partners(
        BeliefMap.from_observations(N_CELLS, own),
        [BeliefMap.from_observations(N_CELLS, b) for b in others],
    )
    expected = _reference(own, others)
    got = merged.to_dict() if merged is not None else own
    assert got == expected


def test_belief_map_merge_keeps_the_freshest_observation() -> None:
    old, same = Observation(5, 1.0, 0.1, 1), Observation(9, 2.0, 0.2, 2)
    newer, tie = Observation(7, 3.0, 0.3, 3), Observation(9, 4.0, 0.4, 4)
    a = BeliefMap.from_observations(4, {0: old, 1: same})
    b = BeliefMap.from_observations(4, {0: newer, 1: tie})
    merged = a.merged_with(b)
    assert merged.to_dict() == {0: newer, 1: same}  # strictly fresher wins; a tie keeps ours
    assert 2 not in merged and len(a) == 2
