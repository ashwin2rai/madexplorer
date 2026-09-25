"""Beliefs and bounded social information: patches, lazy expiry, reports, confidence."""

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.mobility.exploration import (
    Reports,
    receive_reports,
    report_confidence,
    select_reports,
)
from madexplorer.population.unit import BeliefMap, Observation, PopulationUnit
from madexplorer.species.profile import SocialInformation

N_CELLS = 60
INFO = SocialInformation(
    reports_per_interaction=4, max_report_age_years=10, transmission_confidence_decay=0.7
)
YEAR, MEMORY = 20, 20


def _unit(beliefs: BeliefMap, cell: int = 0, prior: float = 1000.0) -> PopulationUnit:
    zeros = np.zeros(3, dtype=np.int64)
    unit = PopulationUnit("s", "human", cell, zeros, zeros, 0.0, 0, beliefs=beliefs)
    unit.food_log_prior = math.log(prior)
    return unit


def _reports(observations: dict[int, Observation]) -> Reports:
    cells = np.array(sorted(observations), dtype=np.int64)
    beliefs = BeliefMap.from_observations(N_CELLS, observations)
    return Reports(
        cells,
        beliefs.year[cells],
        beliefs.food_kcal[cells],
        beliefs.population[cells],
        beliefs.hops[cells],
    )


def _apply(own: BeliefMap, received: list[Reports]) -> BeliefMap:
    patch = receive_reports("u", own, received, N_CELLS)
    if patch is not None:
        own.write(patch.cells, patch.year, patch.food_kcal, patch.population, patch.hops)
    return own


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


def test_merge_keeps_the_freshest_then_the_least_relayed_entry() -> None:
    a = BeliefMap.from_observations(
        4, {0: Observation(5, 1.0, 1), 1: Observation(9, 2.0, 2, hops=2)}
    )
    b = BeliefMap.from_observations(
        4, {0: Observation(7, 3.0, 3, hops=1), 1: Observation(9, 4.0, 4, hops=1)}
    )
    merged = a.merged_with(b)
    assert merged.to_dict() == {0: Observation(7, 3.0, 3, 1), 1: Observation(9, 4.0, 4, 1)}
    assert 2 not in merged and merged is not b


def test_confidence_falls_with_each_relay() -> None:
    q = report_confidence(np.array([0, 1, 2, 3]), 0.7)
    assert q[0] == 1.0
    assert np.all(np.diff(q) < 0)
    assert q[2] == pytest.approx(0.49)


def test_an_encounter_passes_a_bounded_number_of_reports_whatever_the_map_size() -> None:
    for known in (10, 50):
        beliefs = BeliefMap.from_observations(
            N_CELLS, {c: Observation(YEAR, 1000.0 + c, 0) for c in range(known)}
        )
        pool = np.arange(known)
        reports = select_reports(_unit(beliefs), pool, YEAR, MEMORY, INFO)
        assert reports.cells.size == INFO.reports_per_interaction


def test_current_cell_first_hand_and_exceptional_places_are_mentioned_first() -> None:
    observations = {
        0: Observation(YEAR, 1000.0, 0),  # the sender's own cell, unremarkable
        1: Observation(YEAR, 1000.0, 0),  # first-hand, unremarkable
        2: Observation(YEAR, 1000.0, 0, hops=3),  # hearsay, unremarkable
        3: Observation(YEAR, 20000.0, 0),  # first-hand, exceptionally rich
        4: Observation(YEAR, 50.0, 0),  # first-hand, exceptionally poor
        5: Observation(YEAR - 9, 1000.0, 0),  # first-hand but old
    }
    beliefs = BeliefMap.from_observations(N_CELLS, observations)
    unit = _unit(beliefs, cell=0, prior=1000.0)
    chosen = select_reports(unit, np.arange(6), YEAR, MEMORY, INFO).cells.tolist()
    assert chosen[0] == 0
    assert set(chosen) == {0, 1, 3, 4}  # hearsay and old unremarkable reports lose out


def test_stale_and_too_old_beliefs_are_not_passed_on() -> None:
    observations = {
        0: Observation(YEAR, 1000.0, 0),
        1: Observation(YEAR - MEMORY, 1000.0, 0),  # forgotten (outside memory)
        2: Observation(YEAR - INFO.max_report_age_years - 1, 1000.0, 0),  # too old to mention
    }
    beliefs = BeliefMap.from_observations(N_CELLS, observations)
    chosen = select_reports(_unit(beliefs), np.arange(3), YEAR, MEMORY, INFO).cells.tolist()
    assert chosen == [0]


