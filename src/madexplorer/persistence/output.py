"""Run output layout.

``<run_dir>/``
    ``manifest.json``      provenance (git commit, config hash, seed, versions)
    ``scenario.json``      fully resolved scenario including species profiles
    ``metrics.csv``        one row per simulated year
    ``events.jsonl``       event log with provenance, one JSON object per line
    ``spatial.npz``        ``years`` and ``population`` (years x height x width)
    ``world.npz``          static world layers (height x width each)
"""

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from madexplorer.core.simulation import SimulationResult

WORLD_LAYERS = (
    "elevation_m",
    "slope",
    "is_water",
    "is_river",
    "water_access",
    "latitude_deg",
    "base_temperature_c",
    "base_rainfall_mm",
    "soil_fertility",
    "base_npp_g_m2",
    "vegetation_density",
)


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_run(result: "SimulationResult", directory: Path) -> Path:
    """Write all outputs of ``result`` into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps(result.manifest, indent=2, default=_json_default)
    )
    (directory / "scenario.json").write_text(json.dumps(result.scenario.to_dict(), indent=2))
    if result.metrics:
        with (directory / "metrics.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(result.metrics[0]))
            writer.writeheader()
            writer.writerows(result.metrics)
    with (directory / "events.jsonl").open("w") as handle:
        for event in result.events:
            handle.write(json.dumps(event.to_record(), default=_json_default) + "\n")
    world = result.world
    np.savez_compressed(
        directory / "spatial.npz",
        years=np.array(result.snapshot_years, dtype=np.int64),
        population=np.stack([world.as_grid(p) for p in result.population_snapshots]),
    )
    layers: dict[str, Any] = {name: world.as_grid(getattr(world, name)) for name in WORLD_LAYERS}
    np.savez_compressed(directory / "world.npz", **layers)
    return directory


def read_manifest(directory: Path) -> dict[str, Any]:
    """Load a run's manifest."""
    data: dict[str, Any] = json.loads((directory / "manifest.json").read_text())
    return data


def read_metrics(directory: Path) -> list[dict[str, float]]:
    """Load a run's metrics table."""
    with (directory / "metrics.csv").open() as handle:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]
