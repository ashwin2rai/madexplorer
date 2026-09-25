"""The simulation engine: builds state, runs the staged tick loop (spec §19)."""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from madexplorer.config.loader import Scenario
from madexplorer.core.events import EventLog
from madexplorer.core.ids import IdAllocator
from madexplorer.core.invariants import check_nonnegative, check_population_accounting, check_units
from madexplorer.core.provenance import run_manifest
from madexplorer.core.rng import RngManager, Streams
from madexplorer.core.state import CapabilityMap, SimulationState, StepContext
from madexplorer.core.static import StaticContext, static_key
from madexplorer.core.subsystem import Subsystem
from madexplorer.core.types import IntArray
from madexplorer.ecology.resources import initial_ecology
from madexplorer.ecology.subsystems import EcologySubsystem
from madexplorer.economy.agriculture import FarmingSubsystem, FieldPlanningSubsystem
from madexplorer.economy.foraging import ForagingSubsystem
from madexplorer.economy.trade import TradeSubsystem
from madexplorer.knowledge.diffusion import DiffusionSubsystem
from madexplorer.knowledge.innovation import InnovationSubsystem
from madexplorer.knowledge.learning import LearningSubsystem
from madexplorer.knowledge.system import KnowledgeModel
from madexplorer.metrics.recorder import MetricsRecorder
from madexplorer.mobility.exploration import KnowledgeSharingSubsystem, PerceptionSubsystem
from madexplorer.mobility.migration import MigrationSubsystem
from madexplorer.population.demography import DemographySubsystem
from madexplorer.population.energetics import EnergeticsSubsystem
from madexplorer.population.groups import ExtinctionSubsystem, FissionSubsystem, FusionSubsystem
from madexplorer.population.initialization import found_unit
from madexplorer.resolution.coarsening import CoarseningSubsystem
from madexplorer.world.climate import ClimateYear
from madexplorer.world.grid import WorldGrid
from madexplorer.world.subsystems import ClimateSubsystem

logger = logging.getLogger(__name__)


def build_pipeline(scenario: Scenario, knowledge: KnowledgeModel | None) -> list[Subsystem]:
    """Ordered subsystems for one step, honoring ablation switches.

    Order (documented because it matters): environment -> perception -> crop
    harvest -> foraging -> exchange -> energy balance -> demography -> field
    planning -> learning -> diffusion -> innovation -> group dynamics ->
    migration -> resolution. Each subsystem evaluates against the state left by
    the previous one; knowledge-dependent subsystems need a knowledge system.
    """
    mechanisms = scenario.config.mechanisms
    farming = mechanisms.cultivation and knowledge is not None
    pipeline: list[Subsystem] = [ClimateSubsystem(), EcologySubsystem(), PerceptionSubsystem()]
    if mechanisms.knowledge_sharing:
        pipeline.append(KnowledgeSharingSubsystem())
    if farming:
        pipeline.append(FarmingSubsystem())
    pipeline.append(ForagingSubsystem())
    if mechanisms.trade:
        pipeline.append(TradeSubsystem())
    pipeline += [EnergeticsSubsystem(), DemographySubsystem(), ExtinctionSubsystem()]
    if farming:
        pipeline.append(FieldPlanningSubsystem())
    if knowledge is not None:
        if mechanisms.knowledge_learning:
            pipeline.append(LearningSubsystem(knowledge))
        if mechanisms.knowledge_diffusion:
            pipeline.append(DiffusionSubsystem(knowledge))
        if mechanisms.innovation:
            pipeline.append(InnovationSubsystem(knowledge))
    if mechanisms.fission:
        pipeline.append(FissionSubsystem())
    if mechanisms.fusion:
        pipeline.append(FusionSubsystem())
    if mechanisms.migration:
        pipeline.append(MigrationSubsystem())
    if mechanisms.aggregation:
        pipeline.append(CoarseningSubsystem())
    return pipeline


@dataclass(eq=False)
class SimulationResult:
    """Everything a run produced."""

    scenario: Scenario
    world: WorldGrid
    metrics: list[dict[str, float | int]]
    events: EventLog
    snapshot_years: list[int]
    population_snapshots: list[IntArray]
    manifest: dict[str, Any] = field(default_factory=dict)

    def save(self, directory: str | Path) -> Path:
        """Write outputs to ``directory`` (see :mod:`madexplorer.persistence.output`)."""
        from madexplorer.persistence.output import write_run

        return write_run(self, Path(directory))


