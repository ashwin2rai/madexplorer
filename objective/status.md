# Implementation Status — Current Canonical State

This file is the **forward-looking implementation status** for Mad Explorer after the MVP 2 model freeze.
It intentionally omits the experiment-by-experiment history that accumulated during MVP 2 stabilization.

For scientific/model requirements, read `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` (document version 2.0) first.
For exact freeze provenance, read `baselines/mvp2/freeze_manifest.json`.
Use this file to answer: **What exists now? What is frozen? What is still limited? What should we do next?**

---

## 1. Current phase

**MVP 1:** complete.  
**MVP 2:** complete and scientifically frozen.  
**Current milestone:** **MVP 2 Performance Hardening**.  
**Next scientific milestone:** **MVP 3 — Distributional Society**.

The current task is to make the frozen MVP 2 simulator substantially faster **without changing model semantics**.
Model changes are out of scope during performance hardening unless a genuine correctness bug is demonstrated.

### Frozen MVP 2 identity

- Freeze commit: `f505fd118aa17bda3cc1cbb92afed13008bf102b`
- Source-tree SHA-256: `7692ac03a2c75ad598e771098231b1f8bfb74bf918cd4b148227837b0be6bea5`
- Freeze manifest: `baselines/mvp2/freeze_manifest.json`
- Canonical scientific scenarios:
  - `scenarios/mvp2_neolithic.yaml`
  - `scenarios/mvp2_pressure.yaml`

If the source tree differs from the frozen hash, classify the change explicitly as an optimization, numerical reformulation, bug fix, or model change.

---

## 2. Source-of-truth hierarchy

When documents disagree, use this order:

1. `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` (v2.0) — canonical scientific and architectural objective.
2. `baselines/mvp2/freeze_manifest.json` — exact frozen revision, scenarios, seeds, reference outcomes, and performance baseline.
3. This file — current implementation priorities, accepted limitations, and handoff notes.
4. Tests and model-rule documentation — executable mechanism contracts.
5. README and older comments — convenience documentation only; some text may still be stale.

Do **not** reopen a resolved MVP 2 issue merely because historical notes or comments describe the pre-freeze state.

---

## 3. Frozen MVP 2 model contract

The frozen simulator currently contains:

- grid topology, terrain, hydrology, climate, and resource fields;
- human species/life-history configuration;
- stochastic age/sex cohort demography;
- food requirements, energy deficits, fertility response, starvation mortality;
- foraging with familiarity-dependent efficiency;
- agriculture, clearing labor, soil depletion/recovery, storage, and simple trade;
- bounded perception and socially transmitted geographic information;
- uncertainty-aware direct-observation shrinkage;
- decaying practiced ecological familiarity, separate from geographic belief;
- whole-group migration using perceived destination utility;
- agricultural-capital replacement cost when leaving fields;
- group fission and fusion;
- knowledge learning and social diffusion across domains;
- endogenous technology invention through competing hazards;
- settlement/crowding mortality;
- deterministic provenance, isolated RNG streams, metrics, ensembles, and golden regression fixtures.

### Important frozen mechanism defaults

The MVP 2 freeze canonicalized:

- `direct_observation_shrinkage = true`
- `familiarity_decay = true`
- `field_growth_to_target = true`
- `field_replacement_cost = true`
- `expected_tenure = false`
- `aggregation = false` in canonical scientific scenarios

These defaults should not be changed during performance hardening.

---

## 4. Current subsystem flow

The annual simulation is staged through subsystem `evaluate()` / proposal / `apply()` phases.
Conceptually, the frozen pipeline is:

```text
climate / ecology
    -> perception
    -> social geographic information sharing
    -> farming
    -> foraging
    -> trade
    -> energy balance
    -> demography
    -> field planning
    -> knowledge learning
    -> knowledge diffusion
    -> innovation
    -> fission
    -> fusion
    -> migration
    -> optional coarsening
```

Canonical runs have coarsening disabled.

The proposal architecture is valuable for auditability and deterministic staging, but proposal-object allocation is now a legitimate performance target.

---

## 5. Population representation today

`PopulationUnit` remains the central social actor.

A unit currently contains:

### Demography

- exact integer female age cohorts;
- exact integer male age cohorts.

### Spatial cognition

- dense per-cell belief arrays;
- bounded social reports;
- recent residence history;
- per-cell practiced familiarity with timestamps.

### Culture / technology

- domain knowledge;
- owned technologies;
- technology-derived capabilities;
- social/trade ties.

### Subsistence / economic state

