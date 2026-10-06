"""Counterfactual store release (MVP 3 Stage 4D). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §R. A candidate answer to *how
much* stored food a unit releases when its current harvest falls short, evaluated
counterfactually only: no simulator path calls this module, it is not a registered model
rule, and its parameter is not a scenario setting. The authoritative release stays the MVP
2.1 ``pooled_energy_balance`` rule ``X = min(D, K)``.

The release is a unit-level, symmetric decision: it reads no stratum state (claims, shares,
ids). *Who* receives a release is the separate Stage 4C question
(the Stage 4C counterfactual allocator, design §Q).

- ``D`` remaining external deficit ``max(Need - H, 0)`` after the post-trade harvest, before
  body reserves; ``K`` stores available at the withdrawal (after trade).
- Current rule: ``X = min(D, K)``.
- Reserve-target rule: ``X = min(D, max(K - R, 0))`` with a protected stock ``R >= 0``.
  ``R = 0`` is the current rule exactly.
- Candidate target (future-need buffer, persistence expectation): ``R = b * Need``, where
  ``Need`` is the requirement the unit has this year (known at the decision) and ``b`` is the
  experimental ``reserve_target_fraction`` (no canonical value; ``b = 0`` is MVP 2.1).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StoreRelease:
    """One unit-year's release: ``withdrawal`` (X), ``retained_by_policy`` (what the current
    rule would also have released), ``unmet_external_need`` (``D - X``, before reserves)."""

    withdrawal: float
    retained_by_policy: float
    unmet_external_need: float


def _check(deficit: float, stores: float, target: float = 0.0) -> None:
    for name, value in (("deficit", deficit), ("stores", stores), ("reserve target", target)):
        if not (value == value and value >= 0.0 and value != float("inf")):
            raise ValueError(f"{name} must be finite and nonnegative, got {value!r}")


def release_current(deficit: float, stores: float) -> StoreRelease:
    """The MVP 2.1 rule: release whatever covers the deficit, up to the whole store."""
    _check(deficit, stores)
    x = min(deficit, stores)
    return StoreRelease(x, 0.0, deficit - x)


def release_with_reserve_target(deficit: float, stores: float, target: float) -> StoreRelease:
    """Release at most the stores above a protected reserve ``target``."""
    _check(deficit, stores, target)
    x = min(deficit, max(stores - target, 0.0))
    return StoreRelease(x, min(deficit, stores) - x, deficit - x)


def need_buffer_target(need: float, buffer_fraction: float) -> float:
    """Candidate reserve target ``b * Need`` (this year's requirement as the expectation of
    the next; a persistence assumption, not foresight)."""
    if not buffer_fraction >= 0.0:
        raise ValueError("buffer_fraction must be nonnegative")
    _check(need, 0.0)
    return buffer_fraction * need
