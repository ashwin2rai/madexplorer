"""Multi-seed ensembles: one summary row per run plus distribution statistics (spec §25).

Runs are independent, so they execute in separate processes (spec §27.6). Each
run is reduced to a row of milestones and end-state measures; milestones that a
run never reaches are NaN, and the aggregate reports how often each was reached.
Comparisons between model variants should reuse the same seeds (paired design).
"""

import csv
import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.provenance import run_manifest
from madexplorer.core.simulation import SimulationResult, Simulator

# Farming milestones: first year the farmed share of all food reaches each level.
FARM_SHARE_THRESHOLDS = (0.1, 0.25, 0.5)
QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
# Final-state averages use the last years of a run to smooth year-to-year noise.
TAIL_YEARS = 50

Row = dict[str, float | int]


def _first_year(
    metrics: Sequence[Mapping[str, float | int]], predicate: Callable[..., bool]
) -> float:
    for row in metrics:
        if predicate(row):
            return float(row["year"])
    return math.nan


def _tail_mean(metrics: Sequence[Mapping[str, float | int]], key: str) -> float:
    values = [float(r[key]) for r in metrics[-TAIL_YEARS:] if not math.isnan(float(r[key]))]
    return float(np.mean(values)) if values else math.nan


def summarize_run(result: SimulationResult, seed: int) -> Row:
    """Milestones and end-state measures of one run (NaN = never reached / undefined)."""
    metrics = result.metrics
    last = metrics[-1]
    populations = [int(r["population"]) for r in metrics]
    peak = int(np.argmax(populations))
    technologies = (
        [t.id for t in result.scenario.knowledge.technologies]
        if (result.scenario.knowledge)
        else []
    )
    row: Row = {
        "seed": seed,
        "final_year": int(last["year"]),
        "final_population": int(last["population"]),
        "peak_population": populations[peak],
        "peak_year": int(metrics[peak]["year"]),
        "extinct": int(last["population"] == 0),
        "first_cultivation_year": _first_year(metrics, lambda r: r["cultivated_ha"] > 0),
    }
    for tech in technologies:
        row[f"first_{tech}_year"] = _first_year(metrics, lambda r, t=tech: r[f"tech_share_{t}"] > 0)
    for threshold in FARM_SHARE_THRESHOLDS:
        row[f"farm_share_{int(threshold * 100)}pct_year"] = _first_year(
            metrics, lambda r, x=threshold: r["farm_share_of_harvest"] >= x
        )
    migrations = sum(int(r["migrations"]) for r in metrics)
    unit_years = sum(int(r["units"]) for r in metrics)
    tail = metrics[-TAIL_YEARS:]
    row.update(
        {
            "migration_rate": migrations / unit_years if unit_years else math.nan,
            "final_migration_rate": (
                sum(int(r["migrations"]) for r in tail) / max(sum(int(r["units"]) for r in tail), 1)
            ),
            "final_farm_share": _tail_mean(metrics, "farm_share_of_harvest"),
            "final_sedentary_share": _tail_mean(metrics, "sedentary_share"),
            "final_soil_farmed": _tail_mean(metrics, "mean_soil_nutrients_farmed"),
            "final_crowding_hazard": _tail_mean(metrics, "mean_crowding_hazard"),
            "final_crowding_death_share": _tail_mean(metrics, "crowding_death_share"),
            "final_crude_death_rate": _tail_mean(metrics, "crude_death_rate"),
            "inventions": sum(int(r["inventions"]) for r in metrics),
            "units": int(last["units"]),
            "runtime_seconds": float(result.manifest.get("runtime_seconds", math.nan)),
        }
    )
    for tech in technologies:
        row[f"final_share_{tech}"] = float(last[f"tech_share_{tech}"])
    return row


@dataclass(frozen=True)
class _Job:
    scenario: Scenario
    seed: int
    n_years: int | None
    save_dir: Path | None


def _run_job(job: _Job) -> Row:
    scenario = job.scenario.with_overrides(seed=job.seed, n_years=job.n_years)
    result = Simulator(scenario).run()
    if job.save_dir is not None:
        result.save(job.save_dir / f"seed_{job.seed}")
    return summarize_run(result, job.seed)


def run_ensemble(
    scenario: Scenario,
    seeds: Sequence[int],
    jobs: int = 1,
    n_years: int | None = None,
    save_runs_dir: Path | None = None,
    progress: Callable[[Row], None] | None = None,
) -> list[Row]:
    """Run ``scenario`` once per seed (in ``jobs`` processes); rows are ordered by seed."""
    work = [_Job(scenario, seed, n_years, save_runs_dir) for seed in seeds]
    rows: list[Row] = []
    if jobs <= 1:
        for job in work:
            rows.append(_run_job(job))
            if progress:
                progress(rows[-1])
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for row in pool.map(_run_job, work):
                rows.append(row)
                if progress:
                    progress(row)
    return sorted(rows, key=lambda r: int(r["seed"]))


