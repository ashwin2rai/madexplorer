"""The :class:`SpeciesProfile` (spec §5).

Humanity is one profile loaded from ``species/human.yaml``; no species
parameter has a default in code, so every biological or behavioral assumption
is visible in a versioned parameter file.

MVP 1-2 implement the trait groups the sandbox and early agriculture use.
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


class Health(FrozenModel):
    """Settlement health costs (a minimal precursor of the MVP 3 health system)."""

    crowding_mortality_per_log_contact: float = Field(ge=0)  # adult hazard per unit pressure
    crowding_reference_population: float = Field(gt=0)  # settled contacts at pressure log(2)
    sedentism_timescale_years: float = Field(gt=0)  # residence at which sedentism is 63%
    contact_radius_km: float = Field(gt=0)  # settlement-scale contact radius
    crowding_vulnerable_multiplier: float = Field(ge=0)  # children and elders vs adults


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
    carry_kcal_per_capita: float = Field(ge=0)  # stored food one individual can carry when moving


class Cognition(FrozenModel):
    """Perception, memory, and learning (no single intelligence scalar)."""

    perception_radius_km: float = Field(gt=0)
    vegetation_occlusion: float = Field(ge=0, le=1)
    observation_noise_sigma: float = Field(ge=0)
    memory_years: int = Field(ge=1)
    familiarity_learning_rate: float = Field(ge=0, le=1)
    initial_familiarity: float = Field(gt=0, le=1)
    learning_speed: float = Field(ge=0)  # multiplier on domain learning rates
    teaching_efficiency: float = Field(ge=0)  # multiplier on knowledge transmissibility
    knowledge_retention: float = Field(gt=0)  # divides domain decay rates
    invention_propensity: float  # additive logit shift on innovation hazards
    planning_horizon_years: int = Field(ge=1)  # horizon over which investments are weighed


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


class SubsistenceBehavior(FrozenModel):
    """How groups adjust cultivation effort (a behavioral hypothesis, spec §4.5)."""

    field_adjustment_rate: float = Field(ge=0, le=1)
    initial_plot_ha: float = Field(ge=0)
    return_comparison_margin: float  # farming must beat marginal foraging by this fraction
    max_farm_labor_share: float = Field(ge=0, le=1)


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
    food_sharing_propensity: float = Field(ge=0, le=1)  # share of surplus offered to neighbors

    @model_validator(mode="after")
    def _check_fraction(self) -> Self:
        if self.fission_fraction_min > self.fission_fraction_max:
            raise ValueError("fission_fraction_min must not exceed fission_fraction_max")
        return self


class SocialInformation(FrozenModel):
    """Bounded social transmission of geographic information (MVP 2 stabilization).

    One encounter passes a few reports, not a whole remembered map; each relay lowers the
    confidence the receiver places in a report (``decay ** hops``).
    """

    reports_per_interaction: int = Field(ge=1)  # reports a group passes per encounter
    max_report_age_years: int = Field(ge=0)  # older observations are not passed on
    transmission_confidence_decay: float = Field(gt=0, le=1)  # confidence factor per relay


class MigrationBehavior(FrozenModel):
    """Weights of the perceived-utility migration model (spec §10.2)."""

    food_weight: float
    water_weight: float
    movement_cost_weight: float
    movement_reference_km: float = Field(gt=0)
    uncertainty_weight: float
    inertia: float
    decisiveness: float = Field(ge=0)
    food_ratio_cap: float = Field(gt=0)
    abandoned_stores_weight: float = Field(ge=0)  # per year of need left behind when moving
    abandoned_fields_weight: float = Field(ge=0)  # per year of need of crop output forgone
    # Optional cap on destinations evaluated per year (nearest by path cost, utility-blind);
    # null = every reachable known cell (physical reachability is the bound).
    max_considered_destinations: int | None = Field(ge=2)


class SpeciesProfile(FrozenModel):
    """Complete description of one intelligent species."""

    id: str
    name: str
    life_history: LifeHistory
    metabolism: Metabolism
    health: Health
    movement: Movement
    cognition: Cognition
    foraging: Foraging
    subsistence: SubsistenceBehavior
    social: SocialBehavior
    social_information: SocialInformation
    migration: MigrationBehavior