- stores;
- fields;
- farm and forage harvests;
- food ratio / energy deficit;
- labor quantities;
- residence and migration state.

This representation is scientifically adequate for MVP 2 but expensive in Python because thousands of independent units carry Python objects, mappings, sets/deques, proposal objects, and per-unit arrays.

---

## 6. Canonical scientific conclusions from MVP 2

These are settled for the frozen model and should not be reopened during performance hardening.

### Agriculture

The previous bootstrap problem in field expansion was fixed.
When cultivation is worthwhile, fields now grow toward a meaningful target subject to labor and land constraints.

The bounded pressure scenario validates the intended mechanism:

```text
resource pressure
    -> cultivation adoption
    -> substantially higher sustainable population/density
```

Agriculture does **not** need to dominate every abundant-foraging frontier.

### Migration and information

- The old destination-level Gumbel / best-of-many artifact is gone.
- Social interactions do not synchronize entire remembered maps.
- Social information bandwidth is bounded and relayed information loses confidence.
- Direct noisy observations are shrunk toward an experience-based prior.
- Human migration candidate sets are already bounded by physical reachability; no additional attention cap is active.

### Familiarity

Geographic belief and ecological familiarity are distinct:

- belief = knowledge that a place exists and approximate information about it;
- familiarity = practiced ability to exploit its ecology efficiently.

Unpracticed familiarity decays exponentially toward the species baseline and is evaluated lazily.

### Agricultural capital and migration

Existing fields increase the value of staying through crop production.
Leaving incurs the **future labor opportunity cost of recreating equivalent cleared fields**, not a penalty for sunk historical labor and not a second charge on crop output.

### Population growth

MVP 2 does not require an imposed population plateau.
Food stress, resource competition, soil effects, starvation, and settlement crowding provide negative feedback, but continued growth at the end of a finite run is not itself a model failure.

---

## 7. Frozen reference validation

### 7.1 Canonical Neolithic scenario

Freeze reference:

- scenario: `scenarios/mvp2_neolithic.yaml`
- seeds: `0,1,2,3`
- horizon: 600 years

Across the four freeze seeds at year 600:

- population: approximately **15.8k–33.1k**;
- occupied cells: approximately **497–790**;
- final farm share: approximately **0.42–0.50**;
- final sedentary share: approximately **0.77–0.85**;
- migration rate: approximately **0.047–0.054**;
- first cultivation: approximately years **147–238**.

The seeds intentionally diverge in timing and trajectory.
Do not optimize toward any one seed.

### 7.2 Pressure scenario

Freeze reference:

- scenario: `scenarios/mvp2_pressure.yaml`
- seeds: `0,1,2,3`
- horizon: 400 years
- paired cultivation ON/OFF comparison

Late-run means show a large and consistent carrying-capacity effect:

- farming ON: roughly **3.36k–4.17k** people;
- farming OFF: roughly **1.13k–1.25k** people;
- farming ON also produces substantially higher people-per-occupied-cell and sedentism.

This compact paired experiment is the canonical MVP 2 agriculture validation.

---

## 8. Testing contract

### Routine engineering

Keep `make check` green.
At the freeze it recorded:

- **185 passing tests**.

Golden fixtures live under `tests/regression/golden/`.
They are numeric-platform sensitive; on a machine with a different NumPy/CPU dispatch signature they may be skipped rather than treated as failed reference behavior.

### Statistical tests

- Compact statistical validation is intentionally small and suitable for routine use.
- Extended long statistical validation is manual/research-grade and is **not** required for ordinary optimization work.
- Aggregation remains a documented strict xfail because naive coarsening is scientifically non-neutral.

### Optimization validation

During Performance Hardening:

- exact optimizations should preserve golden outputs;
- RNG draw order and stream semantics should remain unchanged unless an explicitly tolerated numerical reformulation is approved;
- numerical reformulations require a documented error tolerance and targeted equivalence test;
- large ensembles are not required for routine implementation changes.

Use the smallest diagnostic capable of detecting a regression.

---

## 9. Performance baseline

The committed MVP 2 pre-hardening baseline is in:

- `benchmarks/perf/mvp2_freeze_synthetic.json`
- `benchmarks/perf/mvp2_freeze_seed0_600y.json`

Reference seed-0, 600-year run:

- CPU: **41.88 s**
- wall: **43.82 s**
- final active units: **1,212**
- peak RSS: **123.3 MB**
- average: approximately **0.293 ms per unit-year**

Late window, years 571–600:

