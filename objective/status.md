# Implementation Status — Current Canonical State

This file is the **forward-looking implementation status** for Mad Explorer after the MVP 2 model freeze.
It intentionally omits the experiment-by-experiment history that accumulated during MVP 2 stabilization.

For scientific/model requirements, read `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` (document version 2.0) first.
For exact provenance, read `baselines/mvp2_1/freeze_manifest.json` (current scientific base) and
`baselines/mvp2/freeze_manifest.json` (historical MVP 2 freeze).
Use this file to answer: **What exists now? What is frozen? What is still limited? What should we do next?**

---

## 1. Current phase

> **Resume point:** MVP 2.1 scientific base established; Performance Hardening complete;
> **MVP 3 ready to begin** with the design of the socioeconomic-strata model (Section 16),
> before any MVP 3 mechanism is implemented.

**MVP 1:** complete.  
**MVP 2:** complete and scientifically frozen (historical reference, reproducible).  
**MVP 2 Performance Hardening:** complete (Section 9).  
**MVP 2.1 semantic cleanup:** complete — B1 corrected; the scientific base for MVP 3.  
**Next scientific milestone:** **MVP 3 — Distributional Society** (design first).

### MVP 2.1 identity (current scientific base)

- Manifest: `baselines/mvp2_1/freeze_manifest.json` (commit: the one adding the manifest)
- Source-tree SHA-256: `55a9ea94b81cf786f3948f43d648696acad20504a540fe8494e09ca44192845c`
- Only semantic difference from MVP 2: B1 (Section 12.7)
- Golden fixtures: `tests/regression/golden/` (MVP 2 versions kept in `baselines/mvp2/golden/`)
- Oracles: `benchmarks/perf/oracle_mvp2_1.json` (raw, dense) and
  `benchmarks/perf/oracle_mvp2_1_logical.json` (logical, any backend); MVP 2 oracles kept
- Reference runs: `baselines/mvp2_1/` (neolithic 4 × 600 y; pressure 4 × 400 y, both arms)

### Frozen MVP 2 identity (historical)

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

## 9. Performance Hardening — COMPLETE (2026-10-01)

The frozen MVP 2 model runs identically (golden fixtures, exactness oracles, RNG streams)
and substantially faster. Full history, measurements and decisions:
`objective/performance_hardening_log.md`; reports `benchmarks/perf/`.

| | MVP 2 freeze (PH0) | Final (PH4b/PH5) |
|---|---:|---:|
| Canonical seed 0, 600 y: CPU | 41.9 s | ~15.5 s (≈2.7×) |
| Late window (~1,086 units): ms/tick | 328 | ~105 |
| Python calls per unit per tick (1k units) | 509 | ~126-137 |
| Scale at fixed density (2k-50k units) | — | ~95-112 µs/unit/year (flat within +18%) |
| 50k units (400×400) | infeasible (dense beliefs ~8 GB) | ~6.6 s/year, ~2.5 GB RSS |
| Beliefs | dense, 13 B × world cells per unit | sparse, ~40-50 current entries/unit, world-size-independent |

Architecture now: authoritative columnar `UnitTable` (`PopulationUnit` is a view);
lifecycle operations on table rows (`population/lifecycle.py`); batched column kernels per
subsystem; Numba kernels for foraging and field planning (`core/jit.py` policy); sparse
belief store as production default (`--beliefs dense` is the reference backend; the
resolved backend is recorded in every manifest); JIT prewarm before ensemble workers
(`madexplorer jit-warmup`).

**Main architectural result:** the next major multiplicative cost is expected to come
from MVP 3 distributional demography (`[U, S, sex, age]` state and its temporaries), not
from the current group-level engine, whose cost per unit is flat in scale and spread over
many subsystems (pair/contact processing ~25%, no single dominant component).

Engineering rules established during hardening (still binding):
- Compiled kernels are exact transcriptions: builtin `sum()` of floats is compensated
  (`jit.python_sum`), `ndarray.sum()` is pairwise from zero (`jit.numpy_sum`), Python
  `min`/`max` keep argument-order semantics, float `** int` is C `pow`; never replace
  numpy *array* transcendental calls with libm in kernels (numpy uses its own SIMD
  versions on AVX-512); no recursion in cached kernels (warm-cache segfault).
- RNG stays on the named Python streams; kernels receive pre-drawn values.
- Expired beliefs are semantically invisible (`tests/test_belief_expiry.py`); stores may
  drop them.
- Two oracles: raw-byte (`exactness_oracle.py`, dense) and logical (`--logical`).
- Future scale optimizations, only if needed: array-backed movement graph and
  reachability store (cell-keyed Python containers ~550 MB at 400×400), lazy unit views
  and packed history/familiarity/ties (~4 kB Python state per unit).

---

## 10. MVP 2.1 semantic cleanup — COMPLETE (2026-10-01)

