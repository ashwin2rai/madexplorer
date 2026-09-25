"""Beliefs: sharing equals the reference dictionary merge; patches, lazy expiry, ownership."""

import numpy as np
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
    st.tuples(st.integers(-5, 20), st.floats(0, 1e6, width=32), st.integers(0, 500)).map(
        lambda t: Observation(year=t[0], food_kcal=t[1], population=t[2])
    ),
    max_size=40,
)


@settings(max_examples=200, deadline=None)
@given(own=beliefs_strategy, others=st.lists(beliefs_strategy, min_size=1, max_size=6))
def test_vectorized_sharing_matches_reference(
    own: dict[int, Observation], others: list[dict[int, Observation]]
) -> None:
    beliefs = BeliefMap.from_observations(N_CELLS, own)
    patch = freshest_from_partners(
        "u", beliefs, [BeliefMap.from_observations(N_CELLS, b) for b in others], N_CELLS
    )
    if patch is not None:
        beliefs.write(patch.cells, patch.year, patch.food_kcal, patch.population)
    assert beliefs.to_dict() == _reference(own, others)


def test_belief_map_merge_keeps_the_freshest_observation() -> None:
    old, same = Observation(5, 1.0, 1), Observation(9, 2.0, 2)
    newer, tie = Observation(7, 3.0, 3), Observation(9, 4.0, 4)
    a = BeliefMap.from_observations(4, {0: old, 1: same})
    b = BeliefMap.from_observations(4, {0: newer, 1: tie})
    merged = a.merged_with(b)
    assert merged.to_dict() == {0: newer, 1: same}  # strictly fresher wins; a tie keeps ours
    assert 2 not in merged and len(a.to_dict()) == 2
    assert merged is not b


def test_expiry_is_lazy_and_checked_on_read() -> None:
    beliefs = BeliefMap.from_observations(
        5, {0: Observation(10, 1.0, 0), 1: Observation(3, 1.0, 0)}
    )
    cells = np.arange(5)
    # Memory 8 in year 12: year 10 is current, year 3 is stale, cells 2-4 never observed.
    assert beliefs.current(cells, 12, 8).tolist() == [True, False, False, False, False]
    assert beliefs.known_cells(12, 8) == 1
    assert 1 in beliefs  # still stored; only readers treat it as forgotten
    assert beliefs.known_cells(19, 8) == 0


def test_patch_changes_only_its_cells_and_copies_are_independent() -> None:
    beliefs = BeliefMap.from_observations(6, {0: Observation(1, 5.0, 2), 4: Observation(2, 7.0, 3)})
    daughter = beliefs.copy()
    before = beliefs.to_dict()
    cells = np.array([1, 4])
    beliefs.write(cells, np.array([9, 9], dtype=np.int32), np.array([1.5, 2.5]), np.array([0, 1]))
    after = beliefs.to_dict()
    assert after[0] == before[0]
    assert after[1] == Observation(9, 1.5, 0) and after[4] == Observation(9, 2.5, 1)
    assert daughter.to_dict() == before  # the copy is unaffected
