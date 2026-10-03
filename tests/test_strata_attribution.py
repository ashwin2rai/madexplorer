"""MVP 3 Stage 3C: crop-output attribution by field claims (``field_output_claim_weight``).

The weight ``w`` changes only socioeconomic accounting: crop-output attribution, the harvest
and store components of pooling transfers and the claims on newly stored food. It never
changes physical unit state, RNG state, events, metrics or field claims (counterfactual
isolation tests below), and at ``w = 0`` it reproduces Stage 3B (the Stage 3B fixture in
``tests/regression/test_strata_fixture.py``).
"""

import collections
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import SimulationResult, Simulator
from madexplorer.core.static import static_key
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.energetics import EnergeticsSubsystem
from madexplorer.population.strata_accounting import (
    FoodAccounts,
    account_strata,
    crop_output_corrections,
    food_flows,
    leftover_pooling_transfers,
    new_store_corrections,
    store_claims_after_year,
)
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, replay_key, step_context
from tests.test_strata_composition import CROSS_CUTTING, block
from tests.test_unit_table import _same, assert_same_simulation, unit_state

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"
WEIGHTS = (0.0, 0.25, 0.5, 1.0)
SHARE = np.array([0.8, 0.2])
FIELD = np.array([0.5, 0.5])  # the minority holds 2.5x its share of the land
STORE = np.array([0.8, 0.2])


def _with_weight(scenario: Scenario, weight: float) -> Scenario:
    return scenario.with_settings({"strata.field_output_claim_weight": weight})


def _accounts(n: int = 1, **values: Any) -> FoodAccounts:
    """One-unit food accounts (no unit objects needed by :func:`food_flows`)."""
    defaults = dict(
        opening=0.0,
        stored=0.0,
        withdrawn=0.0,
        closing=0.0,
        harvest=0.0,
        crop=0.0,
        forage=0.0,
        leftover=0.0,
    )
    defaults.update(values)
    arrays = {k: np.full(n, v, dtype=np.float64) for k, v in defaults.items()}
    fed = np.full(n, bool(values.get("fed", True)))
    arrays.pop("fed", None)
    return FoodAccounts((), fed=fed, **arrays)


# ---------------------------------------------------------------- configuration


def test_the_weight_defaults_to_the_neutral_limit_and_is_bounded() -> None:
    scenario = Scenario.from_yaml(SCENARIO)
    assert scenario.config.strata.field_output_claim_weight == 0.0
    for bad in (-0.1, 1.5):
        with pytest.raises(ValidationError):
            _with_weight(scenario, bad)
    varied = _with_weight(scenario, 0.5)
    # Provenance records w; the static context (world, ecology, agronomy) does not depend on it.
    assert varied.config_hash() != scenario.config_hash()
    assert static_key(varied) == static_key(scenario)


# ---------------------------------------------------------------- crop-output attribution


def test_the_correction_vanishes_exactly_in_every_neutral_limit() -> None:
    def d(weight: float, field: np.ndarray, crop: float) -> np.ndarray:
        return crop_output_corrections(SHARE, field, weight, 9e5, crop, 9e5 - crop)

    assert not d(0.0, FIELD, 6e5).any()  # w = 0
    assert not d(1.0, FIELD, 0.0).any()  # no farming
    assert not d(1.0, SHARE.copy(), 6e5).any()  # field claims follow shares
    correction = d(1.0, FIELD, 6e5)
    assert correction.tolist() == pytest.approx([-1.8e5, 1.8e5])
    attribution = 9e5 * SHARE + correction  # q_i = H * share_i + d_i
    assert abs(attribution.sum() - 9e5) <= 9e5 * 1e-15


def test_the_correction_is_linear_in_the_weight() -> None:
    full = crop_output_corrections(SHARE, FIELD, 1.0, 9e5, 6e5, 3e5)
    for weight in WEIGHTS:
        partial = crop_output_corrections(SHARE, FIELD, weight, 9e5, 6e5, 3e5)
        assert partial == pytest.approx(weight * full, rel=1e-15, abs=0)


