import numpy as np
from hypothesis import given
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
    shares, removal = cell_harvest(
        accessible, np.array([1000.0, 2500.0]), np.array(labor), np.ones(len(labor)), target
    )
    assert (removal <= accessible + 1e-6).all()
    assert np.isclose(shares.sum(), removal.sum())
    assert (shares >= 0).all()


def test_foraging_has_diminishing_returns() -> None:
    accessible, rates = np.array([1e7, 0.0]), np.array([1000.0, 0.0])
    harvests = [
        cell_harvest(accessible, rates, np.array([h]), np.ones(1), 1e12)[0][0]
        for h in (1e3, 2e3, 4e3)
    ]
    assert harvests[0] < harvests[1] < harvests[2]
    assert harvests[2] - harvests[1] < 2 * (harvests[1] - harvests[0])


def test_satisficing_stops_near_target() -> None:
    shares, _ = cell_harvest(
        np.array([1e8, 1e7]), np.array([1000.0, 2500.0]), np.array([1e5]), np.ones(1), 1e6
    )
    assert np.isclose(shares.sum(), 1e6, rtol=1e-3)


def test_crowding_reduces_per_group_harvest() -> None:
    accessible, rates = np.array([5e6, 1e6]), np.array([1000.0, 2500.0])
    alone, _ = cell_harvest(accessible, rates, np.array([1e4]), np.ones(1), 1e12)
    crowded, _ = cell_harvest(accessible, rates, np.array([1e4, 1e4, 1e4]), np.ones(3), 1e12)
    assert crowded[0] < alone[0]


def test_familiarity_increases_share() -> None:
    shares, _ = cell_harvest(
        np.array([1e7, 0.0]),
        np.array([1000.0, 0.0]),
        np.array([1e4, 1e4]),
        np.array([1.0, 0.5]),
        1e12,
    )
    assert shares[0] > shares[1]


def test_energy_balance_uses_reserves_before_deficit() -> None:
    ratio, deficit, reserve = energy_balance(
        need_kcal=100, harvest_kcal=80, reserve_kcal=30, reserve_cap_kcal=50
    )
    assert (ratio, deficit, reserve) == (0.8, 0.0, 10.0)
    _, deficit, reserve = energy_balance(
        need_kcal=100, harvest_kcal=50, reserve_kcal=10, reserve_cap_kcal=50
    )
    assert np.isclose(deficit, 0.4) and reserve == 0
    _, _, reserve = energy_balance(
        need_kcal=100, harvest_kcal=500, reserve_kcal=0, reserve_cap_kcal=50
    )
    assert reserve == 50  # surplus beyond the physiological cap spoils
