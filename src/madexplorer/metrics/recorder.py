"""Per-year scalar metrics and periodic spatial snapshots (spec §24, §31)."""

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.economy.agriculture import arable_hectares
from madexplorer.population.unit import PopulationUnit


class MetricsRecorder:
    """Collects one metrics row per year and population grids at a fixed interval."""

    def __init__(self, scenario: Scenario, snapshot_interval_years: int) -> None:
        self.species_ids = sorted(scenario.species)
        knowledge = scenario.knowledge
        self.domains = tuple(knowledge.domains) if knowledge else ()
        self.technologies = tuple(t.id for t in knowledge.technologies) if knowledge else ()
        self.interval = snapshot_interval_years
        self.start_year = scenario.config.simulation.start_year
        self.rows: list[dict[str, float | int]] = []
        self.snapshot_years: list[int] = []
        self.snapshots: list[IntArray] = []
        self._arable: FloatArray | None = None

    def _farming_metrics(
        self,
        state: SimulationState,
        ctx: StepContext,
        units: list[PopulationUnit],
        cell_pop: IntArray,
    ) -> dict[str, float]:
        """Land use, labor and density diagnostics of farming (NaN where nothing is farmed).

        Everything is computed from cell totals or summed over units, so splitting identical
        groups into more computational units does not change the values.
        """
        if self._arable is None:
            self._arable = arable_hectares(state.world, ctx.scenario.config.agriculture)
        fields = state.cell_fields_ha()
        farmed = fields > 0
        occupied = cell_pop > 0
        area = state.world.cell_area_km2
        cultivated = float(fields.sum())
        hours = sum(u.farm_hours for u in units)
        farm_pop = sum(u.population for u in units if u.farm_hours > 0)
        nan = float("nan")

        def ratio(numerator: float, denominator: float) -> float:
            return numerator / denominator if denominator > 0 else nan

        def quantile(values: FloatArray, q: float) -> float:
            return float(np.quantile(values, q)) if values.size else nan

        farmed_density = cell_pop[farmed] / area
        occupied_density = cell_pop[occupied] / area
        return {
            "mean_soil_nutrients_farmed": ratio(
                float((state.ecology.soil_nutrients * fields).sum()), cultivated
            ),
            "arable_utilization": ratio(cultivated, float(self._arable[farmed].sum())),
            "cultivated_ha_per_capita": ratio(
                cultivated, sum(u.population for u in units if u.fields_ha > 0)
            ),
            "farm_hours_per_capita": ratio(hours, farm_pop),
            "crop_kcal_per_farm_hour": ratio(ctx.ledger.farm_harvest_kcal, hours),
            "farmed_cell_population_density": ratio(
                float(cell_pop[farmed].sum()), float(farmed.sum()) * area
            ),
            "farmed_density_p50": quantile(farmed_density, 0.5),
            "farmed_density_p90": quantile(farmed_density, 0.9),
            "occupied_density_p50": quantile(occupied_density, 0.5),
            "occupied_density_p90": quantile(occupied_density, 0.9),
        }

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
        harvest = ledger.harvest_kcal
        row.update(
            {
                "farm_share_of_harvest": ledger.farm_harvest_kcal / harvest if harvest else 0.0,
                "cultivated_ha": float(sum(u.fields_ha for u in units)),
                "farming_population_share": (
                    sum(u.population for u in units if u.fields_ha > 0) / population
                    if population
                    else 0.0
                ),
                "sedentary_share": (
                    sum(u.population for u in units if u.residence_years >= 10) / population
                    if population
                    else 0.0
                ),
                "stores_per_capita_kcal": float(sum(u.stores_kcal for u in units) / population)
                if population
                else 0.0,
                "cells_over_100": int((cell_pop > 100).sum()),
                "cells_over_500": int((cell_pop > 500).sum()),
                "mean_groups_per_unit": float(np.mean([u.groups for u in units])) if units else 0.0,
                "resolution_merges": ledger.resolution_merges,
                "trade_volume_kcal": ledger.trade_volume_kcal,
                "trade_share_of_harvest": ledger.trade_volume_kcal / harvest if harvest else 0.0,
                "transport_loss_kcal": ledger.transport_loss_kcal,
                "spoilage_kcal": ledger.spoilage_kcal,
                "inventions": ledger.inventions,
                "adoptions": ledger.adoptions,
                "technology_losses": ledger.technology_losses,
            }
        )
        row.update(self._farming_metrics(state, ctx, units, cell_pop))
        for i, domain in enumerate(self.domains):
            row[f"knowledge_{domain}"] = weighted([float(u.knowledge[i]) for u in units])
        for tech in self.technologies:
            row[f"tech_share_{tech}"] = (
                sum(u.population for u in units if tech in u.technologies) / population
                if population
                else 0.0
            )
        if len(self.species_ids) > 1:
            for sid in self.species_ids:
                row[f"population_{sid}"] = sum(u.population for u in units if u.species_id == sid)
        self.rows.append(row)
        if (state.year - self.start_year) % self.interval == 0:
            self.snapshot(state)
        return row
