"""The :class:`SpeciesProfile` (spec §5).

Humanity is one profile loaded from ``species/human.yaml``; no species
parameter has a default in code, so every biological or behavioral assumption
is visible in a versioned parameter file.

MVP 1 implements the trait groups the ecological-demographic sandbox uses.
Physiology distributions, social psychology distributions, and manipulation /
niche-construction traits arrive with the subsystems that consume them.
"""

from typing import Self

from pydantic import Field, model_validator

from madexplorer.config.base import FrozenModel


class LifeHistory(FrozenModel):
    """Survival, maturation and reproduction schedules."""

    max_age_years: int = Field(ge=2, le=2000)
    maturation_age_years: int = Field(ge=1)
    # Siler competing-hazards mortality: a1*exp(-b1*age) + a2 + a3*exp(b3*age), per year.
    siler_juvenile_a1: float = Field(ge=0)
    siler_juvenile_b1: float = Field(ge=0)
    siler_baseline_a2: float = Field(ge=0)
    siler_senescent_a3: float = Field(ge=0)
    siler_senescent_b3: float = Field(ge=0)
    fertility_onset_years: int = Field(ge=1)
    fertility_end_years: int = Field(ge=2)
    fertility_shape_p: float = Field(gt=0)
    fertility_shape_q: float = Field(gt=0)
    total_fertility_rate: float = Field(gt=0)
    offspring_per_birth: int = Field(ge=1)
    male_birth_fraction: float = Field(ge=0, le=1)
    sexual_reproduction: bool
    male_fertility_end_years: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_ages(self) -> Self:
        if not self.fertility_onset_years < self.fertility_end_years <= self.max_age_years:
            raise ValueError("require fertility_onset < fertility_end <= max_age")
        if self.maturation_age_years >= self.max_age_years:
            raise ValueError("maturation_age_years must be below max_age_years")
        return self


class Metabolism(FrozenModel):
    """Energy requirements, reserves, and nutritional sensitivity."""

    adult_daily_kcal: float = Field(gt=0)
    newborn_need_fraction: float = Field(gt=0, le=1)
    reserve_days_max: float = Field(ge=0)
    starvation_mortality_sensitivity: float = Field(ge=0)
    starvation_vulnerable_multiplier: float = Field(ge=0)
    vulnerable_child_age_years: int = Field(ge=0)
    vulnerable_elder_age_years: int = Field(ge=0)
    fertility_food_midpoint: float = Field(gt=0)
    fertility_food_scale: float = Field(gt=0)
    comfort_temp_low_c: float
    comfort_temp_high_c: float
    cold_cost_per_c: float = Field(ge=0)
    heat_cost_per_c: float = Field(ge=0)


class Movement(FrozenModel):
    """Locomotion capabilities and terrain sensitivity."""

    annual_relocation_range_km: float = Field(gt=0)
    can_swim: bool
    can_fly: bool
    slope_friction_coefficient: float = Field(ge=0)
    vegetation_friction_coefficient: float = Field(ge=0)
    water_friction: float = Field(ge=1)
    flight_terrain_factor: float = Field(ge=0, le=1)
    travel_kcal_per_km: float = Field(ge=0)


class Cognition(FrozenModel):
    """Perception, memory, and learning (no single intelligence scalar)."""

    perception_radius_km: float = Field(gt=0)
    vegetation_occlusion: float = Field(ge=0, le=1)
    observation_noise_sigma: float = Field(ge=0)
    memory_years: int = Field(ge=1)
    familiarity_learning_rate: float = Field(ge=0, le=1)
    initial_familiarity: float = Field(gt=0, le=1)


class Foraging(FrozenModel):
    """Harvest technology-free returns and labor supply."""

    plant_return_kcal_per_hour: float = Field(ge=0)
    game_return_kcal_per_hour: float = Field(ge=0)
    plant_canopy_access_penalty: float = Field(ge=0, le=1)
    game_search_vegetation_penalty: float = Field(ge=0, le=1)
    foraging_hours_per_day: float = Field(ge=0, le=24)
    labor_onset_age_years: int = Field(ge=0)
    labor_decline_age_years: int = Field(ge=0)
    elder_labor_fraction: float = Field(ge=0, le=1)
    surplus_target: float = Field(ge=0)


class SocialBehavior(FrozenModel):
    """Group fission/fusion and information-sharing hypotheses."""

    reference_group_size: float = Field(gt=0)
    fission_baseline_logit: float
    fission_size_weight: float
    fission_food_stress_weight: float
    fission_fraction_min: float = Field(gt=0, lt=1)
    fission_fraction_max: float = Field(gt=0, lt=1)
    fusion_baseline_logit: float
    fusion_small_group_weight: float
    fusion_mate_shortage_weight: float
    knowledge_sharing_probability: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _check_fraction(self) -> Self:
        if self.fission_fraction_min > self.fission_fraction_max:
            raise ValueError("fission_fraction_min must not exceed fission_fraction_max")
        return self


class MigrationBehavior(FrozenModel):
    """Weights of the perceived-utility migration model (spec §10.2)."""

    food_weight: float
    water_weight: float
    movement_cost_weight: float
    movement_reference_km: float = Field(gt=0)
    uncertainty_weight: float
    perception_noise: float = Field(ge=0)
    inertia: float
    decisiveness: float = Field(ge=0)
    food_ratio_cap: float = Field(gt=0)


class SpeciesProfile(FrozenModel):
    """Complete description of one intelligent species."""

    id: str
    name: str
    life_history: LifeHistory
    metabolism: Metabolism
    movement: Movement
    cognition: Cognition
    foraging: Foraging
    social: SocialBehavior
    migration: MigrationBehavior
