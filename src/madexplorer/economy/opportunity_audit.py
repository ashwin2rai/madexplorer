"""Opportunity structure of foraging patches (MVP 3 Stage 6B). NOT ACTIVE.

Design: ``objective/STAGE6B_SOCIOECOLOGICAL_MECHANISM_REVIEW.md`` and
``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §AE. Read-only diagnostics: no simulator
path calls this module, it registers no model rule, and its references are not scenario
settings.

Within a year the accessible wild stock of a cell is finite and harvest is concave in total
effective effort, ``H(E) = sum_k a_k (1 - exp(-r_k E w_k / a_k))`` (``foraging._harvest``).
Production (``satisficing_group_foraging``) makes co-located units of one species apply
one common effort fraction until the *summed* target is met, and splits the harvest in
proportion to effective labor. Three static references, all on the same stock, labor,
efficiency, targets and harvest function:

- :func:`pooled_harvest`: the production rule itself (exact replay);
- :func:`independent_harvest`: each unit stops at its *own* target (or its labor), harvest
  shared in proportion to effort (simultaneous scramble). With one unit it equals pooled;
- :func:`alone_harvest`: the unit with the cell to itself (the others absent).

They change no stock and draw no random numbers. :func:`regrowth_loss` prices how much of
one year's removal is still missing from next year's stock under ``logistic_regrowth``.

Measurement definitions (Stage 6B-P1):

- :func:`remaining_target_met`: the recorded foraging target is already net of crops
  (``max(need (1 + surplus_target) - farm_harvest, 0)``, ``ForagingSubsystem._inputs``), so
  attainment compares wild harvest alone with it; units with no remaining target are not
  eligible. Meeting it is not the same as meeting nutritional need.
- :func:`utilization`: kcal removed / accessible stock before harvest. Applied to one unit's
  harvest it is that unit's *share* of the stock; applied to a foraging group's removal it is
  the cell's *collective* utilization. Neither says by itself which input limited harvest.
- :func:`labor_elasticity`: the harvest function's elasticity in effort. A group that missed
  its target applied all its labor (``cell_harvest``), but that alone does not make labor
  the binding margin: the elasticity at full effort says how far more labor would help.
"""

from collections.abc import Sequence

import numpy as np

from madexplorer.ecology.resources import logistic_regrowth
from madexplorer.economy.foraging import (
    _harvest,
    _marginal_return,
    cell_harvest,
    single_unit_harvest,
)

Pair = tuple[float, float]
BISECTION_STEPS = 200
# Relative shortfall below which a remaining target counts as met. The production solver
# stops at |H - T| <= 1e-12 T (``foraging.SOLVER_TOLERANCE``; its bisection fallback ends at
# or above T) and splitting a group's removal by effort adds rounding near 1e-16 relative;
# 1e-9 sits well above both and far below any nutritionally meaningful shortfall.
TARGET_REL_TOL = 1e-9


def remaining_target_met(
    forage: float, remaining_target: float, rel_tol: float = TARGET_REL_TOL
) -> bool | None:
    """Whether wild harvest met the crop-net foraging target; ``None`` if none remained."""
    if remaining_target <= 0:
        return None
    return forage >= remaining_target * (1.0 - rel_tol)


def utilization(removed: float, accessible: float) -> float | None:
    """Removed kcal / accessible stock before harvest; ``None`` when nothing was accessible."""
    return removed / accessible if accessible > 0 else None


def labor_elasticity(stock: Pair, returns: Pair, effective_hours: float) -> float | None:
    """``E H'(E) / H(E)`` of the harvest function at ``effective_hours``: the % change in
    harvest per % change in effort. 1 means harvest scales with labor; near 0, extra labor
    takes almost nothing more from the stock. ``None`` when nothing can be harvested."""
    harvest = sum(_harvest(stock, returns, effective_hours))
    if harvest <= 0:
        return None
    return effective_hours * _marginal_return(stock, returns, effective_hours) / harvest


def pooled_harvest(
    stock: Pair, returns: Pair, labor: Sequence[float], efficiency: Sequence[float],
    targets: Sequence[float],
) -> list[float]:  # fmt: skip
    """Each unit's harvest under the production rule (one group, one species)."""
    if len(labor) == 1:
        return [single_unit_harvest(stock, returns, labor[0], efficiency[0], 0 + targets[0])[0]]
    out = cell_harvest(
        np.array(stock), np.array(returns), np.array(labor, dtype=np.float64),
        np.array(efficiency, dtype=np.float64), sum(targets),
    )  # fmt: skip
    shares: list[float] = out.shares.tolist()
    return shares


def independent_harvest(
    stock: Pair, returns: Pair, labor: Sequence[float], efficiency: Sequence[float],
    targets: Sequence[float],
) -> tuple[list[float], list[float]]:  # fmt: skip
    """``(harvest, effective effort)`` per unit when each stops at its own target.

    Shares are proportional to effort, so unit ``i`` reaches ``T_i`` with effort
    ``T_i E / H(E)``; it works ``e_i = min(cap_i, T_i E / H(E))``. The total ``E`` solves
    ``sum_i e_i = E`` (bisection; the left side minus ``E`` falls from positive to <= 0).
    """
    caps = [lab * eff for lab, eff in zip(labor, efficiency, strict=True)]
    total_cap = sum(caps)
    if total_cap <= 0 or sum(targets) <= 0:
        return [0.0] * len(caps), [0.0] * len(caps)

    def total(effort: float) -> float:
        return sum(_harvest(stock, returns, effort))

    def efforts(effort: float) -> list[float]:
        h = total(effort)
        if h <= 0:
            return list(caps)
        return [min(c, t * effort / h) for c, t in zip(caps, targets, strict=True)]

    if sum(efforts(total_cap)) >= total_cap:
        effort = total_cap
    else:
        lo, hi = 0.0, total_cap
        for _ in range(BISECTION_STEPS):
            mid = 0.5 * (lo + hi)
            if sum(efforts(mid)) >= mid:
                lo = mid
            else:
                hi = mid
        effort = hi
    e = efforts(effort)
    used = sum(e)
    h = total(used)
    return ([h * x / used if used > 0 else 0.0 for x in e], e)


def alone_harvest(
    stock: Pair, returns: Pair, labor: float, efficiency: float, target: float
) -> float:
    """The unit's harvest with the cell's stock to itself (production single-unit rule)."""
    return single_unit_harvest(stock, returns, labor, efficiency, 0 + target)[0]


def regrowth_loss(
    stock_end: float, capacity_next: float, rate: float, recolonization: float, removed: float
) -> float:
    """Next year's stock lost to ``removed`` kcal taken this year (``logistic_regrowth``)."""
    with_removal, without = logistic_regrowth(
        np.array([stock_end, stock_end + removed]), np.array([capacity_next] * 2), rate,
        recolonization,
    ).tolist()  # fmt: skip
    return float(without - with_removal)


def gini(values: Sequence[float]) -> float:
    """Gini coefficient of nonnegative values (0 for an empty or all-zero set)."""
    x = np.sort(np.asarray(values, dtype=np.float64))
    if x.size == 0 or x.sum() <= 0:
        return 0.0
    n = x.size
    return float((2.0 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))
