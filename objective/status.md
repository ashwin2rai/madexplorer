# Implementation Status — Current Canonical State

This file is the **forward-looking implementation status** for Mad Explorer after the MVP 2 model freeze.
It intentionally omits the experiment-by-experiment history that accumulated during MVP 2 stabilization.

For scientific/model requirements, read `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` (document version 2.0) first.
For exact freeze provenance, read `baselines/mvp2/freeze_manifest.json`.
Use this file to answer: **What exists now? What is frozen? What is still limited? What should we do next?**

---

## 1. Current phase

> **Resume point:** PH5 (scale and MVP 3 readiness) is complete (Section 9, "PH5"): recommendation "ready for semantic cleanup → MVP 3". Next, pending decision: make sparse the default belief backend, fix B1 under an explicit model-version change with a new reference, then MVP 3.

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

| PH3a | Global dense `BeliefStore` (`population/beliefs.py`): the four belief fields as `(capacity, cells)` matrices with the frozen dtypes and sentinel, one row per storage slot. `state.units` is a `UnitRegistry` that allocates a slot on insertion and releases it on removal (copying beliefs back out); the processing order stays the registry's insertion order. `unit.beliefs` is a compatibility row view (cold paths, tests); perception, sharing and migration gather and scatter through the store with slot arrays in one indexing operation per field. Growth: +25% per resize, in place (numpy realloc; falls back to copying if a view is alive) | A | seed 0, 600 y: CPU 29.7 → 24.9 s; 1k synthetic 157 → 130 ms/tick | unchanged |

PH3a lifecycle tests: a reused slot never leaks a dead unit's beliefs; growth preserves
every row; fusion and fission on store-backed units equal the same operations on
detached, object-held beliefs (the PH2 representation). The first growth policy (doubling,
copying resize) doubled peak RSS for large stores (4k units at fixed density: 1,586 MB);
the in-place +25% policy fixed it (918 MB, versus 788 MB in PH2).

**PH3a results** (CPU; seeded output identical: seed 0 over 600 years ends with 33,070 people and 1,212 units).

| Benchmark | PH2 | PH3a |
|---|---:|---:|
| Seed 0, 600 y: CPU s / late window ms/tick | 29.7 / 198 | 24.9 / 183 |
| ... migration / sharing / perception, s | 3.97 / 5.87 / 1.89 | 2.09 / 3.82 / 0.84 |
| 1k synthetic: CPU ms/tick / calls/unit/tick | 157 / 300 | 130 / 296 |
| 10k synthetic: CPU ms/tick / calls/unit/tick | 2,327 / 232 | 2,022 / 231 |
| Fixed density, 500 / 1k / 2k / 4k: µs/unit/tick | 156 / 146 / 164 / 169 | 150 / 146 / 148 / 157 |
| Varied density, 250 / 1k / 4k: µs/unit/tick | 149 / 159 / 169 | 133 / 128 / 148 |
| Peak RSS: 1k / 2k / 4k at fixed density; 1k on 100×100 | 131 / 291 / 788; 244 MB | 136 / 309 / 918; 258 MB |
| Belief store at 4k units (fixed density): allocated / active rows | per-unit arrays | 736 MB, 4,651 / 4,355 rows, 16 in-place resizes |

- Belief memory is unchanged in kind: active beliefs still cost 13 bytes per unit per cell
  (689 MB for 4,355 units on 12,769 cells). The store adds up to 25% of allocated but
  unused rows (7% in this case), and RSS for large stores is +5-16% over PH2. **The dense
  belief memory problem is not solved**; the sparse backend is later work.
- Migration and sharing lost their per-unit belief loops. Calls per unit barely changed:
  those loops were numpy-heavy rather than call-heavy.

### PH3b: authoritative `UnitTable` — COMPLETE (2026-10-01); PH4 not yet chosen

State at pause: `make check` green (208 tests), exactness oracle IDENTICAL, golden
fixtures unchanged. Everything below is Level A. Nothing has been benchmarked beyond
`bench-quick`.

Done:
- PH3a sanity check: no attached unit keeps a private belief array; no `BeliefRowView`
  outlives a tick; the store matrix has a single reference (in-place growth works; no
  copy fallback in any benchmark); traced memory grows only with unit count. The remaining
  PH3a RSS excess is store capacity overshoot (≤ 25%) plus allocator behaviour; not
  investigated further.
- `population/table.py` `UnitTable`: authoritative slot-aligned scalar columns
  (`FLOAT_FIELDS`, `INT_FIELDS`, `BOOL_FIELDS`), cohort matrices with an exactly
  maintained `population` column, the knowledge matrix, technology sets plus bitmasks, and
  species codes. One slot per unit, shared with the belief store; the registry allocates
  slots, keeps the ordered slot array (`UnitRegistry.slots()`, registry insertion order)
  and resets rows on release.
- `PopulationUnit` is a view while registered: table fields are descriptors that read and
  write the row (no copy on the object); detached units keep plain values. External state
  (familiarity, residence, report cells, trade ties, harvest history) stays on the object.
- `core/columns.py`: coarse column access per phase (`ctx.columns(state)`), with
  `TableColumns` (production) and `ObjectColumns` (object-authoritative reference,
  `Simulator(unit_table=False)`).
- Converted to columns: energetics, demography (cohort matrices authoritative), farming,
  field planning, foraging, learning, diffusion, innovation, perception, sharing,
  migration (including a batched `MoveHazards`), fission, fusion, trade evaluate,
  extinction, ecology soil management, the recorder, the state aggregates and the per-tick
  invariants (now also checking cached population against cohort sums). Ledger float
  totals stay sequential Python accumulations (bit-identical).
- `tests/test_unit_table.py`: whole-engine differential tests (table vs object
  reference; pressure 160 y, neolithic 220 y, MVP 1 120 y, Hypothesis synthetic states
  with farming): complete unit state, beliefs, familiarity, ties, residence, events, every
  RNG stream.

Quick benchmark (1k synthetic units, CPU): PH3a 130 ms/tick, 296 calls/unit/tick → now
116 ms/tick, ~200-207 calls/unit/tick.

