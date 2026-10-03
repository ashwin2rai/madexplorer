"""Socioeconomic accounting of strata claims (MVP 3 Stages 3B and 3C).

Design: ``objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`` §L. The physical simulation is not
touched: the food and field subsystems *record* their gross flows of the step in transient
accounts (:class:`FoodAccounts`, :class:`FieldAccounts`, held by the step context), and
:func:`account_strata`, run by the engine after every subsystem, updates the claims of
differentiated units from them and then applies the zero-stock rule. Accounting follows the
simulator; nothing here is read by any physical mechanism.

- new cultivated land accrues to strata by share; shrinking land keeps claim fractions
  (independent of the crop-output claim weight);
- crop output is attributed before pooling with the crop-control correction
  ``d_i = g * w * Y * (field_claim_i - share_i)`` (Stage 3C; ``w`` is
  ``strata.field_output_claim_weight``, neutral at 0, where Stage 3B is reproduced bit for
  bit); forage, trade received and reserves are attributed by share;
- pooled consumption and reserve top-up stay proportional to share, so the difference
  between attribution and allocation is a recorded, zero-sum pooling transfer, split into a
  harvest component and a store-withdrawal component ``X * (share_i - store_claim_i)``;
- new stores accrue by the stratum's allocated (pre-pool, negatives covered pro rata)
  leftover; depletion (withdrawal, spoilage, trade out, abandonment) keeps store-claim
  fractions.

Each rule is one function on arrays whose last axis is strata: 1-D blocks (object engine)
and padded ``[rows, k]`` rows (table engine; ``k`` the rows' largest active count, padding
is zero) share the arithmetic, and sums over strata are sequential so padding cannot change
rounding. Deviations from the
neutral allocation are computed in difference form, so a zero correction leaves the neutral
values bit-identical. A single-stratum unit's claims stay exactly 1 and are skipped.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import BoolArray, FloatArray

if TYPE_CHECKING:
    from madexplorer.core.state import SimulationState, StepContext
    from madexplorer.population.store import PopulationStore
    from madexplorer.population.unit import PopulationUnit


@dataclass(frozen=True, eq=False)
class FoodAccounts:
    """One step's gross store flows per unit, recorded by energetics (transient).

    ``opening`` is the stores after trade (``K0``), ``stored`` the new stores (``A``, fed
    years only), ``withdrawn`` the stores eaten (``X``, short years only), ``closing`` the
    stores after retention (``K1 = (K0 - X + A) * r``). For crop-output attribution:
    ``harvest`` is the food after trade (``H``), ``crop`` and ``forage`` the unit's own
    harvests (``Y``, ``W``; ``Y + W`` is the harvest before trade), ``leftover`` the food
    left after need and reserve top-up in a fed year (``L``: stored plus discarded), ``fed``
    whether the harvest covered need. Without them (``crop`` None) no crop is attributed.
    """

    units: tuple["PopulationUnit", ...]
    opening: FloatArray
    stored: FloatArray
    withdrawn: FloatArray
    closing: FloatArray
    harvest: FloatArray | None = None
    crop: FloatArray | None = None
    forage: FloatArray | None = None
    leftover: FloatArray | None = None
    fed: BoolArray | None = None


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
    name="crop_output_attribution",
    version="1.0",
    rationale=(
        "Modeling hypothesis about the basis of socioeconomic attribution of crop output, "
        "not an empirical universal, extraction rate, rent, tax or hierarchy coefficient. "
        "A fraction w (strata.field_output_claim_weight) of the crop is attributed by field "
        "control instead of by the population/labor baseline (labor is proportional to "
        "share while it is undifferentiated): crop_output_share_i = (1 - w) * share_i + "
        "w * field_claim_i, i.e. w = 0 attributes the crop by share, w = 1 by field claim, "
        "and intermediate values mix linearly. Before pooling, the stratum's food after "
        "trade is H * share_i + d_i with the crop-control correction d_i = g * w * Y * "
        "(field_claim_i - share_i), where Y is the own crop and g = min(1, H / (Y + W)) the "
        "fraction of the own harvest kept (trade given from harvest leaves in proportion to "
        "the pre-trade attribution; trade received, forage and reserves are by share). The "
        "corrections sum to zero. Actual consumption stays pooled: d_i changes no calories "
        "received, only attribution, pooling transfers and claims on new stores."
    ),
    source_type="heuristic",
    parameters=("field_output_claim_weight",),
    expected_domain="0 <= w <= 1; d_i = 0 when w = 0, Y = 0 or field_claim = share",
    known_limitations=(
        "No canonical nonzero w (0 is the neutral default; 0.25, 0.5 and 1 are sensitivity "
        "cases). Labor is socioeconomically homogeneous, so w is conditional on that "
        "simplification. Field claims themselves do not depend on w."
    ),
)
def crop_output_corrections(
    share: FloatArray,
    field_claim: FloatArray,
    weight: float,
    harvest: PerUnit,
    crop: PerUnit,
    forage: PerUnit,
) -> FloatArray:
    """Each stratum's crop-control correction ``d_i`` (kcal) to its share of the harvest."""
    h = np.asarray(harvest, dtype=np.float64)
    own = np.asarray(crop, dtype=np.float64) + np.asarray(forage, dtype=np.float64)
    kept = np.minimum(np.divide(h, own, out=np.zeros_like(own), where=own > 0), 1.0)
    scale = kept * weight * np.asarray(crop, dtype=np.float64)
    correction: FloatArray = _per_unit(scale, share) * (field_claim - share)
    return correction


