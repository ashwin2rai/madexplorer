"""MVP 3 Stage 4E: counterfactual control over new cultivated capacity. NOT ACTIVE.

``madexplorer.population.field_control`` compares who controls newly cleared fields: H1
population share (the authoritative ``field_claim_accretion``), H2 clearing contribution
(collapses to H1: clearing labor comes from one unit-level pool) and H3 continuity of
existing control with weight ``p = field_claim_continuity``. No simulator path calls it.
"""

import ast
from pathlib import Path

import numpy as np
import pytest

from madexplorer.config.schema import StrataConfig
from madexplorer.core.governance import RULES
from madexplorer.population.field_control import (
    continuity_new_capacity_shares,
    control_deviation,
    counterfactual_field_claim_after_expansion,
    field_claim_step,
    field_claims_after_expansion,
    retention_factor,
)
from madexplorer.population.strata_accounting import field_claims_after_change
from tests.conftest import ROOT

CONTINUITIES = (0.0, 0.25, 0.5, 0.75, 1.0)
SHARE = np.array([0.8, 0.2])
CLAIM = np.array([0.5, 0.5])


def _random_partition(rng: np.random.Generator, n: int) -> np.ndarray:
    values = rng.random(n) + 1e-3
    return values / values.sum()


def test_zero_continuity_is_the_authoritative_rule_bit_for_bit() -> None:
    rng = np.random.default_rng(4)
    for _ in range(300):
        n = int(rng.integers(1, 17))
        share, claim = _random_partition(rng, n), _random_partition(rng, n)
        f0 = float(rng.choice([0.0, rng.random() * 50]))
        f1 = float(rng.choice([0.0, f0, f0 * rng.random(), f0 + rng.random() * 80]))
        expected = field_claims_after_change(share, claim, f0, f1)
        got = counterfactual_field_claim_after_expansion(share, claim, f0, f1, 0.0)
        assert np.array_equal(got, expected)


def test_zero_continuity_matches_on_padded_table_rows() -> None:
    rng = np.random.default_rng(5)
    rows, width = 40, 8
    share, claim = np.zeros((rows, width)), np.zeros((rows, width))
    for r in range(rows):
        k = int(rng.integers(1, width + 1))
        share[r, :k], claim[r, :k] = _random_partition(rng, k), _random_partition(rng, k)
    before = rng.random(rows) * 10
    after = before * rng.choice([0.0, 0.5, 1.0, 1.3, 4.0], rows)
    expected = field_claims_after_change(share, claim, before, after)
    got = counterfactual_field_claim_after_expansion(share, claim, before, after, 0.0)
    assert np.array_equal(got, expected)
    assert (got[share == 0] == 0).all()  # padding stays zero


def test_full_continuity_preserves_claims_under_pure_expansion() -> None:
    rng = np.random.default_rng(6)
    for _ in range(300):
        n = int(rng.integers(1, 17))
        share, claim = _random_partition(rng, n), _random_partition(rng, n)
        f0 = float(rng.random() * 50 + 1e-3)
        f1 = f0 * float(1 + rng.random() * 20)
        got = counterfactual_field_claim_after_expansion(share, claim, f0, f1, 1.0)
        np.testing.assert_allclose(got, claim, rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("p", CONTINUITIES)
def test_neutral_control_stays_neutral_for_every_continuity(p: float) -> None:
    rng = np.random.default_rng(7)
    share = _random_partition(rng, 6)
    claim = share.copy()
    fields = 1.0
    for _ in range(500):
        grown = fields * float(1 + rng.random())
        claim = counterfactual_field_claim_after_expansion(share, claim, fields, grown, p)
        fields = grown
    np.testing.assert_allclose(claim, share, rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("p", CONTINUITIES)
def test_no_expansion_has_no_effect(p: float) -> None:
    for f1 in (10.0, 7.0, 0.0):  # unchanged, shrink, to zero (reset applied separately)
        got = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 10.0, f1, p)
        assert np.array_equal(got, CLAIM)


@pytest.mark.parametrize("p", CONTINUITIES)
@pytest.mark.parametrize("growth", (1.01, 1.5, 2.0, 10.0, 1000.0))
def test_one_expansion_scales_every_deviation_by_the_retention_factor(
    p: float, growth: float
) -> None:
    got = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 10.0, 10.0 * growth, p)
    rho = retention_factor(10.0, 10.0 * growth, p)
    assert rho == pytest.approx(p + (1 - p) / growth)
    np.testing.assert_allclose(got - SHARE, rho * (CLAIM - SHARE), rtol=1e-12, atol=1e-15)
    assert control_deviation(SHARE, got) == pytest.approx(rho * control_deviation(SHARE, CLAIM))
    assert abs(got.sum() - 1.0) <= 1e-15 and (got >= 0).all()


def test_large_expansion_dilutes_at_zero_and_preserves_at_full_continuity() -> None:
    diluted = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 1.0, 1000.0, 0.0)
    kept = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 1.0, 1000.0, 1.0)
    assert control_deviation(SHARE, diluted) == pytest.approx(0.3 / 1000)
    np.testing.assert_allclose(kept, CLAIM, rtol=1e-12)


