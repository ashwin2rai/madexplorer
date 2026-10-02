"""Neutral socioeconomic accounting of strata claims (MVP 3 Stage 3B).

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §L. The physical simulation is not
touched: the food and field subsystems *record* their gross flows of the step in transient
accounts (:class:`FoodAccounts`, :class:`FieldAccounts`, held by the step context), and
:func:`account_strata`, run by the engine after every subsystem, updates the claims of
differentiated units from them and then applies the zero-stock rule. Accounting follows the
simulator; nothing here is read by any physical mechanism.

Stage 3B attribution is neutral: crop and forage output are attributed in proportion to
population share (no ``field_output_claim_weight``), so

- new cultivated land accrues to strata by share; shrinking land keeps claim fractions;
- new stores accrue by share; depletion (withdrawal, spoilage, trade out, abandonment) keeps
  store-claim fractions;
- pooled consumption is proportional to share, which makes withdrawals from unequally held
  stores a recorded, zero-sum pooling transfer.

Each rule is one function on arrays whose last axis is strata: 1-D blocks (object engine)
and padded ``[rows, S_MAX]`` rows (table engine; padding is zero) share the arithmetic, and
sums over strata are sequential so padding cannot change rounding. A single-stratum unit's
claims stay exactly 1 and are skipped.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import FloatArray

if TYPE_CHECKING:
    from madexplorer.core.state import SimulationState, StepContext
    from madexplorer.population.store import PopulationStore
    from madexplorer.population.unit import PopulationUnit


@dataclass(frozen=True, eq=False)
class FoodAccounts:
    """One step's gross store flows per unit, recorded by energetics (transient).

    ``opening`` is the stores after trade (``K0``), ``stored`` the new stores (``A``, fed
    years only), ``withdrawn`` the stores eaten (``X``, short years only), ``closing`` the
    stores after retention (``K1 = (K0 - X + A) * r``).
    """

    units: tuple["PopulationUnit", ...]
    opening: FloatArray
    stored: FloatArray
    withdrawn: FloatArray
    closing: FloatArray


@dataclass(frozen=True, eq=False)
class FieldAccounts:
    """One step's ordinary field changes per unit, recorded by field planning (transient)."""

    units: tuple["PopulationUnit", ...]
    before: FloatArray  # F0
    after: FloatArray  # F1


def _total(values: FloatArray) -> FloatArray:
    """Sum over the strata axis, left to right (padding zeros add exactly nothing)."""
    total: FloatArray = np.cumsum(values, axis=-1)[..., -1]
    return total


PerUnit = FloatArray | float  # one value per unit: an array over rows, or a scalar


def _per_unit(values: PerUnit, like: FloatArray) -> FloatArray:
    """A per-unit quantity broadcast against strata arrays."""
    array = np.asarray(values, dtype=np.float64)
    expanded: FloatArray = array[..., None] if like.ndim > array.ndim else array
    return expanded


@model_rule(
    name="field_claim_accretion",
    version="1.0",
    rationale=(
        "Neutral accounting convention, not a theory of historical land tenure: without an "
        "explicit institution or differentiated labor, newly cultivated land does not go to "
        "incumbent controllers but to strata in proportion to population share (labor clears "
        "land, and labor is proportional to share). Absolute control a_i = field_claim_i * F0 "
        "+ share_i * (F1 - F0), normalized by its own sum. Shrinking land is a proportional "
        "loss (fractions kept); zero land is claim_zero_stock."
    ),
    source_type="heuristic",
    parameters=(),
    expected_domain="field_claim sums to 1; moves toward share as land expands",
    known_limitations="No tenure institution, inheritance rule or labor differentiation.",
)
def field_claims_after_change(
    share: FloatArray, claim: FloatArray, before: PerUnit, after: PerUnit
) -> FloatArray:
    """Field claims after an ordinary change ``before -> after`` of the unit's fields."""
    f0, f1 = _per_unit(before, claim), _per_unit(after, claim)
    absolute = claim * f0 + share * (f1 - f0)
    total = _per_unit(_total(absolute), claim)
    grows = (f1 > f0) & (total > 0)
    updated: FloatArray = np.where(grows, absolute / np.where(grows, total, 1.0), claim)
    return updated