Done 2026-10-01 (items 1-2; `make check` green, 211 tests; oracle IDENTICAL; golden
fixtures unchanged):
- `population/lifecycle.py`: `create_unit` / `remove_unit` / `split_unit` / `merge_units`.
  With a table they apply the `composition` rules directly to table and belief-store rows
  (`UnitTable.copy_row`, `DenseBeliefStore.copy_row` / `merge_row`); a daughter is built in
  place over a claimed slot (`UnitRegistry.claim_slot`, `unit.bound_unit`) instead of
  detached-then-loaded; absorbed and extinct units free their rows without copying state
  back (`UnitRegistry.discard`; a removed object keeps only `EXTERNAL_FIELDS` and raises
  `AttributeError` on table fields). Without a table every function delegates to
  `composition` (reference engine). Fission, fusion, coarsening, extinction and founding use
  it. Relocation and trade transfers write table rows directly (same Python-float
  arithmetic); trade tie decay skips units without ties.
- `tests/test_lifecycle.py`: random create / split / move / merge (both modes) / remove /
  re-technology sequences against the object reference after every operation; freed rows
  reset (scalars, cohorts, knowledge, technology names and bits, beliefs), slot reuse
  exercised, then ordinary ticks stay identical. Mutation-checked (dropping the belief
  merge, the share subtraction, the daughter's group reset or the row reset each fails).
- Quick benchmark (1k synthetic, CPU): 111.5 → 101-103 ms/tick; 207 → 180.5
  calls/unit/tick. Profiled fission apply −70%, fusion apply −45%.

**Found in PH3b:** a frozen semantic bug in `merge_state` (familiarity decay year), reproduced
exactly and deferred; see Section 12.7, B1.

Item 3 (2026-10-01, time-boxed by measured value; every change Level A with a focused
differential test, `make check` green at 214 tests, oracle IDENTICAL):
- **Diffusion trade contacts — done.** `diffusion.merge_trade_contacts`: one flat pass over
  the tie dictionaries into `(receiver, source, value)` arrays, then an exact vectorized match
  against the local pair keys (partner ids are unique per receiver, so each contact gets at
  most one addition) and vectorized positions for appended contacts. 4.25 → 1.88 ms per tick
  at 1k (≈2.4% of a tick). Test: against the PH2 dictionary loop with random local, distant
  and dead ties. The remaining flat pass needs a tie store (arrays instead of per-unit
  dictionaries) — a social-network rewrite, deferred.
- **Capability columns — done.** `energetics.capability_column` finds distinct technology
  sets from the table's bitmasks (`np.unique`; a mask identifies its set exactly) and looks up
  one capability map per distinct set: 0.155 → 0.042 ms per call, 5 calls per tick. Test:
  every capability against `ctx.capabilities(unit)` on random sets.
- **Trade donor search — tried, reverted.** A lazy (cost, id)-ordered scan over cached
  equal-cost cell groups was exact but no faster (A/B 4.0-4.4 vs 4.4-4.7 ms): at 1k units a
  recipient reaches only ~21 cells, offers rarely cover a deficit (no early exit), and the
  existing search is already ~9k dictionary lookups per tick. Candidate discovery is cheap.
- **Foraging familiarity — deferred.** One `effective` pass is 0.36 ms per tick at 1k
  (≈1% for evaluate plus `practice`); reusing evaluate's value in apply would save ≈0.35%.
  A packed sparse familiarity store is not justified by PH3b's profile; revisit for MVP 3
  scale or a memory/data-layout phase.
- **Not changed (measured small):** fusion's `has_reproductive_pair` (~110 calls per tick),
  fission/fusion evaluate (~2 ms each including a spatial index build; the per-unit hazard
  and its interleaved draws stay scalar), innovation (< 1%). Rare structural applies are
  left scalar by design.
- Quick benchmark: 180.5 → 166.6 calls/unit/tick (CPU ms/tick within machine noise,
  ~103 ms).

Item 4 — object↔table sync (cProfile access counting, 1k units, 4 ticks): descriptor and
accessor calls are 0.54 per unit per tick (farming state 0.40), against ~239 reads and ~35
writes per unit per tick in PH2: ≈0.2 ms per tick, versus ≈25 ms in PH2. The remainder is
fusion's `has_reproductive_pair` cohort reads and the lifecycle applies. Normal ticks do
not sync objects with the table.

Item 5 — **PH3b results** (CPU; same 2-core machine; seeded output identical: seed 0 over 600
years ends with 33,070 people and 1,212 units; reports `benchmarks/perf/ph3b_*.json`).

| Benchmark | PH0 | PH1 | PH2 | PH3a | PH3b | PH0 → PH3b |
|---|---:|---:|---:|---:|---:|---:|
| Seed 0, 600 y: CPU s | 41.9 | 35.8 | 29.7 | 24.9 | **17.9** | −57% (2.34×) |
| Late window (~1,086 units): ms/tick (wall) | 328 | 273 | 198 | 183 | **132** | −60% |
| 1k synthetic (40×40): CPU ms/tick | 264 | 210 | 157 | 130 | **102** | −61% |
| ... calls/unit/tick | 509 | 435 | 300 | 296 | **167** | −67% |
| 10k synthetic (40×40): CPU ms/tick | 5,092 | 3,589 | 2,327 | 2,022 | **1,545** | −70% |
| ... calls/unit/tick | 1,064 | 799 | 232 | 231 | **114** | −89% |
| Fixed density 500 / 1k / 2k / 4k: µs/unit/tick | 234 / 221 / 246 / 263 | 230 / 190 / 216 / 227 | 156 / 146 / 164 / 169 | 150 / 146 / 148 / 157 | **96 / 97 / 99 / 106** | −55 to −60% |
| Varied density on 40×40, 250 / 1k / 4k: µs/unit/tick | 228 / 251 / 291 | 185 / 202 / 246 | 149 / 159 / 169 | 133 / 128 / 148 | **92 / 106 / 109** | −58 to −63% |
| 1k units on 100×100: CPU ms/tick | 253 | 207 | 153 | 155 | **103** | −59% |
| Peak RSS: 4k fixed density / seed 0 600 y | 787 / — | 785 / — | 788 / — | 918 / 146 | 913 / 121 MB | |

The 2× stretch target over the freeze is met on every benchmark. Fixed-density cost is flat
within ±5% from 500 to 4k units (linear scaling at constant local density).

Runtime structure:
- Python calls per unit per tick: 167 (1k), 114 (10k), 163-168 (fixed density).
- Object↔table sync: ≈0.5 accessor calls per unit per tick (item 4), effectively zero.
- Transient Python memory per tick: 11 MB at 1k (~11 kB per unit), ~44 MB at 4k on 113×113
  in ordinary ticks. The 4k fixed-density report's ~500 MB mean (also in PH3a) is one
  belief-store growth tick (+25%, 955 MB traced as an allocation; resized in place, RSS
  unaffected) averaged over the two traced ticks, not per-tick churn.

Memory (warmed synthetic states):

| | 1k on 40×40 | 1k on 100×100 | 4k on 113×113 |
|---|---:|---:|---:|
| UnitTable total (capacity rows) | 2.0 MB (1,220) | 2.0 MB (1,220) | 7.6 MB (4,651) |
| ... per live unit: cohorts (91 ages × 2 × int64) / scalars / knowledge+tech | 1,472 / 193 / ~60 B per row | same | same |
| External per-unit object state (familiarity, residence, reports, history, ties) | ~2.1 kB | ~2.0 kB | ~2.0 kB |
| Dense belief store (13 B per unit per cell) | 24 MB | 151 MB | 736 MB |
| Unused slot capacity (table and store) | 14% | 15% | 9% |

Non-belief state is ≈4 kB per unit (half of it the int64 cohort matrices); beliefs are
23-179 kB per unit and grow with world cells. **Dense beliefs are the memory ceiling**: 10k
units on 113×113 would need ~1.7 GB of beliefs, 50k units ~8 GB (beyond this 7 GB machine).

**Hotspots** (py-spy native sampling; share of tick and where the samples' leaves are:
numpy inner loops / numpy call dispatch / interpreter (bytecode, dicts, attributes) /
allocation). Canonical seed 0 over 600 years:

| Component | Share | Kernel / dispatch / interp. / alloc | Class |
|---|---:|---|---|
| Knowledge sharing (select + receive reports) | 20% | 65 / 9 / 12 / 14 | pair/contact processing (numpy-bound) |
| Demography | 11% | 41 / 40 / 12 / 7 | numeric kernel (many small numpy calls) |
| Foraging evaluate (per-cell solver, single-group fast path) | 11% | 8 / 11 / 77 / 4 | numeric kernel in scalar Python |
| Migration evaluate | 10% | 33 / 21 / 38 / 7 | numeric kernel + per-unit Python |
| Diffusion evaluate | 9% | 28 / 19 / 45 / 8 | pair/contact processing + Python containers (ties, adoption loop) |
| Fission/fusion apply | 7% | 8 / 25 / 59 / 8 | structural event |
| Field planning (agriculture evaluate) | 6% | 17 / 12 / 54 / 17 | numeric kernel in scalar Python (exact investment rule) |
| Fission/fusion evaluate | 5% | 7 / 20 / 71 / 3 | Python scalar hazards with interleaved draws |
| Innovation | 5% | 15 / 28 / 50 / 7 | Python container/state lookup (per candidate) |
| Ecology | 4% | 23 / 27 / 36 / 13 | numeric kernel |
| Trade evaluate + apply | 3-8% | ~90% interpreter | Python container/state lookup (tie dictionaries) |

Whole tick: numpy kernels 31%, numpy dispatch 18%, interpreter 41%, allocation 10%
(canonical); 1k synthetic 34 / 17 / 41 / 8; 4k fixed density 34 / 16 / 42 / 8 (migration
then leads at 19%); **10k on 40×40: 65 / 10 / 19 / 6, with knowledge sharing 52% and
diffusion 13% of the tick (pairwise contacts, 74 per unit)**.

PH3b is complete. Stop before PH4: the PH4 choice is a decision (Section 9.2 rule).

### PH4a: selective compilation of interpreter-bound numeric kernels — COMPLETE (2026-10-01)

Numba (0.68, `numba>=0.68.0`; numpy unchanged at 2.5.3) behind one policy in `core/jit.py`
(`kernel`): nopython, `fastmath=False`, `error_model="python"`, `cache=True`, no
`parallel`/`prange`, no Numba RNG. `MADEXPLORER_JIT=0` runs the same kernel source as plain
Python. All Level A: `make check` green (526 tests), oracle IDENTICAL, golden fixtures
unchanged. B1 (Section 12.7) is untouched (merges are not compiled).

Exactness facts established (and tested), needed by any future kernel:
- Numba `math.exp`/`math.expm1` equal CPython's (both libm) on 500k inputs; no FMA
  contraction with `fastmath=False`.
- `ndarray.sum()` (float64) is numpy's pairwise sum *from zero*:
  `jit.numpy_sum` (tested for lengths 0-300, 383, 1,000, 1,031, 4,097, 9,000, 100,003).
- The builtin `sum()` of floats is compensated (Neumaier) since Python 3.12:
  `jit.python_sum` (tested against the builtin with signed zeros and extremes). A
  sequential `+=` is *not* equivalent — the first foraging transcription differed by 1 ulp
  in a cell's target and was caught by the scalar differential test.
- Python's `min`/`max` argument-order semantics (first extreme wins) are written out;
  float `** int` is C `pow` (`math.pow`), not repeated multiplication.
- numpy's `np.exp`/`np.log` equal libm on this AVX2 machine, but numpy dispatches its own
  SIMD versions on AVX-512 hardware, so a kernel replacing numpy transcendental *array*
  calls would be exact only per platform: not Level A. Kernels only transcribe scalar
  `math` calls.
- Numba's on-disk cache is unreliable for a self-recursive function linked into another
  cached kernel: a warm cache segfaulted (single process and ensemble workers). The
  pairwise sum uses an explicit stack instead.

Compiled (one coarse call per subsystem per tick; Python references kept as
`_evaluate_reference`, differential-tested):
- **Foraging** (`economy/foraging_kernel.forage_groups`): every (cell, species) group's
  shared-pool solve (single-group and multi-group paths, Newton then bisection, shared
  per-cell depletion across species). Tests: scalar rules on random groups (zero stocks,
  zero labor/efficiency, unmet/met/boundary targets, equal returns, groups > 128),
  whole-evaluate equality with farming on/off, forced shared cells, and two species in one
  cell. evaluate 8.3-13.4 → 2.2-2.4 ms at ~1k units; the remainder is the shared input
  preparation (familiarity lookup, need, labor).
- **Field planning** (`economy/agriculture_kernel.plan_fields`): per-unit decisions (both
  `field_growth_to_target` and `adjusted_fields_ha`, both tenure rules) and per-cell arable
  sharing. Tests: whole-evaluate equality over random hazards (NaN/0/1), residence, fields,
  thresholds, crowded cells and all mechanism combinations; `math.pow` against `**`.
  3.9-4.7 → 1.6-1.7 ms.

Measured and not compiled:
- **Migration**: no tight interpreter loop — cost is spread over numpy candidate work (need
  9%, belief gather 9%, utilities ~10%, shrinkage/food utility ~8%; the per-unit hazard
  loop ~7% of 6.4 ms). A fused kernel would replace numpy `exp`/`log`/`power` array calls
  (platform-dependent exactness, above) for ~1-2%. Deferred.
- **Demography**: binomial draws are ~40% (must stay on the named numpy streams); the rest
  is matrix `exp`/logistic terms (same exactness caveat). Deferred.
- **Trade**: the deficit/transfer loop runs on string-id ordering, offer dictionaries and
  reachability dictionaries, not numeric inputs. Deferred (container work).
- Knowledge sharing, diffusion, fission/fusion, innovation, ecology: not targeted (pair
  processing, RNG-interleaved or container-bound; see PH3b hotspots).

Benchmark harness: synthetic cases now compile/load kernels before timing
(`benchmark.warm_kernels`: the compiled evaluates on a throwaway context, no draws, no state
change; `jit_warm_seconds` in reports). Timed runs (`bench runs`) include the load.

**PH4a results** (CPU; same 2-core machine; seeded output identical). Canonical figures are
a same-session alternating A/B against PH3b (worktree at `abfa41a`), two runs each; the
recorded PH3b report said 17.9 s, the same-session reruns 17.5 s.

| Benchmark | PH0 | PH1 | PH2 | PH3a | PH3b | PH4a |
|---|---:|---:|---:|---:|---:|---:|
| Seed 0, 600 y: CPU s | 41.9 | 35.8 | 29.7 | 24.9 | 17.9 (17.5) | **15.4-15.5** |
| Late window: ms/tick (wall) | 328 | 273 | 198 | 183 | 132 (121-122) | **104-107** |
| 1k synthetic (40×40): CPU ms/tick | 264 | 210 | 157 | 130 | 102 | **90** |
| ... calls/unit/tick | 509 | 435 | 300 | 296 | 167 | **126** |
| 10k synthetic (40×40): CPU ms/tick | 5,092 | 3,589 | 2,327 | 2,022 | 1,545 | 1,609 (noise; pair-bound) |
| ... calls/unit/tick | 1,064 | 799 | 232 | 231 | 114 | **105** |
| Fixed density 500 / 1k / 2k / 4k: µs/unit/tick | 234 / 221 / 246 / 263 | 230 / 190 / 216 / 227 | 156 / 146 / 164 / 169 | 150 / 146 / 148 / 157 | 96 / 97 / 99 / 106 | **84 / 91 / 96 / 95** |
| Varied density 250 / 1k / 4k: µs/unit/tick | 228 / 251 / 291 | 185 / 202 / 246 | 149 / 159 / 169 | 133 / 128 / 148 | 92 / 106 / 109 | **86 / 90 / 114** |
| 1k on 100×100: CPU ms/tick (paired A/B) | 253 | 207 | 153 | 155 | 103 (105-110) | **91-95** |
| 4k on 40×40, paired A/B: CPU ms/tick | | | | | 503-513 | 486-502 (−3%) |

- PH0 → PH4a canonical: **41.9 → 15.5 s (2.7×)**; PH3b → PH4a −12% (same session).
- Python calls 126/unit/tick at 1k; transient Python memory per tick unchanged (10.8 MB at
  1k).
- **Peak RSS: +~100 MB fixed per process** (Numba/LLVM): canonical 122 → 226 MB, 4k fixed
  density 913 → 1,024 MB. Per-unit state unchanged.
- **JIT cost**: cold cache (first ever run, or source changed) ~4.0 s of compilation in the
  first tick; warm cache ~0.3 s load (+ Numba import ~0.1 s). Spawned ensemble workers
  reuse the on-disk cache (`__pycache__`, gitignored).
- **Experiment throughput** (4 canonical seeds × 600 y, `--jobs 2`, wall / total CPU incl.
  workers): PH3b 38.1 s / 63.2 s; PH4a cold cache 38.4 s / 65.3 s (both workers compile);
  **PH4a warm cache 34.1 s / 56.0 s (−10% wall)**. Short runs pay the fixed load; long and
  repeated runs gain.

Hotspots, canonical seed 0 over 600 years (py-spy native samples; columns: compiled /
numpy kernel / numpy dispatch / interpreter / allocation):

| Component | Share | Mix | Class |
|---|---:|---|---|
| Knowledge sharing (select + receive) | 21% | 0 / 60 / 11 / 20 / 9 | pair/contact |
| Demography | 11% | 0 / 32 / 40 / 23 / 5 | NumPy numeric (+ RNG) |
| Foraging evaluate | 10% | 38 / 5 / 4 / 43 / 10 | compiled numeric + container lookup (familiarity, inputs) |
| Diffusion | 10% | 0 / 24 / 20 / 50 / 6 | pair/contact + container lookup (ties, adoption loop) |
| Migration evaluate | 9% | 0 / 31 / 11 / 47 / 10 | NumPy numeric (candidate arrays) |
| Fission/fusion apply | 6% | 0 / 13 / 30 / 45 / 11 | structural event |
| Fission/fusion evaluate | 5% | 0 / 17 / 12 / 69 / 2 | Python interpreter (scalar hazards, interleaved draws) |
| Innovation | 5% | 0 / 17 / 33 / 46 / 5 | container lookup |
| Ecology/world subsystems | 4% | 0 / 21 / 26 / 48 / 5 | NumPy numeric |
| Field planning | 3% | 2 / 29 / 26 / 26 / 16 | NumPy numeric (inputs) + compiled |
| Trade | 3% | 0 / 11 / 6 / 76 / 7 | container lookup |

Whole tick: compiled 4%, numpy kernels 30%, numpy dispatch 18%, interpreter 40%, allocation
8%. The interpreter share is now spread over container state (familiarity, ties, ids,
event-producing loops) and RNG-interleaved scalar rules; no remaining tight numeric loop
dominates. Compiling further is low-value until the containers become arrays.

**Belief occupancy and access** (PH4b design input; instrumentation only, canonical seed 0
over 600 years and warmed synthetic states):

| | canonical y100 | y300 | y600 | 1k on 40×40 | 1k on 100×100 | 4k on 113×113 |
|---|---:|---:|---:|---:|---:|---:|
| Units / cells | 10 / 1,600 | 96 / 1,600 | 1,212 / 1,600 | 1,077 / 1,600 | 1,106 / 10,000 | 4,433 / 12,769 |
| Current (within memory) cells per unit, p10 / p50 / p90 / max | 34 / 42 / 52 / 55 | 34 / 46 / 54 / 61 | 38 / 53 / 66 / 105 | 29 / 48 / 63 / 102 | 23 / 36 / 46 / 62 | 29 / 45 / 56 / 86 |
| ... as % of cells (mean) | 2.7% | 2.8% | 3.3% | 3.0% | 0.35% | 0.34% |
| Ever-observed cells per unit, p50 / max | 71 / 90 | 114 / 196 | 171 / 390 | 49 / 102 | 36 / 62 | 45 / 89 |

- Current knowledge is ~35-55 cells per unit and does **not** grow with the world; ever-observed
  entries accumulate (11% of a 40×40 world by year 600) because expired entries are never
  removed and fission copies them. A sparse store that prunes expired entries holds
  ~50-70 entries per unit: ~25× less than dense on 40×40, ~200× on 113×113.
- Access is point access only (no row scans in ordinary ticks), per unit per tick:
  reads — report receipt ≤ 28-38 (own year and hops), report selection 11-32, migration
  20-23 (year of every reachable cell) plus the gather of the known ones; writes —
  perception + accepted reports 24-30. Row operations are rare (per 600 years: 3,970 row
  copies at fission, 2,746 merges, 6,730 resets).
- Migration asks about a reachable cell with no current belief 0.1% (canonical) to 3% (large
  sparse worlds) of the time; almost all lookups hit known cells.
- Implication: a hash/open-addressing or sorted-key per-unit sparse row with expiry
  pruning must serve ~120-140 random point lookups/updates per unit per tick cheaply and
  in batches; the batched gather/scatter interface already isolates every access site
  (perception, report selection, report receipt, migration).

PH4a is complete. Stop: the next step is a decision (PH4b sparse beliefs is the planned
scaling task; pair processing only after re-assessing MVP 3 regimes).

### PH4b: scalable belief storage — COMPLETE (2026-10-01)

**Semantic audit (gate).** No model path distinguishes an expired belief (``year <= t -
memory_years``) from a never-observed cell:
- migration (batched and reference) keeps only current cells before reading any value;
- report selection filters on currency (and report age);
- report receipt compares an incoming report with the receiver's own entry; encounters are
  same-species (equal memory), and a report is current for the sender, so it is strictly
  fresher than any expired own entry: accepted whether that entry is expired or absent;
- fusion keeps the freshest entry per cell: a current entry always beats an expired one,
  so the merged current entries do not depend on expired ones; fission copies;
- perception only writes; food priors come from this year's observations;
- remaining readers are diagnostics (traced-unit events read current candidates only;
  benchmark counters);
- expiry is monotone (an entry's year never changes; time only advances).
Pinned by `tests/test_belief_expiry.py`: erasing every expired entry from the dense store
before each tick leaves trajectories, ledgers, events, every RNG stream and all current
beliefs identical (neolithic 260 y, pressure 200 y, MVP 1 150 y, 300 dense synthetic
units over 40 y with migration). Physical deletion of expired entries is therefore Level A.

**Representation choice (prototyped on recorded traces).** Every belief access is a
batched point read or write at (slot, cell) pairs, ~120k per tick at 1k units (writes 29k,
gathers 50k, year lookups 22k, year+hops 20k), ~480k at 4k; row operations are rare
(hundreds per 10 ticks). Two numeric layouts were prototyped in Numba and replayed against
the trace (both exact on current entries): A, sorted packed rows (binary search, shift on
insert) and B, open-addressed per-row tables. Gather/scatter for 10 ticks: dense 31.5 /
13.6 ms (1k, 40×40) and 310 / 94 ms (4k, 113×113); A 22.3 / 11.9 and 120 / 49; B 11.9 / 8.5
and 84 / 40. **A was chosen**: within ~1 ms/tick of B at 1k, ~1.5× more compact, and its
lifecycle (row copy, sorted merge, compaction, deterministic iteration) is simpler. No
per-unit Python dictionaries, no row-size cap.

**`SparseBeliefStore`** (`population/beliefs.py`, kernels in `population/belief_kernels.py`):
each unit's row is its observed cells sorted by id in shared pools (`cell` int32, `year`
int32, `food` float32, `population` int32, `hops` int8; 17 B per entry) with per-slot start,
length and capacity. A missing cell reads exactly as a never-observed dense entry
(`NEVER_OBSERVED`, 0, 0, 0). Rows double when full (no maximum). Expired entries are dropped
wherever a row is rewritten anyway: a full row is pruned in place before it would grow;
copies (fission) and merges (fusion) keep current entries only; the pool is compacted
(rows rewritten contiguously without expired entries) when released capacity exceeds half
of it. There is no annual traversal: pruning is amortized over the insertions that filled a
row and compaction over the releases that created garbage. The store learns horizons from
`configure_expiry(memory by species code)` and `set_clock(year)` (set by `Simulator.step`
only, so pruning can lag but never precede semantic expiry). `view()` is a read-only dense
copy; all writes go through `scatter`/`assign` (`BeliefPatch.apply` now writes through the
store for registered units). `DenseBeliefStore` is unchanged and remains the reference.

Interface changes (Level A on dense; oracle IDENTICAL): the two direct dense indexings
(migration's years of reachable cells, report receipt's own year/hops) go through
`store.years` / `store.years_and_hops`; stores take the species code at `claim`; both
stores provide `entries(slot)` (logical comparisons) and `stored_entries`.

**Backend selection:** `Simulator(belief_backend=...)`, `--beliefs dense|sparse|auto` on
`run`, `ensemble` and `bench` (sets `MADEXPLORER_BELIEFS`, inherited by spawned workers),
default **dense**. `auto` is static: sparse from 2,500 cells (above 50×50), dense below.
The resolved backend is recorded in every run manifest (`belief_backend`) and benchmark
storage report. Backends never switch during a run.

**Exactness.** `make check` green (538 tests) on the dense default and with the whole suite
forced onto sparse (`MADEXPLORER_BELIEFS=sparse`: 538 passed, golden fixtures included).
Raw oracle (dense) IDENTICAL; new logical oracle (`exactness_oracle.py --logical`, current
belief entries instead of raw rows; reference `benchmarks/perf/oracle_ph4b_logical.json`
recorded with dense): sparse IDENTICAL. Tests (`tests/test_belief_backends.py`): whole
engine dense vs sparse (neolithic 320 y, pressure 220 y, MVP 1 160 y; object-reference
engine 150 y; dense synthetic states 30 y with and without farming) comparing everything
plus current beliefs; randomized store sequences (claim, release, writes of fresh and stale
observations, reads, copies, merges, assigns, advancing clock: observe → expire → delete →
revisit) with a tiny pool forcing growth and compaction (60 examples in CI; 1,000 run once,
1,064 compactions); read-only views; static backend resolution. Tests that inspect dense
internals now say so (`belief_backend="dense"`) or compare logically; B1 is untouched.

**Results** (CPU, same machine; synthetic cases one run each, ±5-10% noise):

| Case | Dense: CPU ms/tick, RSS, belief MB | Sparse: CPU ms/tick, RSS, belief MB | Belief memory |
|---|---|---|---:|
| Canonical seed 0, 600 y (CPU s, alternating ×2) | 15.7-16.9 s, 224 MB | **15.1-15.6 s, 205 MB** | — |
| 1k on 40×40 | 91, 211 MB, 21.6 | 95, 189 MB, 1.6 | 13× |
| 1k on 100×100 | 103, 360 MB, 148 | 99, 210 MB, 2.6 | 58× |
| 2k on 80×80 (fixed density) | 229, 409 MB, 172 | 200, 229 MB, 5.8 | 30× |
| 4k on 113×113 (fixed density) | 403, 1,042 MB, 689 | 416, 294 MB, 8.7 | 79× |
| 10k on 180×180 (fixed density) | (~4.2 GB of beliefs) | 1,073, 469 MB, 19.7 | ~210× |
| 20k on 255×255 (fixed density) | (~17 GB of beliefs) | 2,221, 797 MB, 44.3 | ~380× |

- Sparse CPU is within noise of dense at every size (−13% to +4%); the canonical run is
  not slower. Fixed-density sparse cost: 97 / 100 / 106 / 109 µs/unit/tick at 2k / 4k / 10k
  / 20k units (near-linear).
- Sparse storage: 40-52 current entries per unit and as many stored (pruning keeps stored ≈
  current); 17 B per entry, 30-65 B per current entry including pool headroom and the slot
  index (pool / stored entries 1.7-3.8: row doubling, ×1.5 pool growth, garbage below the
  compaction threshold); ~1.6-2.8 kB per unit at every world size, versus 13 B × cells
  (21-845 kB) dense.
- Per operation (trace replay, ns per element, dense / sparse): gather 23 / 18 (1k) and
  62 / 24 (4k); year lookup 7 / 16 and 19 / 19; year+hops 11 / 21 and 29 / 27; scatter
  40 / 57 and 66 / 68; row copy 14 / 13 µs, merge 132 / 32 µs, claim 73 / 2 µs at 4k;
  compaction of the whole store 0.5 ms (1k) / 14 ms (4k). Logical mismatches after replay: 0.
- RSS is now dominated by the unit table, unit objects and the fixed Numba/LLVM ~100 MB, not
  beliefs (20k units: 797 MB total, 44 MB beliefs).

**JIT prewarm for ensembles.** `prewarm_kernels(scenario)` runs two years of a copy of the
scenario (kernels compile for production argument types) and exercises the sparse row
operations on spare slots; `run_ensemble` calls it before starting workers (`--no-prewarm`
to skip); `madexplorer jit-warmup <scenario> [--beliefs ...]` fills the cache explicitly.
Compile costs: PH4a kernels ~3.9 s cold, sparse-store kernels ~2.3 s more, ~0.35 s to load
when cached. Ensemble, 4 seeds × 600 y, 2 jobs (dense): cold without prewarm 39.6 s wall /
66.2 s CPU; **cold with prewarm 37.6 s / 60.0 s**; warm cache 34.2 s / 57.1 s. Prewarming
saves the duplicate compilation (−2 s wall, −6 s CPU here; more with more workers); only a
warm cache removes the compile entirely (the cache persists across runs until the kernel
sources change).

**Backend policy recommendation:** sparse is exact, never materially slower and an order of
magnitude or more smaller from 1k units on medium worlds; keep dense as default and
validation reference for now (per plan), use `--beliefs sparse` (or `auto`) for scale work,
and decide on making sparse/auto the production default after the scaling campaign.

PH4b is complete. Stop: next is the realistic scaling campaign (1k-50k units at constant
local density, sparse beliefs), not a predetermined optimization.

### PH5: scale and MVP 3 readiness — measurement campaign (2026-10-01)

One committed implementation for every point (`f894f6a`, no engine changes during the
campaign), `--beliefs sparse`, warm JIT cache (`jit-warmup` first; kernels loaded in
0.3-0.5 s), synthetic valid states at constant local density (world side
`40·sqrt(U/500)`; units drawn on land cells), 20 years of belief warm-up, then untimed and
timed ticks. Scripts: `scripts/perf/ph5_scale.py` (one size per process: timing, contacts,
occupancy, deep-size memory breakdown, ordinary-tick allocation, call counts) and
`scripts/perf/ph5_steady.py` (equal-age timing); reports `benchmarks/perf/ph5_scale_*u.json`.

**Scaling table** (CPU on one core of this 2-core machine; "short" = 2 untimed ticks,
"equal age" = 10 untimed ticks, the fair comparison — see below):

| Units (mean) | World | Units / land cell | Units per occupied cell (mean; p99, max) | CPU ms/tick short | µs/unit/tick short | µs/unit/tick equal age | Peak RSS | Accounted bytes/unit | Beliefs/unit (entries; bytes) | Sharing pairs / diffusion contacts per unit |
|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 2,141 | 80×80 | 0.47 | 1.07 (2, 4) | 173 | 80.8 | 95.1 | 247 MB | 19.8 k | 45.9; 2.7 k | 3.9 / 6.3 |
| 5,322 | 126×126 | 0.47 | 1.07 (2, 6) | 441 | 82.8 | 95.1 | 361 MB | 19.6 k | 46.5; 2.5 k | 3.9 / 6.0 |
| 10,608 | 179×179 | 0.46 | 1.06 (2, 6) | 873 | 82.3 | 103.5 | 583 MB | 20.1 k | 45.0; 2.8 k | 3.7 / 5.7 |
| 21,006 | 253×253 | 0.45 | 1.06 (2, 6) | 1,964 | 93.5 | 99.1-104.4 | 934 MB | 19.0 k | 44.0; 2.1 k | 3.7 / 5.4 |
| 52,558 | 400×400 | 0.45 | 1.07 (2, 10) | 5,674 | 108.0 | 112.1 | 2,534 MB | 20.4 k | 45.8; 2.9 k | 3.8 / 5.6 |

- **Fixed-density cost is nearly flat**: 95 → 112 µs/unit/tick from 2k to 50k units at equal
  state age (+18% over 25×). T(U)/U has no super-linear term; contacts per unit are constant
  (sharing 3.7-3.9 pairs, diffusion 5.4-6.3 contacts), and so is the cost per contact
  (sharing 3.5-4.9 µs per candidate pair, diffusion 0.8-1.0 µs per contact): pair work grows
  only because there are more (scientifically required) contacts, linearly.
- The residual drift is (1) lazy reachability searches for newly visited origin cells (a
  Python shortest-path search per origin, cached: 3% of the short-run tick at 2k, 13% at 10k,
  19% at 50k, falling to ~6k new origins per 3 ticks at 50k once warmer; a one-time cost of a
  few seconds per run in long simulations, but 1.8 kB of cache per origin) and (2) locality
  on larger arrays. Nothing is quadratic.
- The synthetic state is not stationary: groups grow and accumulate knowledge, trade ties
  and familiarity (10 more ticks at 20k: units +13%, trade edges and familiarity entries
  ×2). Costs per unit rise with state age, not with scale; compare equal ages.
- Python calls per unit per tick: 131.5 (2k), 136.9 (10k).
- Ordinary-tick transient allocation (tracemalloc peak, storage-growth ticks excluded):
  22.6 MB (2k), 111 MB (10k), 560 MB (50k): a constant ~10.6 kB per unit per tick. By
  subsystem at 5k (peak within the subsystem): demography 9.4 kB/unit (cohort-matrix
  temporaries), migration 5.6, knowledge sharing 3.9, perception 2.3, others ≤ 1.6.

**Runtime profile** (py-spy native; share of tick; columns compiled / numpy kernel / numpy
dispatch / interpreter / allocation for the whole tick):
- 2k: knowledge sharing 17%, demography 11%, migration 11%, fission/fusion 12%, innovation
  (bursty in that window) 23%, diffusion 5%, trade 6%; whole tick 1 / 30 / 17 / 45 / 7.
- 10k: knowledge sharing 22%, migration 21%, demography 11%, trade 10%, innovation 6%,
  fission/fusion 10%, diffusion 5%, foraging 7%; whole tick 1 / 27 / 15 / 50 / 6.
- 50k: migration 26% (75% interpreter; 19% of the tick is first-visit reachability search
  and 15% reachability lookups), knowledge sharing 20%, demography 14%, trade 15% (96%
  interpreter), diffusion 5%, fission/fusion 10%; whole tick 0 / 27 / 14 / 54 / 5.
- Equal-age timers (10k, ms/tick): innovation 256 (21%), knowledge sharing 234 (19%),
  migration 191 (16%), fission 111, demography 104, trade 82, fusion 77, perception 75,
  diffusion 73, foraging 57, field planning 16.
- Classification: pair/contact processing (sharing + diffusion) ~25%; Python/container
  traversal ~45-55% spread over migration's per-unit reachability, trade's dictionaries,
  innovation's per-candidate path and fission/fusion hazards; NumPy numeric (demography,
  sharing arrays) ~30-40%; structural events ~10%; compiled numeric ~1% (foraging and
  field planning are now cheap); recording negligible. No single component dominates.

