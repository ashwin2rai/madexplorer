import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from madexplorer.economy.foraging import cell_harvest
from madexplorer.population.energetics import energy_balance

stocks = st.floats(min_value=0, max_value=1e9)
positive = st.floats(min_value=1.0, max_value=1e6)


@given(
    stocks,
    stocks,
    st.lists(positive, min_size=1, max_size=5),
    st.floats(min_value=0, max_value=1e9),
)
def test_harvest_never_exceeds_accessible_stock(
    plant: float, game: float, labor: list[float], target: float
) -> None:
    accessible = np.array([plant, game])
    outcome = cell_harvest(
        accessible, np.array([1000.0, 2500.0]), np.array(labor), np.ones(len(labor)), target
    )
    shares, removal = outcome.shares, outcome.removal
    assert (removal <= accessible + 1e-6).all()
    assert np.isclose(shares.sum(), removal.sum())
    assert (shares >= 0).all()


def test_foraging_has_diminishing_returns() -> None:
    accessible, rates = np.array([1e7, 0.0]), np.array([1000.0, 0.0])
    harvests = [
        cell_harvest(accessible, rates, np.array([h]), np.ones(1), 1e12).shares[0]
        for h in (1e3, 2e3, 4e3)
    ]
    assert harvests[0] < harvests[1] < harvests[2]
    assert harvests[2] - harvests[1] < 2 * (harvests[1] - harvests[0])


def test_satisficing_stops_near_target() -> None:
    shares = cell_harvest(
        np.array([1e8, 1e7]), np.array([1000.0, 2500.0]), np.array([1e5]), np.ones(1), 1e6
    ).shares
    assert np.isclose(shares.sum(), 1e6, rtol=1e-3)


def test_crowding_reduces_per_group_harvest() -> None:
    accessible, rates = np.array([5e6, 1e6]), np.array([1000.0, 2500.0])
    alone = cell_harvest(accessible, rates, np.array([1e4]), np.ones(1), 1e12).shares
    crowded = cell_harvest(accessible, rates, np.array([1e4, 1e4, 1e4]), np.ones(3), 1e12).shares
    assert crowded[0] < alone[0]


def test_familiarity_increases_share() -> None:
    shares = cell_harvest(
        np.array([1e7, 0.0]),
        np.array([1000.0, 0.0]),
        np.array([1e4, 1e4]),
        np.array([1.0, 0.5]),
        1e12,
    ).shares
    assert shares[0] > shares[1]


def test_energy_balance_uses_reserves_before_deficit() -> None:
    b = energy_balance(need_kcal=100, harvest_kcal=80, reserve_kcal=30, reserve_cap_kcal=50)
    assert (b.food_ratio, b.deficit, b.reserve_kcal) == (0.8, 0.0, 10.0)
    b = energy_balance(need_kcal=100, harvest_kcal=50, reserve_kcal=10, reserve_cap_kcal=50)
    assert np.isclose(b.deficit, 0.4) and b.reserve_kcal == 0
    b = energy_balance(need_kcal=100, harvest_kcal=500, reserve_kcal=0, reserve_cap_kcal=50)
    assert b.reserve_kcal == 50 and b.spoiled_kcal == 350  # no storage: surplus beyond cap spoils


def test_storage_captures_surplus_and_buffers_shortfalls() -> None:
    b = energy_balance(100, 500, 0, 50, stores_kcal=0, can_store=True)
    assert b.reserve_kcal == 50 and b.stores_kcal == 350 and b.spoiled_kcal == 0
    b = energy_balance(100, 20, 30, 50, stores_kcal=60, can_store=True)
    assert b.stores_kcal == 0 and b.reserve_kcal == 10 and b.deficit == 0  # stores first


def test_marginal_return_falls_with_effort() -> None:
    accessible, rates = np.array([1e7, 1e6]), np.array([1000.0, 2500.0])
    low = cell_harvest(accessible, rates, np.array([1e3]), np.ones(1), 1e12)
    high = cell_harvest(accessible, rates, np.array([1e5]), np.ones(1), 1e12)
    assert 0 < high.marginal_kcal_per_effective_hour < low.marginal_kcal_per_effective_hour <= 2500


@settings(max_examples=300, deadline=None)
@given(
    plant=st.floats(1e3, 1e10),
    game=st.floats(0, 1e10),
    plant_rate=st.floats(100, 3000),
    game_rate=st.floats(100, 3000),
    capacity=st.floats(1e3, 1e6),
    share=st.floats(0.01, 0.99),
)
def test_newton_effort_fraction_matches_a_fine_bisection(
    plant: float, game: float, plant_rate: float, game_rate: float, capacity: float, share: float
) -> None:
    from madexplorer.economy.foraging import _effort_fraction, _harvest

    stock, rates = (plant, game), (plant_rate, game_rate)
    target = share * sum(_harvest(stock, rates, capacity))
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        lo, hi = (lo, mid) if sum(_harvest(stock, rates, capacity * mid)) >= target else (mid, hi)
    fraction = _effort_fraction(stock, rates, capacity, target)
    assert 0.0 <= fraction <= 1.0
    assert fraction == pytest.approx(hi, rel=1e-9, abs=1e-12)
    assert sum(_harvest(stock, rates, capacity * fraction)) == pytest.approx(target, rel=1e-10)
