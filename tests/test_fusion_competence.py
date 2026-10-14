"""MVP 3 Stage 5F: fusion-born knowledge heterogeneity. NOT ACTIVE.

``madexplorer.population.fusion_competence`` keeps a shadow distribution of one domain's
knowledge after fusion instead of the authoritative population-weighted mean. No simulator
path calls it.
"""

import importlib
import importlib.util
import sys
from typing import Any

import numpy as np
import pytest

from madexplorer.core.governance import RULES
from madexplorer.population.fusion_competence import (
    coalesce,
    compact_exact,
    distance,
    efficiency,
    fuse,
    jensen_gap,
    learn,
    mean,
    pool,
    slope,
    summary,
    turnover_pool,
    variance,
)
from madexplorer.population.lifecycle import merge_units
from tests.conftest import ROOT

HALF, LAM = 2.0, 0.02


def one(k: float) -> tuple[np.ndarray, np.ndarray]:
    return np.ones(1), np.array([k])


def test_efficiency_and_slope_match_the_knowledge_model() -> None:
    from madexplorer.config.loader import Scenario
    from madexplorer.knowledge.system import KnowledgeModel, KnowledgeSystem

    scenario = Scenario.from_yaml(ROOT / "scenarios/mvp2_neolithic.yaml")
    assert isinstance(scenario.knowledge, KnowledgeSystem)
    model = KnowledgeModel(scenario.knowledge)
    i = model.index["agriculture"]
    assert model.half_efficiency[i] == HALF and model.decay_rate[i] == LAM
    for k in (0.0, 0.4, 2.0, 9.0):
        vector = np.zeros(len(model.domains))
        vector[i] = k
        assert efficiency(k, HALF) == model.efficiency(vector, "agriculture")
        h = 1e-6
        lo = max(k - h, 0.0)
        numeric = (efficiency(k + h, HALF) - efficiency(lo, HALF)) / (k + h - lo)
        assert slope(k, HALF) == pytest.approx(numeric, rel=1e-4)


def test_fuse_mean_is_the_authoritative_population_weighted_mean() -> None:
    w, k = fuse([(*one(0.4), 30), (*one(9.0), 10)])
    assert mean(w, k) == pytest.approx((0.4 * 30 + 9.0 * 10) / 40, rel=1e-15)
    assert w.tolist() == [0.75, 0.25] and k.tolist() == [0.4, 9.0]
    # heterogeneous sources concatenate, never two new groups only
    w2, k2 = fuse([(w, k, 40), (*one(3.0), 20)])
    assert k2.size == 3 and mean(w2, k2) == pytest.approx((mean(w, k) * 40 + 3.0 * 20) / 60)
    with pytest.raises(ValueError):
        fuse([(*one(1.0), 0)])


def test_fusion_is_input_order_invariant() -> None:
    a = fuse([(*one(1.0), 20), (*one(5.0), 10), (*one(9.0), 15)])
    b = fuse([(*one(9.0), 15), (*one(1.0), 20), (*one(5.0), 10)])
    sa, sb = summary(*compact_exact(*a), HALF), summary(*compact_exact(*b), HALF)
    for key in sa:
        assert sa[key] == pytest.approx(sb[key], abs=1e-15)


def test_common_learning_keeps_the_mean_and_shrinks_deviations_by_one_minus_decay() -> None:
    w, k = fuse([(*one(0.4), 20), (*one(9.0), 20)])
    authoritative = mean(w, k)
    for gain in (0.0, 0.18, 0.4, 0.0, 0.1):
        k2 = learn(k, LAM, gain)
        authoritative = authoritative + gain - LAM * authoritative  # learning.learn form
        assert mean(w, k2) == pytest.approx(authoritative, rel=1e-14)
        assert k2[1] - k2[0] == pytest.approx((1 - LAM) * (k[1] - k[0]), rel=1e-14)
        k = k2
    with pytest.raises(ValueError):
        learn(k, LAM, -1.0)


def test_homogeneous_shadow_reproduces_authoritative_learning_exactly() -> None:
    k_auth = 3.7
    w, k = one(k_auth)
    for gain in (0.2, 0.0, 0.05):
        k = learn(k, LAM, gain)
        k_auth = max(k_auth + gain - LAM * k_auth, 0.0)
        assert k[0] == pytest.approx(k_auth, rel=1e-15)
        assert summary(w, k, HALF)["jensen"] == 0.0


def test_turnover_pool_moves_levels_toward_the_mean_without_changing_it() -> None:
    w, k = np.array([0.25, 0.75]), np.array([1.0, 5.0])
    k2 = turnover_pool(w, k, 0.1)
    assert mean(w, k2) == pytest.approx(mean(w, k))
    assert k2[1] - k2[0] == pytest.approx(0.9 * 4.0)
    assert np.array_equal(turnover_pool(w, k, 0.0), k)
    with pytest.raises(ValueError):
        turnover_pool(w, k, 1.5)


def test_pool_and_exact_compaction() -> None:
    w, k = np.array([0.2, 0.3, 0.5]), np.array([2.0, 1.0, 2.0])
    wp, kp = pool(w, k)
    assert wp.tolist() == [1.0] and kp[0] == pytest.approx(mean(w, k))
    wc, kc = compact_exact(w, k)
    assert kc.tolist() == [1.0, 2.0] and wc.tolist() == pytest.approx([0.3, 0.7])
    # equal pre-fusion levels give a homogeneous unit
    assert compact_exact(*fuse([(*one(3.0), 5), (*one(3.0), 9)]))[1].size == 1


