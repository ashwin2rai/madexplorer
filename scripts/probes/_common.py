"""Shared helpers of the MVP 3 counterfactual probes (observation only).

The frozen reference scenarios, digests of authoritative and strata state (to prove a probe
changes nothing), a step-by-step driver, and small distribution statistics.
"""

import hashlib
import json
import time
from typing import Any, Protocol

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator

REFERENCE = {  # the frozen MVP 2.1 reference runs (baselines/mvp2_1)
    "neolithic": ("scenarios/mvp2_neolithic.yaml", 600, {}),
    "pressure+cult": ("scenarios/mvp2_pressure.yaml", 400, {"mechanisms.cultivation": True}),
    "pressure-cult": ("scenarios/mvp2_pressure.yaml", 400, {"mechanisms.cultivation": False}),
}
SEEDS = (0, 1, 2, 3)


def scenario_for(name: str, seed: int, weight: float, years: int | None = None) -> Scenario:
    """A reference scenario at ``strata.field_output_claim_weight = weight``."""
    path, horizon, settings = REFERENCE[name]
    base = Scenario.from_yaml(path).with_overrides(seed=seed, n_years=years or horizon)
    return base.with_settings({**settings, "strata.field_output_claim_weight": weight})


class Observer(Protocol):
    def install(self) -> Any: ...
    def remove(self) -> None: ...


def drive(scenario: Scenario, observer: Observer | None) -> tuple[Simulator, float]:
    """Run ``scenario`` year by year (strata recorded) with ``observer`` installed."""
    if observer is not None:
        observer.install()
    try:
        sim = Simulator(scenario, record_strata=True)
        started = time.perf_counter()
        for _ in range(scenario.config.simulation.n_years):
            sim.step()
            if not sim.state.units:
                break
        return sim, time.perf_counter() - started
    finally:
        if observer is not None:
            observer.remove()


def physical_digest(sim: Simulator) -> str:
    """The frozen event stream, RNG states and unit physical state (metrics are covered by
    the MVP 2.1 oracles; probes step without the recorder)."""
    h = hashlib.sha256()
    h.update(json.dumps([(e.year, e.kind, e.data) for e in sim.events], default=str).encode())
    for name in sorted(sim.rng._streams):
        h.update(repr(sim.rng.stream(name).bit_generator.state).encode())
    for unit in sim.state.units.values():
        h.update(unit.id.encode())
        for array in (unit.females, unit.males, unit.knowledge):
            h.update(np.ascontiguousarray(array).tobytes())
        h.update(repr((unit.cell, unit.stores_kcal, unit.fields_ha, unit.food_ratio,
                       unit.harvest_kcal, list(unit.harvest_history))).encode())  # fmt: skip
    return h.hexdigest()


def strata_digest(sim: Simulator) -> str:
    """Strata sidecar (events, flows) and final strata of every unit."""
    population = sim.state.population
    h = hashlib.sha256()
    h.update(json.dumps(population.strata_log, default=repr).encode())
    h.update(json.dumps(population.strata_flows, default=repr).encode())
    for unit in sim.state.units.values():
        for name, values in unit.strata.columns.items():
            h.update(name.encode() + np.ascontiguousarray(values).tobytes())
    return h.hexdigest()


def weighted_quantiles(
    values: np.ndarray, weights: np.ndarray, qs: tuple[float, ...]
) -> list[float]:
    if values.size == 0:
        return [float("nan")] * len(qs)
    order = np.argsort(values, kind="stable")
    v, cw = values[order], np.cumsum(weights[order])
    cw = cw / cw[-1]
    return [float(v[min(np.searchsorted(cw, q), v.size - 1)]) for q in qs]


def w1(pa: np.ndarray, wa: np.ndarray, pb: np.ndarray, wb: np.ndarray) -> float:
    """Wasserstein-1 between two weighted point measures on the line (weights normalized)."""
    points = np.concatenate([pa, pb])
    order = np.argsort(points, kind="stable")
    cum = np.cumsum(np.concatenate([wa / wa.sum(), -wb / wb.sum()])[order])
    return float((np.abs(cum[:-1]) * np.diff(points[order])).sum())


def q(values: Any, qs: tuple[float, ...] = (0.5, 0.9, 0.99)) -> str:
    """``p50/p90/p99/max`` of the non-None values (``-`` if none)."""
    array = np.asarray([v for v in values if v is not None], dtype=float)
    if array.size == 0:
        return "-"
    return "/".join(f"{np.quantile(array, x):.3g}" for x in qs) + f"/max {array.max():.3g}"