@model_rule(
    name="store_claim_accretion",
    version="1.1",
    rationale=(
        "Neutral accounting convention: existing stores keep their claim fractions through "
        "proportional depletion (withdrawal, spoilage, trade out, abandonment); newly stored "
        "food A is claimed by the strata's allocated leftover (pooled_leftover_shares): "
        "A_i = A * share_i + A * (pool_i + d_i) / L, which is A * share_i when crop output "
        "is attributed by share (Stage 3B). With opening stores K0 (nothing is withdrawn in "
        "a year with additions): store_claim_i = (store_claim_i * K0 + A_i) / sum; "
        "retention scales both alike. Zero closing stores: claim_zero_stock."
    ),
    source_type="heuristic",
    parameters=(),
    expected_domain="store_claim sums to 1; moves toward the attribution of new stores",
    known_limitations="Discarded leftover is owned by the same allocation as stored food.",
)
def store_claims_after_year(
    share: FloatArray,
    claim: FloatArray,
    opening: PerUnit,
    stored: PerUnit,
    closing: PerUnit,
    stored_correction: FloatArray | float = 0.0,
) -> FloatArray:
    """Store claims after the year's energetics flows (gross, from :class:`FoodAccounts`).

    ``stored_correction`` is each stratum's new stores minus ``share * stored`` (from
    :func:`new_store_corrections`; 0 attributes new stores by share).
    """
    accreted = np.maximum(share * _per_unit(stored, claim) + stored_correction, 0.0)
    absolute = claim * _per_unit(opening, claim) + accreted
    total = _per_unit(_total(absolute), claim)
    adds = (_per_unit(stored, claim) > 0) & (total > 0)
    updated = np.where(adds, absolute / np.where(adds, total, 1.0), claim)
    empty = _per_unit(closing, claim) == 0
    result: FloatArray = np.where(empty, share, updated)
    return result


@model_rule(
    name="food_pooling_transfer",
    version="1.1",
    rationale=(
        "Accounting identity of the existing unit-level pooling (observation only): "
        "pool_transfer_i = post-pool allocation - pre-pool attribution, which sums to zero "
        "over a unit's strata. Consumption and reserve top-up are proportional to share. "
        "Store component: stores withdrawn X in a short year are contributed by store claim "
        "and eaten by share, X * (share_i - store_claim_i). Harvest component: in a short "
        "year the whole harvest is eaten by share, so -d_i (crop_output_attribution); in a "
        "fed year the leftover L is allocated by pooled_leftover_shares. Positive: the "
        "stratum receives more from the pool than it contributes. Carries no institutional "
        "meaning (not tax, rent, tribute or welfare)."
    ),
    source_type="theoretical",
    parameters=(),
    expected_domain="kcal per stratum; each component sums to zero per unit",
    known_limitations="Pooling itself (equal access by share) is the MVP 2.1 behavior.",
)
def pooling_transfers(share: FloatArray, claim: FloatArray, withdrawn: PerUnit) -> FloatArray:
    """Each stratum's store-withdrawal pooling transfer (kcal) for the year."""
    transfer: FloatArray = _per_unit(withdrawn, claim) * (share - claim)
    return transfer