def test_trade_scales_the_correction_by_the_fraction_of_own_harvest_kept() -> None:
    full = crop_output_corrections(SHARE, FIELD, 1.0, 9e5, 6e5, 3e5)
    donor = crop_output_corrections(SHARE, FIELD, 1.0, 6e5, 6e5, 3e5)  # gave 1/3 away
    assert donor == pytest.approx(full * (6e5 / 9e5), rel=1e-15)
    recipient = crop_output_corrections(SHARE, FIELD, 1.0, 12e5, 6e5, 3e5)  # received 3e5
    assert recipient.tolist() == full.tolist()  # receipts are attributed by share
    gave_all = crop_output_corrections(SHARE, FIELD, 1.0, 0.0, 6e5, 3e5)
    assert not gave_all.any()
    nothing = crop_output_corrections(SHARE, FIELD, 1.0, 5e5, 0.0, 0.0)  # all received
    assert not nothing.any()


# ---------------------------------------------------------------- fed years


def test_negative_pre_pool_leftovers_are_covered_pro_rata_by_the_others() -> None:
    share = np.array([0.5, 0.3, 0.2])
    correction = np.array([-300.0, 100.0, 200.0])
    leftover = 400.0
    raw = leftover * share + correction  # [-100, 220, 280]
    transfer = leftover_pooling_transfers(share, correction, leftover)
    allocated = raw + transfer
    positive = np.maximum(raw, 0.0)
    assert allocated == pytest.approx(leftover * positive / positive.sum(), rel=1e-15)
    assert (allocated >= 0).all() and allocated[0] == 0.0
    assert abs(transfer.sum()) <= leftover * 1e-15
    assert transfer[0] == 100.0 and transfer[1] < 0 and transfer[2] < 0


def test_a_fed_year_without_leftover_pools_the_whole_correction() -> None:
    # All surplus went to reserves (by share): the attribution difference is pooled away.
    transfer = leftover_pooling_transfers(SHARE, np.array([-50.0, 50.0]), 0.0)
    assert transfer.tolist() == [50.0, -50.0]


def test_new_stores_follow_the_allocated_leftover_and_discarded_food_moves_nothing() -> None:
    share = np.array([0.5, 0.3, 0.2])
    correction = np.array([-300.0, 100.0, 200.0])
    leftover = 400.0
    transfer = leftover_pooling_transfers(share, correction, leftover)
    allocated = leftover * share + correction + transfer
    for stored in (400.0, 100.0, 0.0):  # all, part (the rest discarded) or none stored
        new = stored * share + new_store_corrections(share, correction, transfer, stored, leftover)
        assert new == pytest.approx(stored * allocated / leftover, abs=1e-12)
        assert abs(new.sum() - stored) <= 1e-12 * max(stored, 1.0)
        # The transfer does not depend on how much of the leftover could be stored.
        assert leftover_pooling_transfers(share, correction, leftover).tolist() == (
            transfer.tolist()
        )
    claims = store_claims_after_year(share, share, 1e3, 0.0, 1e3, np.zeros(3))
    assert claims.tolist() == share.tolist()  # nothing stored: no accretion


def test_stores_built_from_zero_take_the_attribution_of_the_food_stored() -> None:
    def claims(weight: float) -> np.ndarray:
        accounts = _accounts(
            stored=4e5, closing=4e5 * 0.9, harvest=1.4e6, crop=1e6, forage=4e5, leftover=4e5
        )
        flows = food_flows(SHARE, FIELD, SHARE.copy(), weight, accounts, 0)
        return store_claims_after_year(
            SHARE, SHARE.copy(), 0.0, 4e5, 4e5 * 0.9, flows.stored_correction
        )

    assert claims(0.0).tolist() == SHARE.tolist()  # by share
    neutral_to_field = [claims(w)[1] for w in WEIGHTS]
    assert neutral_to_field == sorted(neutral_to_field)  # rises with w
    # w = 1: d = 1e6 * (0.5 - 0.2) = 3e5, so the minority is attributed 0.8e5 + 3e5 of the
    # 4e5 leftover.
    assert claims(1.0).tolist() == pytest.approx([0.05, 0.95], rel=1e-14)


