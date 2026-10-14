"""MVP 3 Stage 5G: statistical population representation benchmark.

METHODOLOGICAL BENCHMARK — NOT A SOCIOLOGICAL MECHANISM. The event is the production's
representative fission (independent departure with probability ``f``); the attributes and
the capability threshold are hypothetical. Nothing here touches the simulator.
"""

import importlib.util
import sys
from typing import Any

import numpy as np
import pytest

from tests.conftest import ROOT


def _bench() -> Any:
    path = ROOT / "scripts/probes/representation_benchmark.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("representation_benchmark", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = _bench()


def test_configurations_share_marginals_but_not_joint_counts() -> None:
    aligned = B.compartments(B.population(40, 10, 10, 10))
    independent = B.compartments(B.population(40, 10, 10, 2))
    disjoint = B.compartments(B.population(40, 10, 10, 0))
    for counts in (aligned, independent, disjoint):
        assert B.marginals(counts) == (40, 0.25, 0.25)
    assert [int(c[1, 1]) for c in (aligned, independent, disjoint)] == [10, 2, 0]
    with pytest.raises(ValueError):
        B.population(10, 6, 6, 1)


def test_compartment_fission_conserves_integers_and_matches_the_exact_law() -> None:
    counts = B.compartments(B.population(40, 10, 10, 10))
    exact = B.exact_capable(counts, 0.4, 2)
    assert exact["mean"] == pytest.approx(4.0) and exact["var"] == pytest.approx(2.4)
    rng = np.random.default_rng(0)
    sampled = B.compartment_capable(counts, 0.4, 2, 50_000, rng)  # asserts conservation
    individual = B.individual_capable(B.population(40, 10, 10, 10), 0.4, 2, 50_000, rng)
    for key in ("mean", "var", "p_daughter", "p_both"):
        assert sampled[key] == pytest.approx(exact[key], abs=0.03)
        assert individual[key] == pytest.approx(exact[key], abs=0.03)


def test_expected_value_mixture_keeps_the_mean_but_not_the_split_variance() -> None:
    counts = B.compartments(B.population(40, 10, 10, 10))
    mix = B.mixture_capable(counts, 0.4, 2, 50_000, np.random.default_rng(1))
    exact = B.exact_capable(counts, 0.4, 2)
    assert mix["mean"] == pytest.approx(exact["mean"], abs=0.02)
    assert mix["var"] < 0.5 * exact["var"]
    assert mix["p_both"] > exact["p_both"] + 0.03  # the threshold tail is overstated


def test_independent_marginals_cannot_distinguish_the_configurations() -> None:
    rng = np.random.default_rng(2)
    means = {}
    for both in (10, 2, 0):
        counts = B.compartments(B.population(40, 10, 10, both))
        means[both] = B.marginal_capable(counts, 0.4, 2, 20_000, rng)["mean"]
    assert max(means.values()) - min(means.values()) < 0.05  # same answer for 4, 0.8 and 0
    u1 = B.compartments(B.population(20, 10, 0, 0))
    u2 = B.compartments(B.population(20, 0, 10, 0))
    assert int(B.fuse_counts(u1, u2)[1, 1]) == 0
    assert B.marginal_fusion_capable(u1, u2) == pytest.approx(2.5)  # spurious capability


def test_second_moments_recover_pairwise_overlap_but_not_three_way() -> None:
    counts = B.compartments(B.population(40, 10, 10, 2))
    assert B.moment_capable(counts, 0.4, 2)["mean"] == pytest.approx(0.8)
    p0, p1 = B.triple_populations(5)
    m0, s0 = B.moments(p0)
    m1, s1 = B.moments(p1)
    assert np.array_equal(m0, m1) and np.array_equal(s0, s1)
    assert int(p0.all(axis=1).sum()) == 0 and int(p1.all(axis=1).sum()) == 5


def test_partition_respecting_merge_is_exact_for_the_capable_count() -> None:
    g = np.random.default_rng(7)
    exp_ = g.gamma(3.0, 3.0, 30)
    acc = (g.random(30) < 0.5).astype(float)
    people = B.Mixture(np.ones(30), exp_, acc)
    truth = B.capable(people, 10.0)
    cells = len({(bool(e >= 10.0), a) for e, a in zip(exp_.tolist(), acc.tolist(), strict=True)})
    merged = B.coalesce(people, cells, B.partition_distance(10.0, 10.0))
    assert merged.weight.sum() == pytest.approx(30.0)
    assert B.capable(merged, 10.0) == pytest.approx(truth)
    blind = B.coalesce(people, 2, B.equal_weight_distance(10.0))
    assert blind.weight.sum() == pytest.approx(30.0)
