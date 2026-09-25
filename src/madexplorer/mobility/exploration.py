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
from madexplorer.world.grid import WorldGrid


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


def perceived_cells(unit: PopulationUnit, cognition: Cognition, world: WorldGrid) -> IntArray:
    """Land cells the unit observes this year (ascending)."""
    radius = perception_radius_cells(
        cognition, float(world.vegetation_density[unit.cell]), world.cell_size_km
    )
    return world.land_cells_within(unit.cell, radius)


class PerceptionSubsystem:
    """Each unit observes nearby land cells and forms its food prior from them."""

    name = "perception"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[BeliefPatch]:
        """This year's direct observations of the cells each unit can see (sparse patches).

        Old observations are not scanned or erased here: expiry is lazy (see
        :class:`BeliefMap`), so the cost is proportional to the cells perceived. The mean of
        this year's food observations becomes the unit's prior for uncertain reports.
        """
        rng = ctx.rng.stream(Streams.PERCEPTION)
        world = state.world
        cell_population = state.cell_population()
        food_by_species = {
            sid: accessible_food_kcal(state, profile.foraging)
            for sid, profile in ctx.scenario.species.items()
        }
        year = np.int32(state.year)
        updates: list[BeliefPatch] = []
        for unit in state.units.values():
            cognition = ctx.species(unit.species_id).cognition
            cells = perceived_cells(unit, cognition, world)
            noise = np.exp(cognition.observation_noise_sigma * rng.standard_normal(cells.size))
            food = food_by_species[unit.species_id][cells] * noise
            others = cell_population[cells]
            updates.append(
                BeliefPatch(
                    unit.id,
                    cells,
                    np.full(cells.size, year, dtype=YEAR_DTYPE),
                    food,
                    np.where(cells == unit.cell, others - unit.population, others),
                    np.zeros(cells.size, dtype=HOPS_DTYPE),
                    food_prior_kcal=float(food.mean()),
                    resident_cell=unit.cell,
                )
            )
        return updates


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
        "(1 + |ln(food / prior)|), so first-hand, recent and unusually rich or poor places are "
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
    prior_kcal: FloatArray | float,
) -> FloatArray:
    """Salience of candidate reports (higher is mentioned first); elementwise.

    A nonpositive prior (a group that has not perceived yet) makes no place exceptional.
    """
    recency = 1.0 - age_years / (np.asarray(max_age_years) + 1.0)
    prior = np.broadcast_to(np.asarray(prior_kcal, dtype=np.float64), food_kcal.shape)
    safe = np.where(prior > 0, prior, 1.0)
    exceptional = np.where(prior > 0, np.abs(np.log(np.maximum(food_kcal, 1.0) / safe)), 0.0)
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
        per_sender([s.unit.food_prior_kcal for s in senders]),
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


def report_pool(unit: PopulationUnit, cognition: Cognition, world: WorldGrid) -> IntArray:
    """Cells a group could mention: seen this year, lived in recently, or recently heard about.

    "Lived in" is the group's own residence within its memory horizon (at most one cell per
    year), not inherited foraging familiarity, so the pool stays small however long the
    lineage has been exploring.
    """
    lived = np.fromiter(unit.recent_residence, dtype=np.int64, count=len(unit.recent_residence))
    return np.concatenate([perceived_cells(unit, cognition, world), lived, unit.report_cells])


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

        Encounters are drawn unit by unit in a fixed order (one draw per candidate pair);
        report selection and receipt then run once for all units.
        """
        rng = ctx.rng.stream(Streams.KNOWLEDGE_SHARING)
        by_cell = state.units_by_cell()
        world = state.world
        sender_index: dict[str, int] = {}
        senders: list[PopulationUnit] = []
        receivers: list[tuple[str, BeliefMap]] = []
        pair_receiver: list[int] = []
        pair_sender: list[int] = []
        for unit in state.units.values():
            probability = ctx.species(unit.species_id).social.knowledge_sharing_probability
            receiver = len(receivers)
            for cell in world.cells_within(unit.cell, 1):
                for other in by_cell.get(cell, []):
                    if other is unit or other.species_id != unit.species_id:
                        continue
                    if rng.random() < probability:
                        index = sender_index.get(other.id)
                        if index is None:
                            index = sender_index[other.id] = len(senders)
                            senders.append(other)
                        pair_receiver.append(receiver)
                        pair_sender.append(index)
            if pair_receiver and pair_receiver[-1] == receiver:
                receivers.append((unit.id, unit.beliefs))
        if not pair_receiver:
            return []
        inputs = []
        for sender in senders:
            profile = ctx.species(sender.species_id)
            inputs.append(
                SenderInputs(
                    sender,
                    report_pool(sender, profile.cognition, world),
                    profile.cognition.memory_years,
                    profile.social_information,
                )
            )
        table = select_reports_batch(inputs, state.year, world.n_cells)
        return receive_reports_batch(
            receivers,
            np.asarray(pair_receiver, dtype=np.int64),
            np.asarray(pair_sender, dtype=np.int64),
            table,
            world.n_cells,
        )
