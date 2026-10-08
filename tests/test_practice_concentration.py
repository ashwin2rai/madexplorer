"""MVP 3 Stage 5B: participation overhead and practice concentration. NOT ACTIVE.

``madexplorer.population.practice_concentration`` asks whether a per-participant overhead
gives a reason to concentrate a finite amount of cultivation on part of a unit, and what
concentrated practice would do to competence under the authoritative learning rule. No
simulator path calls it.
"""

import numpy as np
import pytest

from madexplorer.config.schema import StrataConfig
from madexplorer.core.governance import RULES
from madexplorer.knowledge.learning import learn
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.population.practice_concentration import (
    component_practice,
    diagnostic_share,
    efficiency,
    efficiency_slope,
    learn_components,
    min_participating_share,
    optimal_participating_share,
    participation_labor,
)
from tests.conftest import ROOT

C, D, M = 36_500.0, 2_000.0, 0.9  # capacity, clearing debt, max cultivation share
L = C / (5.0 * 365.0)  # labor-equivalent people


def test_minimum_share_follows_the_post_debt_cultivation_budget() -> None:
    assert min_participating_share(0.0, C, D, M) == 0.0  # no cultivation, no participants
    p = 6_000.0
    assert min_participating_share(p, C, D, M) == pytest.approx(p / (M * (C - D)))
    assert min_participating_share(M * (C - D), C, D, M) == 1.0  # everyone needed
    assert min_participating_share(M * (C - D) + 1, C, D, M) == 1.0  # labor-capped
    assert min_participating_share(10.0, C, C + 5, M) == 1.0  # nothing left after debt


def test_overhead_raises_the_minimum_share_and_is_paid_per_participant() -> None:
    p = 6_000.0
    base = min_participating_share(p, C, D, M)
    with_overhead = min_participating_share(p, C, D, M, overhead_hours=50.0, labor_equivalents=L)
    assert with_overhead == pytest.approx(p / (M * (C - D) - 50.0 * L))
    assert with_overhead > base
    f = with_overhead
    assert participation_labor(f, p, 50.0, L) == pytest.approx(p + 50.0 * f * L)
    # Labor conservation: participants' cultivation budget is exactly used at f_min.
    assert participation_labor(f, p, 50.0, L) == pytest.approx(M * f * (C - D))


def test_zero_overhead_is_indifferent_between_all_feasible_shares() -> None:
    opt = optimal_participating_share(6_000.0, C, D, M, 0.0, L)
    assert opt.indifferent and not opt.corner and opt.share is None
    costs = {participation_labor(f, 6_000.0, 0.0, L) for f in np.linspace(opt.minimum, 1, 11)}
    assert costs == {6_000.0}


@pytest.mark.parametrize("overhead", [1e-9, 0.01, 1.0, 50.0, 300.0])
def test_any_positive_overhead_selects_the_corner(overhead: float) -> None:
    """Documented corner solution: cost is linear and increasing in f for every o > 0, so
    the optimum jumps from indifference straight to the minimum feasible share."""
    p = 6_000.0
    opt = optimal_participating_share(p, C, D, M, overhead, L)
    assert opt.corner and opt.share == opt.minimum
    grid = np.linspace(opt.minimum, 1.0, 101)
    costs = [participation_labor(f, p, overhead, L) for f in grid]
    assert int(np.argmin(costs)) == 0 and all(np.diff(costs) > 0)


def test_full_participation_and_no_cultivation_are_not_concentrated() -> None:
    full = optimal_participating_share(M * (C - D), C, D, M, 10.0, L)
    assert full.minimum == 1.0
    none = optimal_participating_share(0.0, C, D, M, 10.0, L)
    assert none.minimum == 0.0 and none.indifferent


def test_diagnostic_share_interpolates_between_spread_and_minimum() -> None:
    assert diagnostic_share(0.0, 0.3) == 1.0
    assert diagnostic_share(1.0, 0.3) == pytest.approx(0.3)
    assert diagnostic_share(0.5, 0.3) == pytest.approx(0.65)
    with pytest.raises(ValueError):
        diagnostic_share(1.5, 0.3)


def _model() -> KnowledgeModel:
    from madexplorer.config.loader import Scenario

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    assert scenario.knowledge is not None
    return KnowledgeModel(scenario.knowledge)


