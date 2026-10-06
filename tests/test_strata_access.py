"""MVP 3 Stage 4C: counterfactual stored-food access by store claim. NOT ACTIVE.

``madexplorer.population.strata_access`` allocates a unit's fixed physical store withdrawal
``X`` to strata by access priority ``q = s + a * (c - s)`` with need caps (bounded weighted
water-filling). It is evaluated counterfactually only: no simulator path calls it, and the
observation wrappers used here (as in ``scripts/probes/store_access_counterfactual.py``)
leave every authoritative output identical.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest

import madexplorer.core.simulation as simulation
from madexplorer.config.loader import Scenario
from madexplorer.experiments.benchmark import synthetic_simulator
from madexplorer.population.energetics import EnergyUpdates
from madexplorer.population.strata import StrataBlock
from madexplorer.population.strata_access import (
    REL_TOL,
    allocate_store_access_counterfactual,
    counterfactual_store_access,
)
from madexplorer.population.strata_accounting import (
    account_strata,
    pooling_transfers,
    store_claims_after_year,
)
from tests.conftest import ROOT

WEIGHTS = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)


def _cases(n: int = 200, seed: int = 4) -> list[tuple[np.ndarray, np.ndarray, float, float, float]]:
    """Deterministic heterogeneous shortage states: (share, claim, Need, H, X), X < Need - H.

    Claims include exact zeros, so ``a = 1`` exercises the zero-priority fallback."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        k = int(rng.integers(2, 17))
        share = rng.dirichlet(np.ones(k))
        claim = rng.dirichlet(np.full(k, 0.3))
        claim[rng.random(k) < 0.2] = 0.0
        claim = claim / claim.sum() if claim.sum() > 0 else share.copy()
        need = float(rng.uniform(1e5, 1e7))
        harvest = need * float(rng.uniform(0.0, 0.95))
        withdrawal = (need - harvest) * float(rng.uniform(0.0, 1.0))
        out.append((share, claim, need, harvest, withdrawal))
    return out


def _alloc(s: list[float], c: list[float], d: list[float], x: float, a: float) -> Any:
    return allocate_store_access_counterfactual(np.array(s), np.array(c), np.array(d), x, a)


# ---------------------------------------------------------------- neutral limits


def test_a_zero_reproduces_complete_pooling_and_the_stage3b_transfer() -> None:
    for share, claim, need, harvest, x in _cases():
        result = counterfactual_store_access(share, claim, need, harvest, x, 0.0)
        access = result.counterfactual_store_access_kcal
        assert np.abs(access - x * share).max() <= REL_TOL * x
        # The access transfer at a = 0 is the Stage 3B store pooling transfer X * (s - c).
        stage3b = pooling_transfers(share, claim, x)
        transfer = result.counterfactual_store_access_transfer_kcal
        assert np.abs(transfer - stage3b).max() <= REL_TOL * x
        assert result.redistribution_kcal <= REL_TOL * x
        ratio = result.counterfactual_external_food_allocation_ratio
        assert np.abs(ratio - (harvest + x) / need).max() <= REL_TOL


def test_claims_equal_to_shares_make_the_weight_irrelevant_bit_for_bit() -> None:
    for share, _, need, harvest, x in _cases(50):
        claim = share.copy()
        base = counterfactual_store_access(share, claim, need, harvest, x, 0.0)
        for a in WEIGHTS:
            other = counterfactual_store_access(share, claim, need, harvest, x, a)
            assert np.array_equal(other.allocation.priority, share)
            for name in (
                "counterfactual_store_access_kcal",
                "counterfactual_external_food_allocation_kcal",
                "counterfactual_external_food_allocation_ratio",
                "counterfactual_unmet_external_need_kcal",
                "counterfactual_store_access_transfer_kcal",
            ):
                assert np.array_equal(getattr(other, name), getattr(base, name))
            assert other.redistribution_kcal == base.redistribution_kcal
            assert other.redistribution_kcal <= REL_TOL * x


# ---------------------------------------------------------------- invariants


