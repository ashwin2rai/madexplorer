"""Age-indexed life tables derived from a :class:`SpeciesProfile` (spec §5.3, §8).

All functions are pure. Arrays are indexed by completed age in years,
``0 .. max_age_years`` inclusive.
"""

from dataclasses import dataclass

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import FloatArray
from madexplorer.species.profile import Foraging, LifeHistory, Metabolism, SpeciesProfile


def ages(life_history: LifeHistory) -> FloatArray:
    """Completed ages ``0 .. max_age`` as floats."""
    return np.arange(life_history.max_age_years + 1, dtype=np.float64)


@model_rule(
    name="siler_mortality_hazard",
    version="1.0",
    rationale=(
        "Competing-hazards model with declining juvenile, constant adult, and rising "
        "senescent components; fits forager and pre-industrial life tables well."
    ),
    source_type="empirical",
    parameters=(
        "siler_juvenile_a1",
        "siler_juvenile_b1",
        "siler_baseline_a2",
        "siler_senescent_a3",
        "siler_senescent_b3",
    ),
    expected_domain="ages 0..max_age; hazards per year",
    known_limitations="Baseline only; starvation modifies it multiplicatively elsewhere.",
)
def siler_hazard(life_history: LifeHistory) -> FloatArray:
    """Annual mortality hazard at the midpoint of each age year."""
    a = ages(life_history) + 0.5
    lh = life_history
    hazard: FloatArray = (
        lh.siler_juvenile_a1 * np.exp(-lh.siler_juvenile_b1 * a)
        + lh.siler_baseline_a2
        + lh.siler_senescent_a3 * np.exp(lh.siler_senescent_b3 * a)
    )
    return hazard


def death_probability(hazard: FloatArray) -> FloatArray:
    """Convert a constant within-year hazard into an annual death probability."""
    probability: FloatArray = 1.0 - np.exp(-hazard)
    return probability


@model_rule(
    name="age_specific_fertility",
    version="1.0",
    rationale=(
        "Beta-shaped natural-fertility schedule between onset and end ages, scaled so the "
        "sum equals the total fertility rate of a well-nourished female surviving all ages."
    ),
    source_type="heuristic",
    parameters=(
        "fertility_onset_years",
        "fertility_end_years",
        "fertility_shape_p",
        "fertility_shape_q",
        "total_fertility_rate",
    ),
    expected_domain="probabilities of a birth event per female per year, in [0, 1]",
    known_limitations="Ignores birth spacing and parity effects within the annual step.",
)
def age_specific_fertility(life_history: LifeHistory) -> FloatArray:
    """Annual probability of a birth event per female, before nutritional modifiers."""
    lh = life_history
    a = ages(lh) + 0.5
    span = lh.fertility_end_years - lh.fertility_onset_years
    x = (a - lh.fertility_onset_years) / span
    inside = (x > 0) & (x < 1)
    shape = np.zeros_like(a)
    xi = x[inside]
    shape[inside] = xi ** (lh.fertility_shape_p - 1) * (1 - xi) ** (lh.fertility_shape_q - 1)
    births_per_event = lh.offspring_per_birth
    shape *= (lh.total_fertility_rate / births_per_event) / shape.sum()
    rates: FloatArray = np.clip(shape, 0.0, 1.0)
    return rates


def survivorship(life_history: LifeHistory) -> FloatArray:
    """Probability of surviving from birth to each completed age, ``l(a)``."""
    q = death_probability(siler_hazard(life_history))
    survival = np.ones_like(q)
    survival[1:] = np.cumprod(1.0 - q[:-1])
    return survival


def life_expectancy_at_birth(life_history: LifeHistory) -> float:
    """Period life expectancy at birth under baseline mortality."""
    survival = survivorship(life_history)
    q = death_probability(siler_hazard(life_history))
    # Deaths are assumed to occur mid-year on average.
    return float((survival * (1.0 - 0.5 * q)).sum())


