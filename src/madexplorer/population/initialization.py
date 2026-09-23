"""Founding populations from scenario seeds."""

import numpy as np

from madexplorer.config.schema import InitialPopulation
from madexplorer.population.unit import PopulationUnit
from madexplorer.species.life_history import LifeTables
from madexplorer.species.profile import SpeciesProfile


def found_unit(
    unit_id: str,
    seed: InitialPopulation,
    cell: int,
    profile: SpeciesProfile,
    tables: LifeTables,
    year: int,
    rng: np.random.Generator,
) -> PopulationUnit:
    """Sample a founding group with a stationary age structure."""
    weights = tables.survivorship / tables.survivorship.sum()
    counts = rng.multinomial(seed.population, weights).astype(np.int64)
    males = rng.binomial(counts, profile.life_history.male_birth_fraction).astype(np.int64)
    reserve = (
        seed.initial_reserve_fraction
        * profile.metabolism.reserve_days_max
        * profile.metabolism.adult_daily_kcal
    )
    return PopulationUnit(
        id=unit_id,
        species_id=profile.id,
        cell=cell,
        females=counts - males,
        males=males,
        reserve_kcal_per_capita=reserve,
        founded_year=year,
        familiarity={cell: 1.0},  # founders know their homeland
    )