def test_conservation_and_need_caps_hold_for_every_weight() -> None:
    for share, claim, need, harvest, x in _cases():
        for a in WEIGHTS:
            result = counterfactual_store_access(share, claim, need, harvest, x, a)
            access, deficit = result.counterfactual_store_access_kcal, result.deficit
            assert (access >= 0).all() and (access <= deficit).all()
            assert abs(access.sum() - x) <= REL_TOL * x
            assert np.allclose(result.counterfactual_unmet_external_need_kcal, deficit - access)
            assert abs(result.counterfactual_store_access_transfer_kcal.sum()) <= 2 * REL_TOL * x


def test_remaining_deficit_is_need_minus_harvest_by_share_without_reserves() -> None:
    share = np.array([0.6, 0.3, 0.1])
    result = counterfactual_store_access(share, np.array([0.2, 0.3, 0.5]), 1000.0, 400.0, 0.0, 1)
    assert np.allclose(result.deficit, 600.0 * share)
    assert abs(result.deficit.sum() - 600.0) <= REL_TOL * 600.0
    fed = counterfactual_store_access(share, np.array([0.2, 0.3, 0.5]), 1000.0, 1200.0, 0.0, 1)
    assert (fed.deficit == 0).all()


def test_no_withdrawal_gives_no_access_and_no_signal() -> None:
    share, claim = np.array([0.5, 0.5]), np.array([0.9, 0.1])
    for a in WEIGHTS:
        result = counterfactual_store_access(share, claim, 1000.0, 600.0, 0.0, a)
        assert (result.counterfactual_store_access_kcal == 0).all()
        assert (result.counterfactual_store_access_transfer_kcal == 0).all()
        assert result.redistribution_kcal == 0.0 and result.redistribution_fraction == 0.0


def test_enough_stores_means_claims_cease_to_matter() -> None:
    for share, claim, need, harvest, _ in _cases(50):
        x = float((max(need - harvest, 0.0) * share).sum())  # X == sum(D)
        for a in WEIGHTS:
            result = counterfactual_store_access(share, claim, need, harvest, x, a)
            assert np.array_equal(result.counterfactual_store_access_kcal, result.deficit)
            assert (result.counterfactual_unmet_external_need_kcal == 0).all()


# ---------------------------------------------------------------- water-filling


def test_no_cap_allocates_by_priority() -> None:
    result = _alloc([0.5, 0.5], [0.6, 0.4], [100.0, 100.0], 100.0, 1.0)
    assert np.allclose(result.access, [60.0, 40.0])
    assert not result.capped.any() and result.rounds == 1 and not result.fallback


def test_one_saturated_stratum_passes_its_excess_on() -> None:
    # Priority 0.5/0.5 offers 30 each; the minority's deficit is 20.
    result = _alloc([0.8, 0.2], [0.5, 0.5], [80.0, 20.0], 60.0, 1.0)
    assert np.allclose(result.access, [40.0, 20.0])
    assert result.capped.tolist() == [False, True] and result.rounds == 2


def test_strata_saturate_in_sequence() -> None:
    result = _alloc([0.4, 0.3, 0.2, 0.1], [0.05, 0.15, 0.3, 0.5], [40.0, 30.0, 20.0, 10.0], 70.0, 1)
    assert np.allclose(result.access, [10.0, 30.0, 20.0, 10.0])
    assert result.capped.tolist() == [False, True, True, True] and result.rounds == 3


def test_zero_priority_hungry_strata_share_the_rest_by_remaining_need() -> None:
    result = _alloc([0.5, 0.3, 0.2], [1.0, 0.0, 0.0], [50.0, 30.0, 20.0], 80.0, 1.0)
    assert np.allclose(result.access, [50.0, 18.0, 12.0])
    assert result.fallback and result.capped.tolist() == [True, False, False]
    # Under proportional needs the fallback is the a -> 1 limit (continuity).
    near = _alloc([0.5, 0.3, 0.2], [1.0, 0.0, 0.0], [50.0, 30.0, 20.0], 80.0, 1.0 - 1e-6)
    assert not near.fallback and np.abs(near.access - result.access).max() < 1e-6


