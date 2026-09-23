"""Procedural world generation from a world seed."""

import numpy as np

from madexplorer.config.schema import EcologyConfig, WorldConfig
from madexplorer.core.types import FloatArray
from madexplorer.ecology.resources import miami_npp, vegetation_density
from madexplorer.world.climate import base_rainfall, base_temperature, spectral_noise
from madexplorer.world.grid import NeighborGraph, WorldGrid, build_neighbor_table
from madexplorer.world.hydrology import fill_depressions, flow_accumulation, freshwater_access


def _distance_from(mask: np.ndarray, graph: NeighborGraph, n_cells: int) -> FloatArray:
    """Grid distance (km) from any cell in ``mask``; inf if mask is empty."""
    sources = np.flatnonzero(mask).tolist()
    if not sources:
        return np.full(n_cells, np.inf)
    costs = graph.shortest_costs(sources, [1.0] * n_cells)
    distance = np.full(n_cells, np.inf)
    distance[list(costs)] = list(costs.values())
    return distance


def _rescale_uniform(field: FloatArray, low: float, high: float) -> FloatArray:
    """Map a field to ``[low, high]`` by rank (uniform marginal)."""
    ranks = np.argsort(np.argsort(field, kind="stable"), kind="stable")
    rescaled: FloatArray = low + (high - low) * ranks / max(field.size - 1, 1)
    return rescaled


def generate_world(world: WorldConfig, ecology: EcologyConfig) -> WorldGrid:
    """Build a world deterministically from ``world.topology.seed``."""
    topo, climate = world.topology, world.climate
    rng = np.random.default_rng(np.random.SeedSequence([topo.seed, 0x574F524C44]))  # "WORLD"
    h, w = topo.height, topo.width
    n = h * w
    neighbor_index, neighbor_distance = build_neighbor_table(w, h, topo.cell_size_km)
    graph = NeighborGraph(neighbor_index, neighbor_distance)

    # Topography: sea level at the requested quantile; land relief concave above it.
    z = spectral_noise(rng, h, w, topo.elevation_spectral_exponent).ravel()
    sea_level = np.quantile(z, topo.sea_fraction) if topo.sea_fraction > 0 else z.min() - 1.0
    is_water = z < sea_level
    relief = np.clip((z - sea_level) / (z.max() - sea_level), 0.0, 1.0)
    elevation = np.where(is_water, 0.0, topo.max_elevation_m * relief**1.5)
    grad_y, grad_x = np.gradient(elevation.reshape(h, w), topo.cell_size_km * 1000.0)
    slope = np.hypot(grad_x, grad_y).ravel()

    # Hydrology.
    routing_elevation = fill_depressions(elevation, is_water, neighbor_index)
    accumulation = flow_accumulation(routing_elevation, is_water, neighbor_index)
    is_river = (~is_water) & (accumulation >= topo.river_threshold_cells)
    distance_to_river = _distance_from(is_river, graph, n)
    distance_to_ocean = _distance_from(is_water, graph, n)
    ocean_for_climate = np.where(np.isinf(distance_to_ocean), 1e6, distance_to_ocean)

    # Climate. Row 0 is the poleward (northern) edge so printed maps have north up.
    lat_south, lat_north = climate.latitude_range_deg
    rows = np.arange(n) // w
    latitude = lat_north + (lat_south - lat_north) * rows / max(h - 1, 1)
    temperature = base_temperature(latitude, elevation, climate)
    rain_noise = spectral_noise(rng, h, w, exponent=2.5).ravel()
    rainfall = base_rainfall(rain_noise, ocean_for_climate, (~is_water).astype(float), climate)
    water_access = freshwater_access(
        distance_to_river,
        rainfall,
        is_water,
        topo.water_access_distance_scale_km,
        topo.rainfall_surface_water_mm,
    )

    # Soil and vegetation.
    soil_noise = spectral_noise(rng, h, w, exponent=2.0).ravel()
    low, high = ecology.soil_fertility_range
    soil = _rescale_uniform(soil_noise, low, high) * np.exp(-slope / 0.5)
    npp = np.where(is_water, 0.0, miami_npp(temperature, rainfall) * soil)
    vegetation = vegetation_density(npp, ecology.vegetation_half_saturation_npp_g_m2)

    return WorldGrid(
        width=w,
        height=h,
        cell_size_km=topo.cell_size_km,
        elevation_m=elevation,
        slope=slope,
        is_water=is_water,
        flow_accumulation=accumulation,
        is_river=is_river,
        distance_to_ocean_km=distance_to_ocean,
        water_access=water_access,
        latitude_deg=latitude,
        base_temperature_c=temperature,
        base_rainfall_mm=rainfall,
        soil_fertility=soil,
        base_npp_g_m2=npp,
        vegetation_density=vegetation,
        neighbor_index=neighbor_index,
        neighbor_distance_km=neighbor_distance,
    )
