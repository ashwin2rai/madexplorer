"""Per-year scalar metrics and periodic spatial snapshots (spec §24, §31)."""

from typing import TYPE_CHECKING

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.population.health import crowding_hazard_columns

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns


class MetricsRecorder:
    """Collects one metrics row per year and population grids at a fixed interval.

    The full recorder (default) is for detailed inspection; ``light=True`` keeps only the
    per-year fields ensemble summaries use (:data:`LIGHT_FIELDS`) and skips snapshots.
    """

    def __init__(
        self, scenario: Scenario, snapshot_interval_years: int, light: bool = False
    ) -> None:
        self.species_ids = sorted(scenario.species)
        knowledge = scenario.knowledge
        self.domains = tuple(knowledge.domains) if knowledge else ()
        self.technologies = tuple(t.id for t in knowledge.technologies) if knowledge else ()
        self.interval = snapshot_interval_years
        self.light = light
        self.start_year = scenario.config.simulation.start_year
        self.rows: list[dict[str, float | int]] = []
        self.snapshot_years: list[int] = []
        self.snapshots: list[IntArray] = []

    def _farming_metrics(
        self,
        state: SimulationState,
        ctx: StepContext,
        cols: "UnitColumns",
        cell_pop: IntArray,
    ) -> dict[str, float]:
        """Land use, labor and density diagnostics of farming (NaN where nothing is farmed).

        Everything is computed from cell totals or summed over units, so splitting identical
        groups into more computational units does not change the values.
        """
        fields = state.cell_fields_ha()
        farmed = fields > 0
        occupied = cell_pop > 0
        area = state.world.cell_area_km2
        cultivated = float(fields.sum())
        farm_hours = cols.get("farm_hours")
        people = cols.population()
        hours = sum(farm_hours.tolist())
        farm_pop = int(people[farm_hours > 0].sum())
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
            "arable_utilization": ratio(cultivated, float(ctx.arable_ha[farmed].sum())),
            "cultivated_ha_per_capita": ratio(
                cultivated, int(people[cols.get("fields_ha") > 0].sum())
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

    def _crowding(
        self, state: SimulationState, ctx: StepContext, cols: "UnitColumns"
    ) -> FloatArray:
        if not ctx.mechanisms.crowding_mortality:
            return np.zeros(len(cols))
        return crowding_hazard_columns(
            cols.population().astype(np.float64),
            cols.get("groups"),
            cols.get("residence_years"),
            cols.get("cell"),
            cols.species(),
            {sid: p.health for sid, p in ctx.scenario.species.items()},
            state.world.cell_area_km2,
        )

    def _tech_population(self, cols: "UnitColumns", people: IntArray, tech: str) -> int:
        held = np.array([tech in techs for techs in cols.technologies()], dtype=bool)
        return int(people[held].sum()) if held.size else 0

    def record(self, state: SimulationState, ctx: StepContext) -> dict[str, float | int]:
        """Compute and store this year's metrics row."""
        if self.light:
            return self._record_light(state, ctx)
        cols = ctx.columns(state)
        people = cols.population()
        sizes = people.astype(np.float64)
        population = int(sizes.sum())
        n_units = len(cols)
        cell_pop = state.cell_population()
        eco = state.ecology
        ledger = ctx.ledger
        per_thousand = 1000.0 / population if population else 0.0

        def weighted(values: FloatArray) -> float:
            return float(np.dot(values, sizes) / population) if population else 0.0

        mean_age = 0.0
        if population:
            ages = max((len(t.need_fraction) for t in ctx.tables.values()), default=0)
            females, males = cols.cohorts(ages)
            per_unit = ((females + males) * np.arange(ages)[None, :]).sum(axis=1)
            mean_age = sum(per_unit.astype(np.float64).tolist()) / population
        fields_ha = cols.get("fields_ha")
        residence = cols.get("residence_years")
        row: dict[str, float | int] = {
            "year": state.year,
            "population": population,
            "units": n_units,
            "occupied_cells": int((cell_pop > 0).sum()),
            "max_cell_population": int(cell_pop.max()) if cell_pop.size else 0,
            "mean_group_size": float(sizes.mean()) if n_units else 0.0,
            "max_group_size": int(sizes.max()) if n_units else 0,
            "births": ledger.births,
            "deaths": ledger.deaths,
            "crude_birth_rate": ledger.births * per_thousand,
            "crude_death_rate": ledger.deaths * per_thousand,
            "mean_age": mean_age,
            "migrations": ledger.migrations,
            "migration_decisions": ledger.migration_decisions,
            "food_saturated_decisions": ledger.food_saturated_decisions,
            "fissions": ledger.fissions,
            "fusions": ledger.fusions,
            "extinctions": ledger.extinctions,
            "mean_food_ratio": weighted(cols.get("food_ratio")),
            "mean_energy_deficit": weighted(cols.get("energy_deficit")),
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
                "cultivated_ha": float(sum(fields_ha.tolist())),
                "farming_population_share": (
                    int(people[fields_ha > 0].sum()) / population if population else 0.0
                ),
                "sedentary_share": (
                    int(people[residence >= 10].sum()) / population if population else 0.0
                ),
                "stores_per_capita_kcal": float(sum(cols.get("stores_kcal").tolist()) / population)
                if population
                else 0.0,
                "cells_over_100": int((cell_pop > 100).sum()),
                "cells_over_500": int((cell_pop > 500).sum()),
                "mean_groups_per_unit": float(np.mean(cols.get("groups"))) if n_units else 0.0,
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
        row.update(self._farming_metrics(state, ctx, cols, cell_pop))
        row["mean_crowding_hazard"] = weighted(self._crowding(state, ctx, cols))
        row["crowding_death_share"] = (
            ledger.crowding_deaths_expected / ledger.deaths if ledger.deaths else 0.0
        )
        if self.domains:
            knowledge = cols.knowledge()
            for i, domain in enumerate(self.domains):
                row[f"knowledge_{domain}"] = weighted(knowledge[:, i].astype(np.float64))
        for tech in self.technologies:
            row[f"tech_share_{tech}"] = (
                self._tech_population(cols, people, tech) / population if population else 0.0
            )
        if len(self.species_ids) > 1:
            species_ids = [u.species_id for u in cols.units]
            for sid in self.species_ids:
                row[f"population_{sid}"] = int(
                    people[np.array([s == sid for s in species_ids], dtype=bool)].sum()
                )
        self.rows.append(row)
        if (state.year - self.start_year) % self.interval == 0:
            self.snapshot(state)
        return row

    def _record_light(self, state: SimulationState, ctx: StepContext) -> dict[str, float | int]:
        """The ensemble subset of :meth:`record` (same formulas; checked by a test)."""
        cols = ctx.columns(state)
        people = cols.population()
        population = int(people.sum())
        ledger = ctx.ledger
        harvest = ledger.harvest_kcal
        fields = state.cell_fields_ha()
        cultivated = float(fields.sum())

        def share(selected: int) -> float:
            return selected / population if population else 0.0

        crowding = self._crowding(state, ctx, cols)
        sizes = people.astype(np.float64)
        row: dict[str, float | int] = {
            "year": state.year,
            "population": population,
            "units": len(cols),
            "occupied_cells": int((state.cell_population() > 0).sum()),
            "crude_death_rate": ledger.deaths * (1000.0 / population if population else 0.0),
            "migrations": ledger.migrations,
            "migration_decisions": ledger.migration_decisions,
            "food_saturated_decisions": ledger.food_saturated_decisions,
            "farm_share_of_harvest": ledger.farm_harvest_kcal / harvest if harvest else 0.0,
            "cultivated_ha": float(sum(cols.get("fields_ha").tolist())),
            "sedentary_share": share(int(people[cols.get("residence_years") >= 10].sum())),
            "inventions": ledger.inventions,
            "mean_soil_nutrients_farmed": (
                float((state.ecology.soil_nutrients * fields).sum()) / cultivated
                if cultivated > 0
                else float("nan")
            ),
            "mean_crowding_hazard": (
                float(np.dot(crowding, sizes) / population) if population else 0.0
            ),
            "crowding_death_share": (
                ledger.crowding_deaths_expected / ledger.deaths if ledger.deaths else 0.0
            ),
        }
        for tech in self.technologies:
            row[f"tech_share_{tech}"] = share(self._tech_population(cols, people, tech))
        self.rows.append(row)
        return row


LIGHT_FIELDS = (
    "year",
    "population",
    "units",
    "occupied_cells",
    "crude_death_rate",
    "migrations",
    "migration_decisions",
    "food_saturated_decisions",
    "farm_share_of_harvest",
    "cultivated_ha",
    "sedentary_share",
    "inventions",
    "mean_soil_nutrients_farmed",
    "mean_crowding_hazard",
    "crowding_death_share",
)  # plus tech_share_<technology> for every technology
