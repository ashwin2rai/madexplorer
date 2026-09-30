"""Births, deaths, and aging with nutrition-dependent rates (spec §8).

Rates are applied per age-by-sex cohort with binomial draws, so small groups
experience strong demographic stochasticity and large ones become predictable
(spec §6.6) without any special-casing.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.rng import Streams
from madexplorer.core.state import SimulationState, StepContext
from madexplorer.core.types import FloatArray, IntArray
from madexplorer.population.health import crowding_hazard_columns
from madexplorer.species.life_history import LifeTables

if TYPE_CHECKING:
    from madexplorer.core.columns import UnitColumns


@model_rule(
    name="nutritional_fertility",
    version="1.0",
    rationale=(
        "Fecundity declines logistically as food intake falls below requirement (energetic "
        "constraint on ovulation)."
    ),
    source_type="heuristic",
    parameters=("fertility_food_midpoint", "fertility_food_scale"),
    expected_domain="multiplier in [0, 1], equal to 1 at food_ratio >= 1",
    known_limitations=(
        "Uses intake relative to need only; body condition and lactation not tracked."
    ),
)
def fertility_multiplier(food_ratio: FloatArray, midpoint: float, scale: float) -> FloatArray:
    """Multiplier on age-specific fertility from last year's food ratio."""

    def logistic(x: FloatArray | float) -> FloatArray:
        return np.asarray(
            1.0 / (1.0 + np.exp(-(np.asarray(x) - midpoint) / scale)), dtype=np.float64
        )

    multiplier: FloatArray = np.minimum(logistic(food_ratio) / logistic(1.0), 1.0)
    return multiplier


@model_rule(
    name="starvation_mortality",
    version="1.0",
    rationale=(
        "Energy deficit multiplies the baseline hazard exponentially, more strongly for the young"
        " and old."
    ),
    source_type="heuristic",
    parameters=("starvation_mortality_sensitivity", "starvation_vulnerable_multiplier"),
    expected_domain="hazard >= baseline hazard",
    known_limitations="No explicit disease-nutrition interaction yet.",
)
def mortality_hazards(
    tables: LifeTables, deficit: FloatArray, sensitivity: float, crowding: FloatArray
) -> tuple[FloatArray, FloatArray]:
    """Total and crowding annual hazards, each of shape ``(units, ages)``.

    Causes add: ``h = h_baseline + h_starvation + h_crowding``, where the first two are the
    baseline hazard scaled by the starvation factor and ``crowding`` holds each unit's adult
    crowding hazard.
    """
    background = tables.hazard[None, :] * np.exp(
        sensitivity * deficit[:, None] * tables.vulnerability[None, :]
    )
    crowd: FloatArray = crowding[:, None] * tables.crowding_vulnerability[None, :]
    total: FloatArray = background + crowd
    return total, crowd


@dataclass(frozen=True)
class CohortOutcome:
    """Vectorized demographic outcome for a batch of units of one species."""

    females: IntArray  # (units, ages) after aging
    males: IntArray
    births: IntArray  # (units,)
    deaths: IntArray  # (units,)


def demographic_step(
    females: IntArray,
    males: IntArray,
    death_probability: FloatArray,
    fertility: FloatArray,
    male_birth_fraction: float,
    offspring_per_birth: int,
    rng: np.random.Generator,
) -> CohortOutcome:
    """One year of mortality, reproduction, and aging for stacked cohort arrays.

    ``fertility`` has shape ``(units, ages)`` and already includes nutritional and
    mate-availability modifiers. Individuals past the last age class die.
    """
    dead_f = rng.binomial(females, death_probability)
    dead_m = rng.binomial(males, death_probability)
    surv_f, surv_m = females - dead_f, males - dead_m
    birth_events = rng.binomial(surv_f, np.clip(fertility, 0.0, 1.0)).sum(axis=1)
    births = birth_events * offspring_per_birth
    born_m = rng.binomial(births, male_birth_fraction)
    new_f = np.zeros_like(females)
    new_m = np.zeros_like(males)
    new_f[:, 1:], new_m[:, 1:] = surv_f[:, :-1], surv_m[:, :-1]
    new_f[:, 0], new_m[:, 0] = births - born_m, born_m
    deaths = dead_f.sum(axis=1) + dead_m.sum(axis=1) + surv_f[:, -1] + surv_m[:, -1]
    return CohortOutcome(new_f, new_m, births.astype(np.int64), deaths.astype(np.int64))


