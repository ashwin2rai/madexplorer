"""Surface hydrology: depression filling, D8 flow accumulation, rivers, and freshwater access."""

import heapq

import numpy as np

from madexplorer.core.governance import model_rule
from madexplorer.core.types import BoolArray, FloatArray, IntArray


@model_rule(
    name="priority_flood_fill",
    version="1.0",
    rationale=(
        "Fill closed depressions so every land cell drains to the sea or the map edge "
        "(priority-flood with epsilon gradient, Barnes et al. 2014)."
    ),
    source_type="theoretical",
    expected_domain="filled elevation >= original elevation",
    known_limitations="Removes lakes entirely instead of representing them as water bodies.",
)
def fill_depressions(
    elevation_m: FloatArray, is_water: BoolArray, neighbor_index: IntArray, epsilon_m: float = 1e-3
) -> FloatArray:
    """Hydrologically conditioned elevation used only for flow routing."""
    filled = elevation_m.copy()
    done = np.zeros(elevation_m.size, dtype=bool)
    heap: list[tuple[float, int]] = []
    border = (neighbor_index < 0).any(axis=1)
    for start in np.flatnonzero(is_water | border).tolist():
        heap.append((float(filled[start]), start))
        done[start] = True
    heapq.heapify(heap)
    neighbors_of = neighbor_index.tolist()
    while heap:
        level, cell = heapq.heappop(heap)
        for neighbor in neighbors_of[cell]:
            if neighbor < 0 or done[neighbor]:
                continue
            done[neighbor] = True
            filled[neighbor] = max(filled[neighbor], level + epsilon_m)
            heapq.heappush(heap, (float(filled[neighbor]), neighbor))
    return filled


@model_rule(
    name="d8_flow_accumulation",
    version="1.0",
    rationale=(
        "Each land cell drains to its lowest neighbor; rivers form where drainage area is large."
    ),
    source_type="theoretical",
    parameters=("river_threshold_cells",),
    expected_domain="counts of upstream land cells, >= 1 on land",
    known_limitations=(
        "Expects depression-filled elevation; no evaporation, infiltration, or rainfall weighting."
    ),
)
def flow_accumulation(
    elevation_m: FloatArray, is_water: BoolArray, neighbor_index: IntArray
) -> FloatArray:
    """Number of land cells (including itself) whose flow passes through each land cell."""
    accumulation = np.where(is_water, 0.0, 1.0)
    for cell in np.argsort(-elevation_m, kind="stable"):
        if is_water[cell]:
            continue
        neighbors = neighbor_index[cell]
        neighbors = neighbors[neighbors >= 0]
        lower = neighbors[elevation_m[neighbors] < elevation_m[cell]]
        if lower.size == 0:
            continue
        target = lower[np.argmin(elevation_m[lower])]
        if not is_water[target]:
            accumulation[target] += accumulation[cell]
    return accumulation


@model_rule(
    name="freshwater_access",
    version="1.0",
    rationale=(
        "Drinking water comes from rivers (decaying with distance) or from local surface water "
        "that increases with rainfall; the better source dominates."
    ),
    source_type="heuristic",
    parameters=("water_access_distance_scale_km", "rainfall_surface_water_mm"),
    expected_domain="[0, 1]; 0 on sea cells",
    known_limitations="Seasonal drying, lakes, springs, and wells are not modeled.",
)
def freshwater_access(
    distance_to_river_km: FloatArray,
    rainfall_mm: FloatArray,
    is_water: BoolArray,
    distance_scale_km: float,
    rainfall_scale_mm: float,
) -> FloatArray:
    """Freshwater access index per cell."""
    river = np.exp(-distance_to_river_km / distance_scale_km)
    surface = 1.0 - np.exp(-rainfall_mm / rainfall_scale_mm)
    access: FloatArray = np.where(is_water, 0.0, np.maximum(river, surface))
    return access