def aggregate(rows: Sequence[Row]) -> dict[str, dict[str, float]]:
    """Per-column distribution statistics; ``reached`` is the share of runs with a value."""
    summary: dict[str, dict[str, float]] = {}
    for key in rows[0]:
        if key == "seed":
            continue
        values = np.array([float(r[key]) for r in rows])
        present = values[~np.isnan(values)]
        stats: dict[str, float] = {
            "n": float(len(values)),
            "reached": float(len(present) / len(values)) if len(values) else math.nan,
        }
        if present.size:
            stats |= {
                "mean": float(present.mean()),
                "std": float(present.std(ddof=1)) if present.size > 1 else 0.0,
                "min": float(present.min()),
                "max": float(present.max()),
            }
            stats |= {f"q{int(q * 100):02d}": float(np.quantile(present, q)) for q in QUANTILES}
        summary[key] = stats
    return summary


def write_ensemble(
    directory: Path,
    scenario: Scenario,
    seeds: Sequence[int],
    rows: Sequence[Row],
    settings: Mapping[str, Any] | None = None,
    wall_seconds: float | None = None,
) -> Path:
    """Write ``runs.csv``, ``summary.json``, ``summary.csv`` and ``manifest.json``."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "runs.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = aggregate(rows)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    columns = [
        "n",
        "reached",
        "mean",
        "std",
        "min",
        *[f"q{int(q * 100):02d}" for q in QUANTILES],
        "max",
    ]
    with (directory / "summary.csv").open("w", newline="") as handle:
        table = csv.writer(handle)
        table.writerow(["measure", *columns])
        for key, stats in summary.items():
            table.writerow([key, *[stats.get(c, "") for c in columns]])
    manifest = run_manifest(
        scenario,
        seeds=list(seeds),
        settings=dict(settings or {}),
        wall_seconds=wall_seconds,
        n_runs=len(rows),
    )
    manifest.pop("seed", None)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return directory


def timed_ensemble(
    scenario: Scenario,
    seeds: Sequence[int],
    out: Path,
    jobs: int = 1,
    n_years: int | None = None,
    settings: Mapping[str, Any] | None = None,
    save_runs: bool = False,
    progress: Callable[[Row], None] | None = None,
) -> tuple[list[Row], Path]:
    """Apply ``settings``, run the ensemble, and write its outputs to ``out``."""
    variant = scenario.with_settings(settings) if settings else scenario
    started = time.perf_counter()
    rows = run_ensemble(
        variant, seeds, jobs, n_years, out / "runs" if save_runs else None, progress
    )
    wall = time.perf_counter() - started
    return rows, write_ensemble(out, variant, seeds, rows, settings, wall)


def read_runs(path: Path) -> list[Row]:
    """Read a ``runs.csv`` written by :func:`write_ensemble`."""
    with path.open() as handle:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(handle)]


def paired_differences(
    baseline: Sequence[Row], variant: Sequence[Row]
) -> dict[str, dict[str, float]]:
    """Per-measure paired comparison over the seeds both ensembles share.

    For each measure: mean of ``variant - baseline`` over seed pairs where both are defined,
    its standard error, the number of such pairs, and how often each side reached a value.
    """
    base = {int(r["seed"]): r for r in baseline}
    other = {int(r["seed"]): r for r in variant}
    seeds = sorted(base.keys() & other.keys())
    if not seeds:
        raise ValueError("the ensembles share no seeds")
    result: dict[str, dict[str, float]] = {}
    for key in base[seeds[0]]:
        if key == "seed" or key not in other[seeds[0]]:
            continue
        a = np.array([float(base[s][key]) for s in seeds])
        b = np.array([float(other[s][key]) for s in seeds])
        both = ~np.isnan(a) & ~np.isnan(b)
        diff = b[both] - a[both]
        result[key] = {
            "pairs": float(both.sum()),
            "baseline_mean": float(np.nanmean(a)) if (~np.isnan(a)).any() else math.nan,
            "variant_mean": float(np.nanmean(b)) if (~np.isnan(b)).any() else math.nan,
            "mean_difference": float(diff.mean()) if diff.size else math.nan,
            "se_difference": float(diff.std(ddof=1) / math.sqrt(diff.size))
            if diff.size > 1
            else math.nan,
            "baseline_reached": float((~np.isnan(a)).mean()),
            "variant_reached": float((~np.isnan(b)).mean()),
        }
    return result
