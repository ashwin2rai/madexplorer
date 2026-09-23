"""Base climate fields and stochastic interannual variation (spec §3.1, §4.2)."""

from dataclasses import dataclass

import numpy as np

from madexplorer.config.schema import ClimateConfig
from madexplorer.core.governance import model_rule
from madexplorer.core.types import FloatArray
from madexplorer.world.grid import WorldGrid


def spectral_noise(
    rng: np.random.Generator, height: int, width: int, exponent: float
) -> FloatArray:
    """Standardized 2-D random field with power spectrum proportional to ``f**-exponent``.

    Larger exponents give smoother fields. The field is periodic at the edges.
    """
    white = rng.standard_normal((height, width))
    spectrum = np.fft.rfft2(white)
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.rfftfreq(width)[None, :]
    frequency = np.sqrt(fx**2 + fy**2)
    frequency[0, 0] = 1.0
    spectrum *= frequency ** (-exponent / 2.0)
    spectrum[0, 0] = 0.0
    field = np.fft.irfft2(spectrum, s=(height, width))
    std = field.std()
    standardized: FloatArray = (field - field.mean()) / (std if std > 0 else 1.0)
    return standardized


@model_rule(
    name="base_temperature",
    version="1.0",
    rationale=(
        "Temperature falls with absolute latitude and with elevation (environmental lapse rate)."
    ),
    source_type="empirical",
    parameters=(
        "equator_sea_level_temp_c",
        "latitude_temp_gradient_c_per_deg",
        "lapse_rate_c_per_km",
    ),
    expected_domain="mean annual temperature, Celsius",
    known_limitations="No ocean currents, continentality, or rain shadows.",
)
def base_temperature(
    latitude_deg: FloatArray, elevation_m: FloatArray, config: ClimateConfig
) -> FloatArray:
    """Mean annual temperature under the base climate."""
    temperature: FloatArray = (
        config.equator_sea_level_temp_c
        - config.latitude_temp_gradient_c_per_deg * np.abs(latitude_deg)
        - config.lapse_rate_c_per_km * elevation_m / 1000.0
    )
    return temperature


@model_rule(
    name="base_rainfall",
    version="1.0",
    rationale=(
        "Rainfall is a lognormal spatial field modulated by distance from the ocean moisture "
        "source."
    ),
    source_type="heuristic",
    parameters=("mean_rainfall_mm", "rainfall_spatial_sigma", "coastal_moisture_scale_km"),
    expected_domain="annual rainfall, mm; land mean equals mean_rainfall_mm",
    known_limitations="No orographic lift or prevailing-wind rain shadows.",
)
def base_rainfall(
    noise: FloatArray, distance_to_ocean_km: FloatArray, land: FloatArray, config: ClimateConfig
) -> FloatArray:
    """Mean annual rainfall under the base climate. ``land`` is a 0/1 weight for normalization."""
    sigma = config.rainfall_spatial_sigma
    field = np.exp(sigma * noise - 0.5 * sigma**2)
    field *= 0.5 + 0.5 * np.exp(-distance_to_ocean_km / config.coastal_moisture_scale_km)
    land_mean = (field * land).sum() / max(land.sum(), 1.0)
    rainfall: FloatArray = config.mean_rainfall_mm * field / land_mean
    return rainfall


@dataclass(frozen=True, eq=False)
class ClimateYear:
    """Realized climate for one year plus the anomaly state carried to the next."""

    temperature_c: FloatArray
    rainfall_mm: FloatArray
    temp_anomaly_c: float
    log_rain_anomaly: float

    @classmethod
    def base(cls, world: WorldGrid) -> "ClimateYear":
        """The unperturbed base climate."""
        return cls(world.base_temperature_c, world.base_rainfall_mm, 0.0, 0.0)


@model_rule(
    name="interannual_climate_variation",
    version="1.0",
    rationale=(
        "Global temperature and rainfall anomalies follow AR(1) processes, plus an independent "
        "low-frequency regional rainfall field each year (droughts and wet spells)."
    ),
    source_type="heuristic",
    parameters=(
        "temp_anomaly_sd_c",
        "temp_anomaly_persistence",
        "rainfall_anomaly_sd",
        "rainfall_anomaly_persistence",
        "rainfall_regional_anomaly_sd",
        "temp_trend_c_per_century",
    ),
    expected_domain="annual fields; rainfall stays positive",
    known_limitations="No seasonality within the annual step; regional anomalies lack persistence.",
)
def next_climate_year(
    previous: ClimateYear,
    world: WorldGrid,
    config: ClimateConfig,
    years_elapsed: int,
    rng: np.random.Generator,
    variability: bool,
) -> ClimateYear:
    """Draw the next year's climate."""
    trend = config.temp_trend_c_per_century * years_elapsed / 100.0
    if not variability:
        return ClimateYear(world.base_temperature_c + trend, world.base_rainfall_mm, 0.0, 0.0)
    phi_t, phi_p = config.temp_anomaly_persistence, config.rainfall_anomaly_persistence
    temp_anomaly = (
        phi_t * previous.temp_anomaly_c
        + config.temp_anomaly_sd_c * np.sqrt(1 - phi_t**2) * rng.standard_normal()
    )
    log_rain = (
        phi_p * previous.log_rain_anomaly
        + config.rainfall_anomaly_sd * np.sqrt(1 - phi_p**2) * rng.standard_normal()
    )
    regional_sd = config.rainfall_regional_anomaly_sd
    regional = spectral_noise(rng, world.height, world.width, exponent=4.0).ravel() * regional_sd
    rain_multiplier = np.exp(log_rain + regional - 0.5 * regional_sd**2)
    return ClimateYear(
        temperature_c=world.base_temperature_c + trend + temp_anomaly,
        rainfall_mm=world.base_rainfall_mm * rain_multiplier,
        temp_anomaly_c=float(temp_anomaly),
        log_rain_anomaly=float(log_rain),
    )