def test_complete_satisfaction_and_zero_withdrawal_cases() -> None:
    full = _alloc([0.5, 0.5], [0.9, 0.1], [50.0, 50.0], 100.0, 1.0)
    assert full.access.tolist() == [50.0, 50.0] and full.rounds == 0
    none = _alloc([0.5, 0.5], [0.9, 0.1], [50.0, 50.0], 0.0, 1.0)
    assert none.access.tolist() == [0.0, 0.0] and not none.capped.any()


def test_allocation_is_continuous_in_the_weight_across_cap_transitions() -> None:
    s, c, d = (
        np.array([0.4, 0.3, 0.2, 0.1]),
        np.array([0.05, 0.15, 0.3, 0.5]),
        100 * np.array([0.4, 0.3, 0.2, 0.1]),
    )
    grid = np.linspace(0.0, 1.0, 2001)
    runs = [allocate_store_access_counterfactual(s, c, d, 70.0, a) for a in grid]
    access = np.array([r.access for r in runs])
    capped = np.array([r.capped for r in runs])
    assert np.abs(np.diff(access, axis=0)).max() < 0.05  # Lipschitz-sized steps of 5e-4 in a
    transitions = np.flatnonzero((capped[1:] != capped[:-1]).any(axis=1))
    assert transitions.size >= 2
    for i in transitions.tolist():
        lo, hi = float(grid[i]), float(grid[i + 1])
        for _ in range(50):  # bisect the transition
            mid = (lo + hi) / 2
            same = (
                allocate_store_access_counterfactual(s, c, d, 70.0, mid).capped == capped[i]
            ).all()
            lo, hi = (mid, hi) if same else (lo, mid)
        left = allocate_store_access_counterfactual(s, c, d, 70.0, lo).access
        right = allocate_store_access_counterfactual(s, c, d, 70.0, hi).access
        assert np.abs(left - right).max() < 1e-9


# ---------------------------------------------------------------- neutrality


def test_order_and_identity_do_not_matter() -> None:
    rng = np.random.default_rng(9)
    for share, claim, need, harvest, x in _cases(50):
        order = rng.permutation(share.size)
        for a in WEIGHTS:
            base = counterfactual_store_access(share, claim, need, harvest, x, a)
            moved = counterfactual_store_access(share[order], claim[order], need, harvest, x, a)
            got = moved.counterfactual_store_access_kcal
            assert np.abs(got - base.counterfactual_store_access_kcal[order]).max() <= REL_TOL * x
    # Stratum ids never enter: renumbering a block's ids changes nothing.
    block = StrataBlock(
        {"share": np.array([0.7, 0.3]), "field_claim": np.array([0.5, 0.5]),
         "store_claim": np.array([0.2, 0.8])},
        np.array([5, 9], dtype=np.int64),
    )  # fmt: skip
    renumbered = StrataBlock(dict(block.columns), np.array([1000, 3], dtype=np.int64))
    results = [
        counterfactual_store_access(
            b.columns["share"], b.columns["store_claim"], 900.0, 300.0, 250.0, 1.0
        ).counterfactual_store_access_kcal
        for b in (block, renumbered)
    ]
    assert np.array_equal(results[0], results[1])


def test_inputs_are_not_modified() -> None:
    share, claim, d = np.array([0.8, 0.2]), np.array([0.5, 0.5]), np.array([80.0, 20.0])
    copies = share.copy(), claim.copy(), d.copy()
    allocate_store_access_counterfactual(share, claim, d, 60.0, 1.0)
    counterfactual_store_access(share, claim, 1000.0, 900.0, 60.0, 1.0)
    for before, after in zip(copies, (share, claim, d), strict=True):
        assert np.array_equal(before, after)


