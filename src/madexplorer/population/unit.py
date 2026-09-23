"""The :class:`PopulationUnit`, the core simulation actor (spec §6.1).

In MVP 1 a unit is a small co-residing group (a band). Its demographic state
is an exact age-by-sex cohort vector, so every individual is represented while
bookkeeping stays vectorized. Weighted statistical super-agents and adaptive
resolution arrive in MVP 2/3.
"""

from dataclasses import dataclass, field

import numpy as np

from madexplorer.core.types import IntArray


@dataclass(frozen=True, slots=True)
class Observation:
    """What a unit believes about a cell, and when it learned it."""

    year: int
    food_kcal: float  # perceived accessible wild food stock
    water_access: float
    population: int  # other people perceived in the cell (excluding the observer)


@dataclass(eq=False)
class PopulationUnit:
    """A co-residing group of one species."""

    id: str
    species_id: str
    cell: int
    females: IntArray  # counts by completed age
    males: IntArray
    reserve_kcal_per_capita: float
    founded_year: int
    parent_id: str | None = None
    energy_debt_kcal: float = 0.0  # e.g. travel energy, charged against next year's budget
    harvest_kcal: float = 0.0  # food acquired this year
    food_ratio: float = 1.0  # acquired / required, last year
    energy_deficit: float = 0.0  # unmet fraction of requirement after reserves, last year
    knowledge: dict[int, Observation] = field(default_factory=dict)
    familiarity: dict[int, float] = field(default_factory=dict)

    @property
    def population(self) -> int:
        """Number of individuals."""
        return int(self.females.sum() + self.males.sum())

    @property
    def total_reserve_kcal(self) -> float:
        """Group energy reserve."""
        return self.reserve_kcal_per_capita * self.population

    def has_reproductive_pair(
        self, female_ok: np.ndarray, male_ok: np.ndarray
    ) -> tuple[bool, bool]:
        """Whether the unit contains at least one fertile-age female and male."""
        return bool((self.females * female_ok).sum() > 0), bool((self.males * male_ok).sum() > 0)