MVP 2.1 removed the known category-A defect (B1) under an explicit semantic version. Golden
fixtures and oracles were re-recorded intentionally; MVP 2 artifacts stay intact
(`baselines/mvp2/`). Validation (details in `baselines/mvp2_1/freeze_manifest.json`):
mechanism tests of the corrected rule; matched seeds (neolithic 4 × 600 y) diverge
stochastically with unchanged means (final population 22,504 → 22,320, farm share 0.463 →
0.456, sedentary share 0.820 → 0.800, fusions 1,622 → 1,598, no extinctions); pressure
(6 matched seeds × 400 y) keeps cultivation's carrying-capacity effect (population 3.1-3.8×,
density 2.3-2.5×, farm share 0.62-0.67). One statistical check changed: the pressure test's
energy-deficit comparison is pooled over its matched seeds (per seed it flipped on 2 of 6
seeds under MVP 2.1; 6-seed means 0.029 vs 0.038, farming lower); per-seed population,
density and farm-share checks are unchanged.

---

## 11. (Retired) Performance-hardening acceptance criteria

Met and archived in `objective/performance_hardening_log.md`.

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

### 12.6 Belief storage (resolved in PH4b)

Formerly dense per-unit maps scaling with units × world cells. The sparse store (default)
holds only current beliefs (~40-50 entries per unit), independent of world size.

### 12.7 Known semantic defects

**B1. Merge familiarity decayed to the wrong year — fixed in MVP 2.1.** In MVP 2,
`composition.merge_state`'s residence loop (`for cell, year in
source.recent_residence.items()`) shadowed the merge year, so merged familiarity was
decayed to the source's last-iterated residence year (half of all merges in canonical runs,
usually by 10+ years). MVP 2.1 combines both units' effective familiarity at the merge year
(`merge_state`, `lifecycle.merge_units`; tests in `tests/test_composition.py`). Exponential
decay composes and the population-weighted mean is linear in the excess over baseline, so
the systematic effect is small; MVP 2 preserved the defect for freeze equivalence.

Defect audit at MVP 2.1 (status.md, comments, xfails):

| Item | Class |
|---|---|
| B1 merge familiarity decay year | A — correctness bug (fixed) |
| Aggregation not scientifically neutral (12.1; strict xfail) | B — accepted limitation; MVP 3 statistical units |
| Migration food utility mixes wild stock and crop flow (12.2) | B — accepted approximation, deferred |
| Simple ecology (12.3) | C — deferred scientific feature |
| Group-level social state, whole-group migration (12.4, 12.5) | C — MVP 3 |
| Stale README/comments/docstrings, aggregation warning (Section 14) | D — documentation/tooling |

No other category-A defect is known.

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

Performance Hardening is closed; its workflow (profile first, classify every patch as
exact optimization / numerical reformulation / bug fix / model change, smallest coherent
change, golden + oracle checks, before/after measurements) is archived in
`objective/performance_hardening_log.md` and still applies to any future performance work.

### Reproducibility rules

- Use isolated named RNG streams.
- Vectorizing RNG generation is allowed only when stochastic semantics and deterministic ordering remain equivalent.
- Do not reduce the number of independent stochastic decisions merely to make code faster.
- Do not retune coefficients to recover a benchmark trajectory after an optimization.

---

## 16. Gate to MVP 3

MVP 2.1 is recorded and Performance Hardening is complete: MVP 3 may begin, starting with a
careful design of the socioeconomic-strata model before any mechanism is written.

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

Architecture constraints from PH5 (measured, `objective/performance_hardening_log.md`):

- **Shared group state stays `[U]`:** location, species, beliefs, familiarity,
  technologies, most knowledge/culture, the social network, environmental perception,
  group-level migration candidate generation. Do not multiply these by strata.
- **Distributional state is `[U, S]`:** wealth, nutrition, health, occupation, status,
  preferences/autonomy where appropriate.
- **Demography is `[U, S, sex, age]`** and is the main expected multiplicative cost
  (8-14% of today's tick, 40% of it binomial draws). Persistent memory is acceptable
  (50k units × 16 strata ≈ 1.7 GB with int32 counts), but today's per-tick temporaries
  (~9.4 kB per unit) multiplied by S would reach 3.5-7 GB at 50k units: design stratified
  demography from the start as fused/chunked processing with bounded workspace
  (pre-drawn RNG on the named streams → compiled kernel over blocks of units/strata →
  direct writes to authoritative cohort state), not as S copies of the current array
  pipeline.
- **Cohort counts int32** for persistent `unit × stratum × sex × age` bins, after making
  the bound explicit (a bin cannot exceed a unit's population, orders of magnitude below
  2^31); int64 for accumulators and population totals.
- The large-world movement graph/reachability memory is a future scale optimization
  (worlds materially beyond ~400×400), not a prerequisite.

Only distribution-sensitive mechanisms should operate over strata. MVP 3's
adaptive-resolution work must also solve the current aggregation problem by allowing
fractions/strata inside a statistical unit to respond differently rather than converting
merged populations into one homogeneous decision-maker.

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
baselines/mvp2/  MVP 2 freeze manifest, compact reference runs, MVP 2 golden fixtures
baselines/mvp2_1/ MVP 2.1 manifest and reference runs (current scientific base)
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

> **MVP 2.1 scientific base established (B1 fixed); Performance Hardening complete; MVP 3
> ready to begin — design the socioeconomic-strata model before implementing it.**