# ---------------------------------------------------------------- deficit years


def test_a_deficit_year_has_a_harvest_and_a_store_component() -> None:
    share, field, store = (
        CROSS_CUTTING.columns[k] for k in ("share", "field_claim", "store_claim")
    )
    accounts = _accounts(opening=1e5, withdrawn=1e5, harvest=6e5, crop=4e5, forage=2e5, fed=False)
    flows = food_flows(share, field, store, 1.0, accounts, 0)
    # A leads on fields: its crop correction is pooled away; B leads on stores: it supplies
    # the withdrawal. Neither is collapsed into one socioeconomic rank.
    assert flows.correction.tolist() == pytest.approx([8e4, -8e4])
    assert flows.harvest_transfer.tolist() == pytest.approx([-8e4, 8e4])
    assert flows.store_transfer.tolist() == pytest.approx([3e4, -3e4])
    assert flows.transfer.tolist() == pytest.approx([-5e4, 5e4])
    assert not flows.stored_correction.any()


# ---------------------------------------------------------------- neutrality and continuity


@pytest.mark.parametrize("fed", [True, False])
def test_a_neutral_state_stays_bit_identical_for_every_weight(fed: bool) -> None:
    accounts = _accounts(
        opening=2e5,
        stored=3e5 if fed else 0.0,
        withdrawn=0.0 if fed else 5e4,
        closing=4e5,
        harvest=1.3e6,
        crop=9e5,
        forage=4e5,
        leftover=3e5 if fed else 0.0,
        fed=fed,
    )
    share = np.array([0.3, 0.7])
    results = []
    for weight in WEIGHTS:
        flows = food_flows(share, share.copy(), share.copy(), weight, accounts, 0)
        assert not flows.correction.any() and not flows.transfer.any()
        results.append(
            store_claims_after_year(share, share.copy(), 2e5, 3e5, 4e5, flows.stored_correction)
        )
    assert all(r.tolist() == results[0].tolist() for r in results)


def test_tiny_input_differences_give_correspondingly_tiny_attribution_differences() -> None:
    share = np.array([0.25, 0.25, 0.5])
    field = np.array([0.25, 0.25, 0.5])
    nudged = field.copy()
    nudged[1] = np.nextafter(0.25, 1.0)
    nudged[2] = 1.0 - nudged[0] - nudged[1]
    accounts = _accounts(
        opening=1e5, stored=2e5, closing=2.7e5, harvest=1.2e6, crop=8e5, forage=4e5,
        leftover=2e5,
    )  # fmt: skip
    for weight in WEIGHTS:
        a = food_flows(share, field, share.copy(), weight, accounts, 0)
        b = food_flows(share, nudged, share.copy(), weight, accounts, 0)
        # A few ulps of field claim move at most a few ulps of the kcal scale.
        for name in ("correction", "harvest_transfer", "stored_correction"):
            assert np.abs(getattr(a, name) - getattr(b, name)).max() <= 1e-9, name
        ca = store_claims_after_year(share, share.copy(), 1e5, 2e5, 2.7e5, a.stored_correction)
        cb = store_claims_after_year(share, share.copy(), 1e5, 2e5, 2.7e5, b.stored_correction)
        assert np.abs(ca - cb).max() <= 1e-15


# ---------------------------------------------------------------- through the engine hook


def _sims(weight: float) -> list[Simulator]:
    scenario = _with_weight(Scenario.from_yaml(SCENARIO).with_overrides(seed=5), weight)
    sims = []
    for table in (True, False):
        sim = synthetic_simulator(scenario, 6, unit_table=table)
        sim.state.population.strata_log, sim.state.population.strata_flows = [], []
        sims.append(sim)
    return sims