- mean active units: **1,085.5**
- approximately **328 ms/tick**
- approximately **0.302 ms/unit/tick**

Synthetic benchmark scaling remains approximately linear over the measured range:

| Approx. units | CPU ms/tick |
|---:|---:|
| ~128 | ~31 |
| ~610 | ~142 |
| ~1,098 | ~269 |
| ~1,763 | ~451 |

The dominant diagnosis is therefore not one catastrophic quadratic algorithm in normal ranges.
The dominant cost is **Python work repeated per active social unit**.

Historically large runtime consumers include:

- geographic information sharing;
- migration;
- foraging;
- knowledge diffusion;
- demography.

Re-profile after every substantial representation change; do not assume the old ranking remains true.

---

### 9.1 Performance-hardening baseline (PH0, 2026-09-30)

Frozen model code (freeze source tree plus benchmark tooling only). 2-core codespace.
Synthetic states: 20 warm-up years, then timed ticks. CPU time. Reports are in
`benchmarks/perf/ph0_scale_*.json`. Commands: `make bench-quick` (engineering loop) and
`make bench-scale`.

| Case | Mean units | CPU ms/tick | µs/unit/tick | Python calls/unit/tick | Peak RSS | Dense beliefs | Top subsystems (ms/tick) |
|---|---:|---:|---:|---:|---:|---:|---|
| 100 units, 40×40 | 112 | 29 | 263 | 514 | 63 MB | 2.5 MB | migration 9, foraging 7, demography 4 |
| 1k units, 40×40 | 1,055 | 264 | 250 | 509 | 107 MB | 22 MB | migration 60, sharing 59, foraging 53, diffusion 45, demography 39 |
| 10k units, 40×40 | 9,990 | 5,092 | 510 | 1,064 | 852 MB | 135 MB | diffusion 1,582, sharing 1,487, fusion 805, trade 668, migration 575 |
| 25k units, 40×40 (3 ticks) | 27,464 | 18,690 | 681 | 1,889 | 3.0 GB | 584 MB | diffusion 14,632, sharing 9,629, trade 7,019, fusion 3,940, migration 2,546 |
| 1k units, 100×100 | 1,081 | 253 | 234 | 525 | 243 MB | 148 MB | migration 82, foraging 64, demography 32 |

Findings:
- **Up to ~1k units, cost is linear, at ~250 µs and ~510 Python calls per unit per tick.**
  The overhead is Python per unit, spread over every subsystem (a flat profile; no single
  kernel dominates).
- **Above that, cost grows superlinearly: per-unit cost ×2 at 10k and ×2.7 at 25k.** These
  synthetic states put 8-17 units in each land cell, so encounter and contact counts grow
  with local density:
  - diffusion contacts, sharing encounter pairs and trade donor scans are pairwise by the
    model's definition. Part of this cost is inherent to the frozen semantics; only the
    constant factor is implementation.
  - Fusion is quadratic in the implementation: `rewire_ties` scans every unit on each
    merge.
  - Scaling runs at realistic density need larger worlds, which the dense beliefs prevent
    (next point).
- **Dense beliefs cost 12 bytes × cells per unit:** 20.8 kB per unit at 1,600 cells and
  130 kB at 10,000 cells. 10k units on a 100×100 world would need ~1.2 GB of beliefs alone.
  Beliefs are the first memory limit for larger worlds.
- Familiarity (1-5 entries per unit), residence records and report pools are small after
  P4b. Trade edges vary with the state.

### 9.2 Performance-hardening plan (PH1-PH5)

Strategy, from the measurements above (row-view micro-benchmark: a field read through a
numpy-backed view costs 4-7× a plain attribute, and `np.float64` scalar arithmetic ~4.6×
Python float):
1. First convert subsystems to **batched column computations** over a per-phase columnar
   snapshot. The large win is removing per-unit Python logic, not storage. While
   `PopulationUnit` objects remain authoritative, gathers cost one pass per field.
2. Then **flip authority** to a columnar `UnitTable`, with `PopulationUnit` as a view for
   cold paths (fission/fusion apply, events, tests, serialization). Flipping earlier would
   slow every unconverted subsystem.
3. All steps are Level A (exact) unless labelled. Golden fixtures and seeded outputs are the
   oracle. Differential tests compare reference and batched kernels on random small states,
   with identical pre-drawn random numbers.

