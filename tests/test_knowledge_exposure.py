"""MVP 3 Stage 5E: partial knowledge exposure and within-unit transmission. NOT ACTIVE.

``madexplorer.population.knowledge_exposure`` asks whether a technique first known by a few
people would still be partly unknown when cultivation needs it. No simulator path calls it.
"""

import importlib
import importlib.util
import sys
from typing import Any

import numpy as np
import pytest

from madexplorer.core.governance import RULES
from madexplorer.population.knowledge_exposure import (
    calibrate_beta,
    fission_expected,
    fission_finite,
    fusion,
    initial_exposure,
    knowledge_constraint,
    min_share,
    transmit,
    turnover,
    years_to,
)
from tests.conftest import ROOT

C, D, M = 36_500.0, 2_000.0, 0.9


def test_initial_exposure_is_k_over_labor_equivalents_and_never_lowers() -> None:
    assert initial_exposure(1, 20.0) == pytest.approx(0.05)
    assert initial_exposure(5, 3.0) == 1.0  # more discoverers than workers
    assert initial_exposure(1, 20.0, current=0.4) == 0.4  # a repeated event is idempotent
    assert initial_exposure(0, 0.0) == 0.0 and initial_exposure(1, 0.0) == 1.0
    with pytest.raises(ValueError):
        initial_exposure(-1, 5.0)


def test_transmission_is_bounded_monotone_and_never_spontaneous() -> None:
    for beta in (0.5, 3.0, 40.0):
        q = 0.02
        for _ in range(200):
            nxt = transmit(q, beta)
            assert q <= nxt <= 1.0
            q = nxt
        assert q == pytest.approx(1.0)
    assert transmit(0.0, 50.0) == 0.0  # no knowers, nobody learns
    assert transmit(1.0, 3.0) == 1.0  # saturated stays saturated
    assert transmit(0.3, 0.0) == 0.3  # no transmission
    assert transmit(0.01, np.inf) == 1.0  # instantaneous
    # more knowers spread faster
    assert transmit(0.4, 2.0) - 0.4 > transmit(0.1, 2.0) - 0.1


def test_calibration_reaches_half_in_exactly_the_target_years() -> None:
    q0 = 1 / 15
    for years in (1, 2, 5, 10, 20):
        beta = calibrate_beta(q0, years)
        assert years_to(q0, beta, 0.5) == years
        assert (years_to(q0, beta * 0.9, 0.5) or 10**6) >= years  # slower never sooner


def test_half_time_depends_on_the_initial_share() -> None:
    beta = calibrate_beta(1 / 15, 5)
    slow, fast = years_to(1 / 60, beta, 0.5), years_to(1 / 5, beta, 0.5)
    assert slow is not None and slow > 5  # one knower in a larger unit takes longer
    assert fast is not None and fast < 5


def test_turnover_dilutes_and_new_workers_do_not_inherit() -> None:
    assert turnover(0.8, 0.03) == pytest.approx(0.776)
    assert turnover(1.0, 0.0) == 1.0
    assert turnover(0.0, 0.05) == 0.0
    # turnover without transmission eventually empties the knowing share
    q = 1.0
    for _ in range(300):
        q = turnover(q, 0.03)
    assert q < 1e-3


def test_expected_fission_conserves_the_expected_knowing_count() -> None:
    q, n, moved = 0.3, 40, 15
    s = fission_expected(q)
    assert s.parent * (n - moved) + s.daughter * moved == pytest.approx(q * n)


def test_finite_fission_keeps_head_count_and_never_duplicates() -> None:
    rng = np.random.default_rng(1)
    n, moved = 28, 12
    q = 1 / n  # exactly one knower
    both = 0
    for _ in range(2000):
        s = fission_finite(q, n, moved, rng)
        knowers = s.parent * (n - moved) + s.daughter * moved
        assert knowers == pytest.approx(1.0)
        both += int(s.parent > 0 and s.daughter > 0)
        assert (s.parent > 0) != (s.daughter > 0)  # the one person goes one way
    assert both == 0
    # expectation over draws matches the representative split
    draws = [fission_finite(0.3, 40, 15, rng) for _ in range(4000)]
    mean_daughter = np.mean([d.daughter for d in draws])
    assert mean_daughter == pytest.approx(0.3, abs=0.02)


def test_fusion_adds_knowers_not_the_union() -> None:
    assert fusion(1.0, 30, 0.0, 10) == pytest.approx(0.75)  # non-holder brings none
    assert fusion(0.2, 20, 0.6, 20) == pytest.approx(0.4)
    assert fusion(0.0, 10, 0.0, 10) == 0.0
    assert fusion(0.5, 0, 0.5, 0) == 0.0


def test_f_min_boundaries_follow_the_cultivation_budget() -> None:
    assert min_share(0.0, C, D, M) == 0.0
    assert min_share(M * (C - D), C, D, M) == 1.0
    assert min_share(1000.0, C, C + 1, M) == 1.0  # nothing left after debt
    assert min_share(6000.0, C, D, M) == pytest.approx(6000.0 / (M * (C - D)))


def test_constraint_binds_exactly_when_q_is_below_f_min() -> None:
    p = 0.4 * M * (C - D)
    f = min_share(p, C, D, M)
    for q in (0.0, 0.2, f - 1e-6, f, 0.9, 1.0):
        c = knowledge_constraint(q, p, C, D, M)
        assert c.binding == (q < f - 1e-12)
        assert c.capable_hours + c.shortfall_hours == pytest.approx(p)
        assert c.shortfall_hours == pytest.approx(max(p - q * M * (C - D), 0.0))
    none = knowledge_constraint(0.0, 0.0, C, D, M)
    assert not none.binding and none.shortfall_hours == 0.0


