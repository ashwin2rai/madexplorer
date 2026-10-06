"""Counterfactual stored-food access by store claim (MVP 3 Stage 4C). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §Q. This module is a candidate
mechanism evaluated **counterfactually only**: no simulator code path calls it, it is not a
registered model rule, and its results are read-only, non-authoritative diagnostics. Physical
consumption, body reserves and every subsystem stay MVP 2.1 (pooled by share).

Candidate mechanism: when a unit draws on its stores to cover a shortage, existing effective
control over stores (``store_claim``) may give access priority. ``store_claim`` is a share of
continuing control over the surviving aggregate stock, not an exhaustible calorie account:
receiving food debits nothing and changes no claim (claims change only through the
established Stage 3B/3C accounting, and reset to share when stores reach zero).

For one unit-year, with population shares ``s``, pre-withdrawal store claims ``c``, the
experimental weight ``a`` (``store_access_claim_weight``, 0 <= a <= 1; not a scenario setting)
and remaining external deficits ``D_i`` (need minus harvest by share, before body reserves):

- access priority ``q_i = s_i + a * (c_i - s_i)`` (difference form: ``a = 0`` or ``c = s``
  gives ``q = s`` exactly);
- the unit's actual physical withdrawal ``X`` (fixed by MVP 2.1; this module never chooses
  it) is allocated by bounded weighted water-filling: ``x_i`` proportional to ``q_i`` among
  strata with unmet deficit, capped at ``D_i``, the excess redistributed until ``X`` is
  assigned; if the hungry strata left all have zero priority (``a = 1``, zero claims), the
  remainder goes in proportion to remaining unmet need (the neutral rule when claims give no
  ranking; under proportional needs it is also the ``a -> 1`` limit, so the allocation stays
  continuous in ``a``);
- ``X >= sum(D)`` (stores cover everyone's deficit) gives ``x = D`` exactly: control then
  has no effect on who is fed.

Numerical contract (``REL_TOL``): conservation ``|sum(x) - X| <= REL_TOL * X + slack`` and,
at ``a = 0`` with proportional needs, ``|x_i - X * s_i| <= REL_TOL * X``; ``0 <= x_i <= D_i``
exactly. ``slack`` is the caller's absolute rounding allowance for ``X`` against
``sum(D)`` (the physical withdrawal is ``K0 - (K0 - X)``, exact only to ``ulp(K0)``); a
withdrawal within ``REL_TOL * sum(D) + slack`` of ``sum(D)`` counts as covering every
deficit. Near ``a = 1`` the difference form gives tiny priorities ``(1 - a) * s_i`` only to
absolute rounding, which moves the allocation by rounding-sized amounts (continuity holds).
"""

from dataclasses import dataclass

import numpy as np

from madexplorer.core.types import BoolArray, FloatArray

REL_TOL = 1e-12  # the partition tolerance of shares and claims (strata.validate_block)


@dataclass(frozen=True, eq=False)
class StoreAccess:
    """Counterfactual allocation of one unit's store withdrawal to its strata.

    ``access`` is ``x`` (kcal), ``priority`` ``q``, ``capped`` the strata that reached their
    deficit, ``fallback`` whether the remaining-need rule was used, ``rounds`` the
    water-filling rounds (0: every deficit covered), ``unassigned`` ``X`` minus the allocated
    total (signed; rounding only, within the allowance).
    """

    access: FloatArray
    priority: FloatArray
    capped: BoolArray
    fallback: bool
    rounds: int
    unassigned: float


def _vector(name: str, values: FloatArray) -> FloatArray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0:
        raise ValueError(f"{name} must be a non-empty 1-D array")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite")
    return array


