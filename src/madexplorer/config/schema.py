"""Typed scenario configuration (spec §3, §22).

Units are encoded in field-name suffixes: ``_km``, ``_m``, ``_c`` (Celsius),
``_mm`` (per year), ``_deg``, ``_years``, ``_kcal``. World, climate and ecology
fields carry documented defaults; species parameters never do.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from madexplorer.config.base import FrozenModel


class SimulationConfig(FrozenModel):
    """Time horizon and stochastic seed."""

    start_year: int = 0
    n_years: int = Field(default=500, ge=1)
    timestep_years: Literal[1] = 1  # MVP 1 supports annual steps only
    seed: int = Field(default=0, ge=0)


class TopologyConfig(FrozenModel):
    """Procedural grid topology. ``seed`` is the world seed, independent of the run seed."""

    seed: int = Field(default=0, ge=0)
    width: int = Field(default=64, ge=4, le=1024)
    height: int = Field(default=64, ge=4, le=1024)
    cell_size_km: float = Field(default=10.0, gt=0)
    sea_fraction: float = Field(default=0.3, ge=0, lt=1)
    max_elevation_m: float = Field(default=3000.0, gt=0)
    elevation_spectral_exponent: float = Field(default=3.0, gt=0)
    river_threshold_cells: int = Field(default=40, ge=1)
    water_access_distance_scale_km: float = Field(default=20.0, gt=0)
    rainfall_surface_water_mm: float = Field(default=1500.0, gt=0)


class ClimateConfig(FrozenModel):
    """Base climate fields and interannual variability."""

    latitude_range_deg: tuple[float, float] = (10.0, 50.0)
    equator_sea_level_temp_c: float = 27.0
    latitude_temp_gradient_c_per_deg: float = 0.4
    lapse_rate_c_per_km: float = 6.5
    mean_rainfall_mm: float = Field(default=900.0, gt=0)
    rainfall_spatial_sigma: float = Field(default=0.35, ge=0)
    coastal_moisture_scale_km: float = Field(default=300.0, gt=0)
    temp_anomaly_sd_c: float = Field(default=0.5, ge=0)
    temp_anomaly_persistence: float = Field(default=0.6, ge=0, lt=1)
    rainfall_anomaly_sd: float = Field(default=0.15, ge=0)
    rainfall_anomaly_persistence: float = Field(default=0.5, ge=0, lt=1)
    rainfall_regional_anomaly_sd: float = Field(default=0.15, ge=0)
    temp_trend_c_per_century: float = 0.0


class WorldConfig(FrozenModel):
    """Physical world: topology plus climate."""

    topology: TopologyConfig = TopologyConfig()
    climate: ClimateConfig = ClimateConfig()


class EcologyConfig(FrozenModel):
    """Plant and game food resources derived from net primary productivity."""

    npp_energy_kcal_per_g: float = Field(default=4.0, gt=0)
    plant_edible_fraction: float = Field(default=2e-4, ge=0)
    game_edible_fraction: float = Field(default=5e-5, ge=0)
    plant_regrowth_rate_per_year: float = Field(default=1.5, ge=0)
    game_regrowth_rate_per_year: float = Field(default=0.4, ge=0)
    recolonization_fraction: float = Field(default=0.01, ge=0, le=1)
    vegetation_half_saturation_npp_g_m2: float = Field(default=800.0, gt=0)
    soil_fertility_range: tuple[float, float] = (0.6, 1.2)


class AgricultureConfig(FrozenModel):
    """Crop ecology and cultivation labor requirements (spec §4.5)."""

    crop_max_yield_kcal_per_ha: float = Field(default=2.0e6, ge=0)
    crop_reference_npp_g_m2: float = Field(default=1400.0, gt=0)
    cultivation_hours_per_ha: float = Field(default=600.0, gt=0)
    clearing_hours_per_ha: float = Field(default=150.0, ge=0)
    clearing_vegetation_multiplier: float = Field(default=8.0, ge=0)
    arable_slope_limit: float = Field(default=0.15, gt=0)
    max_arable_fraction: float = Field(default=0.3, ge=0, le=1)
    soil_depletion_rate: float = Field(default=0.08, ge=0)  # per year, cultivated land
    soil_cultivated_recovery_rate: float = Field(default=0.02, ge=0)  # natural inputs, cultivated
    soil_recovery_rate: float = Field(default=0.05, ge=0)  # per year, fallow
    wild_plant_displacement: float = Field(default=1.0, ge=0, le=1)
    wild_game_displacement: float = Field(default=0.5, ge=0, le=1)


class TradeConfig(FrozenModel):
    """Food exchange between nearby groups (spec §9, §11.5)."""

    transport_decay_km: float = Field(default=60.0, gt=0)
    tie_persistence: float = Field(default=0.7, ge=0, le=1)


class ResolutionConfig(FrozenModel):
    """Adaptive resolution: coarsening of similar co-located units (spec §6.2, §6.5)."""

    max_units_per_cell: int = Field(default=3, ge=1)
    max_knowledge_distance: float = Field(default=1.0, ge=0)


class SpeciesRef(FrozenModel):
    """A species used in the scenario: a profile file plus optional parameter overrides."""

    id: str
    profile: str
    overrides: dict[str, object] = Field(default_factory=dict)


class InitialPopulation(FrozenModel):
    """A founding population seed."""

    species: str
    cell: tuple[int, int]  # (x, y) grid coordinates
    population: int = Field(ge=1)
    age_structure: Literal["stationary"] = "stationary"
    initial_reserve_fraction: float = Field(default=0.8, ge=0, le=1)
    initial_knowledge: dict[str, float] = Field(default_factory=dict)
    technologies: tuple[str, ...] = ()


class MechanismsConfig(FrozenModel):
    """Switches for ablation studies (spec §25.3)."""

    climate_variability: bool = True
    starvation_mortality: bool = True
    knowledge_sharing: bool = True
    fission: bool = True
    fusion: bool = True
    migration: bool = True
    # MVP 2
    cultivation: bool = True
    storage: bool = True
    trade: bool = True
    knowledge_learning: bool = True
    knowledge_diffusion: bool = True
    innovation: bool = True
    aggregation: bool = True
    # MVP 2 cleanup
    crowding_mortality: bool = True
    # MVP 2 stabilization: shrink single noisy direct observations toward the prior by
    # precision (tau^2 / (tau^2 + sigma^2)); relayed reports are always shrunk.
    direct_observation_shrinkage: bool = True


class OutputConfig(FrozenModel):
    """What gets recorded."""

    spatial_snapshot_interval_years: int = Field(default=10, ge=1)
    log_migrations: bool = True
    trace_units: tuple[str, ...] = ()


class DebugConfig(FrozenModel):
    """Runtime integrity checking."""

    check_invariants: bool = True


class ScenarioConfig(FrozenModel):
    """Complete, versionable definition of a simulation run (together with species files)."""

    name: str
    description: str = ""
    simulation: SimulationConfig = SimulationConfig()
    world: WorldConfig = WorldConfig()
    ecology: EcologyConfig = EcologyConfig()
    agriculture: AgricultureConfig = AgricultureConfig()
    trade: TradeConfig = TradeConfig()
    resolution: ResolutionConfig = ResolutionConfig()
    knowledge_system: str | None = None  # path to a knowledge-system file, relative to the scenario
    species: tuple[SpeciesRef, ...] = Field(min_length=1)
    initial_populations: tuple[InitialPopulation, ...] = Field(min_length=1)
    mechanisms: MechanismsConfig = MechanismsConfig()
    output: OutputConfig = OutputConfig()
    debug: DebugConfig = DebugConfig()

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        ids = [ref.id for ref in self.species]
        if len(ids) != len(set(ids)):
            raise ValueError("species ids must be unique")
        topology = self.world.topology
        for seed in self.initial_populations:
            if seed.species not in ids:
                raise ValueError(f"initial population references unknown species {seed.species!r}")
            x, y = seed.cell
            if not (0 <= x < topology.width and 0 <= y < topology.height):
                raise ValueError(f"initial population cell {seed.cell} is outside the grid")
        return self
