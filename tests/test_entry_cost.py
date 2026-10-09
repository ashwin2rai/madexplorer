"""MVP 3 Stage 5C: entry costs and participation continuity. NOT ACTIVE.

``madexplorer.population.entry_cost`` asks whether a one-time cost of beginning cultivation
explains which part of a unit cultivates (initiation) and why the same part continues
(continuity). No simulator path calls it.
"""

import importlib
import importlib.util
import sys
from collections.abc import Sequence
from typing import Any

import numpy as np
import pytest

from madexplorer.core.governance import RULES
from madexplorer.core.types import FloatArray
from madexplorer.population.entry_cost import (
    NEVER,
    Allocation,
    Components,
    Memory,
    advance_history,
    allocate,
    entry_factor,
    retain_incumbents,
    split_participation,
    spread_allocation,
    turnover,
)
from madexplorer.population.practice_concentration import (
    component_practice,
    learn_components,
    min_participating_share,
)
from tests.conftest import ROOT

C, D, M = 36_500.0, 2_000.0, 0.9  # capacity, clearing debt, max cultivation share
L = C / (5.0 * 365.0)  # labor-equivalent people
B = M * (C - D)  # cultivation budget of the whole unit
W1 = Memory("window", 1)


def _alloc(
    shares: Sequence[float] | FloatArray,
    factors: Sequence[float] | FloatArray,
    p: float,
    e: float = 50.0,
    rank: FloatArray | None = None,
) -> Allocation:
    return allocate(np.array(shares), np.array(factors), p, C, D, M, e, L, rank)


# ---------------------------------------------------------------- memory


def test_window_memory_expires_after_its_years() -> None:
    since = np.array([1.0, 2.0, 10.0, 11.0, NEVER])
    assert entry_factor(since, Memory("window", 1)).tolist() == [0, 1, 1, 1, 1]  # immediate
    assert entry_factor(since, Memory("window", 10)).tolist() == [0, 0, 0, 1, 1]  # finite


def test_decaying_memory_halves_the_advantage_per_half_life() -> None:
    since = np.array([1.0, 11.0, 21.0, NEVER])
    f = entry_factor(since, Memory("decay", 10))
    assert f[0] == 0.0 and f[3] == 1.0
    assert f[1] == pytest.approx(0.5) and f[2] == pytest.approx(0.75)
    assert np.all(np.diff(entry_factor(np.arange(1.0, 60.0), Memory("decay", 10))) > 0)


def test_memory_rejects_meaningless_inputs() -> None:
    with pytest.raises(ValueError):
        Memory("forever", 1)
    with pytest.raises(ValueError):
        Memory("window", 0)
    with pytest.raises(ValueError):
        entry_factor(np.array([0.0]), W1)  # since counts from 1


# ---------------------------------------------------------------- initiation


def test_homogeneous_first_entry_is_the_overhead_corner() -> None:
    """No history: every share pays e, entry labor e L f rises with f, so the minimum is the
    smallest feasible share, which is the §U overhead corner with o = e."""
    p = 0.35 * (C - D)
    for e in (1.0, 10.0, 50.0, 200.0):
        a = _alloc([1.0], [1.0], p, e)
        f_min = min_participating_share(p, C, D, M, e, L)
        assert a.feasible and a.participating == pytest.approx(f_min)
        assert a.entrants == pytest.approx(f_min) and a.free == 0.0
        assert a.entry_hours == pytest.approx(e * L * f_min)
        # every larger share costs strictly more entry labor
        assert e * L * min(1.0, f_min + 0.1) > a.entry_hours


def test_exact_initial_symmetry_gives_a_proportional_exposure_split() -> None:
    """Identical components (no history, equal competence): one tie group, taken in
    proportion. Entry cost decides how many enter, never which component."""
    a = _alloc([0.2, 0.5, 0.3], [1.0, 1.0, 1.0], 0.35 * (C - D))
    assert np.allclose(a.take / np.array([0.2, 0.5, 0.3]), a.participating)