@model_rule(
    name="pooled_leftover_shares",
    version="1.0",
    rationale=(
        "Accounting convention for a fed year's leftover L (food after need and reserve "
        "top-up, both by share; stored and discarded alike): the pre-pool leftover is "
        "l_i = L * share_i + d_i. A negative l_i means the stratum's attributed food does "
        "not cover its pooled consumption and reserve allocation (it holds no negative "
        "food); that shortfall is covered pro rata by the strata with positive l_i, so the "
        "allocated leftover is L * max(l_i, 0) / sum(max(l, 0)) and the harvest pooling "
        "transfer is allocated - l_i = max(-l_i, 0) - max(l_i, 0) * N / P (N, P the sums of "
        "the negative and positive parts). Zero when every d_i is zero."
    ),
    source_type="heuristic",
    parameters=(),
    expected_domain="allocated leftover >= 0 and sums to L; transfers sum to zero",
    known_limitations="Pro rata coverage of shortfalls is a convention, not an institution.",
)
def leftover_pooling_transfers(
    share: FloatArray, correction: FloatArray, leftover: PerUnit
) -> FloatArray:
    """Each stratum's fed-year harvest pooling transfer (kcal), in difference form."""
    raw = _per_unit(leftover, share) * share + correction
    short = np.maximum(-raw, 0.0)
    spare = np.maximum(raw, 0.0)
    shortfall, surplus = _total(short), _total(spare)
    covered = np.divide(shortfall, surplus, out=np.zeros_like(surplus), where=surplus > 0)
    transfer: FloatArray = short - spare * _per_unit(covered, share)
    return transfer


def new_store_corrections(
    share: FloatArray,
    correction: FloatArray,
    transfer: FloatArray,
    stored: PerUnit,
    leftover: PerUnit,
) -> FloatArray:
    """New stores minus ``share * stored`` per stratum: ``A * (pool_i + d_i) / L``.

    The allocated leftover is ``L * share_i + pool_i + d_i``; stored food ``A <= L`` takes
    the same allocation (``A_i = A * allocated_i / L``), so discarded food moves nothing.
    """
    a, total = _per_unit(stored, share), _per_unit(leftover, share)
    ratio = np.divide(a, total, out=np.zeros_like(a * total), where=total > 0)
    result: FloatArray = ratio * (transfer + correction)
    return result


CLAIM_COLUMNS = ("share", "field_claim", "store_claim")
FLOW_FIELDS = ("correction", "harvest_transfer", "store_transfer", "stored_correction")
# Sidecar flow columns of Stage 3B; Stage 3C appends its columns after these.
STAGE3B_FLOW_COLUMNS = (
    "year",
    "unit_id",
    "stratum_id",
    "share",
    "store_claim",
    "withdrawn_kcal",
    "pool_transfer_kcal",
    "pool_transfer_volume_kcal",
)


def account_strata(state: "SimulationState", ctx: "StepContext") -> None:
    """Apply the step's pending accounts to strata claims, then the zero-stock rule.

    Run by the engine after every subsystem; consumes ``ctx.food_accounts`` and
    ``ctx.field_accounts`` (recorded by energetics and field planning).
    """
    population = state.population
    if ctx.food_accounts is not None:
        weight = ctx.scenario.config.strata.field_output_claim_weight
        _apply_food(population, ctx.food_accounts, state.year, weight)
        ctx.food_accounts = None
    if ctx.field_accounts is not None:
        _apply_fields(population, ctx.field_accounts, state.year)
        ctx.field_accounts = None
    population.settle_empty_claims(state.year)


@dataclass(frozen=True, eq=False)
class FoodFlows:
    """One year's attribution and pooling of food per stratum (kcal; strata on the last
    axis): crop-control correction ``d``, harvest and store pooling transfers (their sum is
    the pooling transfer) and the correction of new stores from ``share * A``."""

    correction: FloatArray
    harvest_transfer: FloatArray
    store_transfer: FloatArray
    stored_correction: FloatArray

    @property
    def transfer(self) -> FloatArray:
        total: FloatArray = self.store_transfer + self.harvest_transfer
        return total


def food_flows(
    share: FloatArray,
    field_claim: FloatArray,
    store_claim: FloatArray,
    weight: float,
    accounts: FoodAccounts,
    rows: "np.ndarray | int",
) -> FoodFlows:
    """Attribution and pooling for ``accounts`` rows ``rows`` (an index array with
    ``[rows, S]`` strata arrays, or one index with 1-D blocks)."""
    withdrawn = accounts.withdrawn[rows]
    store_transfer = pooling_transfers(share, store_claim, withdrawn)
    if accounts.crop is None:  # no attribution recorded: crop by share
        zero = np.zeros_like(share)
        return FoodFlows(zero, zero, store_transfer, zero)
    assert accounts.harvest is not None and accounts.forage is not None
    assert accounts.leftover is not None and accounts.fed is not None
    leftover, fed = accounts.leftover[rows], accounts.fed[rows]
    correction = crop_output_corrections(
        share,
        field_claim,
        weight,
        accounts.harvest[rows],
        accounts.crop[rows],
        accounts.forage[rows],
    )
    leftover_transfer = leftover_pooling_transfers(share, correction, leftover)
    # Short year: the whole harvest is eaten by share, so the harvest transfer is -d.
    harvest_transfer = np.where(_per_unit(fed, share), leftover_transfer, -correction)
    stored_correction = new_store_corrections(
        share, correction, leftover_transfer, accounts.stored[rows], leftover
    )
    return FoodFlows(correction, harvest_transfer, store_transfer, stored_correction)


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


