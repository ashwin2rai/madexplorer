"""Entry costs and participation continuity (MVP 3 Stage 5C). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §V. Counterfactual only: no simulator
path calls this module, it registers no model rule, and its parameters are not scenario
settings. The authoritative cultivation labor, learning and strata are unchanged.

Labor (audited, as in §U): capacity ``C``, last year's clearing debt ``D``, productive
cultivation hours ``P = min(fields x hours/ha, m x max(C - D, 0))``; ``L = C / (hours/day x
365)`` labor-equivalents. A share ``x`` of the unit can supply at most ``x m (C - D)``
cultivation hours.

- **Entry cost (the hypothesis under test).** A labor-equivalent that begins (or resumes)
  cultivation spends ``e`` extra hours that year inside the same budget; a continuing
  participant does not. Unlike the recurring overhead of §U it is paid once per entry, not
  every year.
- **Participation memory.** Whether a person still counts as a continuing participant
  depends on the years ``since`` its last participating year (1 = participated last year,
  ``inf`` = never): an entry-cost *factor* ``phi(since)`` in [0, 1] scales ``e``
  (:func:`entry_factor`). Memory is a hypothesis, not a model state.
- **Allocation.** This year's participants are a share ``take_i`` of each component.
  Feasibility: ``sum take_i (m (C - D) - e L phi_i) >= P``; entry labor ``e L sum take_i
  phi_i``. Minimizing entry labor fills components in ascending ``phi`` (cheapest first; a
  cheaper component also adds more capacity, so greedy is optimal) up to the smallest
  feasible share. Equal-cost components are taken in proportion to their shares, so the
  result never depends on component order or identity (:func:`allocate`).
- **Corner.** With no history every component has ``phi = 1`` and the minimum-entry share is
  ``P / (m (C - D) - e L)``: §U's overhead corner with ``o = e``. Incumbents beyond need cost
  nothing to keep or to drop: the optimum is then an interval (``indifferent``).
"""

from dataclasses import dataclass

import numpy as np

from madexplorer.core.types import FloatArray

NEVER = float("inf")


@dataclass(frozen=True)
class Memory:
    """How long participation lowers the entry cost.

    ``window``: no entry cost while ``since <= years`` (``years = 1``: immediate expiry, only
    last year's participants), full cost after. ``decay``: the factor rises as
    ``1 - 2 ** (-(since - 1) / years)`` (half the cost after ``years`` idle years)."""

    kind: str = "window"
    years: float = 1.0

    def __post_init__(self) -> None:
        if self.kind not in ("window", "decay"):
            raise ValueError(f"memory kind must be 'window' or 'decay', got {self.kind!r}")
        if not self.years > 0:
            raise ValueError(f"memory years must be positive, got {self.years!r}")


def entry_factor(since: FloatArray, memory: Memory) -> FloatArray:
    """Entry-cost factor in [0, 1] for components last active ``since`` years ago."""
    s = np.asarray(since, dtype=np.float64)
    if np.any(s < 1):
        raise ValueError("since counts years since the last participating year (>= 1)")
    if memory.kind == "window":
        factor: FloatArray = np.where(s <= memory.years, 0.0, 1.0)
        return factor
    finite = np.isfinite(s)
    idle = np.where(finite, s - 1.0, 0.0)
    decayed = 1.0 - np.exp2(-idle / memory.years)
    factor = np.where(finite, decayed, 1.0)
    return factor


@dataclass(frozen=True)
class Allocation:
    """One year's participation. ``take[i]`` is the share of the unit drawn from component
    ``i``. ``entrants`` is the cost-weighted entering share ``sum take_i phi_i`` and
    ``entry_hours = e L entrants``. Without cultivation nothing is taken. ``feasible`` is
    False when even full participation cannot cover ``P`` plus the entry labor; then
    everyone participates and ``shortfall_hours`` is the uncovered remainder (labor the
    counterfactual would have to displace). ``free`` is the share that could additionally
    participate at no entry cost (``phi = 0`` components not taken): the optimum is the
    interval ``[participating, participating + free]`` when it is positive."""

    take: FloatArray
    participating: float
    entrants: float
    entry_hours: float
    feasible: bool
    shortfall_hours: float
    free: float


def _check(productive: float, capacity: float, debt: float, max_share: float) -> None:
    for name, value in (("productive_hours", productive), ("capacity", capacity), ("debt", debt)):
        if not value >= 0.0:
            raise ValueError(f"{name} must be nonnegative, got {value!r}")
    if not 0.0 < max_share <= 1.0:
        raise ValueError(f"max_share must be in (0, 1], got {max_share!r}")