def test_competence_alone_cannot_select_from_a_homogeneous_tie() -> None:
    k = np.array([1.5, 1.5, 1.5])
    a = _alloc([0.2, 0.5, 0.3], [1.0] * 3, 0.35 * (C - D), rank=-k)
    assert np.allclose(a.take / np.array([0.2, 0.5, 0.3]), a.participating)


def test_zero_entry_cost_is_indifferent_not_concentrating() -> None:
    """e = 0 with no history: nothing distinguishes any feasible share. The allocation still
    reports the smallest one, so a policy that concentrates at e = 0 is a tie rule."""
    p = 0.35 * (C - D)
    a = _alloc([1.0], [1.0], p, e=0.0)
    assert a.entry_hours == 0.0
    assert a.participating == pytest.approx(p / B)
    everyone = spread_allocation(np.ones(1), np.ones(1), p, C, D, M, 0.0, L, everyone=True)
    assert everyone.entry_hours == 0.0 and everyone.participating == 1.0


# ---------------------------------------------------------------- continuity


def test_incumbents_are_used_before_entrants() -> None:
    """Equal competence, different histories: last year's participants cost nothing."""
    p = 0.2 * B
    a = _alloc([0.4, 0.6], [0.0, 1.0], p)
    assert a.take[1] == 0.0 and a.take[0] == pytest.approx(0.2)
    assert a.entrants == 0.0 and a.entry_hours == 0.0


def test_excess_incumbents_leave_an_indifference_interval() -> None:
    """More incumbents than needed: any share between the need and all incumbents costs
    nothing. The minimal and the status-quo (retain) policies are the interval's ends."""
    a = _alloc([0.8, 0.2], [0.0, 1.0], 0.3 * B)
    assert a.participating == pytest.approx(0.3) and a.free == pytest.approx(0.5)
    kept = retain_incumbents(a, np.array([0.8, 0.2]), np.array([0.0, 1.0]))
    assert kept.tolist() == [0.8, 0.0]


def test_equal_cost_incumbents_shrink_in_proportion() -> None:
    a = _alloc([0.3, 0.1, 0.6], [0.0, 0.0, 1.0], 0.2 * B)
    assert a.take[2] == 0.0
    assert a.take[0] / 0.3 == pytest.approx(a.take[1] / 0.1)


def test_insufficient_incumbents_add_minimal_entrants() -> None:
    """All incumbents work; entrants cover the rest net of their own entry labor."""
    h, p, e = 0.2, 0.6 * B, 50.0
    a = _alloc([h, 1 - h], [0.0, 1.0], p, e)
    n = (p - h * B) / (B - e * L)
    assert a.take[0] == pytest.approx(h) and a.take[1] == pytest.approx(n)
    assert a.entrants == pytest.approx(n) and a.entry_hours == pytest.approx(e * L * n)
    # productive hours are covered exactly, entry labor on top (no free setup labor)
    assert a.participating * B - a.entry_hours == pytest.approx(p)


def test_cheaper_former_participants_enter_first() -> None:
    since = np.array([1.0, 3.0, NEVER])
    phi = entry_factor(since, Memory("decay", 10))
    a = _alloc([0.1, 0.2, 0.7], phi, 0.4 * B)
    assert a.take[0] == pytest.approx(0.1) and a.take[1] == pytest.approx(0.2)
    assert 0.0 < a.take[2] < 0.7


def test_infeasible_entry_is_reported_never_absorbed() -> None:
    """Entry labor that the budget cannot carry is reported as a shortfall: productive
    hours are never reduced and no hours are invented."""
    p, e = 0.85 * B, 1_500.0
    a = _alloc([0.1, 0.9], [0.0, 1.0], p, e)
    assert not a.feasible and a.participating == 1.0 and a.shortfall_hours > 0
    supply = 0.1 * B + 0.9 * (B - e * L)
    assert a.shortfall_hours == pytest.approx(p - supply)
    # an entry cost above the per-share budget adds no capacity at all
    assert not _alloc([1.0], [1.0], 0.1 * B, e=B / L + 1).feasible