def _agri(model: KnowledgeModel) -> tuple[int, float, float, float, float]:
    i = model.index["agriculture"]
    return (
        i,
        float(model.learning_rate[i]),
        float(model.practitioner_scale[i]),
        float(model.decay_rate[i]),
        float(model.half_efficiency[i]),
    )


def test_spread_practice_reproduces_the_authoritative_learning_rule_bit_for_bit() -> None:
    model = _model()
    i, lr, scale, decay, _ = _agri(model)
    rng = np.random.default_rng(1)
    k = model.initial_levels()
    for _ in range(200):
        practice = rng.random(len(model.domains))
        n = int(rng.integers(5, 200))
        expected = learn(k, practice, n, model, 1.0, 1.0)
        shares = np.array([0.5, 0.3, 0.2])
        components = component_practice(
            float(practice[i]), 0.4, 0.1, np.ones(3, bool), shares, 1.0, 1.0, 0.15
        )
        got = learn_components(
            np.full(3, k[i]), components, n * float(practice[i]), 1.0, lr, scale, decay, 1.0
        )
        assert (got == expected[i]).all()
        k = expected


def test_components_inherit_equal_competence_and_diverge_only_with_different_practice() -> None:
    model = _model()
    _, lr, scale, decay, _ = _agri(model)
    shares = np.array([0.4, 0.6])
    k = np.full(2, 3.0)
    unit_practice = 1.0 * 0.3 + 0.15 * 0.2
    same = component_practice(unit_practice, 0.3, 0.2, np.ones(2, bool), shares, 1.0, 1.0, 0.15)
    k_same = learn_components(k, same, 40 * unit_practice, 1.0, lr, scale, decay, 1.0)
    assert k_same[0] == k_same[1]
    part = np.array([True, False])
    diff = component_practice(unit_practice, 0.3, 0.2, part, shares, 0.4, 1.0, 0.15)
    assert diff[0] > unit_practice > diff[1]
    assert float((shares * diff).sum()) == pytest.approx(unit_practice)  # hours conserved
    k_diff = learn_components(k, diff, 40 * unit_practice, 1.0, lr, scale, decay, 1.0)
    assert k_diff[0] > k_diff[1]
    assert float((shares * k_diff).sum()) == pytest.approx(float(k_same[0]))  # mean unchanged


def test_competence_decays_without_practice_and_stays_nonnegative() -> None:
    model = _model()
    _, lr, scale, decay, _ = _agri(model)
    k = np.array([10.0, 2.0])
    for _ in range(100):
        k = learn_components(k, np.zeros(2), 0.0, 1.0, lr, scale, decay, 1.0)
    assert (k >= 0).all()
    assert k[0] / k[1] == pytest.approx(5.0)  # proportional decay: the gap halves with K
    assert k[0] == pytest.approx(10.0 * (1 - decay) ** 100)


def test_efficiency_slope_is_the_derivative_of_the_yield_factor() -> None:
    k, h, eps = np.array([0.1, 1.0, 5.0, 40.0]), 2.0, 1e-6
    numeric = (efficiency(k + eps, h) - efficiency(k - eps, h)) / (2 * eps)
    np.testing.assert_allclose(efficiency_slope(k, h), numeric, rtol=1e-6)


def test_order_neutrality_and_no_mutation() -> None:
    shares = np.array([0.2, 0.5, 0.3])
    part = np.array([True, False, True])
    shares_in, part_in = shares.copy(), part.copy()
    got = component_practice(0.4, 0.35, 0.2, part, shares, 0.5, 1.0, 0.15)
    perm = np.array([2, 0, 1])
    permuted = component_practice(0.4, 0.35, 0.2, part[perm], shares[perm], 0.5, 1.0, 0.15)
    np.testing.assert_allclose(permuted, got[perm], rtol=1e-14)
    assert np.array_equal(shares, shares_in) and np.array_equal(part, part_in)


def test_practice_concentration_is_not_active() -> None:
    assert not {"overhead", "concentration", "participation"} & set(StrataConfig.model_fields)
    assert not any("participation" in name or "concentration" in name for name in RULES)
    users = [
        p
        for p in (ROOT / "src/madexplorer").rglob("*.py")
        if "practice_concentration" in p.read_text() and p.name != "practice_concentration.py"
    ]
    assert users == []
