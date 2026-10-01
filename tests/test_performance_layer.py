"""Performance-layer contracts: compiled scenario data and the shared spatial index.

These structures change no equation; the tests check that they reproduce the domain
representation exactly (order included), which exact seeded replay depends on.
"""

from collections.abc import Mapping

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.config.loader import Scenario
from madexplorer.core.compiled import CompiledScenario
from madexplorer.core.simulation import Simulator
from madexplorer.core.spatial import SpatialIndex
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, mvp2_scenario_dict, step_context


def _mvp2() -> Scenario:
    return Scenario.from_dict(mvp2_scenario_dict(), base_dir=ROOT)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.integers(0, 12), min_size=0, max_size=60))
def test_spatial_index_reproduces_units_by_cell_order(cells: list[int]) -> None:
    sim = Simulator(_mvp2())
    (template,) = sim.state.units.values()
    sim.state.units.clear()
    for k, cell in enumerate(cells):
        unit = type(template)(
            id=f"u{1000 - k}",  # ids deliberately not in insertion order
            species_id=template.species_id,
            cell=cell,
            females=template.females,
            males=template.males,
            reserve_kcal_per_capita=0.0,
            founded_year=0,
        )
        sim.state.units[unit.id] = unit
    index = SpatialIndex.build(tuple(sim.state.units.values()))
    reference = sim.state.units_by_cell()
    assert list(index.by_cell) == list(reference)
    for cell, units in reference.items():
        assert [u.id for u in index.by_cell[cell]] == [u.id for u in units]
    for k, cell in enumerate(index.cells.tolist()):
        rows = index.order[index.starts[k] : index.starts[k + 1]]
        assert [index.units[r].id for r in rows] == [u.id for u in reference[cell]]
    assert all(index.row_of[u.id] == i for i, u in enumerate(index.units))