def _energetics(sim: Simulator, unit: PopulationUnit, crop: float, forage: float) -> None:
    """Set the unit's own harvest, then run energetics and the accounting hook."""
    unit.farm_harvest_kcal, unit.forage_harvest_kcal = crop, forage
    unit.harvest_kcal = crop + forage
    ctx = step_context(sim)
    for proposal in EnergeticsSubsystem().evaluate(sim.state, ctx):
        proposal.apply(sim.state, ctx)
    account_strata(sim.state, ctx)


def _rows(sim: Simulator, unit: PopulationUnit) -> list[dict[str, Any]]:
    flows = sim.state.population.strata_flows
    assert flows is not None
    return [f for f in flows if f["unit_id"] == unit.id]


def test_engines_agree_on_a_deficit_year_with_both_pooling_components() -> None:
    sims = _sims(0.5)
    for sim in sims:
        unit = next(iter(sim.state.units.values()))
        unit.fields_ha, unit.stores_kcal = 6.0, 4e4
        sim.state.population.replace_strata(unit, CROSS_CUTTING)
        _energetics(sim, unit, 3e4, 1e4)  # far short of need
        rows = _rows(sim, unit)
        harvest = [r["harvest_pool_transfer_kcal"] for r in rows]
        store = [r["store_pool_transfer_kcal"] for r in rows]
        assert harvest[0] < 0 < harvest[1]  # field-rich A's crop attribution is pooled
        assert store[0] > 0 > store[1]  # store-rich B supplies the withdrawal
        assert harvest[1] == pytest.approx(0.5 * 3e4 * 0.2)
        for column in (harvest, store, [r["pool_transfer_kcal"] for r in rows]):
            assert abs(sum(column)) <= 1e-12 * 4e4
        assert unit.strata.columns["field_claim"].tolist() == [0.7, 0.3]  # untouched
    assert_same_simulation(*sims)


def test_engines_agree_on_a_fed_year_where_field_control_shapes_new_stores() -> None:
    claims = {}
    for weight in (0.0, 1.0):
        sims = _sims(weight)
        for sim in sims:
            unit = next(iter(sim.state.units.values()))
            unit.fields_ha, unit.stores_kcal = 6.0, 1e5
            sim.state.population.replace_strata(
                unit, block(SHARE.tolist(), FIELD.tolist(), STORE.tolist())
            )
            _energetics(sim, unit, 8e8, 2e8)  # plenty: every pre-pool leftover is positive
            claims[weight] = unit.strata.columns["store_claim"].tolist()
            assert _rows(sim, unit) == []  # each stratum keeps its own surplus: no transfer
        assert_same_simulation(*sims)
    assert claims[1.0][1] > claims[0.0][1]  # the field-rich minority gains store control


@pytest.mark.parametrize("stored", [1e5, 4e4, 0.0])
def test_engines_agree_on_negative_leftover_coverage_and_discarded_surplus(
    stored: float,
) -> None:
    # Fed year, crop only: d = 1e6 * (0.5 - 0.8, 0.5 - 0.2) = (-3e5, 3e5); leftover 1e5,
    # so the pre-pool leftovers are (-2.2e5, 3.2e5): the majority's attributed food does
    # not cover its pooled consumption, and the minority's covers it (transfer 2.2e5).
    # ``stored`` < 1e5 discards the rest of the leftover, which moves nothing further.
    sims = _sims(1.0)
    for sim in sims:
        unit = next(iter(sim.state.units.values()))
        unit.fields_ha, unit.stores_kcal = 6.0, (1e5 + stored) * 0.9
        sim.state.population.replace_strata(
            unit, block(SHARE.tolist(), FIELD.tolist(), STORE.tolist())
        )
        food = FoodAccounts(
            (unit,),
            opening=np.array([1e5]),
            stored=np.array([stored]),
            withdrawn=np.array([0.0]),
            closing=np.array([(1e5 + stored) * 0.9]),
            harvest=np.array([1e6]),
            crop=np.array([1e6]),
            forage=np.array([0.0]),
            leftover=np.array([1e5]),
            fed=np.array([True]),
        )
        ctx = step_context(sim)
        ctx.food_accounts = food
        account_strata(sim.state, ctx)
        rows = _rows(sim, unit)
        assert [r["harvest_pool_transfer_kcal"] for r in rows] == pytest.approx([2.2e5, -2.2e5])
        assert [r["store_pool_transfer_kcal"] for r in rows] == [0.0, 0.0]
        # New stores all go to the minority: (0.8e5, 0.2e5 + stored) / (1e5 + stored).
        expected = [0.8e5 / (1e5 + stored), (0.2e5 + stored) / (1e5 + stored)]
        assert unit.strata.columns["store_claim"].tolist() == pytest.approx(expected, rel=1e-14)
    assert_same_simulation(*sims)