def _apply_food(
    population: "PopulationStore", accounts: FoodAccounts, year: int, weight: float
) -> None:
    rows, slots = _differentiated(population, accounts.units)
    if rows.size == 0:
        return
    opening, stored = accounts.opening[rows], accounts.stored[rows]
    withdrawn, closing = accounts.withdrawn[rows], accounts.closing[rows]
    units = [accounts.units[k] for k in rows.tolist()]
    strata = population.strata
    used: list[tuple[dict[str, FloatArray], FoodFlows]] = []
    if strata is not None:
        width = int(strata.n_strata[slots].max())  # active width; the rest is zero padding
        columns = {name: strata.columns[name][slots, :width] for name in CLAIM_COLUMNS}
        flows = food_flows(
            columns["share"],
            columns["field_claim"],
            columns["store_claim"],
            weight,
            accounts,
            rows,
        )
        strata.columns["store_claim"][slots, :width] = store_claims_after_year(
            columns["share"],
            columns["store_claim"],
            opening,
            stored,
            closing,
            flows.stored_correction,
        )
        for k, n in enumerate(strata.n_strata[slots].tolist()):
            used.append(
                (
                    {name: values[k, :n] for name, values in columns.items()},
                    FoodFlows(*(getattr(flows, f)[k, :n] for f in FLOW_FIELDS)),
                )
            )
    else:
        for k, unit in enumerate(units):
            block = unit.strata
            columns = dict(block.columns)
            share, field, claim = (columns[name] for name in CLAIM_COLUMNS)
            flows = food_flows(share, field, claim, weight, accounts, int(rows[k]))
            used.append(({name: columns[name] for name in CLAIM_COLUMNS}, flows))
            columns["store_claim"] = store_claims_after_year(
                share, claim, opening[k], stored[k], closing[k], flows.stored_correction
            )
            unit.strata = type(block)(columns, block.stratum_id)
    crop = accounts.crop[rows] if accounts.crop is not None else np.zeros(rows.size)
    _record_flows(population, year, units, used, withdrawn, crop)
    population.compact_units(units, year)


def _apply_fields(population: "PopulationStore", accounts: FieldAccounts, year: int) -> None:
    rows, slots = _differentiated(population, accounts.units)
    if rows.size == 0:
        return
    before, after = accounts.before[rows], accounts.after[rows]
    units = [accounts.units[k] for k in rows.tolist()]
    strata = population.strata
    if strata is not None:
        width = int(strata.n_strata[slots].max())  # active width; the rest is zero padding
        share = strata.columns["share"][slots, :width]
        claim = strata.columns["field_claim"][slots, :width]
        strata.columns["field_claim"][slots, :width] = field_claims_after_change(
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
    used: list[tuple[dict[str, FloatArray], FoodFlows]],
    withdrawn: FloatArray,
    crop: FloatArray,
) -> None:
    """Sidecar pooling flows (observation only): one row per stratum of each unit whose
    pooling moved food between strata (a nonzero harvest or store component), with the
    claims it used (stratum ids read before this year's compaction). The Stage 3B columns
    come first, in their original order (``STAGE3B_FLOW_COLUMNS``)."""
    flows = population.strata_flows
    if flows is None:
        return
    for unit, (claims, flow), x, y in zip(
        units, used, withdrawn.tolist(), crop.tolist(), strict=True
    ):
        if not (flow.harvest_transfer.any() or flow.store_transfer.any()):
            continue
        transfer = flow.transfer
        volume = float(np.abs(transfer).sum()) / 2.0
        for k, stratum_id in enumerate(unit.strata.stratum_id.tolist()):
            row: dict[str, Any] = {
                "year": year,
                "unit_id": unit.id,
                "stratum_id": stratum_id,
                "share": float(claims["share"][k]),
                "store_claim": float(claims["store_claim"][k]),
                "withdrawn_kcal": x,
                "pool_transfer_kcal": float(transfer[k]),
                "pool_transfer_volume_kcal": volume,
                "crop_kcal": y,
                "field_claim": float(claims["field_claim"][k]),
                "crop_attribution_correction_kcal": float(flow.correction[k]),
                "harvest_pool_transfer_kcal": float(flow.harvest_transfer[k]),
                "store_pool_transfer_kcal": float(flow.store_transfer[k]),
            }
            flows.append(row)