**Memory breakdown** (deep size of everything reachable from the simulator, 50k units;
bytes per unit):

| Component | MB | B/unit | Scales with |
|---|---:|---:|---|
| Static world structures (NeighborGraph lists, world arrays, life tables, forage) | 302 | 6,034 | cells |
| Movement reachability caches (dict + arrays per visited origin) | 221 | 4,402 | visited cells |
| Sparse beliefs | 149 | 2,979 | units |
| Unit table (of which cohorts 94 MB, int64 [U, 2, 91] + 25% row slack) | 111 | 2,216 | units |
| Unit objects (object + `__dict__`) | 79 | 1,569 | units |
| Harvest history deques | 45 | 902 | units |
| Perceived-cell cache | 32 | 645 | units' cells |
| Familiarity maps | 31 | 614 | units |
| Report cells | 24 | 479 | units |
| Residence dicts | 14 | 288 | units |
| Trade ties | 13 | 258 | units |
| Neighborhood table, ecology, events, compiled, registry, rest | 35 | ~690 | |
| **Accounted** | **1,058** | **20.4 k** | |

- Python-side per-unit object state: **4.0 kB per unit** at every size (objects, dicts,
  deques, ties, familiarity, report cells); numeric per-unit state 4.2-5.0 kB (beliefs +
  unit table). The largest single memory items are Python containers keyed by *cells*:
  `NeighborGraph` (lists of lists, ~650 B per cell, per movement model) and the
  reachability caches.