@pytest.mark.parametrize(
    ("share", "claim", "deficit", "x", "a"),
    [
        ([0.5, 0.5], [0.5], [1.0, 1.0], 1.0, 0.5),  # lengths
        ([1.0, 0.0], [0.5, 0.5], [1.0, 1.0], 1.0, 0.5),  # zero-population stratum
        ([0.6, 0.6], [0.5, 0.5], [1.0, 1.0], 1.0, 0.5),  # shares do not sum to 1
        ([0.5, 0.5], [1.2, -0.2], [1.0, 1.0], 1.0, 0.5),  # negative claim
        ([0.5, 0.5], [0.7, 0.7], [1.0, 1.0], 1.0, 0.5),  # claims do not sum to 1
        ([0.5, 0.5], [0.5, 0.5], [1.0, -1.0], 0.0, 0.5),  # negative deficit
        ([0.5, 0.5], [0.5, 0.5], [1.0, 1.0], 1.0, 1.5),  # weight out of range
        ([0.5, 0.5], [0.5, 0.5], [1.0, 1.0], -1.0, 0.5),  # negative withdrawal
        ([0.5, 0.5], [0.5, 0.5], [1.0, 1.0], 2.5, 0.5),  # more than the deficit
        ([0.5, 0.5], [0.5, 0.5], [1.0, np.nan], 1.0, 0.5),  # not finite
        ([], [], [], 0.0, 0.5),  # empty
    ],
)
def test_invalid_inputs_are_rejected(
    share: list[float], claim: list[float], deficit: list[float], x: float, a: float
) -> None:
    with pytest.raises(ValueError):
        _alloc(share, claim, deficit, x, a)


# ---------------------------------------------------------------- store_claim semantics


def test_repeated_shortage_keeps_control_and_depletion_uses_the_pre_reset_claim() -> None:
    """store_claim is continuing control over the surviving stock, not a calorie account."""
    share, claim = np.array([0.8, 0.2]), np.array([0.5, 0.5])
    need, harvest, stores = 1000.0, 400.0, 2000.0
    for _ in range(4):  # rationed shortages (prescribed X < sum D), stores stay positive
        x = 300.0
        pooled = counterfactual_store_access(share, claim, need, harvest, x, 0.0)
        for a in (0.25, 0.5, 1.0):
            result = counterfactual_store_access(share, claim, need, harvest, x, a)
            per_person = result.counterfactual_store_access_kcal / (x * share)
            assert per_person[1] > 1.0 > per_person[0]  # the same preferential access
            assert result.redistribution_kcal > pooled.redistribution_kcal
        after = store_claims_after_year(share, claim, stores, 0.0, stores - x)
        assert np.array_equal(after, claim)  # access debits no claim
        stores -= x
    # A bad year empties the store: the allocation uses the claims held before withdrawal.
    x = stores  # 800 < sum D = 1000
    result = counterfactual_store_access(share, claim, need, 0.0, x, 1.0)
    assert np.allclose(result.counterfactual_store_access_kcal, [600.0, 200.0])
    neutral = counterfactual_store_access(share, share, need, 0.0, x, 1.0)
    assert np.allclose(neutral.counterfactual_store_access_kcal, [640.0, 160.0])
    # Only afterwards does the zero-stock rule erase the old control.
    assert np.array_equal(store_claims_after_year(share, claim, stores, 0.0, 0.0), share)


# ---------------------------------------------------------------- real runs