def allocate(
    shares: FloatArray,
    factors: FloatArray,
    productive_hours: float,
    capacity: float,
    debt: float,
    max_share: float,
    entry_hours: float,
    labor_equivalents: float,
    rank: FloatArray | None = None,
) -> Allocation:
    """Smallest feasible participation drawn in ascending ``rank`` (default: the entry-cost
    ``factors``, i.e. minimum entry labor). Components with equal rank form one tie group,
    taken in proportion to their shares. A group that adds no net capacity (its entry cost
    exceeds its cultivation budget) is skipped. Inputs are not modified."""
    _check(productive_hours, capacity, debt, max_share)
    if not entry_hours >= 0.0 or not labor_equivalents >= 0.0:
        raise ValueError("entry_hours and labor_equivalents must be nonnegative")
    shares = np.asarray(shares, dtype=np.float64)
    phi = np.asarray(factors, dtype=np.float64)
    if shares.shape != phi.shape:
        raise ValueError("shares and factors must have the same shape")
    take = np.zeros(shares.shape)
    zero = phi == 0.0
    if productive_hours == 0.0:
        return Allocation(take, 0.0, 0.0, 0.0, True, 0.0, 0.0)
    budget = max_share * max(capacity - debt, 0.0)
    unit_cost = entry_hours * labor_equivalents
    net = budget - unit_cost * phi  # cultivation hours one unit of share adds, net of entry
    key = phi if rank is None else np.asarray(rank, dtype=np.float64)
    need = productive_hours
    for value in np.unique(key):  # ascending; equal keys tie
        group = (key == value) & (net > 0.0) & (shares > 0.0)
        supply = float((shares[group] * net[group]).sum())
        if supply <= 0.0:
            continue
        if supply >= need:
            take[group] = shares[group] * (need / supply)
            need = 0.0
            break
        take[group] = shares[group]
        need -= supply
    feasible = need <= 1e-9 * productive_hours
    if not feasible:
        take = shares.copy()
    entrants = float((take * phi).sum())
    free = float((shares[zero] - take[zero]).sum())
    return Allocation(
        take,
        float(take.sum()),
        entrants,
        unit_cost * entrants,
        feasible,
        need if not feasible else 0.0,
        free,
    )


def spread_allocation(
    shares: FloatArray,
    factors: FloatArray,
    productive_hours: float,
    capacity: float,
    debt: float,
    max_share: float,
    entry_hours: float,
    labor_equivalents: float,
    everyone: bool,
) -> Allocation:
    """History-blind participation: the same fraction of every component. ``everyone``:
    the whole unit (proportional participation, M0); otherwise the smallest feasible common
    fraction (rotation, M1: who participates is redrawn each year in proportion)."""
    _check(productive_hours, capacity, debt, max_share)
    shares = np.asarray(shares, dtype=np.float64)
    phi = np.asarray(factors, dtype=np.float64)
    if productive_hours == 0.0:
        return Allocation(np.zeros(shares.shape), 0.0, 0.0, 0.0, True, 0.0, 0.0)
    budget = max_share * max(capacity - debt, 0.0)
    unit_cost = entry_hours * labor_equivalents
    supply = float((shares * (budget - unit_cost * phi)).sum())
    fraction = 1.0 if everyone or supply <= productive_hours else productive_hours / supply
    take = shares * fraction
    shortfall = max(productive_hours - fraction * supply, 0.0)
    feasible = shortfall <= 1e-9 * productive_hours
    entrants = float((take * phi).sum())
    zero = phi == 0.0
    return Allocation(
        take,
        float(take.sum()),
        entrants,
        unit_cost * entrants,
        feasible,
        shortfall if not feasible else 0.0,
        float((shares[zero] - take[zero]).sum()),
    )


def retain_incumbents(
    allocation: Allocation, shares: FloatArray, factors: FloatArray
) -> FloatArray:
    """The allocation with every zero-cost component kept in full (status quo: the upper end
    of the indifference interval). A choice, not implied by the cost."""
    take = allocation.take.copy()
    zero = np.asarray(factors) == 0.0
    take[zero] = np.asarray(shares, dtype=np.float64)[zero]
    return take


@dataclass(frozen=True)
class Components:
    """Shadow mixture components of one unit (all arrays aligned)."""

    share: FloatArray
    competence: FloatArray
    since: FloatArray
    participating: np.ndarray


def split_participation(components: Components, take: FloatArray) -> Components:
    """Split each component into its participating part (``take``) and the rest; a
    component wholly in or out is not split. Shares, share-weighted competence and each
    part's history are conserved; the input is not modified."""
    share = components.share
    take = np.clip(np.asarray(take, dtype=np.float64), 0.0, share)
    tol = 1e-15 * np.maximum(share, 1e-300)
    whole = take >= share - tol
    none = take <= tol
    partial = ~whole & ~none
    keep_share = np.where(partial, take, share)
    keep_part = whole | partial
    rest = np.flatnonzero(partial)
    return Components(
        np.concatenate([keep_share, share[rest] - take[rest]]),
        np.concatenate([components.competence, components.competence[rest]]),
        np.concatenate([components.since, components.since[rest]]),
        np.concatenate([keep_part, np.zeros(rest.size, bool)]),
    )


def advance_history(components: Components) -> Components:
    """End of year: participants were last active this year (``since = 1`` next year), the
    rest are one year further away."""
    since = np.where(components.participating, 1.0, components.since + 1.0)
    return Components(
        components.share.copy(),
        components.competence.copy(),
        since,
        components.participating.copy(),
    )


def turnover(components: Components, rate: float) -> Components:
    """Demographic replacement: a share ``rate`` of every component with a participation
    history is people new to work this year, without that history (``since = inf``). They
    inherit the component's competence (strata share the age structure; a stated
    approximation). Shares and competence are conserved."""
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"rate must be in [0, 1], got {rate!r}")
    had = np.isfinite(components.since) & (components.share > 0.0)
    if rate == 0.0 or not had.any():
        return components
    idx = np.flatnonzero(had)
    moved = components.share[idx] * rate
    share = components.share.copy()
    share[idx] -= moved
    return Components(
        np.concatenate([share, moved]),
        np.concatenate([components.competence, components.competence[idx]]),
        np.concatenate([components.since, np.full(idx.size, NEVER)]),
        np.concatenate([components.participating, np.zeros(idx.size, bool)]),
    )
