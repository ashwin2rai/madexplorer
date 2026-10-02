"""MVP 3 Stage 3B: neutral socioeconomic accounting of strata claims.

Field- and store-claim accretion from gross flows, proportional depletion, the zero-stock
rule, pooling transfers, numerical continuity and engine agreement. The physical simulation
is untouched (the MVP 2.1 oracles and golden fixtures check that; so does the twin
comparison here).
"""

from collections import defaultdict

import numpy as np
import pytest

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.economy.trade import TradeRound, Transfer
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.mobility.migration import Relocation
from madexplorer.population.energetics import EnergeticsSubsystem
from madexplorer.population.strata import STRATUM_COLUMNS, StrataBlock, positions
from madexplorer.population.strata_accounting import (
    FieldAccounts,
    FoodAccounts,
    account_strata,
    field_claims_after_change,
    pooling_transfers,
    store_claims_after_year,
)
from madexplorer.population.unit import PopulationUnit
from tests.conftest import ROOT, step_context
from tests.test_strata_composition import CROSS_CUTTING, block
from tests.test_unit_table import assert_same_simulation, unit_state

SCENARIO = ROOT / "scenarios" / "mvp2_neolithic.yaml"
HALVES = np.array([0.5, 0.5])
UNEQUAL = np.array([0.8, 0.2])


# ---------------------------------------------------------------- field claims (pure)


@pytest.mark.parametrize(("f0", "f1"), [(3.0, 9.0), (9.0, 3.0), (0.0, 4.0), (4.0, 4.0)])
def test_a_single_stratum_keeps_field_claim_exactly_one(f0: float, f1: float) -> None:
    one = np.array([1.0])
    assert field_claims_after_change(one, one, np.float64(f0), np.float64(f1)).tolist() == [1.0]


def test_new_land_accrues_by_share_and_dilutes_existing_control() -> None:
    claims = field_claims_after_change(HALVES, UNEQUAL, np.float64(10.0), np.float64(20.0))
    assert claims.tolist() == [13 / 20, 7 / 20]  # (0.8*10 + 0.5*10, 0.2*10 + 0.5*10) / 20
    assert claims[0] > claims[1]  # still unequal, but closer to shares


def test_shrinking_land_keeps_fractions_and_regrowth_after_zero_starts_from_shares() -> None:
    kept = field_claims_after_change(HALVES, UNEQUAL, np.float64(10.0), np.float64(4.0))
    assert kept.tolist() == UNEQUAL.tolist()
    regrown = field_claims_after_change(HALVES, HALVES, np.float64(0.0), np.float64(5.0))
    assert regrown.tolist() == [0.5, 0.5]


# ---------------------------------------------------------------- store claims (pure)


def test_depletion_keeps_store_claims_while_stores_remain() -> None:
    k = np.float64
    kept = store_claims_after_year(HALVES, UNEQUAL, k(100.0), k(0.0), k(40.0))
    assert kept.tolist() == UNEQUAL.tolist()


def test_new_stores_accrue_by_share() -> None:
    k = np.float64
    added = store_claims_after_year(HALVES, UNEQUAL, k(100.0), k(100.0), k(150.0))
    assert added.tolist() == [130 / 200, 70 / 200]
    fresh = store_claims_after_year(HALVES, UNEQUAL, k(0.0), k(60.0), k(30.0))
    assert fresh.tolist() == [0.5, 0.5]  # from zero stores: by share


def test_exhausted_stores_reset_to_shares() -> None:
    k = np.float64
    assert store_claims_after_year(HALVES, UNEQUAL, k(50.0), k(0.0), k(0.0)).tolist() == [0.5, 0.5]


# ---------------------------------------------------------------- pooling transfers (pure)


def test_pooling_transfers_are_zero_when_claims_follow_shares() -> None:
    assert pooling_transfers(HALVES, HALVES, np.float64(1e5)).tolist() == [0.0, 0.0]