def allocate_store_access_counterfactual(
    share: FloatArray,
    store_claim: FloatArray,
    deficit: FloatArray,
    withdrawal: float,
    claim_weight: float,
    slack: float = 0.0,
) -> StoreAccess:
    """Allocate the fixed withdrawal ``X`` to strata (pure; inputs are not modified)."""
    s = _vector("share", share)
    c = _vector("store_claim", store_claim)
    d = _vector("deficit", deficit)
    if not (s.size == c.size == d.size):
        raise ValueError("share, store_claim and deficit must have the same length")
    if (s <= 0).any() or abs(s.sum() - 1.0) > REL_TOL:
        raise ValueError("shares must be positive and sum to 1")
    if (c < 0).any() or abs(c.sum() - 1.0) > REL_TOL:
        raise ValueError("store claims must be nonnegative and sum to 1")
    if (d < 0).any():
        raise ValueError("deficits must be nonnegative")
    if not 0.0 <= claim_weight <= 1.0:
        raise ValueError("claim_weight must be in [0, 1]")
    if not (np.isfinite(withdrawal) and withdrawal >= 0.0 and slack >= 0.0):
        raise ValueError("withdrawal and slack must be finite and nonnegative")
    total = float(d.sum())
    allowance = REL_TOL * total + slack
    if withdrawal > total + allowance:
        raise ValueError(f"withdrawal {withdrawal!r} exceeds the total deficit {total!r}")
    priority = s + claim_weight * (c - s)
    if withdrawal >= total - allowance:  # stores cover every deficit: claims cannot matter
        return StoreAccess(d.copy(), priority, d > 0, False, 0, withdrawal - total)
    access = np.zeros_like(d)
    hungry = d > 0
    capped = np.zeros_like(hungry)
    remaining, fallback, rounds = float(withdrawal), False, 0
    while remaining > 0.0 and hungry.any():
        rounds += 1
        weights = np.where(hungry, priority, 0.0)
        if weights.sum() <= 0.0:  # no ranking left: remaining unmet need
            weights = np.where(hungry, d - access, 0.0)
            fallback = True
        offer = remaining * weights / weights.sum()
        room = d - access
        full = hungry & (offer >= room)
        if not full.any():
            access = access + offer
            remaining = 0.0
            break
        access = np.where(full, d, access)
        remaining -= float(room[full].sum())
        hungry &= ~full
        capped |= full
    return StoreAccess(access, priority, capped, fallback, rounds, remaining)


@dataclass(frozen=True, eq=False)
class CounterfactualAccess:
    """Counterfactual external food allocation of one shortage unit-year (kcal; per
    stratum). Candidate socioeconomic allocation before body reserves, not consumption."""

    withdrawal_kcal: float  # X, the physical withdrawal (fixed by MVP 2.1)
    deficit: FloatArray  # D_i, remaining external deficit after harvest by share
    allocation: StoreAccess
    counterfactual_store_access_kcal: FloatArray  # x_i
    counterfactual_external_food_allocation_kcal: FloatArray  # H * s_i + x_i
    counterfactual_external_food_allocation_ratio: FloatArray  # / (Need * s_i)
    counterfactual_unmet_external_need_kcal: FloatArray  # D_i - x_i
    counterfactual_store_access_transfer_kcal: FloatArray  # x_i - X * c_i
    redistribution_kcal: float  # R = sum|x_i - X * s_i| / 2

    @property
    def redistribution_fraction(self) -> float:
        """``R / X`` (0 when nothing is withdrawn)."""
        x = self.withdrawal_kcal
        return self.redistribution_kcal / x if x > 0 else 0.0


def counterfactual_store_access(
    share: FloatArray,
    store_claim: FloatArray,
    need: float,
    harvest: float,
    withdrawal: float,
    claim_weight: float,
    slack: float = 0.0,
) -> CounterfactualAccess:
    """The candidate allocation for one unit-year from its audited energetics quantities:
    ``need`` (Need), post-trade ``harvest`` (H) and the physical ``withdrawal`` (X), with
    need and harvest by share (shared demography, pooled harvest), so
    ``D_i = max(Need - H, 0) * s_i``: the remaining external deficit after harvest, before
    body reserves."""
    s = _vector("share", share)
    c = _vector("store_claim", store_claim)
    need_i, harvest_i = need * s, harvest * s
    # D_i = max(need_i - harvest_i, 0) with need and harvest by share, in the factored form:
    # identical in exact arithmetic, and free of cancellation when Need is close to H.
    deficit = max(need - harvest, 0.0) * s
    allocation = allocate_store_access_counterfactual(
        s, c, deficit, withdrawal, claim_weight, slack
    )
    x = allocation.access
    external = harvest_i + x
    ratio = np.divide(external, need_i, out=np.full_like(external, np.nan), where=need_i > 0)
    return CounterfactualAccess(
        float(withdrawal),
        deficit,
        allocation,
        x,
        external,
        ratio,
        deficit - x,
        x - withdrawal * c,
        float(np.abs(x - withdrawal * s).sum()) / 2.0,
    )