- RSS (2.3 GB now, 2.5 GB peak at 50k) = ~170 MB fixed (interpreter, numpy, Numba/LLVM) +
  1.06 GB accounted state + allocator retention of the ~0.56 GB per-tick temporaries + ~0.5
  GB unattributed (heap fragmentation, arena slack, objects outside the simulator graph).

**Experiment projections** (measured equal-age CPU per tick, one core per run; real runs
start small and grow, so these are upper bounds for runs that sustain the size):

| Sustained units | 600 y | 1,000 y | 5,000 y | RSS per worker |
|---|---:|---:|---:|---:|
| 10k | 0.2 h | 0.3 h | 1.7 h | ~0.6 GB |
| 20k | 0.4 h | 0.7 h | 3.3 h | ~0.9 GB |
| 50k | 1.1 h | 1.8 h | 9.2 h | ~2.5 GB |

- 4 seeds × 600 y at 50k: 2.2 h on this 2-core / 7 GB machine (2 workers, ~5 GB); 8 seeds
  4.4 h. On a 16-core / 64 GB machine (16 workers fit in memory): 8 seeds in ~1.1 h, 16
  seeds × 1,000 y in ~1.8 h. 10k-20k-unit ensembles of 1,000 years are routine.

**MVP 3 memory projection** (planned architecture: group-shared state stays `[U]`; only
distributional state is `[U, S]` and demography `[U, S, sex, age]`):
- Shared, strata-independent: 18.4 kB/unit measured (beliefs 3.0 k, table scalars 0.3 k,
  Python objects 4.0 k, static/world-attributed 11.5 k at this density).