def test_pooled_withdrawal_from_unequal_stores_moves_food_between_strata() -> None:
    transfer = pooling_transfers(HALVES, UNEQUAL, np.float64(1000.0))
    assert transfer[0] < 0 < transfer[1]  # the store-rich stratum contributes more than it eats
    assert transfer.tolist() == pytest.approx([-300.0, 300.0])
    assert abs(transfer.sum()) <= 1000.0 * 2e-12


# ---------------------------------------------------------------- end to end (both engines)


def _sims(**kwargs: object) -> list[Simulator]:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=5)
    sims = []
    for table in (True, False):
        sim = synthetic_simulator(scenario, 6, unit_table=table, **kwargs)  # type: ignore[arg-type]
        sim.state.population.strata_log = []
        sim.state.population.strata_flows = []
        sims.append(sim)
    return sims


def _first(sim: Simulator) -> PopulationUnit:
    return next(iter(sim.state.units.values()))


def _account(sim: Simulator, **accounts: object) -> None:
    ctx = step_context(sim)
    ctx.food_accounts = accounts.get("food")  # type: ignore[assignment]
    ctx.field_accounts = accounts.get("fields")  # type: ignore[assignment]
    account_strata(sim.state, ctx)


def _arr(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


def test_field_expansion_and_exact_compaction_through_the_accounting_hook() -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        unit.fields_ha = 0.0
        # Field claims unequal over no land (a fixture; the zero-stock rule would reset them).
        sim.state.population.replace_strata(unit, block([0.5, 0.5], [0.75, 0.25], [0.5, 0.5]))
        unit.fields_ha = 2.0
        _account(sim, fields=FieldAccounts((unit,), _arr(0.0), _arr(2.0)))
        # New land by share makes both components identical: compacted to one.
        assert len(unit.strata) == 1 and unit.strata.is_valid()
        log = sim.state.population.strata_log
        assert log is not None and log[-1]["event"] == "exact_compaction"
    assert_same_simulation(*sims)


def test_store_accounting_from_gross_flows_on_both_engines() -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        unit.stores_kcal = 150.0
        sim.state.population.replace_strata(unit, block([0.5, 0.5], [0.5, 0.5], [0.8, 0.2]))
        food = FoodAccounts((unit,), _arr(100.0), _arr(100.0), _arr(0.0), _arr(150.0))
        _account(sim, food=food)
        assert unit.strata.columns["store_claim"].tolist() == [130 / 200, 70 / 200]
        withdrawal = FoodAccounts((unit,), _arr(150.0), _arr(0.0), _arr(50.0), _arr(80.0))
        _account(sim, food=withdrawal)  # depletion: fractions kept
        assert unit.strata.columns["store_claim"].tolist() == [130 / 200, 70 / 200]
        unit.stores_kcal = 0.0
        exhausted = FoodAccounts((unit,), _arr(80.0), _arr(0.0), _arr(80.0), _arr(0.0))
        _account(sim, food=exhausted)  # exhausted: shares, hence one component
        assert len(unit.strata) == 1
    assert_same_simulation(*sims)


def _deficit_year(sim: Simulator, unit: PopulationUnit) -> None:
    """Make the unit short of food with stores to draw on, then run energetics + accounting."""
    unit.harvest_kcal = 0.0
    unit.stores_kcal = 4e5
    ctx = step_context(sim)
    for proposal in EnergeticsSubsystem().evaluate(sim.state, ctx):
        proposal.apply(sim.state, ctx)
    account_strata(sim.state, ctx)


def test_a_deficit_year_with_unequal_stores_records_a_zero_sum_pooling_transfer() -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        sim.state.population.replace_strata(unit, block([0.5, 0.5], [0.5, 0.5], [0.8, 0.2]))
        _deficit_year(sim, unit)
        flows = sim.state.population.strata_flows
        assert flows is not None
        rows = [f for f in flows if f["unit_id"] == unit.id]
        assert [r["store_claim"] for r in rows] == [0.8, 0.2]
        transfer = [r["pool_transfer_kcal"] for r in rows]
        assert transfer[0] < 0 < transfer[1]
        assert abs(sum(transfer)) <= rows[0]["withdrawn_kcal"] * 2e-12
        assert rows[0]["pool_transfer_volume_kcal"] == pytest.approx(
            0.3 * rows[0]["withdrawn_kcal"]
        )
    assert_same_simulation(*sims)
    # The physical outcome is the neutral one: strata do not change consumption.
    neutral = _sims()[0]  # the same seed and state, with one neutral stratum per unit
    _deficit_year(neutral, _first(neutral))
    a, b = unit_state(_first(sims[0])), unit_state(_first(neutral))
    for key in ("food_ratio", "energy_deficit", "stores_kcal", "reserve_kcal_per_capita"):
        assert a[key] == b[key], key


def test_cross_cutting_claims_pool_by_store_claims_only() -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        unit.fields_ha, unit.stores_kcal = 6.0, 4e5  # both stocks exist: claims are meaningful
        sim.state.population.replace_strata(unit, CROSS_CUTTING)  # A field-rich, B store-rich
        _deficit_year(sim, unit)
        flows = sim.state.population.strata_flows
        assert flows is not None
        transfer = [f["pool_transfer_kcal"] for f in flows if f["unit_id"] == unit.id]
        assert transfer[0] > 0 > transfer[1]  # B (store-rich) contributes; field claims ignored
        assert unit.strata.columns["field_claim"].tolist() == [0.7, 0.3]  # untouched
    assert_same_simulation(*sims)


def test_fed_years_record_no_pooling_transfer() -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        sim.state.population.replace_strata(unit, block([0.5, 0.5], [0.5, 0.5], [0.8, 0.2]))
        unit.harvest_kcal, unit.stores_kcal = 1e9, 1e5
        ctx = step_context(sim)
        for proposal in EnergeticsSubsystem().evaluate(sim.state, ctx):
            proposal.apply(sim.state, ctx)
        account_strata(sim.state, ctx)
        assert sim.state.population.strata_flows == []
        claims = unit.strata.columns["store_claim"]
        assert 0.5 < claims[0] < 0.8  # new stores by share dilute the unequal claims
    assert_same_simulation(*sims)


def test_trade_from_stores_keeps_the_donors_claims_and_moves_nothing_between_strata() -> None:
    sims = _sims()
    for sim in sims:
        donor, recipient = list(sim.state.units.values())[:2]
        sim.state.population.replace_strata(donor, block([0.5, 0.5], [0.5, 0.5], [0.8, 0.2]))
        recipient.fields_ha, recipient.stores_kcal = 3.0, 2e3
        sim.state.population.replace_strata(recipient, CROSS_CUTTING)
        donor.harvest_kcal, donor.stores_kcal = 100.0, 1e4
        ctx = step_context(sim)
        round_ = TradeRound((Transfer(donor.id, recipient.id, 600.0, 500.0, 1e4),), 0.7)
        round_.apply(sim.state, ctx)
        account_strata(sim.state, ctx)
        assert donor.stores_kcal == 1e4 - 500.0 and donor.harvest_kcal == 0.0
        assert donor.strata.columns["store_claim"].tolist() == [0.8, 0.2]
        assert recipient.strata.columns["store_claim"].tolist() == [0.2, 0.8]
        assert sim.state.population.strata_flows == []
    assert_same_simulation(*sims)


@pytest.mark.parametrize(("carry", "left"), [(4e3, 4e3), (0.0, 0.0)])
def test_migration_abandonment_is_proportional_until_stores_run_out(
    carry: float, left: float
) -> None:
    sims = _sims()
    for sim in sims:
        unit = _first(sim)
        unit.stores_kcal = 1e4
        sim.state.population.replace_strata(unit, block([0.5, 0.5], [0.5, 0.5], [0.8, 0.2]))
        ctx = step_context(sim)
        Relocation(unit.id, unit.cell, unit.cell + 1, 5.0, 10.0, 0.5, carry).apply(sim.state, ctx)
        account_strata(sim.state, ctx)
        assert unit.stores_kcal == left
        if left > 0:  # proportional abandonment: fractions kept
            assert unit.strata.columns["store_claim"].tolist() == [0.8, 0.2]
        else:  # no stores (and no fields): claims = shares, the two components coincide
            assert len(unit.strata) == 1 and unit.strata.is_neutral()
    assert_same_simulation(*sims)


# ---------------------------------------------------------------- numerical continuity


def test_one_ulp_apart_positions_stay_ulp_scale_apart() -> None:
    share = np.array([0.25, 0.25, 0.5])
    claim = np.array([0.25, np.nextafter(0.25, 1.0), 0.5])
    claim[2] = 1.0 - claim[0] - claim[1]
    for year in range(200):
        claim = store_claims_after_year(
            share, claim, np.float64(1e5 + year), np.float64(3e4), np.float64(1e5)
        )
        position = claim / share
        assert abs(position[0] - position[1]) <= 1e-13
        assert claim.sum() == pytest.approx(1.0, abs=1e-12)


# ---------------------------------------------------------------- whole runs


def _farming(table: bool) -> Simulator:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=3)
    sim = synthetic_simulator(scenario, 40, farming=True, unit_table=table)
    sim.state.population.strata_log = []
    sim.state.population.strata_flows = []
    units = list(sim.state.units.values())
    for unit in units[:3]:
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5  # fixtures over existing stocks
    fixtures = (
        block([0.8, 0.2], [0.5, 0.5], [0.8, 0.2]),
        CROSS_CUTTING,
        block([0.6, 0.4], [0.6, 0.4], [0.3, 0.7]),
    )
    for unit, fixture in zip(units[:3], fixtures, strict=True):
        sim.state.population.replace_strata(unit, fixture)
    return sim


