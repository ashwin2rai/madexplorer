"""The :class:`PopulationUnit`, the core simulation actor (spec §6.1).

A unit is one or more co-residing social groups of one species (``groups``).
Its demographic state is an exact age-by-sex cohort vector, so every
individual is represented while bookkeeping stays vectorized. Co-located
similar groups are coarsened into one unit (MVP 2); distributional
super-agents with wealth and health distributions arrive in MVP 3.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from madexplorer.core.types import FloatArray, IntArray

HARVEST_MEMORY_YEARS = 10


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
    beliefs: dict[int, Observation] = field(default_factory=dict)  # spatial beliefs by cell
    familiarity: dict[int, float] = field(default_factory=dict)
    groups: int = 1  # social groups represented by this unit
    # Knowledge and technology (MVP 2).
    knowledge: FloatArray = field(default_factory=lambda: np.zeros(0))  # level per domain
    technologies: frozenset[str] = frozenset()
    # Subsistence state (MVP 2).
    stores_kcal: float = 0.0  # non-body food storage, immobile beyond carrying capacity
    fields_ha: float = 0.0  # cultivated land held in the current cell
    ever_cultivated: bool = False
    labor_debt_hours: float = 0.0  # e.g. field clearing, charged against next year's labor
    farm_harvest_kcal: float = 0.0
    farm_hours: float = 0.0
    forage_harvest_kcal: float = 0.0
    forage_hours: float = 0.0
    forage_marginal_kcal_per_hour: float = 0.0
    forage_plant_share: float = 0.0  # plant share of wild harvest
    crop_yield_kcal_per_ha: float = 0.0  # realized this year
    clearing_hours: float = 0.0  # spent clearing last planning step
    stored_kcal: float = 0.0  # put into storage this year
    residence_years: int = 0  # consecutive years in the current cell
    harvest_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=HARVEST_MEMORY_YEARS)
    )  # per-capita harvest, most recent last
    trade_ties: dict[str, float] = field(default_factory=dict)  # partner id -> tie strength

    def __setattr__(self, name: str, value: object) -> None:
        # Cohort arrays are always replaced, never mutated in place, so resetting the
        # cached head count on assignment keeps ``population`` exact.
        if name in ("females", "males"):
            object.__setattr__(self, "_population", None)
        object.__setattr__(self, name, value)

    @property
    def population(self) -> int:
        """Number of individuals (cached until the cohort arrays are replaced)."""
        cached: int | None = getattr(self, "_population", None)
        if cached is None:
            cached = int(self.females.sum() + self.males.sum())
            object.__setattr__(self, "_population", cached)
        return cached

    @property
    def total_reserve_kcal(self) -> float:
        """Group energy reserve."""
        return self.reserve_kcal_per_capita * self.population

    def harvest_variability(self) -> float:
        """Coefficient of variation of recent per-capita harvests (0 with < 3 years)."""
        if len(self.harvest_history) < 3:
            return 0.0
        values = np.fromiter(self.harvest_history, dtype=np.float64)
        mean = values.mean()
        return float(values.std() / mean) if mean > 0 else 0.0

    def has_reproductive_pair(
        self, female_ok: np.ndarray, male_ok: np.ndarray
    ) -> tuple[bool, bool]:
        """Whether the unit contains at least one fertile-age female and male."""
        return bool((self.females * female_ok).sum() > 0), bool((self.males * male_ok).sum() > 0)