- Distributional `[U, S]`: ~12 float64 variables per stratum ≈ 0.12 kB × S per unit.
- Demography `[U, S, 2, 91]`: 1.87 kB × S per unit with int64 cohorts (0.94 kB × S with
  int32, ample for group-sized counts).

| Units | S = 8: persistent (int64 / int32 cohorts) | S = 16 | Naive per-tick demography temporaries (S = 8 / 16) |
|---|---|---|---|
| 10k | 0.32 / 0.25 GB | 0.47 / 0.33 GB | 0.70 / 1.41 GB |
| 20k | 0.65 / 0.51 GB | 0.94 / 0.67 GB | 1.41 / 2.81 GB |
| 50k | 1.62 / 1.27 GB | 2.36 / 1.66 GB | 3.52 / 7.03 GB |

Persistent state is fine even at 50k × 16 strata. The risk is transient: today's demography
allocates ~9.4 kB of temporaries per unit per tick; multiplied by S as numpy temporaries it
would reach 3.5-7 GB per tick at 50k. Stratified demography must be a fused kernel (or
chunked) with pre-drawn RNG, not S× the current array pipeline.

**MVP 3 CPU risk** (from the equal-age profile; current shares at 10k):
- Would multiply with strata, O(U·S): demography (8-14% today, 40% of it binomial draws:
  RNG volume grows with S and is inherent to stratified cohorts), energetics/nutrition (1%),
  new health and wealth updates, fertility/mortality modifiers; fission/fusion splitting
  distributional vectors (structural, ~10%, rare events: mild); selective migration only if
  decided per stratum later. Naively, demography alone at S = 16 would cost more than the
  whole present tick: it must be compiled and fused.
