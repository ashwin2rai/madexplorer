"""Partial knowledge exposure and within-unit transmission (MVP 3 Stage 5E). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §X. Counterfactual only: no
simulator path calls this module, it registers no model rule, and its parameters are not
scenario settings. The authoritative technology Boolean, labor and crop output are unchanged.

Shadow quantity ``q``: the share of a unit's labor capacity held by people who know a
technique (equal to the share of people under the representative age composition strata
already assume). The existing invention or adoption event decides *whether* a unit acquires
the technique; the counterfactual decides *how many* know it at first (``k`` people) and
how it spreads:

- **Exposure:** ``q = min(k / L, 1)`` at a genuine acquisition, ``L`` the unit's
  labor-equivalents (a discoverer is a worker); never lowers an existing ``q``.
- **Turnover:** workers new this year do not know it: ``q <- (1 - tau) q``.
- **Transmission (mass action, a hypothesis):** ``q <- q + (1 - q)(1 - exp(-beta q))``.
  Bounded in [0, 1], monotone, no spontaneous knowledge at ``q = 0``, stays at 1.
- **Fission:** expected value (``daughter = parent``), or a finite-knower partition that
  keeps the knowing head count (a shadow draw, never the authoritative RNG).
- **Fusion:** knower-weighted mean by pre-fusion population; a non-holder contributes 0.
- **Constraint:** if cultivation required the technique, knowers could supply at most
  ``q m max(C - D, 0)`` of the ``P`` cultivation hours; it binds when ``q < f_min``.
"""

from dataclasses import dataclass

import numpy as np


def _share(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


def initial_exposure(knowers: float, labor_equivalents: float, current: float = 0.0) -> float:
    """Knowing share after a genuine acquisition by ``knowers`` people (never lowered)."""
    if not knowers >= 0.0 or not labor_equivalents >= 0.0:
        raise ValueError("knowers and labor_equivalents must be nonnegative")
    _share(current, "current")
    if labor_equivalents == 0.0:
        return current if knowers == 0.0 else 1.0
    return max(current, min(knowers / labor_equivalents, 1.0))


def transmit(q: float, beta: float) -> float:
    """One year of within-unit mass-action transmission. ``beta = inf``: instantaneous for
    any ``q > 0``; ``beta = 0``: none."""
    _share(q, "q")
    if not beta >= 0.0:
        raise ValueError(f"beta must be nonnegative, got {beta!r}")
    if q == 0.0 or q == 1.0 or beta == 0.0:
        return q
    if np.isinf(beta):
        return 1.0
    return min(q + (1.0 - q) * -float(np.expm1(-beta * q)), 1.0)


def turnover(q: float, entering: float) -> float:
    """Share after a share ``entering`` of labor is new to work and does not know."""
    _share(q, "q")
    _share(entering, "entering")
    return (1.0 - entering) * q


def years_to(q0: float, beta: float, target: float, limit: int = 1000) -> int | None:
    """Years of transmission (no turnover) until ``q >= target``; None if never."""
    q, years = q0, 0
    while q < target:
        if years >= limit or q == 0.0 or beta == 0.0:
            return None
        q = transmit(q, beta)
        years += 1
    return years


def calibrate_beta(q0: float, years: int, target: float = 0.5) -> float:
    """Smallest ``beta`` that reaches ``target`` from ``q0`` in exactly ``years`` years (a
    reference-case calibration: half-times are not universal under mass action)."""
    if years < 1:
        raise ValueError("years must be at least 1")
    lo, hi = 0.0, 1.0
    while (years_to(q0, hi, target) or years + 1) > years:
        hi *= 2.0
        if hi > 1e9:
            raise ValueError("target unreachable")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        reached = years_to(q0, mid, target)
        if reached is not None and reached <= years:
            hi = mid
        else:
            lo = mid
    return hi


def fusion(q_a: float, n_a: float, q_b: float, n_b: float) -> float:
    """Knowing share of a fused unit: knowers add up (a unit without the technique brings
    none, whatever the authoritative union says)."""
    _share(q_a, "q_a")
    _share(q_b, "q_b")
    total = n_a + n_b
    return 0.0 if total <= 0 else (q_a * n_a + q_b * n_b) / total


@dataclass(frozen=True)
class FissionShares:
    parent: float
    daughter: float


def fission_expected(q: float) -> FissionShares:
    """Representative split: both keep ``q`` (the expected knowing head count is conserved;
    a fractional knower can be assigned to both: an expectation, not a partition)."""
    _share(q, "q")
    return FissionShares(q, q)


def fission_finite(
    q: float, population: int, departing: int, rng: np.random.Generator
) -> FissionShares:
    """Finite knowers. ``population`` counts the parent's labor-equivalent workers and
    ``departing`` those who leave (fission is representative, so the departing labor share
    is the departing population share). ``q population`` knowing workers (stochastic
    rounding keeps the expectation), of whom the departing group draws a hypergeometric
    number: the knowing count is kept exactly and nobody is duplicated. ``rng`` is a
    shadow stream, never the authoritative one."""
    _share(q, "q")
    if not 0 <= departing <= population:
        raise ValueError("departing must be between 0 and the population")
    if population == 0:
        return FissionShares(q, q)
    exact = q * population
    knowers = int(np.floor(exact))
    if rng.random() < exact - knowers:
        knowers += 1
    knowers = min(knowers, population)
    leave = int(rng.hypergeometric(knowers, population - knowers, departing)) if departing else 0
    stay = population - departing
    return FissionShares(
        (knowers - leave) / stay if stay else 0.0,
        leave / departing if departing else 0.0,
    )


def min_share(productive: float, capacity: float, debt: float, max_share: float) -> float:
    """``f_min = P / (m max(C - D, 0))``: the smallest labor share that can perform the
    cultivation hours (0 without cultivation; 1 when everyone is needed or nothing is left
    after debt). As ``FarmingSubsystem``: ``P <= m max(C - D, 0)`` always."""
    if productive <= 0.0:
        return 0.0
    budget = max_share * max(capacity - debt, 0.0)
    return 1.0 if budget <= productive else productive / budget


@dataclass(frozen=True)
class Constraint:
    binding: bool
    capable_hours: float
    shortfall_hours: float


def knowledge_constraint(
    q: float, productive: float, capacity: float, debt: float, max_share: float
) -> Constraint:
    """Cultivation hours knowers could supply if cultivation required the technique, and
    the shortfall against the authoritative hours ``P`` (a diagnostic, never applied)."""
    _share(q, "q")
    capable = min(productive, q * max_share * max(capacity - debt, 0.0))
    short = productive - capable
    return Constraint(short > 1e-9 * max(productive, 1.0), capable, short)
