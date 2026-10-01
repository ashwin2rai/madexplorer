"""Compiled field planning: every unit's desired fields and every cell's arable sharing (PH4a).

The model is :mod:`madexplorer.economy.agriculture` (``expected_tenure_years``,
``clearing_hours_per_ha``, ``fields_toward_target``, ``adjusted_fields_ha`` and
``FieldPlanningSubsystem._evaluate_reference``). This module transcribes those scalar
rules operation by operation (Level A; differential tests against the Python path):

- Python's ``min``/``max`` keep their argument-order semantics (the first extreme wins);
- ``p ** H`` with an integer ``H`` is C ``pow``, as Python's float power;
- the per-cell ``sum()`` of desired fields is the compensated builtin
  (:func:`~madexplorer.core.jit.python_sum`).
"""

import math

import numpy as np

from madexplorer.core.jit import kernel, python_sum


@kernel
def _max2(a: float, b: float) -> float:
    return b if b > a else a  # Python max(a, b)


@kernel
def _min2(a: float, b: float) -> float:
    return b if b < a else a  # Python min(a, b)


@kernel
def _clearing_hours_per_ha(
    vegetation: float, clearing_hours: float, multiplier: float, efficiency: float
) -> float:
    raw = clearing_hours * (1.0 + multiplier * vegetation)
    return raw / _max2(efficiency, 1e-6)


@kernel
def _expected_tenure(move_hazard: float, horizon: int, residence: int) -> float:
    if math.isnan(move_hazard):
        r = residence if residence > 1 else 1  # min(max(residence, 1), horizon)
        return float(horizon if horizon < r else r)
    p = _min2(_max2(1.0 - move_hazard, 0.0), 1.0)
    if 1.0 - p < 1e-9:
        return float(horizon)
    return p * (1.0 - math.pow(p, float(horizon))) / (1.0 - p)


@kernel
def _return_gap(value: float, threshold: float) -> float:
    m = value
    if threshold > m:
        m = threshold
    if m < 1e-9:
        m = 1e-9
    return (value - threshold) / m  # (value - threshold) / max(value, threshold, 1e-9)


@kernel
def plan_fields(
    yields: np.ndarray,  # (U,) float64 per row
    labor: np.ndarray,
    needs: np.ndarray,
    population: np.ndarray,  # (U,) int64
    fields_now: np.ndarray,
    marginal: np.ndarray,
    residence: np.ndarray,  # (U,) int64
    hazard: np.ndarray,
    cells: np.ndarray,  # (U,) int64
    species: np.ndarray,  # (U,) int64
    clearing_efficiency: np.ndarray,
    vegetation: np.ndarray,  # (cells,) float64
    arable: np.ndarray,  # (cells,) float64
    order: np.ndarray,  # spatial index: rows in cell order
    starts: np.ndarray,
    index_cells: np.ndarray,
    # per species (compiled order)
    horizon: np.ndarray,  # int64
    max_farm_labor_share: np.ndarray,
    surplus_target: np.ndarray,
    adjustment_rate: np.ndarray,
    margin: np.ndarray,
    initial_plot_ha: np.ndarray,
    # scenario configuration
    cultivation_hours_per_ha: float,
    clearing_hours_per_ha: float,
    clearing_vegetation_multiplier: float,
    expected_tenure: bool,
    growth_to_target: bool,
    # outputs (capacity U); returns the number of plans
    plan_rows: np.ndarray,
    plan_fields: np.ndarray,
    plan_clearing: np.ndarray,
    plan_return: np.ndarray,
    plan_marginal: np.ndarray,
    plan_gap: np.ndarray,
    desired: np.ndarray,  # scratch (U,)
    farm_return: np.ndarray,  # scratch (U,)
    gaps: np.ndarray,  # scratch (U,)
    terms: np.ndarray,  # scratch, at least the largest cell
) -> int:
    cult = cultivation_hours_per_ha
    for i in range(yields.size):
        yield_per_ha = yields[i]
        farm_return[i] = yield_per_ha / cult
        if yield_per_ha <= 0 or population[i] == 0:
            desired[i] = 0.0
            gaps[i] = -1.0
            continue
        s = species[i]
        clearing = _clearing_hours_per_ha(
            vegetation[cells[i]],
            clearing_hours_per_ha,
            clearing_vegetation_multiplier,
            clearing_efficiency[i],
        )
        h = horizon[s]
        if expected_tenure:
            tenure = _expected_tenure(hazard[i], h, residence[i])
        else:
            r = residence[i] if residence[i] > 1 else 1
            tenure = float(h if h < r else r)
        share = max_farm_labor_share[s]
        farm_labor = share * labor[i]
        labor_cap = farm_labor / cult
        need_cap = needs[i] * (1.0 + surplus_target[s]) / yield_per_ha
        f_now = fields_now[i]
        threshold = marginal[i] * (1.0 + margin[s])
        new_land_return = yield_per_ha / (cult + clearing / _max2(tenure, 1.0))
        expand_gap = _return_gap(new_land_return, threshold)
        rate = adjustment_rate[s]
        if growth_to_target:  # fields_toward_target
            if expand_gap > 0:
                target_step = rate * (need_cap - f_now)
                labor_step = _max2(farm_labor - f_now * cult, 0.0) / (share * clearing + cult)
                step = _min2(target_step, labor_step)
                if step <= 0:
                    fields, gap = f_now, expand_gap
                else:
                    fields, gap = f_now + step, expand_gap
            else:
                keep_gap = _return_gap(yield_per_ha / cult, threshold)
                if keep_gap < 0 and f_now > 0:
                    fields, gap = f_now * (1.0 + rate * _max2(keep_gap, -1.0)), keep_gap
                else:
                    fields, gap = f_now, 0.0
        elif expand_gap > 0:  # adjusted_fields_ha
            fields = f_now + rate * expand_gap * (f_now + initial_plot_ha[s])
            gap = expand_gap
        else:
            keep_gap = _return_gap(yield_per_ha / cult, threshold)
            if keep_gap < 0 and f_now > 0:
                fields, gap = f_now * (1.0 + rate * _max2(keep_gap, -1.0)), keep_gap
            else:
                fields, gap = f_now, 0.0
        best = fields  # min(fields, labor_cap, need_cap)
        if labor_cap < best:
            best = labor_cap
        if need_cap < best:
            best = need_cap
        desired[i] = best
        gaps[i] = gap
    count = 0
    for k in range(index_cells.size):
        cell = index_cells[k]
        lo, hi = starts[k], starts[k + 1]
        for j in range(lo, hi):
            terms[j - lo] = desired[order[j]]
        total = python_sum(terms, 0, hi - lo)
        scale = _min2(1.0, arable[cell] / total) if total > 0 else 1.0
        for j in range(lo, hi):
            r = order[j]
            fields = desired[r] * scale
            if fields < 0.05:
                fields = 0.0
            expansion = _max2(fields - fields_now[r], 0.0)
            clearing = 0.0
            if expansion > 0:
                per_ha = _clearing_hours_per_ha(
                    vegetation[cell],
                    clearing_hours_per_ha,
                    clearing_vegetation_multiplier,
                    clearing_efficiency[r],
                )
                clearing = expansion * per_ha
            if fields != fields_now[r]:
                plan_rows[count] = r
                plan_fields[count] = fields
                plan_clearing[count] = clearing
                plan_return[count] = farm_return[r]
                plan_marginal[count] = marginal[r]
                plan_gap[count] = gaps[r]
                count += 1
    return count
