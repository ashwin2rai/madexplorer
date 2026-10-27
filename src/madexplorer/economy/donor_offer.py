"""Donor-side decomposition of food provisioning (MVP 3 Stage 6A). NOT ACTIVE.

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §AD. Counterfactual only: no
simulator path calls this module, it registers no model rule, and its parameters are not
scenario settings. Trade, ties, energetics and demography are unchanged.

Production (``economy/trade.py``) in five quantities, per donor-year:

- **physical provisionable surplus** ``b = H + S - N`` (harvest before trade, stores, annual
  need including carried energy debt); a donor has ``b > 0``, a recipient ``b < 0``;
- **behavioral offer** ``o = phi * b`` with ``phi = social.food_sharing_propensity`` (0.3,
  a species parameter): the only behavioral quantity, fixed and unconditional;
- **realized transfer** ``x <= o``: what the recipient-driven matching ships
  (``provisioning_counterfactual.match``); ``o - x`` is an *unused* offer, never a refusal;
- **delivered food** ``x * f``, ``f = exp(-cost / transport_decay_km)``;
- **retained food**: the donor pays from harvest first, then stores (``TradeRound.apply``),
  then energetics accounts the rest (``energy_balance``), and stores spoil to
  ``retention * stores`` at the end of the year.

:func:`giving_cost` splits a shipment into what the donor would have carried into the next
year (body reserve plus retained stores) and what would have been lost anyway (year-end
spoilage), by running the production energy balance with and without the shipment.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from madexplorer.economy.provisioning_counterfactual import Deficit, Match
from madexplorer.population.energetics import energy_balance

EXHAUSTED_REL = 1e-9  # remaining offer below this fraction of the offer counts as used up
DUST_KCAL = 1e-6  # shipments below this are floating-point residues (§AA §1), not transfers


def balances(
    harvest: dict[str, float], stores: dict[str, float], need: dict[str, float]
) -> dict[str, float]:
    """``b = H + S - N`` per unit, in the production operation order."""
    return {u: harvest[u] + stores[u] - need[u] for u in need}


def offers_at(balance: dict[str, float], share: dict[str, float] | float) -> dict[str, float]:
    """Offers of the units with a surplus: ``share * b`` (production at ``share = 0.3``)."""
    if isinstance(share, float):
        return {u: share * b for u, b in balance.items() if b > 0}
    return {u: share[u] * b for u, b in balance.items() if b > 0}


def deficits_of(balance: dict[str, float], need: dict[str, float]) -> list[Deficit]:
    """Recipients: ``b < 0`` and ``N > 0``, as the production sort tuple."""
    return [(b / need[u], u, -b, need[u]) for u, b in balance.items() if b < 0 and need[u] > 0]


@dataclass(frozen=True)
class OfferUse:
    """What became of one donor's offer."""

    offered: float
    shipped: float
    delivered: float
    shipments: tuple[float, ...] = ()  # in matching order (the donor pays them in this order)

    @property
    def unused(self) -> float:
        return max(self.offered - self.shipped, 0.0)

    @property
    def state(self) -> str:
        """``unused`` (nothing beyond dust shipped), ``partial`` or ``exhausted``."""
        if self.shipped <= DUST_KCAL:
            return "unused"
        if self.unused <= EXHAUSTED_REL * self.offered:
            return "exhausted"
        return "partial"


def offer_use(offers: dict[str, float], m: Match) -> dict[str, OfferUse]:
    """Per offering donor: offered, shipped and delivered kcal."""
    shipped: dict[str, float] = dict.fromkeys(offers, 0.0)
    got: dict[str, float] = dict.fromkeys(offers, 0.0)
    each: dict[str, list[float]] = {d: [] for d in offers}
    for d, _r, s, g in m.transfers:
        shipped[d] += s
        got[d] += g
        each[d].append(s)
    return {d: OfferUse(o, shipped[d], got[d], tuple(each[d])) for d, o in offers.items()}


def unmet(deficits: list[Deficit], m: Match) -> dict[str, float]:
    """Each recipient's deficit left after the matching (kcal, >= 0)."""
    received = m.received()
    return {r: max(x - received.get(r, 0.0), 0.0) for _, r, x, _ in deficits}


def donor_payment(harvest: float, stores: float, shipments: Sequence[float]) -> tuple[float, float]:
    """Donor's ``(harvest, stores)`` after its shipments, each paid from harvest first, then
    stores (``TradeRound.apply``: the same float operations in the same order)."""
    for sent in shipments:
        from_harvest = min(sent, harvest)
        harvest -= from_harvest
        stores = max(stores - (sent - from_harvest), 0.0)
    return harvest, stores


@dataclass(frozen=True)
class GivingCost:
    """Static consequence of one year's shipments for the donor (same year, same inputs)."""

    sent: float
    from_stores: float  # part of ``sent`` paid from stores
    reserve: float  # body reserve the donor no longer has at year end
    retained: float  # stores the donor no longer carries into next year (after spoilage)
    deficit: float  # extra energy deficit (share of need)
    food_ratio_after: float  # harvest adequacy after giving (fission, innovation read it)
    intake_after: float  # dietary intake after giving (MVP 2.2 fertility reads it)

    @property
    def carried(self) -> float:
        """Food the donor would otherwise have carried into the next year."""
        return self.reserve + self.retained

    @property
    def lost_anyway(self) -> float:
        """Part of the shipment that would have spoiled by year end without giving."""
        return self.sent - self.carried


def giving_cost(
    need: float,
    harvest: float,
    stores: float,
    reserve: float,
    reserve_cap: float,
    retention: float,
    shipments: Sequence[float],
) -> GivingCost:
    """The production energy balance with and without the donor's shipments."""
    h1, s1 = donor_payment(harvest, stores, shipments)
    can_store = retention > 0
    keep = energy_balance(need, harvest, reserve, reserve_cap, stores, can_store)
    give = energy_balance(need, h1, reserve, reserve_cap, s1, can_store)
    eaten = h1 + min(max(need - h1, 0.0), s1)
    intake = 1.0 if need <= 0 or h1 >= need else min(eaten / need, 1.0)
    return GivingCost(
        sum(shipments),
        stores - s1,
        keep.reserve_kcal - give.reserve_kcal,
        (keep.stores_kcal - give.stores_kcal) * retention,
        give.deficit - keep.deficit,
        give.food_ratio,
        intake,
    )


def decay_factor(retentions: list[float]) -> float:
    """Surviving share of a store after the given year-end spoilage steps."""
    return math.prod(retentions)