- Should stay O(U): knowledge sharing, diffusion, innovation, perception, migration
  candidate generation and reachability, trade between groups, beliefs, familiarity,
  technologies, field location, foraging pools (labor may become a per-stratum sum, a
  cheap reduction). These are ~75% of today's tick.

**Python-object memory**: 4.0 kB per unit is held in Python containers (unit objects and
their dicts, deques, familiarity maps, ties), about the same as the numeric unit state.
At 50k it is ~200 MB: not the binding constraint, but lazy unit views and packed
history/familiarity/ties are a clean future reduction. The cell-keyed Python containers
(movement graph lists, reachability dicts, perceived-cell cache: ~550 MB at 400×400) are
the larger and simpler target if worlds grow further.

**Sparse default.** PH5 found no pathology at any size (bounded entries per unit, flat
bytes per unit, no slowdown). Recommendation: make **`sparse` the default** (exact,
never measurably slower, 13-380× smaller), keeping `dense` for the raw-byte oracle, the
expiry-semantics tests and debugging; the backend is recorded in every manifest. Not
changed during the campaign.

**Recommendation: ready for semantic cleanup → MVP 3** (decision-tree case A). CPU per
unit is flat within +18% from 2k to 50k units at fixed density, 50k units run at ~6.6 s per
year in 2.5 GB, and 10k-20k-unit, 1,000-year ensembles are routine. No component
dominates (pair processing ~25%, interpreter work spread across several subsystems), so
another general optimization phase would have diminishing returns. Carry into MVP 3
design, not as a separate phase: (1) stratified demography as a fused compiled kernel with
pre-drawn draws and no S-fold temporaries; (2) int32 cohort counts; (3) optionally, a
packed reachability store (arrays instead of per-origin dicts) and array-backed
`NeighborGraph` if worlds grow beyond ~400×400 or memory per worker matters.