Phases:
- **PH1: infrastructure and first exact conversions.**
  - `CompiledScenario`: numeric species parameters; technology bit positions, prerequisite
    masks, minimum-knowledge and capability-effect matrices.
  - A shared counting-sort `SpatialIndex` (cells in first-appearance order, preserving
    `units_by_cell` order), invalidated by migration, fission, fusion and extinction.
  - A `UnitTable` columnar snapshot, with integer row indices (stable string ids kept for
    events and id-ordered ties).
  - Convert energetics and demography gathers, and grouping in foraging, field planning,
    fusion and trade, to the index and columns.
- **PH2:** replace per-unit proposal dataclasses in hot paths with array buffers; remove
  the remaining `units_by_cell` and per-unit dict/list creation; fix fusion's quadratic
  rewiring (a partner → holders reverse index).
- **PH3:** batch the hottest subsystems as column kernels, with reference-vs-fast
  differential tests: sharing, migration, foraging, diffusion (contact edge arrays),
  learning, innovation.
- **PH4:** flip authority to `UnitTable`, with a dense belief matrix as the first backend;
  Numba only for kernels that remain hot after the flip. RNG draws stay generated by
  Python streams.
- **PH5:** a belief-store abstraction (dense and sparse backends), packed familiarity if it
  is still significant, checkpoint/resume, experiment branching, shared immutable worker
  state, columnar recording. Then the MVP 3 scaling report (1k/10k/50k units at realistic
  density; cost of 8-16 strata).

Accepted optimizations are logged below (area, exact or Level B, before and after,
fixtures).

### 9.3 Accepted optimizations

Exactness oracle for all Level A work: `uv run python scripts/perf/exactness_oracle.py
benchmarks/perf/oracle_ph0.json`. It hashes metrics, events and final unit state of
`mvp2_neolithic` seed 0 over 400 years, `mvp2_pressure` seed 1 over 300 years and a
200-unit synthetic state; it complements the golden fixtures. Both must be unchanged.

| # | Area | Class | Effect | Fixtures and oracle |
|---|---|---|---|---|
| — | Benchmark tooling: storage report, Python calls per tick, resized-world founders, `bench-quick`, `bench-scale`, `bench-scale-units` (fixed density), `bench-scale-density` | tooling | — | unchanged |
| PH1.1 | `CompiledScenario` (`core/compiled.py`): per-species parameter arrays, technology bit positions, prerequisite masks, minimum-knowledge and capability matrices; built once per `Simulator` and exposed as `ctx.compiled` | A | infrastructure | unchanged |
| PH1.2 | Shared `SpatialIndex` (`core/spatial.py`): reproduces `units_by_cell()` order exactly; `ctx.spatial(state)` is built once per phase and `ctx.invalidate_spatial()` is called by relocation, fission, fusion, extinction and coarsening applies; used by foraging, field planning, trade, fusion, diffusion, innovation, coarsening | A | one grouping per phase instead of one per subsystem | unchanged |
| PH1.3 | Energetics: batched need (`annual_need_batch`) and `energy_balance_batch`; one proposal, applied in unit order | A | energetics 0.97 → 0.64 s (seed 0, 600 y) | unchanged |
| PH1.4 | Demography: `crowding_hazard_array`, vectorized mate availability, one proposal per species | A | 3.86 → 2.71 s | unchanged |
| PH1.5 | Foraging: per-unit labor, efficiency and target shares batched; per-cell Newton solver unchanged; cell targets keep Python `sum()` | A | small | unchanged |
| PH1.6 | Farming (fully batched, one proposal) and field planning (batched yields, labor, need; the scalar investment rule only for units with a positive yield) | A | farming 0.87 → 0.60, field planning 2.73 → 2.34 s | unchanged |
| PH1.7 | Trade: batched offers; donors indexed per cell (offering units only) instead of scanning every unit in reachable cells | A | 10k units: 668 → < 180 ms/tick (no longer in the top five) | unchanged |
| PH1.8 | Fusion tie rewiring O(degree): holders of the source's ties are its own live partners (ties are symmetric among live units; invariant tested) | A | 10k units: fusion 805 ms → out of the top five | unchanged |
| PH1.9 | Learning: batched activity shares and learning law; practice weights reproduce Python's compensated `sum()` via `core/exactsum.py` (tested against the builtin) | A | 2.59 → 0.62 s | unchanged |