def test_entry_labor_is_conserved() -> None:
    rng = np.random.default_rng(3)
    for _ in range(50):
        s = rng.dirichlet(np.ones(5))
        phi = rng.choice(np.array([0.0, 0.3, 1.0]), 5).astype(np.float64)
        p = rng.uniform(0.05, 0.8) * B
        a = _alloc(s, phi, p, 20.0)
        if a.feasible:
            assert float((a.take * (B - 20.0 * L * phi)).sum()) == pytest.approx(p)
            assert a.entry_hours == pytest.approx(20.0 * L * float((a.take * phi).sum()))
        assert np.all(a.take >= 0) and np.all(a.take <= s + 1e-15)


def test_rotation_redraws_participants_in_proportion() -> None:
    """Rotation ignores history: every component contributes the same fraction, so
    incumbents are replaced by entrants who pay e."""
    s, phi, p = np.array([0.3, 0.7]), np.array([0.0, 1.0]), 0.3 * B
    rot = spread_allocation(s, phi, p, C, D, M, 50.0, L, everyone=False)
    assert rot.take[0] / 0.3 == pytest.approx(rot.take[1] / 0.7)
    cont = _alloc(s, phi, p)
    assert cont.entry_hours == 0.0 < rot.entry_hours


def test_no_cultivation_takes_nobody() -> None:
    a = _alloc([0.5, 0.5], [0.0, 1.0], 0.0)
    assert a.participating == 0.0 and a.entrants == 0.0 and a.feasible


# ---------------------------------------------------------------- neutrality


def test_allocation_is_order_and_identity_neutral() -> None:
    s = np.array([0.15, 0.25, 0.35, 0.25])
    phi = np.array([1.0, 0.0, 1.0, 0.5])
    a = _alloc(s, phi, 0.5 * B)
    for perm in ([3, 2, 1, 0], [1, 3, 0, 2]):
        b = _alloc(s[perm], phi[perm], 0.5 * B)
        assert np.allclose(b.take, a.take[perm])


def test_allocation_does_not_mutate_inputs() -> None:
    s, phi = np.array([0.4, 0.6]), np.array([0.0, 1.0])
    s0, phi0 = s.copy(), phi.copy()
    allocate(s, phi, 0.5 * B, C, D, M, 50.0, L)
    spread_allocation(s, phi, 0.5 * B, C, D, M, 50.0, L, everyone=False)
    assert s.tolist() == s0.tolist() and phi.tolist() == phi0.tolist()


# ---------------------------------------------------------------- representation


def _components() -> Components:
    return Components(
        np.array([0.5, 0.3, 0.2]),
        np.array([2.0, 1.0, 0.5]),
        np.array([1.0, 4.0, NEVER]),
        np.zeros(3, bool),
    )


def test_split_conserves_shares_competence_and_histories() -> None:
    c = _components()
    out = split_participation(c, np.array([0.5, 0.1, 0.0]))
    assert out.share.sum() == pytest.approx(1.0)
    assert float((out.share * out.competence).sum()) == pytest.approx(
        float((c.share * c.competence).sum())
    )
    assert float(out.share[out.participating].sum()) == pytest.approx(0.6)
    assert out.share.size == 4  # one partial split; wholes and zeros stay single
    assert sorted(out.since.tolist()) == sorted([1.0, 4.0, NEVER, 4.0])
    assert c.share.tolist() == [0.5, 0.3, 0.2]  # no mutation


def test_history_advances_and_marks_participants() -> None:
    c = split_participation(_components(), np.array([0.5, 0.0, 0.0]))
    nxt = advance_history(c)
    assert nxt.since.tolist() == [1.0, 5.0, NEVER]


