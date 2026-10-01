"""Compiled foraging: every (cell, species) group's shared-pool harvest in one call (PH4a).

The model is :mod:`madexplorer.economy.foraging` (``_harvest``, ``_marginal_return``,
``_effort_fraction``, ``single_unit_harvest``, ``cell_harvest``); this module transcribes
those scalar rules operation by operation, in the same order, so results are
bit-identical (Level A, differential tests against the Python reference):

- Python's ``sum`` of a group's targets is :func:`~madexplorer.core.jit.python_sum`
  (compensated); of a harvest pair it is ``0.0 + a + b`` (equal for two terms);
- ``ndarray.sum()`` of a group's effective labor is :func:`~madexplorer.core.jit.numpy_sum`;
- ``max(x, 0.0)`` and ``min(x, c)`` keep Python's argument-order semantics;
- groups are processed in order and deplete the shared per-cell stocks in place, as
  successive species in one cell did.
"""

import math

import numpy as np

from madexplorer.core.jit import kernel, numpy_sum, python_sum
from madexplorer.economy.foraging import SOLVER_MAX_NEWTON, SOLVER_TOLERANCE


@kernel
def _harvest_pair(
    a_p: float, a_g: float, r_p: float, r_g: float, effort: float
) -> tuple[float, float]:
    w_p = r_p * a_p
    w_g = r_g * a_g
    total = w_p + w_g
    if total <= 0 or effort <= 0:
        return 0.0, 0.0
    h_p = a_p * -math.expm1(-r_p * effort * w_p / total / a_p) if a_p > 0 else 0.0
    h_g = a_g * -math.expm1(-r_g * effort * w_g / total / a_g) if a_g > 0 else 0.0
    return h_p, h_g


@kernel
def _harvest_total(a_p: float, a_g: float, r_p: float, r_g: float, effort: float) -> float:
    h_p, h_g = _harvest_pair(a_p, a_g, r_p, r_g, effort)
    return 0.0 + h_p + h_g  # Python's sum() of the pair


@kernel
def _marginal(a_p: float, a_g: float, r_p: float, r_g: float, effort: float) -> float:
    w_p = r_p * a_p
    w_g = r_g * a_g
    total = w_p + w_g
    if total <= 0:
        return 0.0
    marginal = 0.0
    if a_p > 0:
        share = w_p / total
        marginal += r_p * share * math.exp(-r_p * share * effort / a_p)
    if a_g > 0:
        share = w_g / total
        marginal += r_g * share * math.exp(-r_g * share * effort / a_g)
    return marginal


@kernel
def _effort_fraction(
    a_p: float, a_g: float, r_p: float, r_g: float, capacity: float, target: float
) -> float:
    effort = 0.0
    for _ in range(SOLVER_MAX_NEWTON):
        gap = _harvest_total(a_p, a_g, r_p, r_g, effort) - target
        if abs(gap) <= SOLVER_TOLERANCE * target:
            return effort / capacity
        slope = _marginal(a_p, a_g, r_p, r_g, effort)
        if slope <= 0:
            break
        step = effort - gap / slope
        step = 0.0 if step < 0.0 else step  # max(step, 0.0)
        effort = capacity if capacity < step else step  # min(step, capacity)
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _harvest_total(a_p, a_g, r_p, r_g, capacity * mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi


@kernel
def forage_groups(
    rows: np.ndarray,  # (R,) int64 unit rows, grouped
    bounds: np.ndarray,  # (G + 1,) int64 positions in rows
    group_cell: np.ndarray,  # (G,) int64
    group_code: np.ndarray,  # (G,) int64 species codes
    labor: np.ndarray,  # (U,) float64 per unit row
    efficiency: np.ndarray,  # (U,) float64
    target_share: np.ndarray,  # (U,) float64
    plant_left: np.ndarray,  # (cells,) float64, depleted in place
    game_left: np.ndarray,  # (cells,) float64, depleted in place
    plant_access: np.ndarray,  # (species, cells) float64
    game_access: np.ndarray,
    plant_return: np.ndarray,
    game_return: np.ndarray,
    harvest_out: np.ndarray,  # (R,) float64
    hours_out: np.ndarray,  # (R,)
    marginal_out: np.ndarray,  # (R,)
    plant_removed: np.ndarray,  # (G,)
    game_removed: np.ndarray,  # (G,)
    effective: np.ndarray,  # scratch, at least the largest group
    terms: np.ndarray,  # scratch, at least the largest group
) -> None:
    for g in range(group_cell.size):
        cell = group_cell[g]
        code = group_code[g]
        lo = bounds[g]
        m = bounds[g + 1] - lo
        a_p = plant_left[cell] * plant_access[code, cell]
        a_g = game_left[cell] * game_access[code, cell]
        r_p = plant_return[code, cell]
        r_g = game_return[code, cell]
        if m == 1:  # single_unit_harvest
            r = rows[lo]
            hours = labor[r]
            eff = efficiency[r]
            target = 0.0 + target_share[r]
            capacity = hours * eff
            if capacity <= 0:
                share, plant, game, fraction = 0.0, 0.0, 0.0, 0.0
                marginal = _marginal(a_p, a_g, r_p, r_g, 0.0)
            else:
                fraction = 1.0
                if _harvest_total(a_p, a_g, r_p, r_g, capacity) > target:
                    fraction = _effort_fraction(a_p, a_g, r_p, r_g, capacity, target)
                plant, game = _harvest_pair(a_p, a_g, r_p, r_g, capacity * fraction)
                share = (plant + game) * capacity / capacity
                marginal = _marginal(a_p, a_g, r_p, r_g, capacity * fraction)
            harvest_out[lo] = share
            hours_out[lo] = hours * fraction
            marginal_out[lo] = marginal * eff
        else:  # cell_harvest
            for k in range(m):
                r = rows[lo + k]
                effective[k] = labor[r] * efficiency[r]
                terms[k] = target_share[r]
            capacity = numpy_sum(effective, 0, m)  # effective.sum()
            target = python_sum(terms, 0, m)  # sum([target_share[r] for r in members])
            if capacity <= 0:
                plant, game, fraction = 0.0, 0.0, 0.0
                marginal = _marginal(a_p, a_g, r_p, r_g, 0.0)
                for k in range(m):
                    harvest_out[lo + k] = 0.0
            else:
                fraction = 1.0
                if _harvest_total(a_p, a_g, r_p, r_g, capacity) > target:
                    fraction = _effort_fraction(a_p, a_g, r_p, r_g, capacity, target)
                plant, game = _harvest_pair(a_p, a_g, r_p, r_g, capacity * fraction)
                removed = 0.0 + plant + game  # removal.sum() of two elements
                for k in range(m):
                    harvest_out[lo + k] = removed * effective[k] / capacity
                marginal = _marginal(a_p, a_g, r_p, r_g, capacity * fraction)
            for k in range(m):
                r = rows[lo + k]
                hours_out[lo + k] = labor[r] * fraction
                marginal_out[lo + k] = marginal * efficiency[r]
        plant_left[cell] -= plant
        game_left[cell] -= game
        plant_removed[g] = plant
        game_removed[g] = game