| PH2.1 | Sharing: packed report selection (`select_reports_packed`: per-sender parameters as compiled arrays, one gathering pass) and packed receipt (`receive_reports_packed`: acceptance vectorized over all receivers, one `ReceivedReports` proposal); references `select_reports_batch` / `receive_reports_batch` kept | A | sharing 19.5 → 9.8 calls/unit, 51 → 31 ms/tick at 1k (profiled) | unchanged |
| PH2.2 | Shared phase-local pair index (`SpatialIndex.local_pairs`): sharing encounters and diffusion's local contacts are the same pair set, built once while no membership change intervenes | A | one construction instead of two | unchanged |
| PH2.3 | Migration: batched evaluate (per-unit scalars from compiled parameters; the only per-unit work is the gather from the unit's own belief arrays); exact ties, traced units and attention caps fall back to `_evaluate_reference` before any draw; the hazard stays the scalar `migration_probability` | A | 56 → 21 calls/unit, 64 → 31 ms; no fallback in 400 years of seed 0 | unchanged |
| PH2.4 | Diffusion: contacts from the shared pair index plus per-receiver trade merge; scalar loss and adoption rules only where a bitmask test shows they can apply; one `DiffusionBatch` proposal; reference `_evaluate_reference` kept | A | 83 → 36 calls/unit | unchanged |
| PH2.5 | Innovation: candidate eligibility from technology bitmasks and the knowledge matrix; vectorized neighbor counts; scalar hazard and competing-risk draw only for units with candidates; reference kept | A | 26 → 3 calls/unit | unchanged |
| PH2.6 | Perception: one packed `Perceptions` proposal (`as_patches()` gives the reference per-unit patches) | A | 15 → 10 calls/unit | unchanged |
| PH2.7 | Foraging: scalar fast path for single-group cells (`single_unit_harvest`, bit-identical because a one-element numpy sum is the element and a two-element sum is `a + b`); multi-group cells keep the numpy path; one packed `CellHarvests` proposal | A | 67 → 50 calls/unit, 59 → 28 ms | unchanged |
| — | Benchmark: social contacts per tick, µs per contact, transient Python memory per tick (tracemalloc peak within a tick, an allocation-pressure proxy) | tooling | — | — |

**Correction (found in PH2):** the PH0 and PH1 *synthetic* reports (`ph0_scale_*`,
`ph0_density_*`, `ph1_scale_*`, `ph1_density_*`) have inflated per-subsystem ms/tick. The
untimed call-count pass added its two profiled ticks to the breakdown. Their totals, CPU
time and calls per unit are correct. The timed-run reports (`*_seed0_600y.json`) and
`mvp2_freeze_synthetic.json` are unaffected. Fixed from PH2a onward.

**PH2 results** (CPU; same machine; seeded output identical throughout: seed 0 over 600
years ends with 33,070 people and 1,212 units).

| Benchmark | PH0 | PH1 | PH2 |
|---|---:|---:|---:|
| Seed 0, 600 y: CPU s | 41.9 | 35.8 | 29.7 (−29%) |
| Seed 0, late window (1,086 units): ms/tick | 328 | 273 | 198 (−40%) |
| 1k synthetic: CPU ms/tick / calls/unit/tick | 264 / 509 | 210 / 435 | 157 / 300 |
| 10k synthetic (40×40): CPU ms/tick / calls/unit/tick | 5,092 / 1,064 | 3,589 / 799 | 2,327 / 232 |
| Fixed density, 500 / 1k / 2k / 4k units: µs/unit/tick | 234 / 221 / 246 / 263 | 230 / 190 / 216 / 227 | 156 / 146 / 164 / 169 |
| ... calls/unit/tick | 479-493 | 414-425 | 291-299 |
| Varied density on 40×40, 250 / 1k / 4k units: µs/unit/tick | 228 / 251 / 291 | 185 / 202 / 246 | 149 / 159 / 169 |
| ... calls/unit/tick | 475 / 500 / 754 | 411 / 426 / 586 | 295 / 289 / 242 |
| µs per candidate contact (4k units on 40×40; 10k units) | — | 4.1 / 4.2 (PH2a) | 3.3 / 3.1 |
| Peak RSS / dense beliefs (4k units, fixed density) | 787 / 689 MB | 785 / 689 MB | 788 / 689 MB |
| Transient Python memory per tick (1k units) | — | — | ~11 MB |

Seed 0, 600 years, time shares in PH2: sharing 18%, migration 12%, demography 11%,
foraging 10%, field planning 9%, diffusion 8%, perception 6%. The early window (years
61-90, ~8 units) is 4.0-4.8 ms/tick CPU measured directly, the same as the freeze. The
12.4 ms/tick in `ph2_seed0_600y.json` is wall-clock window noise.

**Where the remaining cost is** (1k units, measured on warmed synthetic states):
- *Object access and syncing* (`PopulationUnit` authoritative): ~239 attribute reads and
  ~35 writes per unit per tick. At ~40 ns per read that is ≈ 13 ms; turning gathered lists
  into arrays adds ≈ 12 ms (~60 µs per field at 1k units). Together ≈ 25 ms, about 15% of a
  ~160 ms tick. The batch representation itself is transient: ~11 MB per tick at 1k units
  (~11 kB per unit), with no persistent overhead.
- *Per-unit belief arrays*: migration (~28 ms), sharing (select and receive) and perception
  still gather from each unit's own four belief arrays. That per-unit loop cannot be
  vectorized while beliefs are separate objects; a global belief matrix would remove it.
- *Remaining per-unit calls*: the cached `population` / `weighted_count` accessors, the
  familiarity dictionaries (effective value, practice), the scalar rules kept for exactness
  (field planning's investment rule, fission hazards with their interleaved draws, trade's
  deficit loop), and the per-cell Newton solver for multi-group cells.
- *Pairwise work at high density*: sharing's array work over 740k candidate pairs is
  ~1.0 s of 2.3 s per tick at 10k units (1.4 µs per pair), which is real model work.
- Remaining proposal objects are per event (trade transfers ~0.56 per unit per tick,
  relocations, rare fission/fusion); each batched subsystem emits one proposal per tick.

Differential tests (`tests/test_performance_layer.py`): the spatial index against
`units_by_cell()`, invalidation, compiled data against the configuration, energy balance,
compensated sums, batched need, labor, crop yield and learning against their per-unit
references on a warmed farming state, and tie symmetry.

**PH1 results** (CPU time; same machine; PH0 = committed revision `3bda489` in a
worktree). Seeded output is identical: seed 0 over 600 years ends with 33,070 people and
1,212 units in both.

| Benchmark | PH0 | PH1 | Change |
|---|---:|---:|---:|
| Seed 0, 600 y: CPU / late window ms/tick / µs per unit-year | 41.9 s / 328 / 293 | 35.8 s / 273 / 245 | −15% / −17% / −16% |
| Synthetic 1k units, 40×40: CPU ms/tick; calls/unit/tick | 264; 509 | 210; 435 | −20%; −15% |
| Synthetic 10k units, 40×40: CPU ms/tick; calls/unit/tick | 5,092; 1,064 | 3,589; 799 | −30%; −25% |
| Fixed density (~0.42 units per land cell), 500 / 1k / 2k / 4k units: µs/unit/tick | 234 / 221 / 246 / 263 | 230 / 190 / 216 / 227 | −2 to −14% |
| ... calls/unit/tick | 479-493 | 414-425 | −13% |
| Varied density on 40×40, 250 / 1k / 4k units: µs/unit/tick | 228 / 251 / 291 | 185 / 202 / 246 | −15 to −20% |
| ... calls/unit/tick | 475 / 500 / 754 | 411 / 426 / 586 | −13 to −22% |
| Peak RSS / dense beliefs (4k units at fixed density) | 787 / 689 MB | 785 / 689 MB | unchanged |

Readings:
- **At fixed density the frozen implementation is already close to linear in unit count**
  (µs/unit/tick varies within ±10% from 500 to 4k units). The superlinearity in the PH0
  40×40 cases is local density: pairwise sharing and diffusion contacts, and before PH1
  the trade donor scan and fusion rewiring.
- PH1 removed ~13-25% of Python calls. The remaining ~415 calls/unit/tick are dominated by
  subsystems not yet converted: sharing, migration, perception, diffusion, innovation,
  fission, and the per-cell foraging solver and apply. Those are PH2/PH3 targets.
- Memory is unchanged; dense beliefs dominate (689 of 785 MB at 4k units on 113×113).
- Wall-clock variance on the shared 2-core machine is ±5-10%; compare CPU time and calls.

## 10. Current engineering objective: MVP 2 Performance Hardening

The model is frozen. The next work should target implementation overhead and data layout.

### Primary targets

1. **Reduce repeated Python traversal of `PopulationUnit` objects.**
   - Many subsystems independently loop over `state.units.values()`.
   - Look for opportunities to batch work across units without altering staging or RNG semantics.

2. **Reduce repeated spatial-index construction.**
   - Multiple subsystems rebuild units-by-cell or equivalent structures.
   - Prefer per-tick shared indexes with explicit invalidation when location/unit membership changes.

3. **Move hot scalar state toward hybrid structure-of-arrays storage.**
   - Preserve higher-level `PopulationUnit` semantics at API boundaries if useful.
   - Store frequently accessed numeric fields contiguously where profiling supports it.
   - Keep exact cohort arrays and shared group-level state conceptually separate.

4. **Reduce proposal-object allocation.**
   - Proposal staging is scientifically useful, but thousands of tiny frozen dataclass instances create allocation/GC overhead.
   - Consider typed batched proposal buffers or array-backed proposal structures while preserving evaluate/apply semantics.

5. **Improve cache locality and reduce dictionary/set/property lookups in hot loops.**
   - Technology/capability caches already exist; continue eliminating repeated equivalent object construction.

6. **Review belief-state scaling after profiling.**
   - Social transmission is already bounded, but every unit still owns dense arrays covering all world cells.
   - Dense storage is acceptable for the current 40×40 world, but it scales as units × cells.
   - Do not change belief semantics merely for speed; representation may change.

7. **Use NumPy/batched kernels where they reduce Python overhead.**
   - Demography is already a useful example of this approach.

8. **Use Numba/Cython/Rust/native kernels only after Python representation/dataflow improvements are measured.**
   - Do not compile an inefficient object architecture prematurely.

### Non-goals during this phase

Do not add:

- wealth distributions;
- health strata;
- occupation classes;
- political factions;
- markets/prices;
- disease epidemiology;
- warfare;
- seasons/dynamic vegetation;
- fantasy species mechanics;
- new agriculture or migration equations.

Those belong to later scientific milestones.

---

## 11. Performance-hardening acceptance criteria

There is no single mandatory hardware-specific runtime number.
The phase is successful when:

- frozen scientific semantics remain intact;
- exact regression fixtures remain stable for exact optimizations;
- per-unit Python overhead is materially lower than the freeze baseline;
- memory growth is controlled enough that MVP 3 strata will not immediately make the engine unusable;
- the main hot paths have been re-profiled after refactoring;
- further large speed gains would require either compiled kernels or genuine model/representation changes that belong to MVP 3.

A roughly **2× improvement over the freeze baseline on the same machine** is a useful stretch target, not a reason to compromise scientific behavior.

---

## 12. Accepted MVP 2 limitations

These are known and **do not block** Performance Hardening or MVP 3 unless a later milestone explicitly addresses them.

### 12.1 Aggregation is not scientifically neutral

The current coarsening subsystem merges social actors into one decision-maker and changes population, migration, innovation, and dispersal dynamics.
Canonical scientific scenarios therefore keep aggregation **off**.

Do not use naive coarsening as a performance shortcut.
Correct adaptive statistical units belong to MVP 3.

### 12.2 Food utility mixes wild stock and crop flow

Migration compares perceived wild-food stock with annual crop flow in the stay utility.
The field-replacement rule prevents the worst double counting but does not eliminate the conceptual stock-vs-yield mismatch.
Deferred.

### 12.3 Ecology remains intentionally simple

MVP 2 still has simplifications including:

- static vegetation/resource structure;
- no seasons;
- one soil state pool per cell;
- limited ecological succession;
- simple one-good trade.

### 12.4 Social state remains group-level

MVP 2 does not yet model:

- wealth inequality;
- within-group health distributions;
- occupations/specialists;
- within-group political preferences;
- individual elites or factions;
- selective subpopulation migration.

This is the core reason MVP 3 exists.

### 12.5 Whole-group migration

A `PopulationUnit` still migrates as a social actor.
Selective emigration of socioeconomic strata is deferred to MVP 3.

### 12.6 Dense per-unit belief maps

Belief semantics are now bounded and plausible, but storage still scales with units × world cells.
This is an engineering/scalability limitation, not a current behavioral defect.

---

## 13. Resolved issues that should not be reopened casually

The following were explicitly investigated and resolved during MVP 2 stabilization:

- candidate-count/Gumbel migration artifact;
- map-wide lossless social belief synchronization;
- uncertainty handling for direct observations;
- hard saturation of migration food utility;
- permanent inherited ecological familiarity;
- agriculture field-growth bootstrap trap;
- double counting of fields/crop value in migration;
- innovation ordering bias;
- RNG-stream coupling across unrelated mechanisms;
- treating population plateau as a required outcome;
- treating naive aggregation as scientifically neutral.

If a future change appears to require reopening one of these, first demonstrate a correctness problem against the canonical v2 objective and frozen model rule.

---

## 14. Immediate documentation/housekeeping debt

These are low-risk cleanup tasks and may be completed during performance work:

- update `README.md` so it says MVP 2 is frozen and agriculture validation is complete;
- remove or update comments that claim `max_units_per_cell=8` is scientifically equivalent to aggregation-off;
- update stale aggregation-test docstrings while keeping the strict xfail rationale;
- consider warning when a new scenario enables aggregation, because the global config default may otherwise be misleading.

Do not mix these documentation changes with scientific model changes.

---

## 15. Workflow for performance changes

For each substantial optimization:

1. profile first;
2. state which Python/data-layout cost is being targeted;
3. classify the patch:
   - exact implementation optimization;
   - numerical reformulation;
   - bug fix;
   - model change;
4. implement the smallest coherent change;
5. run targeted unit/mechanism tests;
6. run golden regression where applicable;
7. run the synthetic/performance benchmark if the hot path changed;
8. record before/after CPU and memory measurements;
9. update this file only if the current architecture, limitations, or next-step priorities materially changed.

Avoid large ensemble runs for ordinary optimization work.

### Reproducibility rules

- Use isolated named RNG streams.
- Vectorizing RNG generation is allowed only when stochastic semantics and deterministic ordering remain equivalent.
- Do not reduce the number of independent stochastic decisions merely to make code faster.
- Do not retune coefficients to recover a benchmark trajectory after an optimization.

---

## 16. Gate to MVP 3

Begin substantive MVP 3 work only after Performance Hardening reaches diminishing returns and the frozen MVP 2 model remains reproducible.

MVP 3 should introduce **joint weighted socioeconomic strata**, not unrelated marginal distributions.

Preferred conceptual representation:

```text
shared group-level state
    +
N[sex, age, stratum]
    +
stratum attributes:
    wealth
    health
    occupation
    nutrition
    preferences
    migration propensity
    status / leverage
```

Group-level shared state should remain shared where appropriate:

- location;
- geographic/cultural beliefs;
- technologies;
- institutions;
- social-network relationships.

Do not multiply every subsystem by the number of strata.
Only distribution-sensitive mechanisms should operate over strata.

MVP 3's adaptive-resolution work must also solve the current aggregation problem by allowing fractions/strata inside a statistical unit to respond differently rather than converting merged populations into one homogeneous decision-maker.

---

## 17. Next scientific milestones after MVP 3

### MVP 4 — politics and hierarchy

Planned mechanisms include:

- surplus appropriation;
- wealth concentration;
- status competition;
- factions and coalitions;
- inheritance;
- coercive capacity;
- state capacity versus elite capture;
- public goods versus extraction;
- exit, rebellion, and counter-dominance.

### MVP 5+ — richer species and worlds

Planned extensions include:

- fantasy species profiles;
- different life histories/body plans;
- flight and alternative mobility;
- multi-species interaction;
- richer disease/ecology;
- longer-run biological evolution if justified.

These remain future scientific work and should not enter the current performance milestone.

---

## 18. Compact code map

```text
src/madexplorer/
  config/        scenario schema / loading / overrides
  core/          simulation, state, subsystems, RNG, invariants, provenance
  world/         grid, generation, hydrology, climate
  ecology/       resources and ecology subsystems
  species/       species profile and life history
  population/    units, composition, health, energetics, demography, groups
  economy/       foraging, agriculture, trade
  mobility/      movement, perception/information, migration
  knowledge/     learning, diffusion, innovation
  resolution/    experimental coarsening
  experiments/   ensembles and benchmarks
  metrics/       recorders
  persistence/   outputs
  cli/           command-line interface

scenarios/       canonical MVP scenarios
species/         species profiles
technologies/    technology definitions
tests/           mechanism, regression, statistical tests
benchmarks/perf/ committed performance baselines
baselines/mvp2/  MVP 2 freeze manifest and compact reference runs
```

---

## 19. Working conventions that still matter

- The user commits/tags unless explicitly asking the implementation agent to do so.
- Keep the repository runnable and tests green.
- Prefer checkpoints after coherent phases rather than large opaque batches of changes.
- Do not tune toward a desired historical narrative.
- Model assumptions belong in explicit rules/configuration, not hidden magic constants.
- Every new `PopulationUnit` field must define merge/split semantics.
- Every new stochastic mechanism needs an isolated deterministic RNG strategy.
- Units belong in field names where practical (`_km`, `_kcal`, `_years`, `_ha`, etc.).
- Use the smallest experiment capable of falsifying a claim.

---

## 20. Current one-line handoff

> **MVP 2 science is frozen and validated. The next task is to reduce Python/object/dataflow overhead while reproducing the frozen model; do not start distributional sociology until that performance-hardening phase reaches diminishing returns.**