def test_shares_outside_unit_interval_are_rejected() -> None:
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            transmit(bad, 1.0)
        with pytest.raises(ValueError):
            turnover(bad, 0.1)


def test_module_is_not_registered_as_a_model_rule() -> None:
    assert not any("knowledge_exposure" in rule.qualname for rule in RULES.values())
    assert not any("exposure" in name for name in RULES)


# ---------------------------------------------------------------- replay (Stage 5E probe)


def _probe() -> tuple[Any, Any]:
    probes = ROOT / "scripts" / "probes"
    sys.path.insert(0, str(probes))
    try:
        spec = importlib.util.spec_from_file_location(
            "knowledge_exposure_probe", probes / "knowledge_exposure_counterfactual.py"
        )
        assert spec is not None and spec.loader is not None
        probe: Any = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        common: Any = importlib.import_module("_common")
    finally:
        sys.path.remove(str(probes))
    return probe, common


PROBE, COMMON = _probe()
NEED = 0.3 * 0.9 * 40 * 0.5 * 1825.0  # 30 % of a 40-person unit's labor


def _hist(rows: dict[int, list[Any]], events: list[Any]) -> dict[str, Any]:
    return {"rows": rows, "events": events}


def _acq(year: int, uid: str = "u", kind: str = "invention") -> tuple[int, str, dict[str, Any]]:
    return (year, kind, {"unit_id": uid, "technology": "plant_cultivation", "population": 40})


def test_acquisition_cannot_affect_that_years_farming() -> None:
    """Invention happens after farming in the pipeline: the same year's cultivation is
    evaluated with the knowledge held before it."""
    rows = {1: [PROBE._unit("u", NEED)], 2: [PROBE._unit("u", NEED)]}
    r = PROBE.replay(_hist(rows, [_acq(1)]), PROBE.Config(beta=np.inf))
    assert r.binding["unknown"] == 1  # year 1: nobody knew yet (q = 0 before the event)
    assert r.binding["invention"] == 0  # year 2: known by everyone (instantaneous)


def test_repeated_acquisition_never_lowers_knowledge() -> None:
    rows = {y: [PROBE._unit("u", 0.0)] for y in range(1, 6)}
    r = PROBE.replay(_hist(rows, [_acq(1), _acq(4)]), PROBE.Config(beta=0.5, rate="slow"))
    assert r.repeat_events == 1
    assert r.lineages[1].q0 >= r.lineages[0].q0


def test_replay_fusion_conserves_knowers_and_ignores_the_union() -> None:
    rows = {y: [PROBE._unit("a", 0.0), PROBE._unit("b", 0.0)] for y in range(1, 4)}
    merge = (
        2,
        "population_merge",
        {"unit_id": "b", "into_id": "a", "merged_population": 40, "resulting_population": 80},
    )
    cfg = PROBE.Config(beta=0.0, rate="none", turnover=False)
    r = PROBE.replay(_hist(rows, [_acq(1, "a"), merge]), cfg)
    assert r.final["a"] == pytest.approx(r.lineages[0].q0 * 40 / 80)


def test_replay_finite_fission_keeps_one_knower_on_one_side() -> None:
    rows = {y: [PROBE._unit("u", 0.0)] for y in range(1, 4)}
    split = (
        2,
        "population_split",
        {"unit_id": "u", "daughter_id": "d", "source_population": 40, "moved_population": 15},
    )
    for seed in range(6):
        cfg = PROBE.Config(beta=0.0, rate="none", turnover=False, fission="finite", seed=seed)
        r = PROBE.replay(_hist(rows, [_acq(1), split]), cfg)
        parent, daughter = r.final["u"], r.final["d"]
        assert (parent > 0) != (daughter > 0)
        assert parent * 20 * 25 / 40 + daughter * 20 * 15 / 40 == pytest.approx(1.0, abs=0.35)


def test_extinction_and_loss_remove_knowledge() -> None:
    rows = {y: [PROBE._unit("u", 0.0)] for y in range(1, 4)}
    lost = (2, "technology_lost", {"unit_id": "u", "technology": "plant_cultivation"})
    r = PROBE.replay(_hist(rows, [_acq(1), lost]), PROBE.Config(beta=0.5, rate="slow"))
    assert "u" not in r.final and r.knowledge_lost == 1
    gone = (2, "unit_extinct", {"unit_id": "u"})
    r = PROBE.replay(_hist(rows, [_acq(1), gone]), PROBE.Config(beta=0.5, rate="slow"))
    assert "u" not in r.final


def test_constraint_accounting_matches_the_pure_function() -> None:
    rows = {1: [PROBE._unit("u", 0.0)], 2: [PROBE._unit("u", NEED)]}
    cfg = PROBE.Config(beta=0.0, rate="none", turnover=False)
    r = PROBE.replay(_hist(rows, [_acq(1)]), cfg)
    _, p, c, d, m, _, lab, _ = PROBE._unit("u", NEED)
    expected = knowledge_constraint(1.0 / lab, p, c, d, m)
    assert r.short["invention"] == pytest.approx(expected.shortfall_hours)


def test_recorder_leaves_authoritative_state_unchanged() -> None:
    scenario = COMMON.scenario_for("pressure+cult", 0, 0.0, 90)
    rec = PROBE.Recorder()
    rec.install()
    try:
        observed, _ = COMMON.drive(scenario, None)
    finally:
        rec.remove()
    plain, _ = COMMON.drive(scenario, None)
    assert COMMON.physical_digest(observed) == COMMON.physical_digest(plain)
    assert any(p > 0 for rows in rec.rows.values() for _, p, *_ in rows)
