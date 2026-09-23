import numpy as np
import pytest

from madexplorer.config.schema import AgricultureConfig
from madexplorer.economy.agriculture import (
    adjusted_fields_ha,
    clearing_hours_per_ha,
    update_soil_nutrients,
)
from madexplorer.economy.trade import delivered_fraction


def test_fields_expand_when_farming_beats_foraging() -> None:
    fields, gap = adjusted_fields_ha(10.0, 1e6, 600.0, 0.0, 10, 500.0, 0.3, 2.0, 0.1)
    assert gap > 0 and fields > 10.0


def test_fields_shrink_when_foraging_is_better() -> None:
    fields, gap = adjusted_fields_ha(10.0, 1e5, 600.0, 0.0, 10, 2000.0, 0.3, 2.0, 0.1)
    assert gap < 0 and fields < 10.0


def test_clearing_cost_deters_mobile_groups_but_not_settled_ones() -> None:
    args = dict(
        yield_per_ha=6e5,
        cultivation_hours_per_ha=600.0,
        clearing_hours=1500.0,
        forage_marginal=600.0,
        adjustment_rate=0.3,
        initial_plot_ha=2.0,
        margin=0.1,
    )
    mobile, _ = adjusted_fields_ha(0.0, expected_tenure_years=1, **args)
    settled, _ = adjusted_fields_ha(0.0, expected_tenure_years=10, **args)
    assert mobile == 0.0 and settled > 0.0


def test_forest_clearing_costs_more_and_tools_help() -> None:
    config = AgricultureConfig()
    assert clearing_hours_per_ha(0.7, config, 1.0) > clearing_hours_per_ha(0.1, config, 1.0)
    assert clearing_hours_per_ha(0.7, config, 2.0) < clearing_hours_per_ha(0.7, config, 1.0)


def test_soil_depletes_under_cultivation_and_recovers_in_fallow() -> None:
    config = AgricultureConfig()
    soil = np.array([1.0, 0.5])
    farmed = update_soil_nutrients(soil, np.array([1.0, 0.0]), np.zeros(2), config)
    assert farmed[0] < 1.0 and farmed[1] > 0.5
    managed = update_soil_nutrients(soil, np.array([1.0, 0.0]), np.array([0.5, 0.0]), config)
    assert managed[0] > farmed[0]


def test_transport_loss_grows_with_distance() -> None:
    assert delivered_fraction(0.0, 60.0) == 1.0
    assert delivered_fraction(120.0, 60.0) == pytest.approx(np.exp(-2))