def test_engines_agree_on_accounting_through_ordinary_steps() -> None:
    a, b = _farming(True), _farming(False)
    for _ in range(20):
        a.step()
        b.step()
    assert_same_simulation(a, b)
    assert a.state.population.strata_flows == b.state.population.strata_flows
    assert a.state.population.strata_log == b.state.population.strata_log


def test_pooling_transfers_sum_to_zero_per_unit_year_in_the_canonical_run() -> None:
    scenario = Scenario.from_yaml(SCENARIO).with_overrides(seed=0, n_years=320)
    result = Simulator(scenario, record_strata=True).run()
    assert result.strata_flows  # fusion-born store inequality meets deficit years
    rows: defaultdict[tuple[int, str], list[dict[str, float]]] = defaultdict(list)
    for row in result.strata_flows:
        rows[(row["year"], row["unit_id"])].append(row)
    for key, unit_rows in rows.items():
        transfers = [r["pool_transfer_kcal"] for r in unit_rows]
        withdrawn = unit_rows[0]["withdrawn_kcal"]
        assert abs(sum(transfers)) <= withdrawn * 2e-12, key
        assert sum(abs(t) for t in transfers) / 2 == pytest.approx(
            unit_rows[0]["pool_transfer_volume_kcal"]
        )


def test_claims_reconcile_with_physical_stocks_every_step() -> None:
    sim = _farming(True)
    for _ in range(30):
        sim.step()
        for unit in sim.state.units.values():
            strata = unit.strata
            assert strata.is_valid()
            for stock, claim in (("fields_ha", "field_claim"), ("stores_kcal", "store_claim")):
                if getattr(unit, stock) == 0:
                    assert strata.columns[claim].tolist() == strata.columns["share"].tolist()
            assert np.isfinite(positions(strata)).all()
    assert set(STRATUM_COLUMNS) == {"share", "field_claim", "store_claim"}
    assert isinstance(StrataBlock.neutral(), StrataBlock)