@model_rule(
    name="store_claim_accretion",
    version="1.0",
    rationale=(
        "Neutral accounting convention: existing stores keep their claim fractions through "
        "proportional depletion (withdrawal, spoilage, trade out, abandonment); newly stored "
        "food is claimed according to the attribution of the food entering storage, which in "
        "Stage 3B (no crop-output claim weight) is population share. With opening stores K0 "
        "(nothing is withdrawn in a year with additions) and new stores A: "
        "store_claim_i = (store_claim_i * K0 + share_i * A) / sum; retention scales both "
        "alike. Zero closing stores: claim_zero_stock."
    ),
    source_type="heuristic",
    parameters=(),
    expected_domain="store_claim sums to 1; moves toward share as new stores enter",
    known_limitations="Attribution of new food is neutral until Stage 3C.",
)
def store_claims_after_year(
    share: FloatArray,
    claim: FloatArray,
    opening: PerUnit,
    stored: PerUnit,
    closing: PerUnit,
) -> FloatArray:
    """Store claims after the year's energetics flows (gross, from :class:`FoodAccounts`)."""
    absolute = claim * _per_unit(opening, claim) + share * _per_unit(stored, claim)
    total = _per_unit(_total(absolute), claim)
    adds = (_per_unit(stored, claim) > 0) & (total > 0)
    updated = np.where(adds, absolute / np.where(adds, total, 1.0), claim)
    empty = _per_unit(closing, claim) == 0
    result: FloatArray = np.where(empty, share, updated)
    return result


@model_rule(
    name="food_pooling_transfer",
    version="1.0",
    rationale=(
        "Accounting identity of the existing unit-level pooling (observation only): "
        "pool_transfer_i = post-pool allocation - pre-pool attribution, which sums to zero "
        "over a unit's strata. Consumption and reserves are proportional to share; in Stage "
        "3B harvests are attributed by share too, so the only nonzero term is stores "
        "withdrawn X in a short year, contributed by store claim and eaten by share: "
        "X * (share_i - store_claim_i). Positive: the stratum receives more from the pool "
        "than it contributes. Carries no institutional meaning (not tax, rent or welfare)."
    ),
    source_type="theoretical",
    parameters=(),
    expected_domain="kcal per stratum; zero sum per unit",
    known_limitations="Crop-output attribution by field claims (Stage 3C) adds a harvest term.",
)
def pooling_transfers(share: FloatArray, claim: FloatArray, withdrawn: PerUnit) -> FloatArray:
    """Each stratum's pooling transfer (kcal) for the year's store withdrawal."""
    transfer: FloatArray = _per_unit(withdrawn, claim) * (share - claim)
    return transfer


def account_strata(state: "SimulationState", ctx: "StepContext") -> None:
    """Apply the step's pending accounts to strata claims, then the zero-stock rule.

    Run by the engine after every subsystem; consumes ``ctx.food_accounts`` and
    ``ctx.field_accounts`` (recorded by energetics and field planning).
    """
    population = state.population
    if ctx.food_accounts is not None:
        _apply_food(population, ctx.food_accounts, state.year)
        ctx.food_accounts = None
    if ctx.field_accounts is not None:
        _apply_fields(population, ctx.field_accounts, state.year)
        ctx.field_accounts = None
    population.settle_empty_claims(state.year)


