"""Practiced foraging familiarity per cell (learning by doing, spec §4.4).

Familiarity is a group's practiced competence at extracting food from one cell's ecology.
It is not knowledge that the place exists or of what it holds: that lives in the belief
system (:class:`~madexplorer.population.unit.BeliefMap`), so a group can return to a valley
it knows well while foraging there no better than newcomers until it relearns it.

With ``mechanisms.familiarity_decay`` on, competence that is not practiced decays smoothly
toward the level of an unknown cell, with the species' memory timescale; it is evaluated
lazily from the stored value and the last year practiced. Merges take population-weighted
means of the values decayed to the merge year. With the switch off, the pre-reform rules
apply exactly: no decay, and a merge keeps the maximum per cell.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from madexplorer.core.governance import model_rule

if TYPE_CHECKING:
    from madexplorer.config.schema import MechanismsConfig
    from madexplorer.species.profile import SpeciesProfile

# Implementation threshold, not a model parameter: when entries are materialized (merge,
# split), one within this distance of the baseline is dropped, because a missing entry
# already means the baseline. The foraging effect of the difference is below 1e-5 relative.
REPRESENTATION_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class FamiliarityRule:
    """Species-level familiarity semantics for one run."""

    baseline: float  # familiarity with an unknown cell (F0)
    time_constant_years: float | None  # decay timescale; None = pre-reform rules

    @property
    def decays(self) -> bool:
        """Whether unpracticed familiarity decays (and merges are population-weighted)."""
        return self.time_constant_years is not None


def familiarity_rule(profile: "SpeciesProfile", mechanisms: "MechanismsConfig") -> FamiliarityRule:
    """The rule for ``profile``: F0 = initial familiarity, tau = the memory horizon."""
    cognition = profile.cognition
    return FamiliarityRule(
        baseline=cognition.initial_familiarity,
        time_constant_years=float(cognition.memory_years) if mechanisms.familiarity_decay else None,
    )


@model_rule(
    name="familiarity_decay",
    version="1.0",
    rationale=(
        "Practical competence at exploiting a particular landscape fades when the group stops "
        "using it: members who practiced it die or forget, and the ecology changes. Excess "
        "familiarity above the unknown-cell level decays exponentially with the years the "
        "cell goes unpracticed, on the species' memory timescale (no new timescale)."
    ),
    source_type="heuristic",
    parameters=("initial_familiarity", "memory_years"),
    expected_domain="[initial_familiarity, 1]; unchanged while practiced every year",
    known_limitations=(
        "One value per group and cell: heterogeneous skill inside a merged unit is averaged "
        "(MVP 3 strata could keep it). Knowledge diffusion does not transmit familiarity."
    ),
)
def decayed_familiarity(
    stored: float, idle_years: float, baseline: float, time_constant_years: float
) -> float:
    """``F0 + (F - F0) exp(-idle / tau)``; ``idle`` counts years without practice."""
    if idle_years <= 0:
        return stored
    return baseline + (stored - baseline) * math.exp(-idle_years / time_constant_years)


def idle_years(last_practiced: int, year: int) -> int:
    """Years without practice before ``year``: foraging a cell every year is never idle."""
    return max(year - last_practiced - 1, 0)


class FamiliarityMap:
    """Stored familiarity and last-practiced year per cell (absent cell = baseline)."""

    __slots__ = ("_value", "_year")

    def __init__(
        self, values: dict[int, float] | None = None, years: dict[int, int] | None = None
    ) -> None:
        self._value: dict[int, float] = values if values is not None else {}
        self._year: dict[int, int] = years if years is not None else {}

    def __len__(self) -> int:
        return len(self._value)

    def __contains__(self, cell: object) -> bool:
        return cell in self._value

    def cells(self) -> list[int]:
        """Cells with a stored entry."""
        return list(self._value)

    def stored(self, cell: int) -> tuple[float, int] | None:
        """The stored value and last-practiced year of ``cell`` (None if absent)."""
        value = self._value.get(cell)
        return None if value is None else (value, self._year[cell])

    def effective(self, cell: int, year: int, rule: FamiliarityRule) -> float:
        """Familiarity with ``cell`` in ``year``, decayed for the years it went unpracticed."""
        value = self._value.get(cell)
        if value is None:
            return rule.baseline
        if rule.time_constant_years is None:
            return value
        idle = idle_years(self._year[cell], year)
        return decayed_familiarity(value, idle, rule.baseline, rule.time_constant_years)

    def practice(self, cell: int, year: int, learning_rate: float, rule: FamiliarityRule) -> None:
        """A year of foraging in ``cell``: learn from the current (decayed) level."""
        known = self.effective(cell, year, rule)
        self._value[cell] = known + learning_rate * (1.0 - known)
        self._year[cell] = year

    def _materialized_year(self, cell: int, year: int) -> int:
        # The stamp that keeps the idle clock unchanged once the decay through `year` is
        # folded into the value: the next unpracticed year still counts as idle.
        return max(self._year[cell], year - 1)

    def materialized(self, year: int, rule: FamiliarityRule) -> "FamiliarityMap":
        """An independent copy with decay folded in as of ``year`` (used on fission)."""
        if not rule.decays:
            return FamiliarityMap(dict(self._value), dict(self._year))
        values: dict[int, float] = {}
        years: dict[int, int] = {}
        for cell in self._value:
            value = self.effective(cell, year, rule)
            if abs(value - rule.baseline) >= REPRESENTATION_EPSILON:
                values[cell] = value
                years[cell] = self._materialized_year(cell, year)
        return FamiliarityMap(values, years)

    def merge(
        self,
        other: "FamiliarityMap",
        n_self: int,
        n_other: int,
        year: int,
        rule: FamiliarityRule,
    ) -> None:
        """Fold ``other`` into this map (population-weighted, or maximum without decay)."""
        if not rule.decays:
            for cell, value in other._value.items():
                self._value[cell] = max(value, self._value.get(cell, 0.0))
                self._year[cell] = max(other._year[cell], self._year.get(cell, other._year[cell]))
            return
        total = n_self + n_other
        values: dict[int, float] = {}
        years: dict[int, int] = {}
        for cell in self._value.keys() | other._value.keys():
            a = self.effective(cell, year, rule)
            b = other.effective(cell, year, rule)
            value = (a * n_self + b * n_other) / total if total else a
            if abs(value - rule.baseline) < REPRESENTATION_EPSILON:
                continue
            values[cell] = value
            years[cell] = max(
                source._materialized_year(cell, year)
                for source in (self, other)
                if cell in source._value
            )
        self._value, self._year = values, years