def test_turnover_moves_new_workers_out_of_the_history() -> None:
    c = _components()
    out = turnover(c, 0.04)
    assert out.share.sum() == pytest.approx(1.0)
    assert float((out.share * out.competence).sum()) == pytest.approx(
        float((c.share * c.competence).sum())
    )
    fresh = out.share[3:]
    assert fresh.tolist() == pytest.approx([0.02, 0.012])  # only components with a history
    assert np.isinf(out.since[3:]).all()
    assert turnover(c, 0.0) is c
    with pytest.raises(ValueError):
        turnover(c, 1.5)


# ---------------------------------------------------------------- competence


def test_equal_participation_reproduces_unit_learning() -> None:
    """e = 0 and proportional participation: every component learns exactly as the unit."""
    k = np.array([1.2, 1.2, 1.2])
    practice = component_practice(
        0.4, 0.35, 0.3, np.ones(3, bool), np.full(3, 1 / 3), 1.0, 1.0, 0.15
    )
    out = learn_components(k, practice, 40 * 0.4, 1.0, 0.35, 2.0, 0.02, 1.0)
    unit = learn_components(np.array([1.2]), np.array([0.4]), 40 * 0.4, 1.0, 0.35, 2.0, 0.02, 1.0)
    assert out.tolist() == [unit[0]] * 3


def test_different_histories_diverge_only_through_practice() -> None:
    """Equal competence, different histories: incumbents practice, so they learn more; the
    difference comes from practice, not from the history itself."""
    k = np.array([1.0, 1.0])
    part = np.array([True, False])
    practice = component_practice(0.36, 0.3, 0.4, part, np.array([0.4, 0.6]), 0.4, 1.0, 0.15)
    out = learn_components(k, practice, 40 * 0.36, 1.0, 0.35, 2.0, 0.02, 1.0)
    assert out[0] > out[1]


def test_competence_without_entry_cost_ranks_only_with_m3() -> None:
    """Fusion-born competence difference, no history: M2 (entry cost) ties, M3 selects."""
    s, phi, k = np.array([0.5, 0.5]), np.ones(2), np.array([3.0, 1.0])
    m2 = _alloc(s, phi, 0.3 * B)
    assert m2.take[0] == pytest.approx(m2.take[1])
    m3 = _alloc(s, phi, 0.3 * B, rank=-k)
    assert m3.take[1] == 0.0 and m3.take[0] > 0


def test_competence_decays_without_practice() -> None:
    k = np.array([4.0, 1.0])
    for _ in range(35):
        k = learn_components(k, np.zeros(2), 0.0, 1.0, 0.35, 2.0, 0.02, 1.0)
    assert k[0] - k[1] == pytest.approx(3.0 * 0.98**35)


def test_module_is_not_registered_as_a_model_rule() -> None:
    assert not any("entry" in name for name in RULES)


def test_probe_observer_leaves_authoritative_state_unchanged() -> None:
    """The Stage 5C observer with its shadows reads the simulator and changes nothing: the
    physical digest (events, RNG states, unit state) equals a plain run's."""
    probes = ROOT / "scripts" / "probes"
    sys.path.insert(0, str(probes))
    try:
        spec = importlib.util.spec_from_file_location(
            "entry_cost_probe", probes / "entry_cost_counterfactual.py"
        )
        assert spec is not None and spec.loader is not None
        probe: Any = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        common: Any = importlib.import_module("_common")
    finally:
        sys.path.remove(str(probes))
    scenario = common.scenario_for("pressure+cult", 0, 0.0, 90)
    model = probe.knowledge_model(scenario)
    half = float(model.half_efficiency[model.index["agriculture"]])
    shadows = [
        probe.Shadow(p, half)
        for p in (probe.Policy("M2", ledger=True), probe.Policy("M3"), probe.Policy("M1"))
    ]
    observed, _ = common.drive(scenario, probe.Observer(shadows, model))
    plain, _ = common.drive(scenario, None)
    assert common.physical_digest(observed) == common.physical_digest(plain)
    assert all(s.stats.neutral_max < 1e-12 for s in shadows)
    assert any(s.stats.farming for s in shadows)