def _differentiated(
    population: "PopulationStore", units: tuple["PopulationUnit", ...]
) -> tuple[np.ndarray, list[int]]:
    """Positions (into ``units``, in registry order) of units with more than one stratum,
    and their slots (table engine; empty otherwise)."""
    from madexplorer.population.unit import belief_slot

    strata = population.strata
    if strata is not None:
        slots = np.array([belief_slot(u) for u in units], dtype=np.int64)
        rows = np.flatnonzero(strata.n_strata[slots] > 1) if slots.size else slots
        return rows, slots[rows].tolist()
    rows = np.array([k for k, u in enumerate(units) if len(u.strata) > 1], dtype=np.int64)
    return rows, []


def _apply_food(population: "PopulationStore", accounts: FoodAccounts, year: int) -> None:
    rows, slots = _differentiated(population, accounts.units)
    if rows.size == 0:
        return
    opening, stored = accounts.opening[rows], accounts.stored[rows]
    withdrawn, closing = accounts.withdrawn[rows], accounts.closing[rows]
    units = [accounts.units[k] for k in rows.tolist()]
    strata = population.strata
    if strata is not None:
        share, claim = strata.columns["share"][slots], strata.columns["store_claim"][slots]
        transfers = pooling_transfers(share, claim, withdrawn)
        strata.columns["store_claim"][slots] = store_claims_after_year(
            share, claim, opening, stored, closing
        )
        used = [
            (share[k, :n], claim[k, :n], transfers[k, :n])
            for k, n in enumerate(strata.n_strata[slots].tolist())
        ]
    else:
        used = []
        for k, unit in enumerate(units):
            block = unit.strata
            share, claim = block.columns["share"], block.columns["store_claim"]
            used.append((share, claim, pooling_transfers(share, claim, withdrawn[k])))
            columns = dict(block.columns)
            columns["store_claim"] = store_claims_after_year(
                share, claim, opening[k], stored[k], closing[k]
            )
            unit.strata = type(block)(columns, block.stratum_id)
    _record_flows(population, year, units, used, withdrawn)
    population.compact_units(units, year)


def _apply_fields(population: "PopulationStore", accounts: FieldAccounts, year: int) -> None:
    rows, slots = _differentiated(population, accounts.units)
    if rows.size == 0:
        return
    before, after = accounts.before[rows], accounts.after[rows]
    units = [accounts.units[k] for k in rows.tolist()]
    strata = population.strata
    if strata is not None:
        share, claim = strata.columns["share"][slots], strata.columns["field_claim"][slots]
        strata.columns["field_claim"][slots] = field_claims_after_change(
            share, claim, before, after
        )
    else:
        for k, unit in enumerate(units):
            block = unit.strata
            columns = dict(block.columns)
            columns["field_claim"] = field_claims_after_change(
                block.columns["share"], block.columns["field_claim"], before[k], after[k]
            )
            unit.strata = type(block)(columns, block.stratum_id)
    population.compact_units(units, year)


def _record_flows(
    population: "PopulationStore",
    year: int,
    units: list["PopulationUnit"],
    used: list[tuple[FloatArray, FloatArray, FloatArray]],
    withdrawn: FloatArray,
) -> None:
    """Sidecar pooling flows (observation only): one row per stratum of each unit whose
    pooled withdrawal moved food between strata, with the share and store claim it used
    (stratum ids read before this year's compaction)."""
    flows = population.strata_flows
    if flows is None:
        return
    for unit, (share, claim, transfer), x in zip(units, used, withdrawn.tolist(), strict=True):
        volume = float(np.abs(transfer).sum()) / 2.0
        if volume == 0.0:
            continue
        for k, stratum_id in enumerate(unit.strata.stratum_id.tolist()):
            row: dict[str, Any] = {
                "year": year,
                "unit_id": unit.id,
                "stratum_id": stratum_id,
                "share": float(share[k]),
                "store_claim": float(claim[k]),
                "withdrawn_kcal": x,
                "pool_transfer_kcal": float(transfer[k]),
                "pool_transfer_volume_kcal": volume,
            }
            flows.append(row)
