"""Counterfactual control over newly created cultivated capacity (MVP 3 Stage 4E). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §S. ``field_claim`` is a stratum's
share of *effective control over the unit's cultivated productive capacity* (the modeled
ability to benefit from or direct the use of existing fields; not ownership, title, sale,
inheritance, exclusion, rent or authority). When the unit's fields expand from ``F0`` to
``F1 > F0``, a hypothesis must say who controls the new ``dF = F1 - F0``:

- H1, population allocation (the authoritative ``field_claim_accretion`` rule): ``n = share``;
- H2, clearing-contribution allocation: ``n = contribution / sum(contribution)``. Clearing
  labor is a unit-level flow drawn from one pool whose capacity comes from the shared age
  structure, so every stratum's contribution is ``share * clearing_hours`` and H2 collapses
  to H1 (no differentiated labor is invented here);
- H3, control continuity: ``n = share + p * (field_claim - share)`` with ``p`` the
  experimental ``field_claim_continuity`` in [0, 1] (no canonical value; ``p = 0`` is H1).

Whatever the hypothesis, existing control is carried through the expansion:
``absolute_i = field_claim_i * F0 + n_i * dF``, normalized by its own sum (``= F1``), as the
authoritative rule does, so ``p = 0`` reproduces it bit for bit. Every deviation from
population share is multiplied by ``p + (1 - p) * F0 / F1`` (in ``[F0 / F1, 1]``): the rule
preserves inherited differences at most, never creates or amplifies them.

Only expansion is counterfactual. Shrinking fields keep claim fractions, and zero fields are
the existing ``claim_zero_stock`` reset, applied by the simulator after the transition (here
too: without fields there is no control to continue, so regrowth from zero follows share).

No simulator path calls this module, it registers no model rule, and ``p`` is not a scenario
setting. The probe ``scripts/probes/field_control_counterfactual.py`` substitutes it for the
authoritative transition in shadow runs (strata are passive, so physical state is identical).
"""

import numpy as np

from madexplorer.core.types import FloatArray
from madexplorer.population.strata_accounting import PerUnit, _per_unit, _total


def _check_continuity(continuity: float) -> None:
    if not 0.0 <= continuity <= 1.0:
        raise ValueError(f"field_claim_continuity must be in [0, 1], got {continuity!r}")


def continuity_new_capacity_shares(
    share: FloatArray, field_claim: FloatArray, before: PerUnit, continuity: float
) -> FloatArray:
    """H3: each stratum's share of control over new capacity, ``share + p * (claim - share)``.

    A unit without existing fields (``before == 0``) has no control to continue: ``share``.
    """
    _check_continuity(continuity)
    held = _per_unit(before, field_claim) > 0
    continued = share + continuity * (field_claim - share)
    shares: FloatArray = np.where(held, continued, share)
    return shares


def field_claims_after_expansion(
    share: FloatArray,
    field_claim: FloatArray,
    before: PerUnit,
    after: PerUnit,
    new_capacity_shares: FloatArray,
) -> FloatArray:
    """Field claims after ``before -> after`` when new capacity is controlled by
    ``new_capacity_shares`` (a partition of unity over the strata; H1, H2 or H3).

    The authoritative arithmetic with ``share`` replaced by ``new_capacity_shares``: no
    expansion (or nothing to normalize) keeps the claims; the inputs are never mutated.
    """
    f0, f1 = _per_unit(before, field_claim), _per_unit(after, field_claim)
    absolute = field_claim * f0 + new_capacity_shares * (f1 - f0)
    total = _per_unit(_total(absolute), field_claim)
    grows = (f1 > f0) & (total > 0)
    updated: FloatArray = np.where(grows, absolute / np.where(grows, total, 1.0), field_claim)
    return updated


def counterfactual_field_claim_after_expansion(
    share: FloatArray,
    field_claim: FloatArray,
    old_fields: PerUnit,
    new_fields: PerUnit,
    field_claim_continuity: float,
) -> FloatArray:
    """H3 field claims after an ordinary field change (COUNTERFACTUAL / NOT ACTIVE).

    ``p = 0`` is bit-identical to ``field_claims_after_change``; ``p = 1`` keeps the claims
    under pure expansion (to rounding). Shrinkage keeps them; a zero result is left to the
    zero-stock reset (:func:`field_claim_step` applies it for synthetic trajectories).
    """
    shares = continuity_new_capacity_shares(share, field_claim, old_fields, field_claim_continuity)
    return field_claims_after_expansion(share, field_claim, old_fields, new_fields, shares)


def field_claim_step(
    share: FloatArray,
    field_claim: FloatArray,
    old_fields: float,
    new_fields: float,
    field_claim_continuity: float,
) -> FloatArray:
    """One synthetic step: the H3 transition, then ``claim_zero_stock`` (zero fields: share)."""
    if new_fields == 0:
        return share.copy()
    return counterfactual_field_claim_after_expansion(
        share, field_claim, old_fields, new_fields, field_claim_continuity
    )


def retention_factor(old_fields: float, new_fields: float, continuity: float) -> float:
    """The factor ``p + (1 - p) * F0 / F1`` multiplying every ``field_claim - share`` in one
    expansion step (1 without expansion, 0 for growth from no fields)."""
    _check_continuity(continuity)
    if new_fields <= old_fields:
        return 1.0
    if old_fields <= 0:
        return 0.0
    return continuity + (1.0 - continuity) * old_fields / new_fields


def control_deviation(share: FloatArray, field_claim: FloatArray) -> float:
    """``0.5 * sum |field_claim - share|``: the population share whose control would have to
    move to make control population-proportional (0 neutral, below 1)."""
    return 0.5 * float(np.abs(field_claim - share).sum())