PH5 complete. Next (pending decision): semantic cleanup (B1) with a new reference, then
MVP 3.

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

### 12.7 Known frozen semantic bugs (deferred model corrections)

These are genuine defects that are part of the frozen MVP 2 reference trajectory. They are
preserved exactly during Performance Hardening and must not be fixed in passing: correcting
one is an explicit model-version change with golden re-recording and statistical
revalidation, to be decided after Performance Hardening (before or during the next model
version).

**B1. Merge familiarity decays to the wrong year** (found in PH3b, 2026-10-01).
- *Location:* `population/composition.py`, `merge_state`, the residence loop
  `for cell, year in source.recent_residence.items()`, which shadows the `year` argument
  used by the following `target.familiarity.merge(..., year, ...)`.
  `population/lifecycle.py` `merge_units` reproduces it deliberately (`decay_year`).
- *Intended:* on fusion and aggregation both familiarity maps are decayed to the merge year,
  then population-weighted.
- *Frozen:* they are decayed to the source's last-iterated residence year (dictionary order;
  the merge year only if the source has no residence record), usually earlier than the merge
  year, so merged familiarity is decayed too little and stamped with an early year.
- *Effect:* familiarity after fusion and coarsening; through it, later foraging returns and
  possibly agriculture and migration choices. Only with `mechanisms.familiarity_decay` on
  (without decay a merge takes the per-cell maximum and ignores the year).
- *Why preserved:* changing it changes golden fixtures and long stochastic trajectories of the
  frozen canonical scenarios; Performance Hardening is Level A against that reference.
- *Test:* `tests/test_composition.py::test_merge_familiarity_decay_year_frozen_mvp2_defect`
  pins the frozen behaviour and states that it is a defect.

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
