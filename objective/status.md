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

| # | Area | Class | Benchmark (before → after) | Fixtures |
|---|---|---|---|---|
| — | Benchmark tooling: storage report, Python calls per tick, resized-world founders, `bench-quick` / `bench-scale` | tooling | — | unchanged |

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