def test_received_reports_gain_a_relay_and_replace_only_worse_beliefs() -> None:
    own = BeliefMap.from_observations(
        N_CELLS,
        {
            0: Observation(YEAR, 1.0, 0),  # own direct observation this year
            1: Observation(YEAR - 5, 1.0, 0),  # older direct observation
        },
    )
    sender = _reports(
        {
            0: Observation(YEAR, 9.0, 9),  # as fresh, but hearsay to the receiver: rejected
            1: Observation(YEAR - 1, 9.0, 9),  # fresher: accepted
            2: Observation(YEAR - 2, 9.0, 9, hops=1),  # new: accepted with 2 relays
        }
    )
    result = _apply(own, [sender]).to_dict()
    assert result[0] == Observation(YEAR, 1.0, 0, 0)
    assert result[1] == Observation(YEAR - 1, 9.0, 9, 1)
    assert result[2] == Observation(YEAR - 2, 9.0, 9, 2)


def test_between_partners_the_freshest_then_least_relayed_report_wins() -> None:
    own = BeliefMap.empty(N_CELLS)
    first = _reports({5: Observation(YEAR - 1, 1.0, 1, hops=2), 6: Observation(YEAR, 3.0, 0)})
    second = _reports({5: Observation(YEAR - 1, 2.0, 2, hops=0), 6: Observation(YEAR, 4.0, 0)})
    result = _apply(own, [first, second]).to_dict()
    assert result[5] == Observation(YEAR - 1, 2.0, 2, 1)  # fewer relays
    assert result[6] == Observation(YEAR, 3.0, 0, 1)  # full tie: first partner


observation_strategy = st.tuples(
    st.integers(-5, 20), st.floats(0, 1e6, width=32), st.integers(0, 500), st.integers(0, 5)
).map(lambda t: Observation(year=t[0], food_kcal=t[1], population=t[2], hops=t[3]))
beliefs_strategy = st.dictionaries(st.integers(0, N_CELLS - 1), observation_strategy, max_size=40)


def _better(new: Observation, old: Observation | None) -> bool:
    return old is None or (new.year, -new.hops) > (old.year, -old.hops)


@settings(max_examples=200, deadline=None)
@given(own=beliefs_strategy, senders=st.lists(beliefs_strategy, min_size=1, max_size=5))
def test_vectorized_receipt_matches_a_one_by_one_reference(
    own: dict[int, Observation], senders: list[dict[int, Observation]]
) -> None:
    expected = dict(own)
    received: dict[int, Observation] = {}
    for sender in senders:
        for cell, obs in sender.items():
            relayed = Observation(obs.year, obs.food_kcal, obs.population, obs.hops + 1)
            if _better(relayed, received.get(cell)):
                received[cell] = relayed
    for cell, obs in received.items():
        if _better(obs, own.get(cell)):
            expected[cell] = obs
    got = _apply(BeliefMap.from_observations(N_CELLS, own), [_reports(s) for s in senders])
    assert got.to_dict() == expected


def test_recent_residence_is_bounded_by_the_memory_horizon() -> None:
    unit = _unit(BeliefMap.empty(N_CELLS))
    for year in range(100):
        unit.note_residence(year % 50, year, memory_years=10)
    assert len(unit.recent_residence) <= 11
    assert min(unit.recent_residence.values()) >= 100 - 1 - 11


def test_candidate_encounters_follow_the_nested_loop_order() -> None:
    from madexplorer.config.loader import Scenario
    from madexplorer.experiments.benchmark import synthetic_simulator
    from madexplorer.mobility.exploration import candidate_encounters
    from tests.conftest import ROOT, mvp2_scenario_dict

    scenario = Scenario.from_dict(mvp2_scenario_dict(n_years=1), base_dir=ROOT)
    sim = synthetic_simulator(scenario, n_units=300)  # dense: many co-resident groups
    units = list(sim.state.units.values())
    by_cell = sim.state.units_by_cell()
    index = {u.id: k for k, u in enumerate(units)}
    expected = [
        (k, index[other.id])
        for k, unit in enumerate(units)
        for cell in sim.world.cells_within(unit.cell, 1)
        for other in by_cell.get(cell, [])
        if other is not unit and other.species_id == unit.species_id
    ]
    receiver, partner = candidate_encounters(units, sim.static.neighborhood_table(1))
    assert list(zip(receiver.tolist(), partner.tolist(), strict=True)) == expected
    assert len(expected) > 500