class Simulator:
    """Runs one scenario with one seed."""

    def __init__(
        self,
        scenario: Scenario,
        trace_units: Sequence[str] = (),
        static: StaticContext | None = None,
        record_events: bool = True,
    ) -> None:
        self.scenario = scenario
        config = scenario.config
        self.rng = RngManager(config.simulation.seed)
        self.ids = IdAllocator()
        self.events = EventLog(enabled=record_events)
        self.trace_units = frozenset(config.output.trace_units) | frozenset(trace_units)
        # Cumulative seconds per subsystem (evaluate + apply) when set to a dict; benchmarks only.
        self.timings: dict[str, float] | None = None
        if static is None:
            static = StaticContext.build(scenario)
        elif static.key != static_key(scenario):
            raise ValueError("static context was built for a different scenario")
        self.static = static
        self.world = static.world
        self.tables = static.tables
        self.movement = static.movement
        self.capability_cache: dict[frozenset[str], CapabilityMap] = {}
        self.knowledge = KnowledgeModel(scenario.knowledge) if scenario.knowledge else None
        self.pipeline = build_pipeline(scenario, self.knowledge)
        climate = ClimateYear.base(self.world)
        self.state = SimulationState(
            year=config.simulation.start_year,
            world=self.world,
            climate=climate,
            ecology=initial_ecology(self.world, climate, config.ecology),
            units={},
        )
        self._found_initial_units()

    def _found_initial_units(self) -> None:
        rng = self.rng.stream(Streams.INITIALIZATION)
        for seed in self.scenario.config.initial_populations:
            cell = self.world.cell_id(*seed.cell)
            if self.world.is_water[cell]:
                raise ValueError(f"initial population cell {seed.cell} is water in this world")
            profile = self.scenario.species[seed.species]
            unit = found_unit(
                self.ids.next("u"),
                seed,
                cell,
                profile,
                self.tables[seed.species],
                self.state.year,
                rng,
                self.knowledge,
            )
            self.state.units[unit.id] = unit
            self.events.emit(
                self.state.year,
                "unit_founded",
                unit_id=unit.id,
                species=seed.species,
                cell=list(seed.cell),
                population=unit.population,
                reason="initial_population",
            )

    def context(self) -> StepContext:
        """A fresh step context for the current year (dependencies and an empty ledger)."""
        return StepContext(
            year=self.state.year,
            scenario=self.scenario,
            rng=self.rng,
            ids=self.ids,
            events=self.events,
            static=self.static,
            trace_units=self.trace_units,
            knowledge=self.knowledge,
            capability_cache=self.capability_cache,
        )

    def step(self) -> StepContext:
        """Advance the simulation by one year."""
        state = self.state
        state.year += 1
        ctx = self.context()
        before = state.total_population()
        timings = self.timings
        for subsystem in self.pipeline:
            started = time.perf_counter() if timings is not None else 0.0
            for proposal in subsystem.evaluate(state, ctx):
                proposal.apply(state, ctx)
            if timings is not None:
                elapsed = time.perf_counter() - started
                timings[subsystem.name] = timings.get(subsystem.name, 0.0) + elapsed
        started = time.perf_counter() if timings is not None else 0.0
        if self.scenario.config.debug.check_invariants:
            check_population_accounting(
                before, ctx.ledger.births, ctx.ledger.deaths, state.total_population(), state.year
            )
            check_units(state.units.values(), self.world.n_cells, state.year)
            check_nonnegative("plant_stock_kcal", state.ecology.plant_stock_kcal, state.year)
            check_nonnegative("game_stock_kcal", state.ecology.game_stock_kcal, state.year)
        if timings is not None:
            timings["invariants"] = timings.get("invariants", 0.0) + time.perf_counter() - started
        return ctx

    def run(
        self,
        progress: Callable[[dict[str, float | int]], None] | None = None,
        light: bool = False,
    ) -> SimulationResult:
        """Run the full horizon and return the result.

        ``light`` records only the per-year fields ensemble summaries use and no spatial
        snapshots (the model itself is unaffected).
        """
        config = self.scenario.config
        recorder = MetricsRecorder(
            self.scenario, config.output.spatial_snapshot_interval_years, light=light
        )
        if not light:
            recorder.snapshot(self.state)
        started = time.perf_counter()
        for _ in range(config.simulation.n_years):
            ctx = self.step()
            row = recorder.record(self.state, ctx)
            if progress is not None:
                progress(row)
            if self.state.total_population() == 0:
                logger.info("year=%d all populations extinct; stopping early", self.state.year)
                break
        elapsed = time.perf_counter() - started
        manifest = run_manifest(self.scenario, runtime_seconds=elapsed, final_year=self.state.year)
        return SimulationResult(
            scenario=self.scenario,
            world=self.world,
            metrics=recorder.rows,
            events=self.events,
            snapshot_years=recorder.snapshot_years,
            population_snapshots=recorder.snapshots,
            manifest=manifest,
        )