@model_rule(
    name="energy_need_by_age",
    version="1.0",
    rationale="Energy requirement rises linearly from infancy to adult level at maturation.",
    source_type="heuristic",
    parameters=("newborn_need_fraction", "maturation_age_years", "adult_daily_kcal"),
    expected_domain="fraction of adult requirement, (0, 1]",
    known_limitations="No sex difference, pregnancy/lactation cost, or elderly decline yet.",
)
def need_fraction_by_age(life_history: LifeHistory, metabolism: Metabolism) -> FloatArray:
    """Fraction of the adult daily energy requirement needed at each age."""
    a = ages(life_history)
    ramp = np.clip(a / life_history.maturation_age_years, 0.0, 1.0)
    fraction: FloatArray = (
        metabolism.newborn_need_fraction + (1.0 - metabolism.newborn_need_fraction) * ramp
    )
    return fraction


@model_rule(
    name="labor_capacity_by_age",
    version="1.0",
    rationale=(
        "Foraging labor ramps up from onset age to full capacity at maturation and declines "
        "linearly after the decline age toward an elder floor."
    ),
    source_type="heuristic",
    parameters=(
        "labor_onset_age_years",
        "maturation_age_years",
        "labor_decline_age_years",
        "elder_labor_fraction",
    ),
    expected_domain="fraction of full adult labor, [0, 1]",
    known_limitations="Skill is not modeled separately from labor; no sexual division of labor.",
)
def labor_capacity_by_age(life_history: LifeHistory, foraging: Foraging) -> FloatArray:
    """Fraction of full adult foraging labor supplied at each age."""
    a = ages(life_history)
    onset, mature = foraging.labor_onset_age_years, life_history.maturation_age_years
    ramp = np.clip((a - onset) / max(mature - onset, 1), 0.0, 1.0)
    decline_span = max(life_history.max_age_years - foraging.labor_decline_age_years, 1)
    decline = np.clip((a - foraging.labor_decline_age_years) / decline_span, 0.0, 1.0)
    elder = 1.0 - (1.0 - foraging.elder_labor_fraction) * decline
    capacity: FloatArray = ramp * elder
    return capacity


def starvation_vulnerability(life_history: LifeHistory, metabolism: Metabolism) -> FloatArray:
    """Relative sensitivity of mortality to energy deficit by age (young and old are frailer)."""
    a = ages(life_history)
    vulnerable = (a < metabolism.vulnerable_child_age_years) | (
        a >= metabolism.vulnerable_elder_age_years
    )
    return np.where(vulnerable, metabolism.starvation_vulnerable_multiplier, 1.0)


def crowding_vulnerability(life_history: LifeHistory, profile: SpeciesProfile) -> FloatArray:
    """Age multiplier on the crowding hazard (same frail ages as for starvation)."""
    a = ages(life_history)
    metabolism = profile.metabolism
    vulnerable = (a < metabolism.vulnerable_child_age_years) | (
        a >= metabolism.vulnerable_elder_age_years
    )
    return np.where(vulnerable, profile.health.crowding_vulnerable_multiplier, 1.0)


@dataclass(frozen=True, eq=False)
class LifeTables:
    """Precomputed age schedules for one species."""

    hazard: FloatArray
    fertility: FloatArray
    need_fraction: FloatArray
    labor: FloatArray
    vulnerability: FloatArray
    crowding_vulnerability: FloatArray
    survivorship: FloatArray
    male_reproductive: FloatArray  # 1.0 where males can sire offspring
    female_reproductive: FloatArray  # 1.0 where females can conceive

    @classmethod
    def build(cls, profile: SpeciesProfile) -> "LifeTables":
        """Derive all age schedules from a species profile."""
        lh = profile.life_history
        a = ages(lh)
        fertility = age_specific_fertility(lh)
        male_ok = (a >= lh.maturation_age_years) & (a <= lh.male_fertility_end_years)
        return cls(
            hazard=siler_hazard(lh),
            fertility=fertility,
            need_fraction=need_fraction_by_age(lh, profile.metabolism),
            labor=labor_capacity_by_age(lh, profile.foraging),
            vulnerability=starvation_vulnerability(lh, profile.metabolism),
            crowding_vulnerability=crowding_vulnerability(lh, profile),
            survivorship=survivorship(lh),
            male_reproductive=male_ok.astype(np.float64),
            female_reproductive=(fertility > 0).astype(np.float64),
        )
