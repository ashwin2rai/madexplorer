"""Exactness oracle for performance work: hashes of metrics, events and final unit state.

Level A (exact) optimizations must leave every hash unchanged. The runs complement the
golden fixtures with longer and larger states: mvp2_neolithic seed 0 over 400 years
(farming, ~240 units), mvp2_pressure seed 1 over 300 years, and a 200-unit synthetic
state after 15 ticks. Hashes are numeric-platform specific, like the golden fixtures.

Usage:
    uv run python scripts/perf/exactness_oracle.py benchmarks/perf/oracle_ph0.json
    uv run python scripts/perf/exactness_oracle.py --record <file>   # on a new platform

Raw mode hashes raw belief rows and therefore always runs on the dense reference store
(the production default is sparse). ``--logical`` hashes beliefs in their logical form
(each unit's current entries only) on the default backend (or ``$MADEXPLORER_BELIEFS``):
``... --logical benchmarks/perf/oracle_ph4b_logical.json`` (recorded with the dense store).
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

from madexplorer.config.loader import Scenario
from madexplorer.core.simulation import Simulator
from madexplorer.experiments.benchmark import synthetic_simulator, warm_up_beliefs
from madexplorer.population.unit import belief_slot

LOGICAL = "--logical" in sys.argv
if LOGICAL:
    sys.argv.remove("--logical")
elif os.environ.setdefault("MADEXPLORER_BELIEFS", "dense") != "dense":
    sys.exit("raw-byte hashes need the dense reference store (use --logical for sparse)")


def belief_arrays(sim, u):
    """Raw rows (dense reference), or the logical current entries (``--logical``)."""
    if not LOGICAL:
        return [u.beliefs.year, u.beliefs.food_kcal, u.beliefs.population, u.beliefs.hops]
    memory = sim.scenario.species[u.species_id].cognition.memory_years
    cells, year, food, population, hops = sim.state.belief_store.entries(belief_slot(u))
    keep = year > sim.state.year - memory
    return [cells[keep].astype(np.int64), year[keep], food[keep], population[keep], hops[keep]]


def digest(sim, metrics):
    h = hashlib.sha256()
    h.update(json.dumps(metrics, sort_keys=True, default=float).encode())
    h.update(
        json.dumps(
            [(e.year, e.kind, e.data) for e in sim.events], sort_keys=True, default=str
        ).encode()
    )
    for u in sim.state.units.values():
        h.update(u.id.encode())
        h.update(np.int64(u.cell).tobytes())
        for a in (u.females, u.males, u.knowledge, *belief_arrays(sim, u)):
            h.update(np.ascontiguousarray(a).tobytes())
        h.update(
            repr(
                (
                    u.food_ratio,
                    u.energy_deficit,
                    u.reserve_kcal_per_capita,
                    u.stores_kcal,
                    u.fields_ha,
                    u.residence_years,
                    u.move_hazard,
                    sorted(u.technologies),
                    sorted(u.trade_ties.items()),
                    list(u.harvest_history),
                    u.familiarity._value,
                    u.familiarity._year,
                    u.recent_residence,
                    u.food_log_prior,
                    u.food_log_signal_var,
                    u.labor_debt_hours,
                    u.forage_marginal_kcal_per_hour,
                )
            ).encode()
        )
    return h.hexdigest()[:16]


out = {}
for name, path, seed, years in [
    ("neolithic_s0_400", "scenarios/mvp2_neolithic.yaml", 0, 400),
    ("pressure_s1_300", "scenarios/mvp2_pressure.yaml", 1, 300),
]:
    sim = Simulator(Scenario.from_yaml(path).with_overrides(seed=seed, n_years=years))
    r = sim.run()
    out[name] = (digest(sim, r.metrics), r.metrics[-1]["population"], len(sim.state.units))
s = Scenario.from_yaml("scenarios/mvp2_neolithic.yaml")
sim = synthetic_simulator(s, 200)
warm_up_beliefs(sim, 10)
rows = []
for _ in range(15):
    ctx = sim.step()
    rows.append(
        {
            "pop": sim.state.total_population(),
            "units": len(sim.state.units),
            "births": ctx.ledger.births,
            "harvest": ctx.ledger.harvest_kcal,
            "spoil": ctx.ledger.spoilage_kcal,
            "trade": ctx.ledger.trade_volume_kcal,
        }
    )
out["synthetic200_15"] = (digest(sim, rows), rows[-1]["pop"], len(sim.state.units))
text = json.dumps(out, indent=1)
if len(sys.argv) > 1 and sys.argv[1] == "--record":
    Path(sys.argv[2]).write_text(text)
    print("recorded", text)
else:
    ref = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else None
    print(text)
    if ref is not None:
        ok = all(tuple(ref[k]) == tuple(out[k]) for k in ref)
        print("ORACLE", "IDENTICAL" if ok else "DIFFERENT")
        sys.exit(0 if ok else 1)