# ---------------------------------------------------------------- counterfactual isolation


def _field_measure(rows: list[dict[str, Any]]) -> dict[tuple[int, str], list[list[float]]]:
    """Each unit-year's field-claim distribution: share by field position, with components
    at the same position (to 1e-12) pooled. Invariant to how strata are grouped, which
    exact compaction may do differently once store positions differ."""
    by: collections.defaultdict[tuple[int, str], list[tuple[float, float]]]
    by = collections.defaultdict(list)
    for row in rows:
        by[(row["year"], row["unit_id"])].append((row["relative_field_position"], row["share"]))
    measure = {}
    for key, values in by.items():
        groups: list[list[float]] = []
        for position, share in sorted(values):
            if groups and abs(position - groups[-1][0]) <= 1e-12 * max(1.0, position):
                groups[-1][1] += share
            else:
                groups.append([position, share])
        measure[key] = groups
    return measure


def _assert_same_measure(a: dict[Any, list[list[float]]], b: dict[Any, list[list[float]]]) -> None:
    assert a.keys() == b.keys()
    for key in a:
        assert len(a[key]) == len(b[key]), key
        assert np.allclose(a[key], b[key], rtol=0, atol=1e-12), key


def _physics(sim: Simulator) -> list[tuple[str, dict[str, object]]]:
    return [
        (uid, {k: v for k, v in unit_state(u).items() if k != "strata"})
        for uid, u in sim.state.units.items()
    ]


def _assert_same_physics(a: Simulator, b: Simulator) -> None:
    """Every unit-level physical state, ecology, events and RNG stream state (not strata)."""
    pa, pb = _physics(a), _physics(b)
    assert [uid for uid, _ in pa] == [uid for uid, _ in pb]
    for (uid, sa), (_, sb) in zip(pa, pb, strict=True):
        for key, value in sa.items():
            assert _same(value, sb[key]), (uid, key)
    for name in ("plant_stock_kcal", "game_stock_kcal", "soil_nutrients"):
        assert np.array_equal(getattr(a.state.ecology, name), getattr(b.state.ecology, name))
    assert [(e.year, e.kind, e.data) for e in a.events] == [
        (e.year, e.kind, e.data) for e in b.events
    ]
    assert set(a.rng._streams) == set(b.rng._streams)
    for name in a.rng._streams:
        assert a.rng.stream(name).bit_generator.state == b.rng.stream(name).bit_generator.state


@pytest.fixture(scope="module")
def canonical_runs() -> dict[float, tuple[Simulator, SimulationResult]]:
    """mvp2_neolithic seed 0, 300 years, at each weight (fusion-born field inequality appears
    once farming spreads, after about year 200)."""
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=0, n_years=300)
    runs = {}
    for weight in WEIGHTS:
        sim = Simulator(_with_weight(scenario, weight), record_strata=True)
        runs[weight] = (sim, sim.run())
    return runs