def test_spatial_index_is_shared_within_a_phase_and_rebuilt_after_membership_changes() -> None:
    sim = synthetic_simulator(Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml"), 60)
    for _ in range(12):  # through fissions, fusions and migrations
        ctx = step_context(sim)
        first = ctx.spatial(sim.state)
        assert ctx.spatial(sim.state) is first
        sim.step()
        fresh = step_context(sim).spatial(sim.state)
        reference = sim.state.units_by_cell()
        assert list(fresh.by_cell) == list(reference)
        assert all(
            [u.id for u in fresh.by_cell[c]] == [u.id for u in units]
            for c, units in reference.items()
        )


def test_membership_changing_applies_invalidate_the_index() -> None:
    from madexplorer.mobility.migration import Relocation
    from madexplorer.population.groups import Extinction

    sim = Simulator(_mvp2())
    ctx = step_context(sim)
    (unit,) = sim.state.units.values()
    before = ctx.spatial(sim.state)
    Relocation(unit.id, unit.cell, unit.cell + 1, 1.0, 0.0, 0.5, 0.0).apply(sim.state, ctx)
    moved = ctx.spatial(sim.state)
    assert moved is not before and moved.cell[0] == unit.cell
    unit.females, unit.males = unit.females * 0, unit.males * 0
    Extinction(unit.id).apply(sim.state, ctx)
    assert ctx.spatial(sim.state).units == ()


def test_compiled_scenario_matches_configuration() -> None:
    scenario = _mvp2()
    sim = Simulator(scenario)
    compiled = CompiledScenario.build(scenario, sim.knowledge)
    human = scenario.species["human"]
    k = compiled.species_index["human"]
    assert compiled.parameter("metabolism.adult_daily_kcal")[k] == human.metabolism.adult_daily_kcal
    assert compiled.parameter("cognition.memory_years")[k] == human.cognition.memory_years
    table = compiled.technologies
    assert table is not None and sim.knowledge is not None
    for tech_id, tech in sim.knowledge.technologies.items():
        i = table.position[tech_id]
        required = {t for t in table.ids if table.requires_mask[i] >> table.position[t] & 1}
        assert required == set(tech.requires)
        for domain, level in tech.min_knowledge.items():
            assert table.min_knowledge[i, sim.knowledge.index[domain]] == level
    sets = [frozenset(), frozenset(table.ids[:2]), frozenset(table.ids)]
    held = table.holds(table.masks(sets))
    for row, techs in zip(held, sets, strict=True):
        assert {table.ids[i] for i in np.flatnonzero(row)} == techs


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from([0.0, 1.0, 5e5, 1e6]) | st.floats(1.0, 2e6),
            st.sampled_from([0.0, 1e6]) | st.floats(0.0, 3e6),
            st.floats(0.0, 1e6),
            st.floats(0.0, 1e6),
            st.floats(0.0, 1e6),
            st.booleans(),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_batched_energy_balance_equals_the_scalar_rule(rows: list[tuple]) -> None:  # type: ignore[type-arg]
    from madexplorer.population.energetics import energy_balance, energy_balance_batch

    need, harvest, reserve, cap, stores, can = (np.array(c) for c in zip(*rows, strict=True))
    batched = energy_balance_batch(need, harvest, reserve, cap, stores, can.astype(bool))
    for i, row in enumerate(rows):
        b = energy_balance(*row)
        expected = (
            b.food_ratio,
            b.deficit,
            b.reserve_kcal,
            b.stores_kcal,
            b.stored_kcal,
            b.spoiled_kcal,
        )
        assert tuple(float(a[i]) for a in batched) == expected


def test_trade_ties_stay_symmetric_among_live_units_so_rewiring_is_local() -> None:
    """The O(degree) tie rewiring relies on this invariant; check it through a run."""
    sim = synthetic_simulator(Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml"), 150)
    for _ in range(25):
        sim.step()
        units = sim.state.units
        for uid, unit in units.items():
            for partner in unit.trade_ties:
                if partner in units:
                    assert uid in units[partner].trade_ties


@settings(max_examples=300, deadline=None)
@given(
    st.lists(
        st.lists(
            st.floats(allow_nan=False, allow_infinity=False, width=64)
            | st.sampled_from([0.0, -0.0, 1e16, -1e16, 1.0, 1e-16]),
            min_size=3,
            max_size=3,
        ),
        min_size=1,
        max_size=20,
    ),
    st.integers(1, 3),
)
def test_python_sum_columns_equals_the_builtin_sum(rows: list[list[float]], width: int) -> None:
    from madexplorer.core.exactsum import python_sum_columns

    columns = [np.array([r[j] for r in rows]) for j in range(width)]
    result = python_sum_columns(columns)
    for i, row in enumerate(rows):
        expected = sum(row[:width])
        assert result[i] == expected or (np.isnan(result[i]) and np.isnan(expected))
        assert np.signbit(result[i]) == np.signbit(expected) or result[i] != 0.0


def test_batched_unit_kernels_equal_their_per_unit_references() -> None:
    """Differential test on a warmed-up farming state: every batched kernel against the
    per-unit reference rule it replaces, bit for bit."""
    from madexplorer.economy.agriculture import (
        crop_yield_batch,
        labor_hours_batch,
        unit_crop_yield,
        unit_labor_hours,
    )
    from madexplorer.knowledge.learning import (
        LearningSubsystem,
        activity_shares,
        learn,
    )
    from madexplorer.population.energetics import annual_need_batch, annual_need_kcal

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml")
    sim = synthetic_simulator(scenario, 120, farming=True)
    for _ in range(8):
        sim.step()
    ctx = step_context(sim)
    state = sim.state
    units = tuple(state.units.values())
    need = annual_need_batch(units, state, ctx)
    labor = labor_hours_batch(units, ctx)
    potential = ctx.crop_potential(state)
    crop = crop_yield_batch(units, potential, ctx)
    assert sim.knowledge is not None
    (proposal,) = LearningSubsystem(sim.knowledge).evaluate(state, ctx)
    for i, u in enumerate(units):
        profile, tables = ctx.species(u.species_id), ctx.tables[u.species_id]
        temperature = float(state.climate.temperature_c[u.cell])
        assert need[i] == annual_need_kcal(u, profile, tables, temperature)
        assert labor[i] == unit_labor_hours(u, ctx)
        assert crop[i] == unit_crop_yield(u, potential, ctx)
        practice = sim.knowledge.practice_weights(activity_shares(u, unit_labor_hours(u, ctx)))
        expected = learn(
            u.knowledge,
            practice,
            u.population,
            sim.knowledge,
            profile.cognition.learning_speed,
            profile.cognition.knowledge_retention,
        )
        assert np.array_equal(proposal.knowledge[i], expected)
    assert (crop > 0).any() and any(u.fields_ha > 0 for u in units)


def _warm_state(n_units: int, seed: int, ticks: int = 6):  # type: ignore[no-untyped-def]
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    sim = synthetic_simulator(scenario, n_units)
    for _ in range(ticks):
        sim.step()
    return sim


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000))
def test_packed_sharing_equals_the_reference_selection_and_receipt(seed: int) -> None:
    import copy

    from madexplorer.mobility.exploration import (
        ReportTable,
        SenderInputs,
        receive_reports_batch,
        receive_reports_packed,
        report_pool,
        select_reports_batch,
        select_reports_packed,
    )

    sim = _warm_state(80, seed)
    state, ctx = sim.state, step_context(sim)
    units = list(state.units.values())
    rng = np.random.default_rng(seed)
    senders = [units[i] for i in rng.choice(len(units), size=min(30, len(units)), replace=False)]
    profile = ctx.species("human")
    pools = [
        report_pool(u, ctx.static.perceived_cells(u.species_id, u.cell, profile.cognition))
        for u in senders
    ]
    n_cells = state.world.n_cells
    inputs = [
        SenderInputs(u, pool, profile.cognition.memory_years, profile.social_information)
        for u, pool in zip(senders, pools, strict=True)
    ]
    reference = select_reports_batch(inputs, state.year, n_cells)
    info = profile.social_information
    k = len(senders)
    from madexplorer.population.unit import belief_slot

    store = state.belief_store
    packed = select_reports_packed(
        store,
        np.array([belief_slot(u) for u in senders]),
        pools,
        np.array([u.cell for u in senders]),
        np.array([u.food_log_prior for u in senders]),
        np.full(k, float(profile.cognition.memory_years)),
        np.full(k, float(info.max_report_age_years)),
        np.full(k, info.transmission_confidence_decay),
        np.full(k, info.reports_per_interaction, dtype=np.int64),
        state.year,
        n_cells,
    )
    for name in ReportTable.__dataclass_fields__:
        assert np.array_equal(getattr(reference, name), getattr(packed, name))
    receivers_units = [units[i] for i in rng.choice(len(units), size=25, replace=False)]
    pair_receiver = rng.integers(0, len(receivers_units), size=120)
    pair_sender = rng.integers(0, k, size=120)
    order = np.argsort(pair_receiver, kind="stable")
    pair_receiver, pair_sender = pair_receiver[order], pair_sender[order]
    receivers = [(u.id, u.beliefs) for u in receivers_units]
    patches = receive_reports_batch(receivers, pair_receiver, pair_sender, reference, n_cells)
    proposal = receive_reports_packed(
        [u.id for u in receivers_units],
        np.array([belief_slot(u) for u in receivers_units]),
        store,
        pair_receiver,
        pair_sender,
        reference,
        n_cells,
    )
    state_a, state_b = copy.deepcopy(state), copy.deepcopy(state)
    for patch in patches:
        patch.apply(state_a, ctx)
    proposal.apply(state_b, ctx)
    assert proposal.unit_ids == tuple(p.unit_id for p in patches)
    for uid in state.units:
        a, b = state_a.units[uid], state_b.units[uid]
        for field in ("year", "food_kcal", "population", "hops"):
            assert np.array_equal(getattr(a.beliefs, field), getattr(b.beliefs, field))
        assert np.array_equal(a.report_cells, b.report_cells)


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000), st.booleans())
def test_batched_migration_equals_the_reference_evaluate(seed: int, farming: bool) -> None:
    from madexplorer.core.rng import Streams
    from madexplorer.mobility.migration import MigrationSubsystem, MoveHazards, Relocation

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    sim = synthetic_simulator(scenario, 90, farming=farming)
    for _ in range(7):
        sim.step()
    subsystem = MigrationSubsystem()
    outcomes = []
    for method in (subsystem.evaluate, subsystem._evaluate_reference):
        ctx = step_context(sim)
        rng = ctx.rng.stream(Streams.MIGRATION)
        saved = rng.bit_generator.state
        proposals = method(sim.state, ctx)
        hazards = [p.hazards for p in proposals if isinstance(p, MoveHazards)]
        moves = [
            (m.unit_id, m.destination, m.path_cost_km, m.travel_kcal, m.hazard, m.carry_kcal)
            for m in proposals
            if isinstance(m, Relocation)
        ]
        ledger = (ctx.ledger.migration_decisions, ctx.ledger.food_saturated_decisions)
        outcomes.append((hazards, moves, ledger, rng.bit_generator.state))
        rng.bit_generator.state = saved
    assert outcomes[0] == outcomes[1]
    assert any(h > 0 for h in outcomes[0][0][0].values())
    if farming:
        assert any(u.fields_ha > 0 for u in sim.state.units.values())