@pytest.mark.parametrize("p", (0.0, 0.25, 0.5, 0.75))
def test_repeated_expansion_follows_the_analytical_persistence(p: float) -> None:
    claim, fields, predicted = CLAIM.copy(), 1.0, 1.0
    for _ in range(200):
        grown = fields * 1.02
        predicted *= retention_factor(fields, grown, p)
        claim = counterfactual_field_claim_after_expansion(SHARE, claim, fields, grown, p)
        fields = grown
    assert control_deviation(SHARE, claim) == pytest.approx(0.3 * predicted, rel=1e-10)
    # Small steps: deviation ~ (F / F0)^-(1 - p); discrete steps retain at least that.
    continuous = fields ** -(1.0 - p)
    assert predicted >= continuous
    assert predicted == pytest.approx(continuous, rel=0.05)


def test_expansion_then_shrinkage_adds_no_asymmetry() -> None:
    for p in CONTINUITIES:
        grown = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 10.0, 20.0, p)
        shrunk = counterfactual_field_claim_after_expansion(SHARE, grown, 20.0, 10.0, p)
        assert np.array_equal(shrunk, grown)  # loss is proportional: fractions kept
        regrown = counterfactual_field_claim_after_expansion(SHARE, shrunk, 10.0, 20.0, p)
        rho = retention_factor(10.0, 20.0, p)
        np.testing.assert_allclose(regrown - SHARE, rho * rho * (CLAIM - SHARE), atol=1e-15)


@pytest.mark.parametrize("p", CONTINUITIES)
def test_zero_field_reset_and_regrowth_do_not_resurrect_control(p: float) -> None:
    claim = field_claim_step(SHARE, CLAIM, 10.0, 0.0, p)
    assert np.array_equal(claim, SHARE)
    regrown = field_claim_step(SHARE, claim, 0.0, 5.0, p)
    np.testing.assert_allclose(regrown, SHARE, atol=1e-15)
    # Even claims left stale on an empty stock cannot be continued: nothing is held.
    stale = counterfactual_field_claim_after_expansion(SHARE, CLAIM, 0.0, 5.0, p)
    np.testing.assert_allclose(stale, SHARE, atol=1e-15)
    assert np.array_equal(continuity_new_capacity_shares(SHARE, CLAIM, 0.0, p), SHARE)


@pytest.mark.parametrize("p", CONTINUITIES)
def test_bounded_convex_and_normalized_over_long_random_trajectories(p: float) -> None:
    rng = np.random.default_rng(8)
    share, start = _random_partition(rng, 12), _random_partition(rng, 12)
    lo, hi = np.minimum(start, share), np.maximum(start, share)
    claim, fields, deviation = start.copy(), 5.0, control_deviation(share, start)
    for _ in range(5000):
        change = float(rng.choice([0.7, 1.0, 1.001, 1.05, 1.3, 3.0]))
        new = fields * change
        claim = counterfactual_field_claim_after_expansion(share, claim, fields, new, p)
        fields = new if new < 1e6 else 5.0  # keep magnitudes bounded (shrinkage elsewhere)
        assert (claim >= 0).all() and abs(claim.sum() - 1.0) <= 1e-12
        assert (claim >= lo - 1e-12).all() and (claim <= hi + 1e-12).all()  # convex envelope
        now = control_deviation(share, claim)
        assert now <= deviation * (1 + 1e-12) + 1e-15  # never amplified
        deviation = now
    if p == 1.0:
        np.testing.assert_allclose(claim, start, rtol=1e-9)  # no drift over 5000 steps


def test_order_and_id_neutrality_and_no_mutation() -> None:
    rng = np.random.default_rng(9)
    share, claim = _random_partition(rng, 7), _random_partition(rng, 7)
    share_in, claim_in = share.copy(), claim.copy()
    perm = rng.permutation(7)
    for p in CONTINUITIES:
        got = counterfactual_field_claim_after_expansion(share, claim, 3.0, 8.0, p)
        permuted = counterfactual_field_claim_after_expansion(share[perm], claim[perm], 3.0, 8.0, p)
        np.testing.assert_allclose(permuted, got[perm], rtol=1e-14, atol=1e-16)
    assert np.array_equal(share, share_in) and np.array_equal(claim, claim_in)


def test_clearing_contribution_allocation_collapses_to_population_allocation() -> None:
    """H2: with one unit-level labor pool, each stratum contributes share * clearing hours."""
    rng = np.random.default_rng(10)
    for _ in range(100):
        share, claim = _random_partition(rng, 5), _random_partition(rng, 5)
        clearing_hours = float(rng.random() * 1e5)
        contribution = share * clearing_hours
        h2 = field_claims_after_expansion(share, claim, 4.0, 9.0, contribution / contribution.sum())
        h1 = field_claims_after_change(share, claim, 4.0, 9.0)
        np.testing.assert_allclose(h2, h1, rtol=1e-14, atol=1e-16)


def test_clearing_labor_has_no_stratum_input() -> None:
    """The clearing and labor-capacity code reads unit columns only (no strata)."""
    source = (ROOT / "src/madexplorer/economy/agriculture.py").read_text()
    kernel = (ROOT / "src/madexplorer/economy/agriculture_kernel.py").read_text()
    for text in (source, kernel):
        names = {n.id for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Attribute)}
        assert not names & {"strata", "field_claim", "store_claim", "StrataTable"}


def test_continuity_is_not_active() -> None:
    with pytest.raises(ValueError):
        continuity_new_capacity_shares(SHARE, CLAIM, 1.0, 1.5)
    assert "field_claim_continuity" not in StrataConfig.model_fields
    assert not any("continuity" in name for name in RULES)
    src = ROOT / "src/madexplorer"
    users = [
        p
        for p in src.rglob("*.py")
        if "field_control" in p.read_text() and p.name != "field_control.py"
    ]
    assert users == [], f"field_control must stay counterfactual: {users}"
    assert Path(src / "population/field_control.py").exists()
