"""Simultaneous provisioning feasibility (MVP 3 Stage 6B-P3). NOT ACTIVE.

Design: ``objective/STAGE6B_SOCIOECOLOGICAL_MECHANISM_REVIEW.md`` §17. An analyst's
counterfactual, not an agent rule: no simulator path calls this module, it registers no
model rule, and nothing here is a scenario setting. It needs SciPy (HiGHS), a development
dependency, imported only when :func:`solve` runs.

One trade year is a bipartite problem on recorded inputs. Donor ``i`` can ship at most its
budget ``O_i`` (the production offer ``phi * b_i``, or the full surplus ``b_i``); recipient
``j`` can use at most its deficit ``D_j = -b_j``; an eligible edge ``(i, j)`` (same species,
donor reachable from the recipient's cell, as in ``TradeSubsystem.evaluate``) delivers the
fraction ``f_ij = exp(-cost_ij / transport_decay_km)`` of what is shipped. With shipments
``x_ij >= 0``::

    maximize  sum_ij f_ij x_ij
    s.t.      sum_j x_ij        <= O_i   (donor budget)
              sum_i f_ij x_ij   <= D_j   (recipient deficit)

The optimum is the most food the offers can deliver *simultaneously*; the greedy matching
(``provisioning_counterfactual.match``) is one feasible point, not the bound. Every solution
is checked outside the solver (:func:`check`): feasibility within :data:`FEAS_TOL`, and
optimality by LP duality, i.e. the solver's duals ``y >= 0`` must satisfy
``y_i + f_ij y_j >= f_ij`` on every edge and close the gap ``|sum f x - sum b y|`` within
:data:`GAP_TOL` (both relative to the problem's largest budget or deficit). A failed solve or
check raises; no heuristic result is ever substituted.

The aggregate optimum is generally not unique in who receives food. :func:`solve` with
``priority`` returns, among allocations within :data:`GAP_TOL` of the optimum, one that
maximizes ``sum_j priority_j * received_j``: a labelled tie-break for sensitivity analysis,
not a distribution rule.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np

Edge = tuple[str, str, float]  # (donor, recipient, delivered fraction)
FEAS_TOL = 1e-9  # budget / deficit violation allowed, relative to the problem scale
GAP_TOL = 1e-7  # duality gap and dual infeasibility allowed, relative to the problem scale
# HiGHS's own feasibility tolerances (defaults 1e-7), tighter than FEAS_TOL so that its
# solutions pass the independent check.
HIGHS = {"primal_feasibility_tolerance": 1e-10, "dual_feasibility_tolerance": 1e-10}


class FeasibilityError(RuntimeError):
    """The solver failed or its solution did not pass the independent checks."""


@dataclass(frozen=True)
class Allocation:
    """Shipments ``x`` per edge (kcal shipped) and what they deliver."""

    edges: tuple[Edge, ...]
    shipped: tuple[float, ...]
    gap: float = 0.0  # relative duality gap (0 for an empty problem)

    @property
    def delivered(self) -> float:
        return sum(f * x for (_, _, f), x in zip(self.edges, self.shipped, strict=True))

    def received(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for (_, r, f), x in zip(self.edges, self.shipped, strict=True):
            out[r] = out.get(r, 0.0) + f * x
        return out

    def sent(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for (d, _, _), x in zip(self.edges, self.shipped, strict=True):
            out[d] = out.get(d, 0.0) + x
        return out


def edges_from(
    donors_of: Mapping[str, Iterable[tuple[float, str]]], decay_km: float, lossless: bool = False
) -> list[Edge]:
    """Edges from the recorded reachable donors ``donors_of[r] = [(cost, donor), ...]``."""
    return [
        (d, r, 1.0 if lossless else math.exp(-cost / decay_km))
        for r, cands in donors_of.items()
        for cost, d in cands
    ]


def usable(
    offers: Mapping[str, float], deficits: Mapping[str, float], edges: Iterable[Edge]
) -> list[Edge]:
    """Edges that can carry food: positive budget, positive deficit, ``f > 0``."""
    return [
        e for e in edges if offers.get(e[0], 0.0) > 0 and deficits.get(e[1], 0.0) > 0 and e[2] > 0
    ]


def components(edges: Iterable[Edge]) -> list[tuple[set[str], set[str]]]:
    """Connected ``(donors, recipients)`` groups of the edge graph (independent problems)."""
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for d, r, _ in edges:
        parent[root("d:" + d)] = root("r:" + r)
    groups: dict[str, tuple[set[str], set[str]]] = {}
    for node in list(parent):
        donors, recipients = groups.setdefault(root(node), (set(), set()))
        (donors if node.startswith("d:") else recipients).add(node[2:])
    return list(groups.values())


def _scale(offers: Mapping[str, float], deficits: Mapping[str, float]) -> float:
    return max([1.0, *offers.values(), *deficits.values()])


def check(
    offers: Mapping[str, float],
    deficits: Mapping[str, float],
    allocation: Allocation,
    eligible: Iterable[Edge],
) -> None:
    """Raise unless ``allocation`` is feasible: eligible edges only, ``x >= 0``, budgets and
    deficits respected (within :data:`FEAS_TOL` of the problem scale)."""
    tol = FEAS_TOL * _scale(offers, deficits)
    allowed = {(d, r): f for d, r, f in eligible}
    for (d, r, f), x in zip(allocation.edges, allocation.shipped, strict=True):
        if allowed.get((d, r)) != f:
            raise FeasibilityError(f"shipment on an ineligible edge {d} -> {r} (f={f})")
        if x < 0:
            raise FeasibilityError(f"negative shipment {x} on {d} -> {r}")
    for d, s in allocation.sent().items():
        if s > offers.get(d, 0.0) + tol:
            raise FeasibilityError(f"donor {d} ships {s} > budget {offers.get(d, 0.0)}")
    for r, g in allocation.received().items():
        if g > deficits.get(r, 0.0) + tol:
            raise FeasibilityError(f"recipient {r} receives {g} > deficit {deficits.get(r, 0.0)}")


def solve(
    offers: Mapping[str, float],
    deficits: Mapping[str, float],
    edges: Iterable[Edge],
    priority: Mapping[str, float] | None = None,
) -> Allocation:
    """The maximum simultaneous delivery (see the module docstring), checked."""
    from scipy.optimize import linprog
    from scipy.sparse import csr_array, vstack

    live = usable(offers, deficits, edges)
    if not live:
        return Allocation((), ())
    scale = _scale(offers, deficits)
    donors = sorted({d for d, _, _ in live})
    recipients = sorted({r for _, r, _ in live})
    row = {
        **{d: k for k, d in enumerate(donors)},
        **{r: len(donors) + k for k, r in enumerate(recipients)},
    }
    f = np.array([e[2] for e in live])
    cols = np.arange(len(live))
    a = csr_array(
        (
            np.r_[np.ones(len(live)), f],
            (np.r_[[row[d] for d, _, _ in live], [row[r] for _, r, _ in live]], np.r_[cols, cols]),
        ),
        shape=(len(row), len(live)),
    )
    b = np.array([offers[d] for d in donors] + [deficits[r] for r in recipients]) / scale
    res = linprog(-f, A_ub=a, b_ub=b, bounds=(0, None), method="highs", options=HIGHS)
    if res.status != 0:
        raise FeasibilityError(f"HiGHS status {res.status}: {res.message}")
    x = np.maximum(res.x, 0.0)
    y = -res.ineqlin.marginals  # duals of the (min -f x) problem, >= 0
    best = float(f @ x)
    gap = abs(best - float(b @ y))
    slack = float(np.max(f - a.T @ y, initial=0.0))
    if gap > GAP_TOL or slack > GAP_TOL or float(np.min(y, initial=0.0)) < -GAP_TOL:
        raise FeasibilityError(
            f"optimality not certified: gap {gap:.3g}, dual infeasibility {slack:.3g}"
        )
    if priority is not None:
        weights = np.array([priority.get(r, 0.0) for _, r, _ in live]) * f
        a2 = vstack([a, csr_array(-f[None, :])], format="csr")
        res2 = linprog(
            -weights,
            A_ub=a2,
            b_ub=np.r_[b, -(best - GAP_TOL)],
            bounds=(0, None),
            method="highs",
            options=HIGHS,
        )
        if res2.status != 0:
            raise FeasibilityError(f"HiGHS status {res2.status} (priority stage): {res2.message}")
        x = np.maximum(res2.x, 0.0)
        if float(f @ x) < best - 2 * GAP_TOL:
            raise FeasibilityError("priority stage lost aggregate delivery")
    out = Allocation(tuple(live), tuple((x * scale).tolist()), gap)
    check(offers, deficits, out, live)
    return out