class _Capture:
    """Pre-withdrawal state of every withdrawal unit-year (read-only wrappers)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.records: list[dict[str, Any]] = []
        self.reset_checks = 0
        apply, hook = EnergyUpdates.apply, account_strata
        need: list[np.ndarray] = []

        def apply_observed(updates: EnergyUpdates, state: Any, ctx: Any) -> None:
            apply(updates, state, ctx)
            need.append(updates.need_kcal.copy())

        def hook_observed(state: Any, ctx: Any) -> None:
            acc, pending = ctx.food_accounts, []
            if acc is not None:
                needs = need.pop()
                for r in np.flatnonzero((acc.harvest < needs) & (acc.withdrawn > 0)).tolist():
                    unit = acc.units[r]
                    record = {
                        "need": float(needs[r]), "harvest": float(acc.harvest[r]),
                        "withdrawn": float(acc.withdrawn[r]), "opening": float(acc.opening[r]),
                        "closing": float(acc.closing[r]),
                        "share": unit.strata.columns["share"].copy(),
                        "store_claim": unit.strata.columns["store_claim"].copy(),
                    }  # fmt: skip
                    self.records.append(record)
                    pending.append((unit, record))
            hook(state, ctx)
            for unit, record in pending:
                if record["closing"] == 0.0 and record["share"].size > 1:
                    after = unit.strata.columns
                    assert np.array_equal(after["store_claim"], after["share"])
                    self.reset_checks += 1

        monkeypatch.setattr(EnergyUpdates, "apply", apply_observed)
        monkeypatch.setattr(simulation, "account_strata", hook_observed)


def _heterogeneous_run(years: int = 40) -> Any:
    scenario = Scenario.from_yaml(ROOT / "scenarios" / "mvp2_neolithic.yaml").with_overrides(
        seed=11
    )
    sim = synthetic_simulator(scenario, 30, farming=True)
    population = sim.state.population
    population.strata_log, population.strata_flows = [], []
    blocks = (([0.8, 0.2], [0.5, 0.5]), ([0.5, 0.5], [0.2, 0.8]), ([0.6, 0.4], [0.3, 0.7]))
    for unit, (share, store) in zip(list(sim.state.units.values())[:3], blocks, strict=True):
        unit.fields_ha, unit.stores_kcal = 4.0, 3e5
        population.replace_strata(
            unit,
            StrataBlock(
                {"share": np.array(share), "field_claim": np.array(share),
                 "store_claim": np.array(store)},
                np.zeros(2, dtype=np.int64),
            ),
        )  # fmt: skip
    for _ in range(years):
        sim.step()
    return sim


def _authoritative(sim: Any) -> Any:
    population = sim.state.population
    units = [
        (u.id, u.cell, u.population, u.stores_kcal, u.fields_ha, u.food_ratio,
         u.reserve_kcal_per_capita, {k: v.tolist() for k, v in u.strata.columns.items()})
        for u in sim.state.units.values()
    ]  # fmt: skip
    rng = {name: repr(sim.rng.stream(name).bit_generator.state) for name in sim.rng._streams}
    events = [(e.year, e.kind, repr(e.data)) for e in sim.events]
    return units, rng, events, population.strata_log, population.strata_flows


def test_real_run_deficit_audit_and_pre_reset_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = _authoritative(_heterogeneous_run())
    capture = _Capture(monkeypatch)
    observed = _heterogeneous_run()
    assert _authoritative(observed) == plain  # the observation changes nothing
    assert capture.records
    depleted_nonneutral = 0
    for r in capture.records:
        need, harvest, x = r["need"], r["harvest"], r["withdrawn"]
        deficit = max(need - harvest, 0.0) * r["share"]
        assert abs(deficit.sum() - (need - harvest)) <= REL_TOL * need
        slack = REL_TOL * max(r["opening"], need)
        assert 0.0 <= x <= deficit.sum() + slack
        result = counterfactual_store_access(
            r["share"], r["store_claim"], need, harvest, x, 1, slack
        )
        assert abs(result.counterfactual_store_access_kcal.sum() - x) <= REL_TOL * x + slack
        # MVP 2.1 withdraws min(Need - H, K0): either every deficit is covered, or the store
        # is emptied (and the claims used were those held before the withdrawal).
        assert result.allocation.rounds == 0 or r["closing"] == 0.0
        if r["closing"] == 0.0 and not np.array_equal(r["store_claim"], r["share"]):
            depleted_nonneutral += 1
    assert capture.reset_checks >= depleted_nonneutral


def test_no_production_module_uses_the_counterfactual_allocator() -> None:
    src = Path(simulation.__file__).parents[1]
    users = [
        p
        for p in src.rglob("*.py")
        if "strata_access" in p.read_text() and p.name != "strata_access.py"
    ]
    assert users == []