def test_batched_migration_with_exact_ties_uses_the_reference_tie_break() -> None:
    from dataclasses import replace

    from madexplorer.core.rng import Streams
    from madexplorer.mobility.migration import MigrationSubsystem, Relocation
    from madexplorer.population.unit import BeliefMap, Observation

    sim = Simulator(_mvp2())
    sim.state.world = replace(sim.world, water_access=np.full(sim.world.n_cells, 0.5))
    (unit,) = sim.state.units.values()
    movement = sim.movement[unit.species_id]  # this simulator's own static context
    reachable = {c: 0.0 if c == unit.cell else 20.0 for c in movement.reachable(unit.cell)}
    movement._reachable[unit.cell] = reachable  # equal path costs: exact utility ties
    movement._reachable_arrays.pop(unit.cell, None)
    rich = {c: Observation(year=sim.state.year, food_kcal=4e7, population=0) for c in reachable}
    rich[unit.cell] = Observation(year=sim.state.year, food_kcal=1e5, population=0)
    unit.beliefs = BeliefMap.from_observations(sim.world.n_cells, rich)
    unit.food_log_prior, unit.food_log_signal_var = float(np.log(1e6)), 1.0  # finite utilities
    subsystem = MigrationSubsystem()
    fallbacks: list[int] = []
    reference = subsystem._evaluate_reference

    def counted(state, ctx):  # type: ignore[no-untyped-def]
        fallbacks.append(1)
        return reference(state, ctx)

    subsystem._evaluate_reference = counted  # type: ignore[method-assign]
    results = []
    for method in ("evaluate", "_evaluate_reference"):
        ctx = step_context(sim)
        rng = ctx.rng.stream(Streams.MIGRATION)
        saved = rng.bit_generator.state
        proposals = getattr(subsystem, method)(sim.state, ctx)
        results.append(
            ([(p.destination, p.hazard) for p in proposals if isinstance(p, Relocation)],
             rng.bit_generator.state)
        )  # fmt: skip
        rng.bit_generator.state = saved
    assert results[0] == results[1]
    assert len(fallbacks) == 2  # evaluate handed the tie to the reference path
    assert results[0][0]  # the move happened, to one of the tied cells


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000), st.booleans(), st.booleans())
def test_batched_diffusion_equals_the_reference_evaluate(
    seed: int, farming: bool, forget: bool
) -> None:
    from madexplorer.core.rng import Streams
    from madexplorer.knowledge.diffusion import DiffusionBatch, DiffusionSubsystem

    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=seed
    )
    sim = synthetic_simulator(scenario, 90, farming=farming)
    for _ in range(6):
        sim.step()
    rng = np.random.default_rng(seed)
    units = list(sim.state.units.values())
    for k in rng.choice(len(units), size=len(units) // 3, replace=False).tolist():
        unit = units[k]
        if forget:  # knowledge below requirements: technology loss and cascades
            unit.knowledge = unit.knowledge * rng.uniform(0.0, 0.2)
        elif unit.technologies:  # drop a technology so neighbors can pass it on
            unit.technologies = frozenset(sorted(unit.technologies)[1:])
    assert sim.knowledge is not None
    subsystem = DiffusionSubsystem(sim.knowledge)
    outcomes = []
    for method in (subsystem.evaluate, subsystem._evaluate_reference):
        ctx = step_context(sim)
        stream = ctx.rng.stream(Streams.TECHNOLOGY_ADOPTION)
        saved = stream.bit_generator.state
        rows = []
        for proposal in method(sim.state, ctx):
            if isinstance(proposal, DiffusionBatch):
                ids = [proposal.cols.units[r].id for r in proposal.rows.tolist()]
                for k, uid in enumerate(ids):
                    rows.append((uid, proposal.gains[k].tolist(), proposal.adopted[k],
                                 proposal.lost[k]))  # fmt: skip
            else:
                rows.append((proposal.unit_id, proposal.gain.tolist(), proposal.adopted,
                             proposal.lost))  # fmt: skip
        outcomes.append((rows, stream.bit_generator.state))
        stream.bit_generator.state = saved
    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0]
    if forget and farming:  # every technology is held, so losses must occur
        assert any(r[3] for r in outcomes[0][0])


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000))
def test_batched_innovation_equals_the_reference_evaluate(seed: int) -> None:
    from madexplorer.core.rng import Streams
    from madexplorer.knowledge.innovation import InnovationSubsystem

    sim = _warm_state(90, seed)
    rng = np.random.default_rng(seed)
    units = list(sim.state.units.values())
    assert sim.knowledge is not None
    ids = [t.id for t in sim.knowledge.system.technologies]
    for k in rng.choice(len(units), size=len(units) // 2, replace=False).tolist():
        unit = units[k]  # varied knowledge and holdings: many candidate technologies
        unit.knowledge = unit.knowledge + rng.uniform(0.0, 6.0, size=unit.knowledge.size)
        unit.technologies = frozenset(t for t in ids if rng.random() < 0.3)
    subsystem = InnovationSubsystem(sim.knowledge)
    outcomes = []
    for method in (subsystem.evaluate, subsystem._evaluate_reference):
        ctx = step_context(sim)
        stream = ctx.rng.stream(Streams.INNOVATION)
        saved = stream.bit_generator.state
        proposals = [
            (p.unit_id, p.technology, p.hazard, p.components) for p in method(sim.state, ctx)
        ]
        outcomes.append((proposals, stream.bit_generator.state))
        stream.bit_generator.state = saved
    assert outcomes[0] == outcomes[1]
    assert outcomes[0][1] != saved  # candidates existed and drew


def test_packed_perception_equals_per_unit_patches() -> None:
    import copy

    from madexplorer.mobility.exploration import PerceptionSubsystem

    sim = _warm_state(70, 3)
    sim.capability_cache.clear()
    sim_a, sim_b = copy.deepcopy(sim), copy.deepcopy(sim)  # same state and RNG streams
    ctx_a, ctx_b = step_context(sim_a), step_context(sim_b)
    (packed_a,) = PerceptionSubsystem().evaluate(sim_a.state, ctx_a)
    (packed_b,) = PerceptionSubsystem().evaluate(sim_b.state, ctx_b)
    for patch in packed_a.as_patches(sim_a.state.year):
        patch.apply(sim_a.state, ctx_a)
    packed_b.apply(sim_b.state, ctx_b)
    for uid, a in sim_a.state.units.items():
        b = sim_b.state.units[uid]
        for field in ("year", "food_kcal", "population", "hops"):
            assert np.array_equal(getattr(a.beliefs, field), getattr(b.beliefs, field))
        assert a.food_log_prior == b.food_log_prior or (
            np.isnan(a.food_log_prior) and np.isnan(b.food_log_prior)
        )
        assert a.food_log_signal_var == b.food_log_signal_var
        assert a.recent_residence == b.recent_residence


@settings(max_examples=300, deadline=None)
@given(
    st.floats(0.0, 5e7),
    st.floats(0.0, 5e7),
    st.floats(0.0, 2000.0),
    st.floats(0.0, 2000.0),
    st.sampled_from([0.0]) | st.floats(0.0, 3e5),
    st.floats(0.05, 1.0),
    st.sampled_from([0.0, 1e12]) | st.floats(0.0, 3e7),
)
def test_single_unit_foraging_fast_path_equals_cell_harvest(
    plant: float, game: float, r_p: float, r_g: float, labor: float, eff: float, target: float
) -> None:
    from madexplorer.economy.foraging import cell_harvest, single_unit_harvest

    outcome = cell_harvest(
        np.array([plant, game]), np.array([r_p, r_g]), np.array([labor]), np.array([eff]), target
    )
    share, p_removed, g_removed, fraction, marginal = single_unit_harvest(
        (plant, game), (r_p, r_g), labor, eff, target
    )
    assert share == float(outcome.shares[0])
    assert (p_removed, g_removed) == (float(outcome.removal[0]), float(outcome.removal[1]))
    assert fraction == outcome.effort_fraction
    assert marginal == outcome.marginal_kcal_per_effective_hour


def _beliefs_equal(a, b) -> bool:  # type: ignore[no-untyped-def]
    return all(
        np.array_equal(getattr(a, f), getattr(b, f))
        for f in ("year", "food_kcal", "population", "hops")
    )


def test_belief_store_slot_reuse_never_leaks_old_beliefs() -> None:
    from madexplorer.population.unit import BeliefMap, belief_slot

    sim = _warm_state(40, 1)
    units = sim.state.units
    victim = next(u for u in units.values() if (u.beliefs.year > 0).any())
    kept = victim.beliefs.copy()
    slot = belief_slot(victim)
    units.pop(victim.id)
    assert belief_slot(victim) == -1 and _beliefs_equal(victim.beliefs, kept)  # detached copy
    newcomer = type(victim)(
        id="u_new",
        species_id=victim.species_id,
        cell=victim.cell,
        females=victim.females,
        males=victim.males,
        reserve_kcal_per_capita=0.0,
        founded_year=sim.state.year,
    )
    units[newcomer.id] = newcomer
    assert belief_slot(newcomer) == slot  # the freed row was reused ...
    assert _beliefs_equal(newcomer.beliefs, BeliefMap.empty(sim.world.n_cells))  # ... cleanly


def test_belief_store_growth_preserves_every_row() -> None:
    sim = _warm_state(30, 2)
    store = sim.state.belief_store
    before = {uid: u.beliefs.copy() for uid, u in sim.state.units.items()}
    template = next(iter(sim.state.units.values()))
    for k in range(store.capacity + 5):  # force at least one resize
        extra = type(template)(
            id=f"x{k}",
            species_id=template.species_id,
            cell=template.cell,
            females=template.females,
            males=template.males,
            reserve_kcal_per_capita=0.0,
            founded_year=0,
        )
        sim.state.units[extra.id] = extra
    assert store.resizes >= 1
    for uid, beliefs in before.items():
        assert _beliefs_equal(sim.state.units[uid].beliefs, beliefs)


def test_structural_events_give_the_object_reference_beliefs() -> None:
    """Fission and fusion on store-backed units equal the same operations on detached,
    object-held beliefs (the pre-PH3a representation)."""
    import copy

    from madexplorer.population.composition import MergeMode, merge_state, split_off
    from madexplorer.population.familiarity import familiarity_rule
    from madexplorer.population.unit import detach_beliefs

    sim = _warm_state(60, 5)
    state, ctx = sim.state, step_context(sim)
    rule = familiarity_rule(ctx.species("human"), ctx.mechanisms)
    a, b = list(state.units.values())[:2]
    b.cell = a.cell  # co-locate them (merging requires one cell)
    # Reference: detached deep copies.
    ra, rb = copy.deepcopy(a), copy.deepcopy(b)
    detach_beliefs(ra)
    detach_beliefs(rb)
    merge_state(ra, rb, MergeMode.FUSION, state.year, rule)
    merge_state(a, b, MergeMode.FUSION, state.year, rule)
    assert _beliefs_equal(a.beliefs, ra.beliefs)
    # Fission: the daughter inherits a copy; parent and daughter then diverge independently.
    leave_f, leave_m = a.females // 2, a.males // 2
    rd = split_off(ra, leave_f, leave_m, "ref_d", state.year, rule)
    daughter = split_off(a, leave_f, leave_m, "d", state.year, rule)
    state.units[daughter.id] = daughter
    assert _beliefs_equal(daughter.beliefs, rd.beliefs)
    cell = int(np.flatnonzero(daughter.beliefs.year > 0)[0])
    daughter.beliefs.write(np.array([cell]), 9999, np.array([1.0]), np.array([0]), 0)
    assert a.beliefs.year[cell] != 9999  # separate rows


def _merge_trade_contacts_reference(
    units: list[PopulationUnit],
    row_of: Mapping[str, int],
    receiver: IntArray,
    partner: IntArray,
    weight: FloatArray,
    position: IntArray,
    trade: float,
) -> tuple[IntArray, IntArray, FloatArray, IntArray]:
    """The PH2 per-receiver dictionary loop (kept here as the oracle)."""
    n = len(units)
    weight = weight.copy()
    bounds = np.searchsorted(receiver, np.arange(n + 1)).tolist()
    extra_r: list[int] = []
    extra_s: list[int] = []
    extra_w: list[float] = []
    extra_p: list[int] = []
    for i, unit in enumerate(units):
        ties = unit.trade_ties
        if not ties:
            continue
        lo, hi = bounds[i], bounds[i + 1]
        local = {int(j): lo + k for k, j in enumerate(partner[lo:hi].tolist())}
        appended: dict[int, int] = {}
        for partner_id, tie in ties.items():
            if partner_id not in row_of:
                continue
            j = row_of[partner_id]
            edge = local.get(j)
            if edge is not None:
                weight[edge] = weight[edge] + trade * tie
            else:
                appended[j] = len(extra_w)
                extra_r.append(i)
                extra_s.append(j)
                extra_w.append(0.0 + trade * tie)
                extra_p.append(hi - lo + len(appended) - 1)
    return (
        np.concatenate([receiver, np.array(extra_r, dtype=np.int64)]),
        np.concatenate([partner, np.array(extra_s, dtype=np.int64)]),
        np.concatenate([weight, np.array(extra_w, dtype=np.float64)]),
        np.concatenate([position, np.array(extra_p, dtype=np.int64)]),
    )


@settings(max_examples=8, deadline=None)
@given(st.integers(0, 10_000))
def test_trade_contact_merge_equals_the_dictionary_loop(seed: int) -> None:
    from madexplorer.knowledge.diffusion import merge_trade_contacts

    sim = _warm_state(60, seed, ticks=2)
    rng = np.random.default_rng(seed)
    units = list(sim.state.units.values())
    ids = [u.id for u in units]
    for unit in units:  # random ties: local and distant partners, and dead ids
        unit.trade_ties = {}
        for _ in range(int(rng.integers(0, 6))):
            partner_id = "dead" if rng.random() < 0.15 else ids[int(rng.integers(len(ids)))]
            if partner_id != unit.id:
                unit.trade_ties[partner_id] = float(rng.uniform(0.001, 3.0))
    index = SpatialIndex.build(tuple(units))
    receiver, partner = index.local_pairs(sim.static.neighborhood_table(1))
    weight = rng.uniform(0.1, 1.0, size=receiver.size)
    position = np.arange(receiver.size) - np.searchsorted(receiver, receiver)
    expected = _merge_trade_contacts_reference(
        units, index.row_of, receiver, partner, weight, position, 0.7
    )
    got = merge_trade_contacts(units, index.row_of, receiver, partner, weight.copy(), position, 0.7)
    for a, b in zip(got, expected, strict=True):
        assert a.dtype == b.dtype and np.array_equal(a, b)
    assert got[0].size > receiver.size  # distant ties were appended


@settings(max_examples=6, deadline=None)
@given(st.integers(0, 10_000))
def test_capability_column_equals_per_unit_capabilities(seed: int) -> None:
    from madexplorer.knowledge.system import CAPABILITIES
    from madexplorer.population.energetics import capability_column

    sim = _warm_state(80, seed, ticks=1)
    rng = np.random.default_rng(seed)
    assert sim.knowledge is not None
    ids = [t.id for t in sim.knowledge.system.technologies]
    for unit in sim.state.units.values():  # many distinct sets, some shared, some empty
        unit.technologies = frozenset(t for t in ids if rng.random() < 0.3)
    ctx = step_context(sim)
    cols = ctx.columns(sim.state)
    for name in CAPABILITIES:
        expected = [ctx.capabilities(u)[name] for u in cols.units]
        assert capability_column(cols, ctx, name).tolist() == expected
