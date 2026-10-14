"""Donor routing in food provisioning (MVP 3 Stage 5H). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §AA. Counterfactual only: no
simulator path calls this module, it registers no model rule, and its parameters are not
scenario settings. Authoritative trade, ties, food and demography are unchanged.

:func:`match` is the greedy matching of ``TradeSubsystem.evaluate`` on its recorded inputs:

- recipients in ascending ``(balance / need, unit id, deficit, need)``, i.e. the most
  severe relative deficit first and ties broken by unit id;
- for each recipient, donors with a positive *remaining* offer, in ascending
  ``(path cost, donor id)`` (``H0``, nearest first);
- ``sent = min(offer_remaining, remaining / f)``, ``received = sent * f``,
  ``f = exp(-cost / transport_decay_km)``.

Routing variants change only the donor order, never eligibility, offers, deficits,
transport or the recipient order:

- ``H1`` (``weight = 1``): stronger pre-trade tie first, then nearest, then id;
- ``H2`` (``0 < weight < 1``): ascending ``(1 - weight) * cost / range - weight * t / (1 + t)``
  with ``t`` the pre-trade tie, then cost, then id. ``weight = 0`` is exactly ``H0``.

A tie is a routing input here, not a claim that any unit prefers a partner.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

Deficit = tuple[float, str, float, float]  # (balance / need, recipient id, deficit, need)


@dataclass(frozen=True)
class Candidate:
    """A donor still able to give when the recipient is served."""

    donor: str
    cost: float
    offer: float  # remaining offer (kcal shipped)
    deliverable: float  # offer * delivered fraction
    tie: float


@dataclass(frozen=True)
class Decision:
    """The state at which one recipient is served."""

    recipient: str
    need: float
    deficit: float  # the recipient's whole pre-trade deficit (all of it is still open)
    candidates: tuple[Candidate, ...]  # in the routing order used


@dataclass
class Match:
    transfers: list[tuple[str, str, float, float]] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)

    def received(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for _d, r, _s, got in self.transfers:
            out[r] += got
        return dict(out)

    def sent(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for d, _r, s, _got in self.transfers:
            out[d] += s
        return dict(out)

    def totals(self) -> tuple[float, float]:
        """(shipped, delivered) kcal."""
        return sum(t[2] for t in self.transfers), sum(t[3] for t in self.transfers)


def delivered(cost: float, decay_km: float) -> float:
    """``trade.delivered_fraction``."""
    return math.exp(-cost / decay_km)


def order_key(
    cost: float, donor: str, tie: float, weight: float, range_km: float
) -> tuple[float, float, str]:
    """Donor priority (ascending). ``weight = 0`` sorts exactly as ``(cost, id)``."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError(f"weight must be in [0, 1], got {weight!r}")
    if tie < 0.0:
        raise ValueError("ties are nonnegative")
    if weight == 0.0:
        return (cost, 0.0, donor)
    if weight == 1.0:
        return (-tie, cost, donor)
    return ((1.0 - weight) * cost / range_km - weight * tie / (1.0 + tie), cost, donor)


def match(
    deficits: list[Deficit],
    offers: dict[str, float],
    donors_of: dict[str, list[tuple[float, str]]],
    decay_km: float,
    ties: dict[str, dict[str, float]] | None = None,
    weight: float = 0.0,
    range_km: float = 60.0,
    record: bool = False,
) -> Match:
    """Greedy provisioning on recorded inputs (see the module docstring). ``donors_of[r]``
    lists ``(cost, donor)`` for every offering same-species donor reachable from ``r``."""
    remaining_offer = dict(offers)
    ties = ties or {}
    out = Match()
    for _, rid, deficit, need in sorted(deficits):
        tie_of = ties.get(rid, {})
        ordered = sorted(
            donors_of.get(rid, ()),
            key=lambda cd: order_key(cd[0], cd[1], tie_of.get(cd[1], 0.0), weight, range_km),
        )
        if record:
            out.decisions.append(
                Decision(
                    rid,
                    need,
                    deficit,
                    tuple(
                        Candidate(
                            d,
                            c,
                            remaining_offer[d],
                            remaining_offer[d] * delivered(c, decay_km),
                            tie_of.get(d, 0.0),
                        )
                        for c, d in ordered
                        if remaining_offer[d] > 0
                    ),
                )
            )
        left = deficit
        for cost, did in ordered:
            if left <= 0:
                break
            if remaining_offer[did] <= 0:
                continue
            fraction = delivered(cost, decay_km)
            sent = min(remaining_offer[did], left / fraction)
            remaining_offer[did] -= sent
            left -= sent * fraction
            out.transfers.append((did, rid, sent, sent * fraction))
    return out


def without(offers: dict[str, float], donor: str) -> dict[str, float]:
    """The same offers with one donor withheld (network rematching, same year)."""
    return {**offers, donor: 0.0}


def local_replacement(decision: Decision, primary: str, taken: float) -> float:
    """Share of ``taken`` (what ``primary`` delivered) that the *other* candidates at the
    recipient's decision could deliver from their remaining offers, all other allocations
    unchanged. Capped at 1."""
    if taken <= 0:
        return 1.0
    others = sum(c.deliverable for c in decision.candidates if c.donor != primary)
    return min(others / taken, 1.0)


def choice_levels(decision: Decision, useful: float) -> dict[str, bool]:
    """Donor-choice availability at one decision. ``useful`` is the fraction of the
    recipient's deficit a donor must be able to deliver to count as materially useful."""
    deliver = [c.deliverable for c in decision.candidates]
    need = decision.deficit
    return {
        "nominal": len(deliver) >= 2,
        "effective": sum(d >= useful * need for d in deliver) >= 2,
        "full": sum(d >= need for d in deliver) >= 2,
    }
