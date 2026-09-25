"""The :class:`PopulationUnit`, the core simulation actor (spec §6.1).

A unit is one or more co-residing social groups of one species (``groups``).
Its demographic state is an exact age-by-sex cohort vector, so every
individual is represented while bookkeeping stays vectorized. Co-located
similar groups are coarsened into one unit (MVP 2); distributional
super-agents with wealth and health distributions arrive in MVP 3.
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from madexplorer.core.types import BoolArray, FloatArray, IntArray

if TYPE_CHECKING:
    from madexplorer.core.state import SimulationState, StepContext

HARVEST_MEMORY_YEARS = 10


@dataclass(frozen=True, slots=True)
class Observation:
    """What a unit believes about a cell, and when it learned it.

    Static, noise-free cell properties (such as water access) are not part of a belief:
    once a cell is known they are read from the world.
    """

    year: int
    food_kcal: float  # perceived accessible wild food stock
    population: int  # other people perceived in the cell (excluding the observer)
    hops: int = 0  # provenance: 0 = observed directly, k = report relayed k times


NEVER_OBSERVED = -(2**31)  # observation year of a cell the unit knows nothing about
YEAR_DTYPE = np.int32  # observation years (halves memory traffic versus int64)
POPULATION_DTYPE = np.int32  # perceived head counts
# Perceived food is a noisy estimate (lognormal noise, sigma ~0.3); float32's ~1e-7 relative
# precision is far below that, and halves the memory of the largest belief array.
FOOD_DTYPE = np.float32
HOPS_DTYPE = np.int8  # relay count; saturates at MAX_HOPS
MAX_HOPS = 100
YearArray = npt.NDArray[np.int32]
CountArray = npt.NDArray[np.int32]
FoodArray = npt.NDArray[np.float32]
HopsArray = npt.NDArray[np.int8]


@dataclass(frozen=True, slots=True)
class BeliefPatch:
    """Sparse change to one unit's beliefs: new observations or reports for a few cells.

    Values are copies taken when the patch is built, so patches computed from one year's
    beliefs stay valid while other patches are applied. Perception also sets the unit's food
    prior (log-space mean and signal variance of its current direct observations) and its
    residence; sharing records which cells it received reports about, for relaying.
    """

    unit_id: str
    cells: IntArray
    year: YearArray
    food_kcal: FoodArray | FloatArray
    population: CountArray | IntArray
    hops: HopsArray
    food_log_prior: float | None = None
    food_log_signal_var: float | None = None
    received: bool = False
    resident_cell: int | None = None  # perception: the cell the unit lives in this year

    def apply(self, state: "SimulationState", ctx: "StepContext") -> None:
        """Write the observations into the unit's belief arrays (only these cells)."""
        unit = state.units[self.unit_id]
        unit.beliefs = unit.beliefs.sized(state.world.n_cells)
        unit.beliefs.write(self.cells, self.year, self.food_kcal, self.population, self.hops)
        if self.food_log_prior is not None:
            unit.food_log_prior = self.food_log_prior
        if self.food_log_signal_var is not None:
            unit.food_log_signal_var = self.food_log_signal_var
        if self.received:
            unit.report_cells = self.cells
        if self.resident_cell is not None:
            memory = ctx.species(unit.species_id).cognition.memory_years
            unit.note_residence(self.resident_cell, state.year, memory)