def test_jensen_gap_is_nonnegative_and_zero_only_without_dispersion() -> None:
    rng = np.random.default_rng(0)
    for _ in range(500):
        n = int(rng.integers(1, 6))
        w = rng.dirichlet(np.ones(n))
        k = rng.exponential(3.0, n)
        assert jensen_gap(w, k, HALF) >= -1e-15
    assert jensen_gap(np.array([0.5, 0.5]), np.array([2.0, 2.0]), HALF) == 0.0
    w, k = np.array([0.5, 0.5]), np.array([0.4, 9.0])
    assert jensen_gap(w, k, HALF) == pytest.approx(
        efficiency(4.7, HALF) - 0.5 * (efficiency(0.4, HALF) + efficiency(9.0, HALF))
    )
    assert variance(w, k) == pytest.approx(0.25 * 8.6**2)


def test_slope_weighted_distance_approximates_the_efficiency_gap_for_close_levels() -> None:
    for k1, k2 in ((1.0, 1.1), (5.0, 5.2), (0.2, 0.25)):
        exact = distance(k1, k2, 0.5, 0.5, HALF, "e")
        assert distance(k1, k2, 0.5, 0.5, HALF, "slope") == pytest.approx(exact, rel=0.02)
        assert distance(k1, k2, 0.5, 0.5, HALF, "k") == pytest.approx(abs(k1 - k2))


def test_coalesce_respects_capacity_and_conserves_mass_and_mean() -> None:
    rng = np.random.default_rng(3)
    w = rng.dirichlet(np.ones(30))
    k = rng.exponential(4.0, 30)
    for metric in ("k", "slope", "e"):
        wc, kc = coalesce(w, k, 8, HALF, metric)
        assert kc.size == 8 and wc.sum() == pytest.approx(1.0)
        assert mean(wc, kc) == pytest.approx(mean(w, k), rel=1e-12)
    wc, kc = coalesce(w, k, 64, HALF, "slope")
    assert kc.size == 30  # under capacity: compaction only
    with pytest.raises(ValueError):
        coalesce(w, k, 0, HALF, "k")


def test_summary_validates_inputs() -> None:
    with pytest.raises(ValueError):
        summary(np.array([0.5, 0.4]), np.array([1.0, 2.0]), HALF)
    with pytest.raises(ValueError):
        summary(np.array([1.0]), np.array([-1.0]), HALF)


def test_authoritative_fusion_uses_the_population_weighted_mean() -> None:
    """The equation the shadow anchors to, read from the production merge."""
    import inspect

    source = inspect.getsource(merge_units)
    assert "knowledge[t] = (knowledge[t] * n_t + knowledge[s] * n_s) / (n_t + n_s)" in source


def test_module_is_not_active() -> None:
    """No simulator path imports the module and it registers no model rule."""
    import subprocess

    hits = subprocess.run(
        ["grep", "-rl", "--include=*.py", "fusion_competence", str(ROOT / "src")],
        capture_output=True, text=True, check=False,
    ).stdout.split()  # fmt: skip
    assert [h for h in hits if not h.endswith("fusion_competence.py")] == []
    assert not any("fusion_competence" in rule.qualname for rule in RULES.values())


def _probe() -> Any:
    path = ROOT / "scripts/probes/fusion_competence_counterfactual.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("fusion_competence_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_reproduces_authoritative_means_and_pooling_baseline() -> None:
    probe = _probe()
    hist = probe._synthetic(
        [(2, "u1", "u2", 20, 20), (8, "u3", "u2", 10, 25)],
        {"u1": [0.4], "u2": [9.0], "u3": [3.0]},
        [(5, "u2", "u4")], 30, probe._gain(9.0),
    )  # fmt: skip
    pooled = probe.replay(hist, probe.Config(delay=0))
    assert pooled.het_unit_years == 0 and pooled.harvest_rel_jensen == 0.0
    kept = probe.replay(hist, probe.Config())
    assert kept.mean_err < 1e-12 and kept.fusion_err < 1e-12
    assert kept.max_components == 3 and kept.het_farm_years > 0
    # u2 is heterogeneous at farming in years 3-29; its daughter u4 copies it, years 6-29
    assert kept.het_unit_years == (30 - 3) + (30 - 6)
    late = probe.replay(hist, probe.Config(delay=5))
    assert 0 < late.het_unit_years < kept.het_unit_years
    capped = probe.replay(hist, probe.Config(capacity=2, metric="slope"))
    assert capped.max_components == 2 and capped.mean_err < 1e-12
    homogeneous = probe.replay(probe._synthetic([], {"u1": [0.4]}, [], 10, 0.1), probe.Config())
    assert homogeneous.het_unit_years == 0 and homogeneous.mean_err == 0.0


def test_pair_tracer_gap_decays_by_one_minus_decay_per_year() -> None:
    probe = _probe()
    hist = probe._synthetic([(0, "u1", "u2", 20, 20)], {"u1": [0.4], "u2": [9.0]}, [], 60, 0.1)
    tracer = probe.replay(hist, probe.Config()).tracers[0]
    # age h is the farming check h years after the fusion: h - 1 learning years have passed
    for h in (1, 5, 10, 25, 50):
        assert tracer.at[h][0] == pytest.approx(tracer.gap0 * (1 - LAM) ** (h - 1), rel=1e-12)
    assert tracer.halved == int(np.ceil(np.log(0.5) / np.log(1 - LAM))) + 1