def test_the_weight_changes_no_physical_outcome(
    canonical_runs: dict[float, tuple[Simulator, SimulationResult]],
) -> None:
    neutral_sim, neutral = canonical_runs[0.0]
    for weight in WEIGHTS[1:]:
        sim, result = canonical_runs[weight]
        assert replay_key(result.metrics) == replay_key(neutral.metrics)  # NaN-aware
        assert result.population_snapshots[-1].tolist() == (
            neutral.population_snapshots[-1].tolist()
        )
        _assert_same_physics(sim, neutral_sim)


def test_field_claims_do_not_depend_on_the_weight(
    canonical_runs: dict[float, tuple[Simulator, SimulationResult]],
) -> None:
    neutral = _field_measure(canonical_runs[0.0][1].strata_rows)
    for weight in WEIGHTS[1:]:
        _assert_same_measure(_field_measure(canonical_runs[weight][1].strata_rows), neutral)


def test_the_weight_changes_store_claims_and_pooling_flows(
    canonical_runs: dict[float, tuple[Simulator, SimulationResult]],
) -> None:
    def store_positions(result: SimulationResult) -> list[float]:
        return [r["relative_store_position"] for r in result.strata_rows]

    neutral = canonical_runs[0.0][1]
    assert all(r["harvest_pool_transfer_kcal"] == 0.0 for r in neutral.strata_flows)
    for weight in WEIGHTS[1:]:
        result = canonical_runs[weight][1]
        assert any(r["harvest_pool_transfer_kcal"] != 0.0 for r in result.strata_flows)
        assert store_positions(result) != store_positions(neutral)


@pytest.mark.parametrize("weight", WEIGHTS)
def test_pooling_components_sum_to_zero_per_unit_year(
    canonical_runs: dict[float, tuple[Simulator, SimulationResult]], weight: float
) -> None:
    rows: collections.defaultdict[tuple[int, str], list[dict[str, Any]]]
    rows = collections.defaultdict(list)
    for row in canonical_runs[weight][1].strata_flows:
        rows[(row["year"], row["unit_id"])].append(row)
    for key, unit_rows in rows.items():
        # Partition tolerance (2e-12) of the claims times the flows they multiply: the
        # withdrawal X and the crop Y.
        scale = unit_rows[0]["withdrawn_kcal"] + unit_rows[0]["crop_kcal"]
        for column in (
            "pool_transfer_kcal",
            "harvest_pool_transfer_kcal",
            "store_pool_transfer_kcal",
            "crop_attribution_correction_kcal",
        ):
            total = sum(r[column] for r in unit_rows)
            assert abs(total) <= 4e-12 * max(scale, 1.0), (key, column)
        for r in unit_rows:
            total = r["harvest_pool_transfer_kcal"] + r["store_pool_transfer_kcal"]
            assert r["pool_transfer_kcal"] == total


def _farming(weight: float, table: bool) -> Simulator:
    scenario = _with_weight(Scenario.from_yaml(SCENARIO).with_overrides(seed=3), weight)
    sim = synthetic_simulator(scenario, 40, farming=True, unit_table=table)
    sim.state.population.strata_log, sim.state.population.strata_flows = [], []
    fixtures = (block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2]), CROSS_CUTTING)
    for unit, fixture in zip(list(sim.state.units.values())[:2], fixtures, strict=False):
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5
        sim.state.population.replace_strata(unit, fixture)
    return sim


def test_engines_agree_with_a_nonzero_weight_and_the_weight_stays_physically_inert() -> None:
    table, objects, neutral = _farming(0.5, True), _farming(0.5, False), _farming(0.0, True)
    for _ in range(20):
        for sim in (table, objects, neutral):
            sim.step()
        for unit in table.state.units.values():
            assert unit.strata.is_valid()
    assert_same_simulation(table, objects)
    assert table.state.population.strata_flows == objects.state.population.strata_flows
    assert table.state.population.strata_log == objects.state.population.strata_log
    _assert_same_physics(table, neutral)
