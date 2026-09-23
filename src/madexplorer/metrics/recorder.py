"""Per-year scalar metrics and periodic spatial snapshots (spec §24, §31)."""

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import IntArray


class MetricsRecorder:
    """Collects one metrics row per year and population grids at a fixed interval."""

    def __init__(self, scenario: Scenario, snapshot_interval_years: int) -> None:
        self.species_ids = sorted(scenario.species)
        self.interval = snapshot_interval_years
        self.start_year = scenario.config.simulation.start_year
        self.rows: list[dict[str, float | int]] = []
        self.snapshot_years: list[int] = []
        self.snapshots: list[IntArray] = []

    def snapshot(self, state: SimulationState) -> None:
        """Store the population-per-cell field for the current year."""
        self.snapshot_years.append(state.year)
        self.snapshots.append(state.cell_population())

    def record(self, state: SimulationState, ctx: StepContext) -> dict[str, float | int]:
        """Compute and store this year's metrics row."""
        units = list(state.units.values())
        sizes = np.array([u.population for u in units], dtype=np.float64)
        population = int(sizes.sum())
        cell_pop = state.cell_population()
        eco = state.ecology
        ledger = ctx.ledger
        per_thousand = 1000.0 / population if population else 0.0

        def weighted(values: list[float]) -> float:
            return float(np.dot(values, sizes) / population) if population else 0.0

        mean_age = 0.0
        if population:
            total_age = sum(
                float(((u.females + u.males) * np.arange(u.females.size)).sum()) for u in units
            )
            mean_age = total_age / population
        row: dict[str, float | int] = {
            "year": state.year,
            "population": population,
            "units": len(units),
            "occupied_cells": int((cell_pop > 0).sum()),
            "max_cell_population": int(cell_pop.max()) if cell_pop.size else 0,
            "mean_group_size": float(sizes.mean()) if units else 0.0,
            "max_group_size": int(sizes.max()) if units else 0,
            "births": ledger.births,
            "deaths": ledger.deaths,
            "crude_birth_rate": ledger.births * per_thousand,
            "crude_death_rate": ledger.deaths * per_thousand,
            "mean_age": mean_age,
            "migrations": ledger.migrations,
            "fissions": ledger.fissions,
            "fusions": ledger.fusions,
            "extinctions": ledger.extinctions,
            "mean_food_ratio": weighted([u.food_ratio for u in units]),
            "mean_energy_deficit": weighted([u.energy_deficit for u in units]),
            "harvest_to_need": ledger.harvest_kcal / ledger.need_kcal if ledger.need_kcal else 0.0,
            "plant_stock_fraction": float(
                eco.plant_stock_kcal.sum() / max(eco.plant_capacity_kcal.sum(), 1.0)
            ),
            "game_stock_fraction": float(
                eco.game_stock_kcal.sum() / max(eco.game_capacity_kcal.sum(), 1.0)
            ),
            "temp_anomaly_c": state.climate.temp_anomaly_c,
            "log_rain_anomaly": state.climate.log_rain_anomaly,
        }
        if len(self.species_ids) > 1:
            for sid in self.species_ids:
                row[f"population_{sid}"] = sum(u.population for u in units if u.species_id == sid)
        self.rows.append(row)
        if (state.year - self.start_year) % self.interval == 0:
            self.snapshot(state)
        return row