@dataclass(frozen=True)
class DemographicUpdate:
    """New cohort vectors for one unit (reference form of :class:`DemographicUpdates`)."""

    unit_id: str
    females: IntArray
    males: IntArray
    births: int
    deaths: int
    crowding_deaths_expected: float = 0.0

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Replace the unit's cohorts and record flows."""
        unit = state.units[self.unit_id]
        unit.females, unit.males = self.females, self.males
        ctx.ledger.births += self.births
        ctx.ledger.deaths += self.deaths
        ctx.ledger.crowding_deaths_expected += self.crowding_deaths_expected


@dataclass(frozen=True, eq=False)
class DemographicUpdates:
    """New cohorts of one species' units (rows in unit order), committed as columns."""

    cols: "UnitColumns"
    females: IntArray  # (units, ages)
    males: IntArray
    births: IntArray
    deaths: IntArray
    crowding_deaths_expected: FloatArray

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Replace every row's cohorts and record flows (crowding total in row order)."""
        self.cols.set_cohorts(self.females, self.males)
        ledger = ctx.ledger
        ledger.births += int(self.births.sum())
        ledger.deaths += int(self.deaths.sum())
        total = ledger.crowding_deaths_expected
        for crowding in self.crowding_deaths_expected.tolist():
            total += crowding
        ledger.crowding_deaths_expected = total


def mate_available(
    males: IntArray, cells: IntArray, n_cells: int, tables: LifeTables, sexual: bool
) -> FloatArray:
    """1.0 where a unit's own or a co-located same-species group has a fertile male.

    ``males`` and ``cells`` are one species' units (rows in unit order).
    """
    if not sexual:
        return np.ones(cells.size)
    capable = (males * tables.male_reproductive[None, :]).sum(axis=1) > 0
    has_male = np.zeros(n_cells, dtype=bool)
    has_male[cells[capable]] = True
    available: FloatArray = has_male[cells].astype(np.float64)
    return available


class DemographySubsystem:
    """Mortality, fertility, and aging for all units, batched per species."""

    name = "demography"

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[DemographicUpdates]:
        """Draw one year of demographic events (one batched proposal per species)."""
        rng = ctx.rng.stream(Streams.DEMOGRAPHY)
        updates: list[DemographicUpdates] = []
        everyone = ctx.columns(state)
        if len(everyone) == 0:
            return []
        compiled = ctx.compiled
        assert compiled is not None
        codes = everyone.species()
        crowding_all = (
            crowding_hazard_columns(
                everyone.population().astype(np.float64),
                everyone.get("groups"),
                everyone.get("residence_years"),
                everyone.get("cell"),
                codes,
                {sid: p.health for sid, p in ctx.scenario.species.items()},
                state.world.cell_area_km2,
            )
            if ctx.mechanisms.crowding_mortality
            else np.zeros(len(everyone))
        )
        for code, species_id in enumerate(compiled.species_ids):
            rows = np.flatnonzero(codes == code)
            if rows.size == 0:
                continue
            cols = everyone.subset(rows) if rows.size < len(everyone) else everyone
            profile, tables = ctx.species(species_id), ctx.tables[species_id]
            metabolism, lh = profile.metabolism, profile.life_history
            deficit = cols.get("energy_deficit")
            sensitivity = metabolism.starvation_mortality_sensitivity
            if not ctx.mechanisms.starvation_mortality:
                sensitivity = 0.0
            food = cols.get("food_ratio")
            females, males = cols.cohorts(tables.need_fraction.size)
            cells = cols.get("cell")
            fert = fertility_multiplier(
                food, metabolism.fertility_food_midpoint, metabolism.fertility_food_scale
            )
            fert = fert * mate_available(
                males, cells, state.world.n_cells, tables, lh.sexual_reproduction
            )
            crowding = crowding_all[rows]
            hazard, crowd = mortality_hazards(tables, deficit, sensitivity, crowding)
            probability = 1.0 - np.exp(-hazard)
            # Expected deaths from crowding: cause share of each cohort's death probability.
            share = np.divide(crowd, hazard, out=np.zeros_like(crowd), where=hazard > 0)
            crowding_deaths = ((females + males) * probability * share).sum(axis=1)
            outcome = demographic_step(
                females,
                males,
                probability,
                tables.fertility[None, :] * fert[:, None],
                lh.male_birth_fraction,
                lh.offspring_per_birth,
                rng,
            )
            updates.append(
                DemographicUpdates(
                    cols,
                    outcome.females,
                    outcome.males,
                    outcome.births,
                    outcome.deaths,
                    crowding_deaths,
                )
            )
        return updates
