"""Local spatial beliefs: perception and social information exchange (spec §10.1, §10.3).

Units never see the whole map. Each year they observe cells within a
perception radius shrunk by vegetation, with observation noise; observations
older than their memory horizon are ignored when read (lazy expiry).

Neighboring groups exchange a bounded number of *social reports* per encounter
(``social_information.reports_per_interaction``), not their whole remembered
maps. A group talks about its current place, what it saw first-hand, and
unusually rich or poor places it knows of; each relay lowers the receiver's
confidence in a report. Both steps emit sparse ``BeliefPatch`` proposals, and the
cost of an encounter is proportional to the number of reports, not map cells.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.economy.foraging import accessible_food_kcal
from madexplorer.population.unit import (
    HOPS_DTYPE,
    MAX_HOPS,
    YEAR_DTYPE,
    BeliefMap,
    BeliefPatch,
    CountArray,
    FoodArray,
    HopsArray,
    PopulationUnit,
    YearArray,
)
from madexplorer.species.profile import Cognition, SocialInformation


@model_rule(
    name="perception_radius",
    version="1.0",
    rationale="Line of sight and search radius shrink with local vegetation density.",
    source_type="heuristic",
    parameters=("perception_radius_km", "vegetation_occlusion"),
    expected_domain="radius in cells, >= 1",
    known_limitations="Terrain visibility (ridges, valleys) is not modeled.",
)
def perception_radius_cells(cognition: Cognition, vegetation: float, cell_size_km: float) -> int:
    """Perception radius in cells from the observer's current cell."""
    km = cognition.perception_radius_km * (1.0 - cognition.vegetation_occlusion * vegetation)
    return max(1, round(km / cell_size_km))


class PerceptionSubsystem:
    """Each unit observes nearby land cells and forms its food prior from them."""

    name = "perception"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefPatch]:
        """This year's direct observations of the cells each unit can see (sparse patches).

        Old observations are not scanned or erased here: expiry is lazy (see
        :class:`BeliefMap`), so the cost is proportional to the cells perceived. This year's
        food observations also set the unit's prior (:func:`food_prior`). All units are
        processed in one pass; the noise draws are the same sequence as drawing unit by unit.
        """
        units = list(state.units.values())
        if not units:
            return []
        rng = ctx.rng.stream(Streams.PERCEPTION)
        cell_population = state.cell_population()
        food_by_species = {
            sid: accessible_food_kcal(state, access) for sid, access in ctx.forage.items()
        }
        cognition = {sid: ctx.species(sid).cognition for sid in ctx.scenario.species}
        per_unit = [
            ctx.static.perceived_cells(u.species_id, u.cell, cognition[u.species_id]) for u in units
        ]
        sizes = np.array([c.size for c in per_unit], dtype=np.int64)
        starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        owner = np.repeat(np.arange(len(units)), sizes)
        cells = np.concatenate(per_unit)
        sigma = np.array([cognition[u.species_id].observation_noise_sigma for u in units])
        noise = np.exp(sigma[owner] * rng.standard_normal(cells.size))
        species = [u.species_id for u in units]
        if len(set(species)) == 1:
            food = food_by_species[species[0]][cells] * noise
        else:
            food = np.empty(cells.size)
            unit_species = np.array(species)[owner]
            for sid, stock in food_by_species.items():
                rows = unit_species == sid
                food[rows] = stock[cells[rows]] * noise[rows]
        log_prior, signal_var = food_prior_batch(food, starts, sizes, sigma)
        others = cell_population[cells]
        own_cell = np.array([u.cell for u in units])[owner]
        own_population = np.array([u.population for u in units])[owner]
        population = np.where(cells == own_cell, others - own_population, others)
        year = np.full(cells.size, state.year, dtype=YEAR_DTYPE)
        hops = np.zeros(cells.size, dtype=HOPS_DTYPE)
        updates: list[BeliefPatch] = []
        for k, unit in enumerate(units):
            rows = slice(int(starts[k]), int(starts[k] + sizes[k]))
            updates.append(
                BeliefPatch(
                    unit.id,
                    cells[rows],
                    year[rows],
                    food[rows],
                    population[rows],
                    hops[rows],
                    food_log_prior=float(log_prior[k]),
                    food_log_signal_var=float(signal_var[k]),
                    resident_cell=unit.cell,
                )
            )
        return updates