@dataclass(eq=False)
class BeliefMap:
    """A unit's beliefs about every cell, as dense per-cell arrays owned by one unit.

    ``year[c] == NEVER_OBSERVED`` means the cell was never observed (the other entries are
    then meaningless). Expiry is lazy: an entry is *current* in year ``t`` for a memory of
    ``m`` years while ``year[c] > t - m``; stale entries stay in the arrays and are simply
    ignored by readers (:meth:`current`), so no yearly scan of the whole map is needed.

    The arrays are modified in place, only through :class:`BeliefPatch` in the apply phase
    (staged evaluation stays valid because patches carry copies). A map belongs to exactly
    one unit: fission copies it (:meth:`copy`), so the copying cost falls on rare structural
    events rather than on every perception step.
    """

    year: YearArray
    food_kcal: FoodArray  # perceived accessible wild food stock (float32)
    population: CountArray  # other people perceived in the cell (excluding the observer)
    hops: HopsArray  # provenance: 0 = direct observation, k = relayed k times

    @classmethod
    def empty(cls, n_cells: int) -> "BeliefMap":
        """A map in which nothing is known."""
        return cls(
            np.full(n_cells, NEVER_OBSERVED, dtype=YEAR_DTYPE),
            np.zeros(n_cells, dtype=FOOD_DTYPE),
            np.zeros(n_cells, dtype=POPULATION_DTYPE),
            np.zeros(n_cells, dtype=HOPS_DTYPE),
        )

    @classmethod
    def from_observations(cls, n_cells: int, observations: dict[int, Observation]) -> "BeliefMap":
        """Build a map from ``{cell: Observation}`` (tests and conversions)."""
        beliefs = cls.empty(n_cells)
        for cell, obs in observations.items():
            beliefs.year[cell], beliefs.food_kcal[cell] = obs.year, obs.food_kcal
            beliefs.population[cell], beliefs.hops[cell] = obs.population, obs.hops
        return beliefs

    @property
    def n_cells(self) -> int:
        """Number of cells the map covers (0 for a unit that has never perceived)."""
        return int(self.year.size)

    def copy(self) -> "BeliefMap":
        """An independent copy (for a daughter unit)."""
        return BeliefMap(
            self.year.copy(), self.food_kcal.copy(), self.population.copy(), self.hops.copy()
        )

    def sized(self, n_cells: int) -> "BeliefMap":
        """This map, or an empty one of the right size if it covers no cells yet."""
        if self.n_cells == n_cells:
            return self
        if self.n_cells == 0:
            return BeliefMap.empty(n_cells)
        raise ValueError(f"belief map covers {self.n_cells} cells, expected {n_cells}")

    def write(
        self,
        cells: IntArray,
        year: YearArray | int,
        food_kcal: FoodArray | FloatArray,
        population: CountArray | IntArray,
        hops: HopsArray | int = 0,
    ) -> None:
        """Overwrite the entries of ``cells`` (apply phase only)."""
        self.year[cells] = year
        self.food_kcal[cells] = food_kcal
        self.population[cells] = population
        self.hops[cells] = hops

    def current(self, cells: IntArray, year: int, memory_years: int) -> BoolArray:
        """Which of ``cells`` hold an observation still within memory in ``year``."""
        mask: BoolArray = self.year[cells] > year - memory_years
        return mask

    def known_cells(self, year: int, memory_years: int) -> int:
        """Number of cells with a current observation."""
        return int((self.year > year - memory_years).sum())

    def __contains__(self, cell: int) -> bool:
        """Whether the cell has ever been observed (current or stale)."""
        return 0 <= cell < self.n_cells and int(self.year[cell]) != NEVER_OBSERVED

    def __getitem__(self, cell: int) -> Observation:
        if cell not in self:
            raise KeyError(cell)
        return Observation(
            int(self.year[cell]),
            float(self.food_kcal[cell]),
            int(self.population[cell]),
            int(self.hops[cell]),
        )

    def to_dict(self) -> dict[int, Observation]:
        """``{cell: Observation}`` for every cell ever observed (current or stale)."""
        return {c: self[c] for c in np.flatnonzero(self.year != NEVER_OBSERVED).tolist()}

    def merged_with(self, other: "BeliefMap") -> "BeliefMap":
        """Per cell, ``other``'s entry where it is better than this map's.

        Better means strictly fresher, or equally fresh with fewer relays (higher
        confidence). Returns this map (unchanged) or a new one; never ``other`` itself.
        """
        n = max(self.n_cells, other.n_cells)
        mine, theirs = self.sized(n), other.sized(n)
        better = (theirs.year > mine.year) | (
            (theirs.year == mine.year) & (theirs.hops < mine.hops)
        )
        if not better.any():
            return mine
        return BeliefMap(
            np.where(better, theirs.year, mine.year),
            np.where(better, theirs.food_kcal, mine.food_kcal),
            np.where(better, theirs.population, mine.population),
            np.where(better, theirs.hops, mine.hops),
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
    # Prior for food beliefs from this year's direct observations (log kcal per cell): mean,
    # and the estimated true between-cell variance tau^2 (observed variance minus noise).
    food_log_prior: float = math.nan
    food_log_signal_var: float = 0.0
    report_cells: IntArray = field(
        default_factory=lambda: np.zeros(0, dtype=np.int64)
    )  # cells last received as social reports (candidates for relaying)
    recent_residence: dict[int, int] = field(default_factory=dict)  # cell -> last year lived there
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

    def note_residence(self, cell: int, year: int, memory_years: int) -> None:
        """Record living in ``cell`` this year; forget residences beyond the memory horizon."""
        self.recent_residence[cell] = year
        if len(self.recent_residence) > memory_years:
            horizon = year - memory_years
            self.recent_residence = {c: y for c, y in self.recent_residence.items() if y > horizon}

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
