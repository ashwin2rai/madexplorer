"""Food exchange between nearby groups (spec §9.2, §11.5).

MVP 2 trade is reciprocal provisioning: groups with a surplus (harvest plus
stores above requirement) offer a share of it to groups in deficit within one
relocation range, losing some to transport. Transfers conserve food except for
the explicit transport loss, and each exchange strengthens a persistent tie
that later carries knowledge. Market exchange of distinct goods arrives when
there is more than one good.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.population.energetics import annual_need_batch
from madexplorer.population.unit import PopulationUnit


@model_rule(
    name="transport_loss",
    version="1.0",
    rationale="The delivered share of food decays exponentially with friction-weighted distance.",
    source_type="heuristic",
    parameters=("transport_decay_km",),
    expected_domain="delivered fraction in (0, 1]",
    known_limitations="No transport technology, pack animals, or boats yet.",
)
def delivered_fraction(path_cost_km: float, decay_km: float) -> float:
    """Fraction of shipped food that arrives."""
    return math.exp(-path_cost_km / decay_km)


@dataclass(frozen=True)
class Transfer:
    """One shipment of food."""

    donor_id: str
    recipient_id: str
    sent_kcal: float
    received_kcal: float
    recipient_need_kcal: float


@dataclass(frozen=True)
class TradeRound:
    """All of a year's transfers plus decay of existing ties."""

    transfers: tuple[Transfer, ...]
    tie_persistence: float

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Move food between groups and update ties."""
        for unit in state.units.values():
            unit.trade_ties = {
                p: w * self.tie_persistence
                for p, w in unit.trade_ties.items()
                if p in state.units and w * self.tie_persistence > 1e-3
            }
        for t in self.transfers:
            donor, recipient = state.units[t.donor_id], state.units[t.recipient_id]
            from_harvest = min(t.sent_kcal, donor.harvest_kcal)
            donor.harvest_kcal -= from_harvest
            donor.stores_kcal = max(donor.stores_kcal - (t.sent_kcal - from_harvest), 0.0)
            recipient.harvest_kcal += t.received_kcal
            strength = t.received_kcal / t.recipient_need_kcal if t.recipient_need_kcal > 0 else 0.0
            donor.trade_ties[recipient.id] = donor.trade_ties.get(recipient.id, 0.0) + strength
            recipient.trade_ties[donor.id] = recipient.trade_ties.get(donor.id, 0.0) + strength
            ctx.ledger.trade_volume_kcal += t.sent_kcal
            ctx.ledger.transport_loss_kcal += t.sent_kcal - t.received_kcal


@model_rule(
    name="reciprocal_provisioning",
    version="1.0",
    rationale=(
        "Groups offer a fixed share of their surplus; groups in deficit draw from the nearest "
        "offers first, most severe deficits served first."
    ),
    source_type="heuristic",
    parameters=("food_sharing_propensity", "annual_relocation_range_km", "tie_persistence"),
    expected_domain="sent <= offer; received = sent * delivered fraction",
    known_limitations="No reciprocity accounting, prices, or cross-species exchange.",
)
class TradeSubsystem:
    """Matches food surpluses with nearby deficits."""

    name = "trade"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[TradeRound]:
        """Plan the year's transfers against the post-harvest state."""
        config = ctx.scenario.config.trade
        index = ctx.spatial(state)
        units = index.units
        if not units:
            return [TradeRound((), config.tie_persistence)]
        compiled = ctx.compiled
        assert compiled is not None
        len(units)
        need = annual_need_batch(units, state, ctx)
        harvest = np.array([u.harvest_kcal for u in units], dtype=np.float64)
        stores = np.array([u.stores_kcal for u in units], dtype=np.float64)
        balance = (harvest + stores - need).tolist()
        propensity = compiled.parameter("social.food_sharing_propensity")[
            compiled.species_of([u.species_id for u in units])
        ].tolist()
        offers: dict[str, float] = {}
        offering: dict[int, list[PopulationUnit]] = {}  # cell -> offering units, unit order
        deficits: list[tuple[float, str, float, float]] = []
        for unit, b, n, share in zip(units, balance, need.tolist(), propensity, strict=True):
            if b > 0:
                offers[unit.id] = share * b
                offering.setdefault(unit.cell, []).append(unit)
            elif b < 0 and n > 0:
                deficits.append((b / n, unit.id, -b, n))
        transfers: list[Transfer] = []
        for _, recipient_id, deficit, need_kcal in sorted(deficits):
            recipient = state.units[recipient_id]
            reachable = ctx.movement[recipient.species_id].reachable(recipient.cell)
            donors = sorted(
                (cost, donor.id)
                for cell, cost in reachable.items()
                for donor in offering.get(cell, ())
                if donor.species_id == recipient.species_id and offers[donor.id] > 0
            )
            remaining = deficit
            for cost, donor_id in donors:
                if remaining <= 0:
                    break
                fraction = delivered_fraction(cost, config.transport_decay_km)
                sent = min(offers[donor_id], remaining / fraction)
                offers[donor_id] -= sent
                remaining -= sent * fraction
                transfers.append(Transfer(donor_id, recipient_id, sent, sent * fraction, need_kcal))
        return [TradeRound(tuple(transfers), config.tie_persistence)]