@model_rule(
    name="food_prior",
    version="1.0",
    rationale=(
        "A group's prior for food in a cell is what its surroundings look like this year: the "
        "mean log food of its direct observations. Observation noise is multiplicative "
        "(lognormal), so the observed log variance across those cells is about tau^2 + sigma^2; "
        "the true between-cell variance tau^2 is estimated as max(observed - sigma^2, 0) "
        "(empirical Bayes), using only what the group sees."
    ),
    source_type="theoretical",
    parameters=("observation_noise_sigma",),
    expected_domain="log kcal per cell; tau^2 >= 0",
    known_limitations=(
        "Estimated from one year's neighborhood (often < 25 cells), so tau^2 is itself noisy; "
        "no memory of earlier years or of other regions."
    ),
)
def food_prior(food_kcal: FloatArray, noise_sigma: float) -> tuple[float, float]:
    """``(mean log food, estimated signal variance tau^2)`` of direct observations."""
    log_prior, signal_var = food_prior_batch(
        np.asarray(food_kcal, dtype=np.float64),
        np.array([0]),
        np.array([np.asarray(food_kcal).size]),
        np.array([noise_sigma]),
    )
    return float(log_prior[0]), float(signal_var[0])


def food_prior_batch(
    food_kcal: FloatArray, starts: IntArray, sizes: IntArray, noise_sigma: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """:func:`food_prior` for consecutive segments of ``food_kcal`` (one per unit)."""
    logs = np.log(np.maximum(food_kcal, 1.0))
    mean = np.add.reduceat(logs, starts) / sizes
    deviation = logs - np.repeat(mean, sizes)
    squares = np.add.reduceat(deviation * deviation, starts)
    observed_var = np.where(sizes > 1, squares / np.maximum(sizes - 1, 1), 0.0)
    signal_var: FloatArray = np.maximum(observed_var - noise_sigma**2, 0.0)
    return mean, signal_var


@model_rule(
    name="transmission_confidence",
    version="1.0",
    rationale=(
        "Confidence in a belief is 1 for a direct observation and falls by a constant factor "
        "with each social relay (q = decay ** hops), separating first-hand knowledge, "
        "first-hand reports, and hearsay."
    ),
    source_type="heuristic",
    parameters=("transmission_confidence_decay",),
    expected_domain="confidence in (0, 1]",
    known_limitations="No sender reliability, trust, or cross-checking of reports.",
)
def report_confidence(hops: HopsArray | IntArray, decay: float) -> FloatArray:
    """Confidence of beliefs with the given relay counts."""
    confidence: FloatArray = np.power(decay, hops.astype(np.float64))
    return confidence


@model_rule(
    name="social_report_salience",
    version="1.0",
    rationale=(
        "Groups talk about what matters and what they trust: salience = confidence x recency x "
        "(1 + |ln food - log prior|), so first-hand, recent and unusually rich or poor places are "
        "mentioned first. The group's current place is always mentioned."
    ),
    source_type="heuristic",
    parameters=("reports_per_interaction", "max_report_age_years"),
    expected_domain="salience >= 0; the top reports_per_interaction are passed",
    known_limitations=(
        "Deterministic ranking (a sender tells every partner the same things in a year); no "
        "danger, trade or route content until those mechanisms exist."
    ),
)
def report_salience(
    confidence: FloatArray,
    age_years: FloatArray,
    max_age_years: FloatArray | float,
    food_kcal: FloatArray,
    log_prior: FloatArray | float,
) -> FloatArray:
    """Salience of candidate reports (higher is mentioned first); elementwise.

    A missing prior (NaN: a group that has not perceived yet) makes no place exceptional.
    """
    recency = 1.0 - age_years / (np.asarray(max_age_years) + 1.0)
    prior = np.broadcast_to(np.asarray(log_prior, dtype=np.float64), food_kcal.shape)
    deviation = np.abs(np.log(np.maximum(food_kcal, 1.0)) - np.nan_to_num(prior))
    exceptional = np.where(np.isfinite(prior), deviation, 0.0)
    salience: FloatArray = confidence * recency * (1.0 + exceptional)
    return salience


@dataclass(frozen=True, slots=True)
class Reports:
    """The reports one group passes to each partner this year (sender's beliefs)."""

    cells: IntArray
    year: YearArray
    food_kcal: FoodArray
    population: CountArray
    hops: HopsArray  # sender's relay count (the receiver adds one)


@dataclass(frozen=True, slots=True)
class ReportTable:
    """The reports of many senders, as rows grouped by sender (``start``/``count`` per sender)."""

    start: IntArray
    count: IntArray
    cells: IntArray
    year: YearArray
    food_kcal: FoodArray
    population: CountArray
    hops: HopsArray

    @classmethod
    def from_reports(cls, reports: Sequence[Reports]) -> "ReportTable":
        """Stack per-sender reports (sender ``i`` is ``reports[i]``)."""
        count = np.array([r.cells.size for r in reports], dtype=np.int64)
        start = np.concatenate([[0], np.cumsum(count)[:-1]]).astype(np.int64)
        return cls(
            start,
            count,
            np.concatenate([r.cells for r in reports]).astype(np.int64),
            np.concatenate([r.year for r in reports]),
            np.concatenate([r.food_kcal for r in reports]),
            np.concatenate([r.population for r in reports]),
            np.concatenate([r.hops for r in reports]),
        )

    def of(self, sender: int) -> Reports:
        """One sender's reports."""
        rows = slice(int(self.start[sender]), int(self.start[sender] + self.count[sender]))
        return Reports(
            self.cells[rows],
            self.year[rows],
            self.food_kcal[rows],
            self.population[rows],
            self.hops[rows],
        )


@dataclass(frozen=True, slots=True)
class SenderInputs:
    """What one sender could talk about this year, and the parameters that shape it."""

    unit: PopulationUnit
    pool: IntArray  # candidate cells (duplicates allowed)
    memory_years: int
    info: SocialInformation


def select_reports_batch(senders: Sequence[SenderInputs], year: int, n_cells: int) -> ReportTable:
    """Each sender's ``reports_per_interaction`` most salient current beliefs, in one pass.

    ``pool`` is what a group could talk about: cells it sees this year, cells it has lived
    in, and cells it recently heard about. Only current beliefs no older than
    ``max_report_age_years`` qualify; the current cell always comes first; ties are broken
    by cell id, so the choice is deterministic. Rows come out grouped by sender, most
    salient first.
    """
    n = len(senders)
    sizes = np.array([s.pool.size for s in senders], dtype=np.int64)
    owner = np.repeat(np.arange(n), sizes)
    cells = np.concatenate([s.pool for s in senders]).astype(np.int64) if n else np.zeros(0, int)
    # One row per (sender, cell), sorted by sender then cell.
    _, unique = np.unique(owner * n_cells + cells, return_index=True)
    owner, cells = owner[unique], cells[unique]
    counts = np.bincount(owner, minlength=n)
    offsets = np.concatenate([[0], np.cumsum(counts)[:-1]])

    def gather(field: str) -> Any:
        parts = [
            getattr(s.unit.beliefs, field)[cells[o : o + c]]
            for s, o, c in zip(senders, offsets.tolist(), counts.tolist(), strict=True)
        ]
        return np.concatenate(parts) if parts else np.zeros(0)

    observed, hops = gather("year"), gather("hops")
    food, population = gather("food_kcal"), gather("population")

    def per_sender(values: list[float]) -> FloatArray:
        array: FloatArray = np.asarray(values, dtype=np.float64)[owner]
        return array

    memory = per_sender([s.memory_years for s in senders])
    max_age = per_sender([s.info.max_report_age_years for s in senders])
    age = year - observed.astype(np.int64)
    keep = (observed > year - memory) & (age <= max_age)
    decay = per_sender([s.info.transmission_confidence_decay for s in senders])
    owner, cells, age, decay, max_age = (
        owner[keep],
        cells[keep],
        age[keep],
        decay[keep],
        max_age[keep],
    )
    observed, hops, food, population = observed[keep], hops[keep], food[keep], population[keep]
    salience = report_salience(
        np.power(decay, hops.astype(np.float64)),
        age.astype(np.float64),
        max_age,
        food.astype(np.float64),
        per_sender([s.unit.food_log_prior for s in senders]),
    )
    salience[cells == per_sender([s.unit.cell for s in senders]).astype(np.int64)] = np.inf
    order = np.lexsort((cells, -salience, owner))
    owner = owner[order]
    first_row = np.searchsorted(owner, np.arange(n))
    rank = np.arange(owner.size) - first_row[owner]
    budget = np.array([s.info.reports_per_interaction for s in senders], dtype=np.int64)
    chosen = order[rank < budget[owner]]
    count = np.bincount(owner[rank < budget[owner]], minlength=n).astype(np.int64)
    return ReportTable(
        np.concatenate([[0], np.cumsum(count)[:-1]]).astype(np.int64),
        count,
        cells[chosen],
        observed[chosen],
        food[chosen],
        population[chosen],
        hops[chosen],
    )


def select_reports(
    unit: PopulationUnit,
    pool: IntArray,
    year: int,
    memory_years: int,
    info: SocialInformation,
) -> Reports:
    """One sender's reports (:func:`select_reports_batch` for a single group)."""
    n_cells = unit.beliefs.n_cells
    return select_reports_batch([SenderInputs(unit, pool, memory_years, info)], year, n_cells).of(0)


def report_pool(unit: PopulationUnit, perceived: IntArray) -> IntArray:
    """Cells a group could mention: seen this year, lived in recently, or recently heard about.

    "Lived in" is the group's own residence within its memory horizon (at most one cell per
    year), not inherited foraging familiarity, so the pool stays small however long the
    lineage has been exploring.
    """
    lived = np.fromiter(unit.recent_residence, dtype=np.int64, count=len(unit.recent_residence))
    return np.concatenate([perceived, lived, unit.report_cells])


def receive_reports_batch(
    receivers: Sequence[tuple[str, BeliefMap]],
    pair_receiver: IntArray,
    pair_sender: IntArray,
    table: ReportTable,
    n_cells: int,
) -> list[BeliefPatch]:
    """Patches with the reports that improve each receiver's beliefs, in one pass.

    Pairs ``(pair_receiver[i], pair_sender[i])`` are encounters in partner order (a
    receiver's earlier pairs are its earlier partners). Among reports about one cell the
    freshest wins, then the one relayed fewest times, then the earliest partner. It replaces
    the receiver's belief if strictly fresher, or equally fresh with fewer relays. Accepted
    reports are stored with one more relay than the sender had.
    """
    lengths = table.count[pair_sender]
    pair = np.repeat(np.arange(pair_sender.size), lengths)
    within = np.arange(pair.size) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    rows = table.start[pair_sender][pair] + within
    if rows.size == 0:
        return []
    receiver, cells = pair_receiver[pair], table.cells[rows]
    year = table.year[rows].astype(np.int64)
    hops = np.minimum(table.hops[rows].astype(np.int64) + 1, MAX_HOPS)
    order = np.lexsort((pair, hops, -year, cells, receiver))
    receiver, cells = receiver[order], cells[order]
    first = np.r_[True, (receiver[1:] != receiver[:-1]) | (cells[1:] != cells[:-1])]
    order, receiver, cells = order[first], receiver[first], cells[first]
    year, hops, rows = year[order], hops[order], rows[order]
    bounds = np.searchsorted(receiver, np.arange(len(receivers) + 1))
    patches: list[BeliefPatch] = []
    for index, (unit_id, beliefs) in enumerate(receivers):
        lo, hi = int(bounds[index]), int(bounds[index + 1])
        if lo == hi:
            continue
        own = beliefs.sized(n_cells)
        c, y, h = cells[lo:hi], year[lo:hi], hops[lo:hi]
        own_year = own.year[c]
        better = (y > own_year) | ((y == own_year) & (h < own.hops[c]))
        if not better.any():
            continue
        take = rows[lo:hi][better]
        patches.append(
            BeliefPatch(
                unit_id,
                c[better],
                table.year[take],
                table.food_kcal[take],
                table.population[take],
                h[better].astype(HOPS_DTYPE),
                received=True,
            )
        )
    return patches


def receive_reports(
    unit_id: str, own: BeliefMap, received: Sequence[Reports], n_cells: int
) -> BeliefPatch | None:
    """One receiver's patch from its partners' reports (:func:`receive_reports_batch`)."""
    table = ReportTable.from_reports(received)
    senders = np.arange(len(received), dtype=np.int64)
    patches = receive_reports_batch(
        [(unit_id, own)], np.zeros(senders.size, dtype=np.int64), senders, table, n_cells
    )
    return patches[0] if patches else None


def candidate_encounters(
    units: Sequence[PopulationUnit], neighborhoods: IntArray
) -> tuple[IntArray, IntArray]:
    """All ``(receiver, partner)`` index pairs that may meet this year, in draw order.

    Order: receivers in unit order; for each, the cells of its neighborhood in ascending id
    order; within a cell, partners in unit order. A unit is never its own partner and only
    same-species groups meet. This is the order of the nested loop over receivers, cells and
    co-resident units, so drawing one uniform per pair reproduces its draws exactly.
    """
    n = len(units)
    if n == 0:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty
    cell = np.array([u.cell for u in units], dtype=np.int64)
    species = {sid: k for k, sid in enumerate(sorted({u.species_id for u in units}))}
    code = np.array([species[u.species_id] for u in units])
    by_cell = np.argsort(cell, kind="stable")  # unit order within each cell
    sorted_cells = cell[by_cell]
    n_cells = neighborhoods.shape[0]
    first = np.searchsorted(sorted_cells, np.arange(n_cells), side="left")
    count = np.searchsorted(sorted_cells, np.arange(n_cells), side="right") - first
    slots = neighborhoods[cell]  # (units, neighborhood size), -1 = padding
    valid = slots >= 0
    slot_cells = np.where(valid, slots, 0)
    lengths = np.where(valid, count[slot_cells], 0).ravel()
    offsets = first[slot_cells].ravel()
    receiver = np.repeat(np.repeat(np.arange(n), slots.shape[1]), lengths)
    within = np.arange(receiver.size) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    partner = by_cell[np.repeat(offsets, lengths) + within]
    keep = (partner != receiver) & (code[partner] == code[receiver])
    return receiver[keep], partner[keep]


@model_rule(
    name="neighbor_knowledge_sharing",
    version="2.0",
    rationale=(
        "Groups in the same or adjacent cells meet with a fixed probability per pair; at each "
        "encounter the partner passes its reports_per_interaction most salient beliefs "
        "(social_report_salience), which the receiver adopts where they are fresher than, or "
        "as fresh but less relayed than, what it knows."
    ),
    source_type="heuristic",
    parameters=("knowledge_sharing_probability", "reports_per_interaction"),
    expected_domain="each directed pair meets at most once per year",
    known_limitations=(
        "No trust, language, or cross-species barriers; report content is the sender's belief "
        "without added transmission noise (unreliability enters through confidence)."
    ),
)
class KnowledgeSharingSubsystem:
    """Bounded social transmission of spatial information between nearby groups."""

    name = "knowledge_sharing"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefPatch]:
        """Collect what each unit learns from neighbors (based on pre-sharing beliefs).

        Each candidate pair (receiver, a same-species group in the same or an adjacent cell)
        meets with the receiver's sharing probability, one independent draw per pair, in the
        order of :func:`candidate_encounters`; report selection and receipt run once for
        all units.
        """
        rng = ctx.rng.stream(Streams.KNOWLEDGE_SHARING)
        world = state.world
        units = list(state.units.values())
        receiver, sender = candidate_encounters(units, ctx.static.neighborhood_table(1))
        if receiver.size == 0:
            return []
        probability = np.array(
            [ctx.species(u.species_id).social.knowledge_sharing_probability for u in units]
        )
        met = rng.random(receiver.size) < probability[receiver]
        receiver, sender = receiver[met], sender[met]
        if receiver.size == 0:
            return []
        receiver_ids, pair_receiver = np.unique(receiver, return_inverse=True)
        first_seen = np.unique(sender, return_index=True)[1]
        sender_ids = sender[np.sort(first_seen)]  # in order of first encounter
        position = np.empty(len(units), dtype=np.int64)
        position[sender_ids] = np.arange(sender_ids.size)
        pair_sender = position[sender]
        senders = [units[i] for i in sender_ids.tolist()]
        receivers = [(units[i].id, units[i].beliefs) for i in receiver_ids.tolist()]
        inputs = []
        for sender in senders:
            profile = ctx.species(sender.species_id)
            inputs.append(
                SenderInputs(
                    sender,
                    report_pool(
                        sender,
                        ctx.static.perceived_cells(
                            sender.species_id, sender.cell, profile.cognition
                        ),
                    ),
                    profile.cognition.memory_years,
                    profile.social_information,
                )
            )
        table = select_reports_batch(inputs, state.year, world.n_cells)
        return receive_reports_batch(receivers, pair_receiver, pair_sender, table, world.n_cells)
