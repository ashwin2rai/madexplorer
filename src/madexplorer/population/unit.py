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


NEVER_OBSERVED = -(2**62)  # observation year of a cell the unit knows nothing about


@dataclass(frozen=True, eq=False)
class BeliefMap:
    """A unit's beliefs about every cell, as dense per-cell arrays.

    ``year[c] == NEVER_OBSERVED`` means the cell is unknown (the other entries are then
    meaningless). The arrays are never modified after the map is built: perception, sharing
    and merging all construct new maps, so proposals evaluated against one year's beliefs
    stay valid until applied, and maps can be shared between units safely.
    """

    year: IntArray
    food_kcal: FloatArray  # perceived accessible wild food stock
    water_access: FloatArray
    population: IntArray  # other people perceived in the cell (excluding the observer)

    @classmethod
    def empty(cls, n_cells: int) -> "BeliefMap":
        """A map in which nothing is known."""
        return cls(
            np.full(n_cells, NEVER_OBSERVED, dtype=np.int64),
            np.zeros(n_cells),
            np.zeros(n_cells),
            np.zeros(n_cells, dtype=np.int64),
        )

    @classmethod
    def from_observations(cls, n_cells: int, observations: dict[int, Observation]) -> "BeliefMap":
        """Build a map from ``{cell: Observation}`` (tests and conversions)."""
        year, food, water, population = cls.empty(n_cells).arrays()
        for cell, obs in observations.items():
            year[cell], food[cell] = obs.year, obs.food_kcal
            water[cell], population[cell] = obs.water_access, obs.population
        return cls(year, food, water, population)

    @property
    def n_cells(self) -> int:
        """Number of cells the map covers (0 for a unit that has never perceived)."""
        return int(self.year.size)

    def arrays(self) -> tuple[IntArray, FloatArray, FloatArray, IntArray]:
        """Fresh copies of the four arrays, for building a new map."""
        return (
            self.year.copy(),
            self.food_kcal.copy(),
            self.water_access.copy(),
            self.population.copy(),
        )

    def sized(self, n_cells: int) -> "BeliefMap":
        """This map, or an empty one of the right size if it covers no cells yet."""
        if self.n_cells == n_cells:
            return self
        if self.n_cells == 0:
            return BeliefMap.empty(n_cells)
        raise ValueError(f"belief map covers {self.n_cells} cells, expected {n_cells}")

    def __contains__(self, cell: int) -> bool:
        return 0 <= cell < self.n_cells and int(self.year[cell]) != NEVER_OBSERVED

    def __len__(self) -> int:
        return int((self.year != NEVER_OBSERVED).sum())

    def __getitem__(self, cell: int) -> Observation:
        if cell not in self:
            raise KeyError(cell)
        return Observation(
            int(self.year[cell]),
            float(self.food_kcal[cell]),
            float(self.water_access[cell]),
            int(self.population[cell]),
        )

    def known_cells(self) -> IntArray:
        """Ids of cells with an observation, ascending."""
        cells: IntArray = np.flatnonzero(self.year != NEVER_OBSERVED)
        return cells

    def to_dict(self) -> dict[int, Observation]:
        """``{cell: Observation}`` for every known cell."""
        return {int(c): self[int(c)] for c in self.known_cells()}

    def merged_with(self, other: "BeliefMap") -> "BeliefMap":
        """Per cell, ``other``'s observation where it is strictly fresher than this map's."""
        n = max(self.n_cells, other.n_cells)
        mine, theirs = self.sized(n), other.sized(n)
        fresher = theirs.year > mine.year
        if not fresher.any():
            return mine
        return BeliefMap(
            np.where(fresher, theirs.year, mine.year),
            np.where(fresher, theirs.food_kcal, mine.food_kcal),
            np.where(fresher, theirs.water_access, mine.water_access),
            np.where(fresher, theirs.population, mine.population),
        )


class _Cohort:
    """Descriptor for a cohort vector: assignment clears the unit's derived head counts.

    Cohort arrays are always replaced, never mutated in place, so resetting caches on
    assignment keeps ``population`` and ``weighted_count`` exact while every other
    attribute stays a plain, fast instance attribute.
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self.slot = "_" + name

    def __get__(self, instance: object, owner: type | None = None) -> IntArray:
        if instance is None:
            raise AttributeError(self.slot)  # no class-level default for the dataclass
        value: IntArray = instance.__dict__[self.slot]
        return value

    def __set__(self, instance: object, value: IntArray) -> None:
        state = instance.__dict__
        state[self.slot] = value
        state["_population"] = None
        state["_weighted"] = None


@dataclass(eq=False)
class PopulationUnit:
    """A co-residing group of one species."""

    id: str
    species_id: str
    cell: int
    females: IntArray  # counts by completed age (a _Cohort descriptor, installed below)
    males: IntArray
    reserve_kcal_per_capita: float
    founded_year: int
    parent_id: str | None = None
    energy_debt_kcal: float = 0.0  # e.g. travel energy, charged against next year's budget
    harvest_kcal: float = 0.0  # food acquired this year
    food_ratio: float = 1.0  # acquired / required, last year
    energy_deficit: float = 0.0  # unmet fraction of requirement after reserves, last year
    beliefs: BeliefMap = field(default_factory=lambda: BeliefMap.empty(0))  # spatial beliefs
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

    @property
    def population(self) -> int:
        """Number of individuals (cached until the cohort arrays are replaced)."""
        cached: int | None = self.__dict__["_population"]
        if cached is None:
            cached = int(self.females.sum() + self.males.sum())
            self.__dict__["_population"] = cached
        return cached

    def weighted_count(self, weights: FloatArray) -> float:
        """``sum((females + males) * weights)`` over ages, cached per weight array.

        Used for age schedules that are fixed for a run (need fractions, labor capacity);
        the cache is cleared whenever a cohort array is replaced.
        """
        cache: dict[int, tuple[FloatArray, float]] | None = self.__dict__["_weighted"]
        if cache is None:
            cache = {}
            self.__dict__["_weighted"] = cache
        hit = cache.get(id(weights))
        if hit is not None and hit[0] is weights:
            return hit[1]
        value = float(((self.females + self.males) * weights).sum())
        cache[id(weights)] = (weights, value)
        return value

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


for _name in ("females", "males"):
    _descriptor = _Cohort()
    _descriptor.__set_name__(PopulationUnit, _name)
    setattr(PopulationUnit, _name, _descriptor)
