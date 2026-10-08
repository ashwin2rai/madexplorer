"""Participation overhead and practice concentration (MVP 3 Stage 5B). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §U. Counterfactual only: no simulator
path calls this module, it registers no model rule, and its parameters are not scenario
settings. The authoritative cultivation labor (``FarmingSubsystem``) and learning
(``learn``) are unchanged.

Authoritative labor (audited): capacity ``C`` (age-weighted adults x hours/day x 365),
clearing debt ``D`` (last year's clearing), productive cultivation hours
``P = min(fields x hours/ha, m x max(C - D, 0))`` with ``m = max_farm_labor_share``.

- **Minimum participating share.** If cultivation is concentrated on a share ``f`` of the
  unit's labor (strata share the age structure, so a population share is a labor share),
  each participant may devote at most ``m`` of its post-debt labor, so
  ``f >= P / (m (C - D))``.
- **Participation overhead (the hypothesis under test).** Each participating
  labor-equivalent person (``L = C / (hours/day x 365)`` of them) costs ``o`` extra hours a
  year, spent within the same budget: total cultivation labor ``P + o f L`` and feasibility
  ``m f (C - D) >= P + o f L``. Cost rises linearly in ``f`` for every ``o > 0``, so the
  optimum is always the corner ``f = f_min``; at ``o = 0`` every feasible ``f`` costs the
  same (indifference). Overhead alone is not graded.
- **Diagnostic concentration** ``f(c) = 1 - c (1 - f_min)``: a sensitivity coordinate, not a
  mechanism.
- **Component learning.** Each component learns with the authoritative agriculture rule on its
  own practice ``s_i``; the social-learning term counts the unit's practitioners
  ``N x s_unit`` (unchanged by how the same hours are distributed). With equal practice the
  update is the unit update exactly.
"""

from dataclasses import dataclass

import numpy as np

from madexplorer.core.types import FloatArray


def min_participating_share(
    productive_hours: float,
    capacity: float,
    debt: float,
    max_share: float,
    overhead_hours: float = 0.0,
    labor_equivalents: float = 0.0,
) -> float:
    """Smallest feasible share of the unit's labor that can perform ``productive_hours`` of
    cultivation (0 without cultivation; 1 when everyone is needed or nothing is feasible)."""
    for name, value in (
        ("productive_hours", productive_hours),
        ("capacity", capacity),
        ("debt", debt),
        ("overhead_hours", overhead_hours),
        ("labor_equivalents", labor_equivalents),
    ):
        if not value >= 0.0:
            raise ValueError(f"{name} must be nonnegative, got {value!r}")
    if not 0.0 < max_share <= 1.0:
        raise ValueError(f"max_share must be in (0, 1], got {max_share!r}")
    if productive_hours == 0.0:
        return 0.0
    budget = max_share * max(capacity - debt, 0.0) - overhead_hours * labor_equivalents
    if budget <= productive_hours:
        return 1.0
    return productive_hours / budget


def participation_labor(
    share: float, productive_hours: float, overhead_hours: float, labor_equivalents: float
) -> float:
    """Total cultivation labor ``P + o f L`` when a share ``f`` participates."""
    return productive_hours + overhead_hours * share * labor_equivalents


@dataclass(frozen=True)
class ParticipationOptimum:
    """The labor-minimizing participating share. ``share`` is None when every feasible share
    costs the same (``indifferent``, ``o = 0``); ``corner`` marks the minimum feasible share."""

    share: float | None
    minimum: float
    corner: bool
    indifferent: bool


def optimal_participating_share(
    productive_hours: float,
    capacity: float,
    debt: float,
    max_share: float,
    overhead_hours: float,
    labor_equivalents: float,
) -> ParticipationOptimum:
    """Minimize ``participation_labor`` over feasible shares ``[f_min, 1]``.

    The cost is linear in ``f`` with slope ``o L``: for any ``o > 0`` the minimum is the
    corner ``f_min``; at ``o = 0`` (or no participants to pay for) the cost is flat."""
    f_min = min_participating_share(
        productive_hours, capacity, debt, max_share, overhead_hours, labor_equivalents
    )
    slope = overhead_hours * labor_equivalents
    if slope == 0.0 or productive_hours == 0.0:
        return ParticipationOptimum(None, f_min, corner=False, indifferent=True)
    return ParticipationOptimum(f_min, f_min, corner=True, indifferent=False)


def diagnostic_share(concentration: float, f_min: float) -> float:
    """Participating share at diagnostic concentration ``c`` (0 spread, 1 at ``f_min``)."""
    if not 0.0 <= concentration <= 1.0:
        raise ValueError(f"concentration must be in [0, 1], got {concentration!r}")
    if not 0.0 <= f_min <= 1.0:
        raise ValueError(f"f_min must be in [0, 1], got {f_min!r}")
    return 1.0 - concentration * (1.0 - f_min)


def component_practice(
    unit_practice: float,
    farm_share: float,
    forage_share: float,
    participating: FloatArray,
    shares: FloatArray,
    participant_share: float,
    farm_weight: float,
    forage_weight: float,
) -> FloatArray:
    """Agriculture practice of each component when this year's cultivation is performed by
    the components marked ``participating`` (a share ``participant_share`` of the unit).

    ``farm_share`` and ``forage_share`` are the unit's activity shares (hours / capacity; the
    foraging share already weighted by its plant fraction), ``unit_practice`` the unit's
    practice ``farm_weight * farm_share + forage_weight * forage_share``. Participants farm
    ``farm_share / participant_share``; the remaining labor forages in proportion to what each
    component has left. Deviations are in difference form, so equal participation returns
    ``unit_practice`` exactly."""
    participating = np.asarray(participating, dtype=bool)
    if participating.all() or not participating.any():
        return np.full(shares.shape, unit_practice)
    farm = np.where(participating, farm_share / participant_share, 0.0)
    left = np.maximum(1.0 - farm, 0.0)
    total_left = float((shares * left).sum())
    forage = forage_share * left / total_left if total_left > 0 else np.zeros(shares.shape)
    deviation = farm_weight * (farm - farm_share) + forage_weight * (forage - forage_share)
    practice: FloatArray = unit_practice + deviation
    return practice


def learn_components(
    competence: FloatArray,
    practice: FloatArray,
    unit_practitioners: float,
    learning_speed: float,
    learning_rate: float,
    practitioner_scale: float,
    decay_rate: float,
    retention: float,
) -> FloatArray:
    """One year of the authoritative learning rule (``knowledge.learning.learn``) for each
    component: own practice, the unit's practitioner count, the same operation order."""
    gain = (
        learning_speed
        * learning_rate
        * practice
        * np.log1p(unit_practitioners / practitioner_scale)
    )
    loss = decay_rate / retention * competence
    updated: FloatArray = np.maximum(competence + gain - loss, 0.0)
    return updated


def efficiency(competence: FloatArray | float, half_level: float) -> FloatArray:
    """Agricultural efficiency ``K / (K + K_half)`` (crop yield is proportional to it)."""
    k = np.asarray(competence, dtype=np.float64)
    result: FloatArray = k / (k + half_level)
    return result


def efficiency_slope(competence: FloatArray | float, half_level: float) -> FloatArray:
    """``dE/dK = K_half / (K + K_half)^2``: how much crop yield a competence error moves."""
    k = np.asarray(competence, dtype=np.float64)
    result: FloatArray = half_level / (k + half_level) ** 2
    return result
