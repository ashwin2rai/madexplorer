# Implementation Status

**Last updated:** 2026-09-24
**Code at time of writing:** `adc1a09` plus uncommitted MVP 2 cleanup changes (the baseline
manifest records `source_tree_sha256`, which identifies the exact sources).
**Current phase:** MVP 2 final stabilization pass (Section 0). The earlier cleanup items 1-11
are done (Section 4); the frozen MVP 2 baseline has not been recorded (Section 9) and is now
the last step of the stabilization pass.

This file records what exists, what was learned while building it, what is broken or
unfinished, and what to do next. The specification is `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`;
section numbers below (§) refer to it.

---

## 0. MVP 2 final stabilization pass: plan and progress

Goal: make MVP 2 faster, less prone to representation artifacts, and validated well enough
to freeze, without starting MVP 3. Work proceeds phase by phase. **Each phase ends at a
checkpoint where work pauses for review and the user decides whether to commit.** Every phase
keeps `make check` green; behavior changes are labelled as model changes and re-record the
golden fixtures in that phase only.

Rules for the whole pass: no tuning coefficients toward a desired trajectory; prefer
reformulations that are both more plausible and cheaper; keep aggregation off in reference
runs; keep the MVP 3 split (shared group-level state: beliefs, technologies, location,
network; distributional state: later strata) in every new data structure.

### Findings from the code audit (before any change)

- `BeliefMap` is four dense cell-length arrays per unit, rebuilt every year by perception
  (full copy, full expiry scan) and by sharing (full copy per unit with partners). Sharing
  transmits every fresher cell of every partner: effectively lossless map synchronization.
- `water_access` in beliefs is a copy of a static, noise-free world field.
- Migration scores every believed reachable cell (hundreds late in a run).
- Field planning amortizes clearing over `min(max(residence_years, 1), horizon)`: past, not
  expected future, tenure. A newly arrived group amortizes over 1 year.
- Initial crop yield = potential × `crop_yield` 0.5 × agricultural efficiency `K/(K+2)` with K
  near the 0.5 adoption bonus (≈0.2), i.e. ≈10% of potential: a likely double penalty.
- Foraging allocation bisects 40 times (`economy/foraging.py`).
- `StepContext.capabilities()` copies the cached capability dict on every call.
- Crop potential and arable area are recomputed by both farming and field planning each year.
- The ensemble uses a default `ProcessPoolExecutor` (no explicit start method, no thread
  limits, scenario and world rebuilt per seed).

### Phases (checkpoint after each)

| Phase | Content (brief items) | Kind of change | Status |
|---|---|---|---|
| P0 | Benchmarks first (18): synthetic performance scenario with 100/500/1000/2000 units for 25-50 ticks (ms/tick, ms/unit/tick, per-subsystem time, peak RSS); benchmark tiers smoke / dev / release / baseline as make targets; record **pre-reform reference timings** (incl. 1,000-year seed 0) for target 19 | tooling | **done** |
| P1 | Belief representation (5-8): mutable per-unit arrays updated in place by sparse `BeliefPatch` proposals (apply touches only listed cells); lazy expiry (validity = `year - observed <= memory` checked on read, no yearly scan); copy on fission/fusion only; drop `water_access` from beliefs (read from the world for known cells); float32 estimates | representation (exact on all golden fixtures and the 1,000-year seed 0) | **done** |
| P2 | Bounded social information (1-4): `SocialReport` (cell, observed year, food, population, confidence, provenance: direct / relayed hops); `social_information.reports_per_interaction` (default 8), `max_report_age`, `transmission_confidence_decay`; senders pick reports by salience (current and recently visited cells, direct observations, unusually good or bad cells), not the whole map; direct observation confidence 1, each relay × decay; migration shrinks food belief toward a prior with weight q | **model change** (small measured effect) | **done** |
| P3 | Bounded migration attention (9-10): `migration.max_considered_destinations` (default ~12) drawn by proximity, recency, direct knowledge and a random exploratory slot, **independent of utility**; then argmax + one move draw as now. Rerun perception-noise experiment | **model change** + experiment | planned |
| P4 | Remaining hotspots (11-16): static scenario context (arable ha, movement tables, neighborhoods, foraging access) built once and reused across seeds in a worker; per-tick `CropState` shared by farming and planning; foraging solver precision benchmarked (12/16 iterations or Newton-bisection) against a 1e-4 relative tolerance; immutable shared capability objects; light ensemble recorder (default for ensembles), full recorder on request; explicit `spawn`/`forkserver` context, one BLAS/OpenMP thread per worker, several seeds per worker. Measure against P0 (target ≥ 2×) | optimization; solver precision is a measured approximation | planned |
| P5 | Agriculture (20-25): expected future tenure `p(1-p^H)/(1-p)` from the unit's current stay probability; review tech × knowledge (candidate: knowledge sets distance to the technology frontier, `e_min + (1-e_min)K/(K+K_half)`, with `e_min` justified behaviorally, not fitted); small experimental cultivation share (2-5% labor) when crop returns are within a band of foraging, as generic subsistence exploration; scenarios A (abundant frontier) and B (intensification pressure); paired cultivation on/off ablation on B as a statistical test replacing the strict xfail | **model changes** + validation | planned |
| P6 | Aggregation rerun (26): off / moderate / aggressive, paired seeds, documented approximation errors | experiment | planned |
| P7 | Freeze (31): canonical scenarios, 32-seed × 1,000-year baseline under `baselines/mvp2`, final status, accepted limitations, git tag `mvp2` (tag only on the user's approval) | release | planned |

Open design choices to confirm during review (defaults proposed, not fixed):

- Prior for shrinking uncertain food beliefs (P2): proposal is the unit's own experience,
  the mean of its *direct* observations in its memory window. It needs no hidden world
  knowledge; an alternative is a vegetation-class expectation.
- Transmission decay default ≈0.7 per hop, with reports older than the memory horizon never
  sent.
- Where a phase's result contradicts the plan (e.g. a reform does not speed things up, or
  agriculture still cannot emerge under pressure), the finding is documented rather than
  forced.

### Progress log

(Entries are added per phase: issue, old behavior, new behavior, assumptions, performance,
validation, remaining concerns.)

#### P0. Benchmarks and pre-reform reference (tooling; no behavior change)

- **Added.** `experiments/benchmark.py` and `madexplorer bench {synthetic,runs}`:
  - *synthetic*: the MVP 2 world with `n` groups of 30 placed on random land cells (own
    placement generator, not a model stream), 20 years of perception + belief sharing only
    (so belief maps reach a late-run state), then 30 timed full ticks. `--farming` gives
    every group all technologies. Reports ms/tick, ms/unit/tick, per-subsystem ms/tick,
    known cells per unit, peak RSS. Each case runs in a fresh `spawn` process.
  - *runs*: ordinary seeded runs with a per-subsystem breakdown.
  - `Simulator.timings` (off by default) accumulates evaluate+apply time per subsystem;
    `Simulator.context()` factored out of `step()`. `numeric_platform()` moved to
    `core/provenance.py` (used by golden tests and benchmark reports).
  - Make targets: `bench-perf` (synthetic), `bench-smoke` (2 seeds × 250 y), `bench-dev`
    (8 × 600 y), `bench-rc` (16 × 1,000 y), `baseline` (32 × 1,000 y → `baselines/mvp2`).
  - `tests/test_benchmark.py`. Golden fixtures unchanged; 120 fast tests pass.
- **Pre-reform reference** (2-core codespace; reports in `benchmarks/perf/p0_pre_reform_*.json`):

  | Synthetic units (mean over ticks) | Known cells / unit | ms/tick | ms/unit/tick | sharing | migration | perception | diffusion | RSS |
  |---|---|---|---|---|---|---|---|---|
  | 100 (116) | 26 | 37 | 0.32 | 3 | 7 | 4 | 2 | 71 MB |
  | 500 (577) | 106 | 171 | 0.30 | 41 | 25 | 18 | 12 | 127 MB |
  | 1000 (1059) | 475 | 362 | 0.34 | 112 | 48 | 38 | 28 | 178 MB |
  | 2000 (1792) | 796 | 677 | 0.38 | 255 | 82 | 60 | 60 | 293 MB |

  Farming variant: same pattern (2000 units: 639 ms/tick, field planning 32 ms).
  **1,000-year seed 0, reference mode: 167.9 s** (final 29,794 people, 1,165 units; peak
  RSS 256 MB). Time by subsystem: sharing 47.5 s (28%), migration 19.0, foraging 15.6,
  perception 15.2, diffusion 14.5, demography 11.2, field planning 8.1, learning 7.3,
  fusion 6.1. **Target 19: ≤ ~84 s (2×) on this machine.**
- **What it shows.** Per-unit cost rises with unit count (0.30 → 0.38 ms/unit/tick) because
  belief sharing scales with units × known cells (41 → 255 ms, 6× for 3.5× units) as maps
  saturate (106 → 796 known cells). Fusion (3 → 24 ms) and diffusion also grow faster than
  linearly; to be checked in P4. P1-P3 target sharing, perception and migration directly.

#### P1. Belief representation (representation change; seeded output unchanged)

- **Old.** `BeliefMap` was immutable: perception copied four cell-length arrays per unit per
  year and scanned them to erase stale entries; sharing copied them again for every unit with
  partners; fission shared the map object; `water_access` (static, noise-free) was stored in
  every unit's map.
- **New** (`population/unit.py`, `mobility/exploration.py`, `mobility/migration.py`):
  - `BeliefPatch(unit_id, cells, year, food_kcal, population)` is the proposal of perception
    and sharing; `apply` writes only those cells into the unit's arrays. Patches carry copies,
    so staged evaluate/apply semantics are unchanged.
  - **Lazy expiry.** No yearly scan: an entry is current in year `t` while
    `observed > t - memory_years`; `BeliefMap.current()` / `known_cells()` apply the test on
    read (migration uses it to pick candidates). Stale entries may be merged or relayed, but
    are always older than any current entry, so this never changes a current belief. This is
    exactly equivalent to the old eager erasure.
  - **Ownership.** A map belongs to one unit; fission copies it (`BeliefMap.copy()`), fusion
    builds a merged map. Copy cost moved from every tick to rare structural events.
  - **Static data out of beliefs.** Water access is read from `world.water_access` for known
    cells; `Observation` and `cell_utility` changed accordingly.
  - **Smaller types.** Food estimates float32 (noise sigma 0.3 ≫ 1e-7 precision), perceived
    population int32, years int32: 12 bytes per cell per unit instead of 32.
- **Validation.** All five golden fixtures unchanged (including after float32); the 1,000-year
  seed-0 run is identical (29,794 people, 500,700 unit-years). New mechanism tests: lazy expiry,
  patches touch only their cells, copies are independent; the Hypothesis sharing test now
  applies the patch and compares with the reference dictionary merge.
- **Performance** (`benchmarks/perf/p1_*`):

  | Synthetic units | ms/tick P0 → P1 | perception | sharing | peak RSS |
  |---|---|---|---|---|
  | 500 | 171 → 166 | 18.4 → 10.6 | 41 → 36 | 127 → 87 MB |
  | 1000 | 362 → 305 | 37.6 → 18.2 | 112 → 96 | 178 → 112 MB |
  | 2000 | 677 → 601 | 60.2 → 32.4 | 255 → 235 | 293 → 165 MB |

  1,000-year seed 0: perception 15.2 → 9.4 s, peak RSS 256 → 185 MB, but total 167.9 →
  168.4 s because every other subsystem measured 3-10% slower in this run. That looks like
  machine timing noise on the shared codespace (roughly ±5%), not a regression: the code
  those subsystems run did not change. Whole-run comparisons below that noise level need
  repeated runs.
- **Remaining.** Sharing still compares whole maps with every partner (O(cells × partners)
  per unit) and is now the dominant cost (≈28% of the run); P2 replaces it with bounded
  reports. Perception's remaining cost is per-unit Python overhead (radius, neighborhood,
  noise draw), addressed in P4 if still significant.

#### P2. Bounded social information (model change)

- **Old.** An encounter copied every partner observation fresher than the receiver's own:
  maps converged toward the whole map (≈800 known cells per unit late in a run), at a cost of
  O(cells × partners) per unit.
- **New** (`mobility/exploration.py`, `species/human.yaml` `social_information:`):
  - Beliefs carry provenance `hops` (0 = direct observation, k = relayed k times); confidence
    `q = decay ** hops` (`transmission_confidence`, decay 0.7).
  - Each sender picks `reports_per_interaction` = 8 reports per year from a small pool: cells
    it perceives this year, cells it lived in within its memory (`recent_residence`, at most
    one per year), and cells it last received reports about (so relaying is possible). Only
    current beliefs no older than `max_report_age_years` (20) qualify. Ranking
    (`social_report_salience`): the current cell first, then
    `q × recency × (1 + |ln(food / prior)|)`, i.e. first-hand, recent and unusually rich or poor
    places first; ties by cell id (deterministic).
  - The receiver takes, per cell, the freshest report (then fewest relays, then earliest
    partner) and adopts it if strictly fresher than its own belief, or as fresh with fewer
    relays; it stores one more relay than the sender had.
  - `belief_shrinkage`: migration evaluates `q·food + (1-q)·prior`. **The prior is the mean
    of this year's direct food observations** (the group's current surroundings), a
    simplification of the agreed "mean of its direct observations in memory" that needs no
    scan of the map. Direct observations (q = 1) are unaffected.
  - Report selection and receipt run once for all units (`select_reports_batch`,
    `receive_reports_batch`); the per-unit `select_reports` / `receive_reports` are thin
    wrappers used by the tests, so the rule exists once. The batched version reproduced the
    per-unit version exactly (1,000-year seed 0 identical).
  - New unit fields with merge/split rules: `food_prior_kcal` (weighted mean / copy),
    `report_cells` (union / copy), `recent_residence` (latest year per cell / copy).
- **Finding: social information barely reaches migration.** When a group decides, nearly all
  cells it can reach in one move are cells it perceived directly that year (after 250 years,
  6 of 818 reachable cells were outside perception), and a same-year direct observation always
  beats a report. So map-wide synchronization cost ~28% of run time for almost no behavioral
  effect, and **the earlier claim that migration chose among hundreds of cells was wrong:**
  candidates are limited by reachability (~20 cells). The remaining winner's curse comes from
  noisy *direct* observations of those ~20 cells.
- **Finding: inherited familiarity grows without bound.** `familiarity` (foraging skill per
  cell) is copied on fission and max-merged on fusion, so by year 850 a unit carries ~540
  cells of lineage familiarity. Using it as "places lived" made report pools huge (sharing
  51 s); replaced by `recent_residence`. The dictionary itself still costs memory and lookups;
  noted for P4.
- **Validation.** Golden fixtures unchanged (≤ 250 years, reports never changed a decision);
  1,000-year seed 0 diverges (28,853 → 29,628 people after the residence fix vs 29,794 in P1).
  Paired dev ensemble, P1 (`d47628d`) vs P2, 8 seeds × 600 years: final population −0.4%
  (−52, se 100), migration rate +0.5% (se 0.3%), final-tail migration rate +0.007 (se 0.003),
  identical technology milestones and invention counts. New mechanism tests
  (`tests/test_exploration.py`, `tests/test_migration.py`): bounded report count whatever the
  map size; current, first-hand and exceptional places first; stale and too-old beliefs not
  passed on; relays add a hop and replace only worse beliefs; freshest-then-least-relayed wins
  between partners; Hypothesis test of vectorized receipt against a one-by-one reference;
  confidence falls per relay; hearsay pulls less than a direct observation but still more
  than an average alternative; residence record bounded.
- **Performance** (`benchmarks/perf/p2_*`; CPU time now recorded because wall time on this
  shared machine varied by up to 2× between runs):

  | | P1 | P2 |
  |---|---|---|
  | Synthetic 2000 units, ms/tick (sharing) | 601 (235) | 545 (120) |
  | Synthetic 1000 units, ms/tick (sharing) | 305 (96) | 321 (52) |
  | Known cells per unit after warm-up (2000 units) | 796 | 44 |
  | Seed 0, 1,000 y: total / sharing / perception / migration | 168 / 48 / 9 / 20 s | 175 (169 CPU) / 30 / 16 / 25 s |
  | Peak RSS seed 0 | 185 MB | 182 MB |

- **Remaining.** Sharing is bounded, but the new per-unit work (hops, prior, residence
  record, shrinkage) added fixed overhead to perception and migration, so the whole run is
  not yet faster. Batching perception and migration per unit is a P4 item. The partner-draw
  loop (one Python iteration per candidate pair) is now the largest part of sharing.

---

## 1. Quick restart checklist

```bash
make install                         # uv sync + pre-commit hooks
make check                           # lint, format check, mypy, fast tests (regression + mechanism)
make test-stat                       # statistical multi-seed model tests (~10-15 min on 2 cores)
make golden                          # re-record exact regression fixtures after an INTENDED change
uv run madexplorer run scenarios/mvp1_sandbox.yaml --years 450 --quiet
#   reference: population=6706 units=250 occupied_cells=199 (was 7282/286/267 before cleanup)
uv run madexplorer ensemble scenarios/mvp2_neolithic.yaml --seeds 0:15 --jobs 2 --years 600
uv run madexplorer compare ensembles/<a> ensembles/<b>        # paired, same seeds
uv run madexplorer ensemble ... --set resolution.max_units_per_cell=8 --set mechanisms.aggregation=true
uv run madexplorer rules -v          # every model rule with rationale (43 rules)
make bench-perf BENCH_LABEL=<name>   # synthetic per-unit benchmark -> benchmarks/perf/
make bench-smoke | bench-dev | bench-rc   # ensemble tiers (2x250, 8x600, 16x1000 years)
```

Exact seeded regressions now live in `tests/regression/golden/*.json` (five fixed cases),
recorded on `numpy=2.5.3 machine=x86_64 baseline=X86_V2 dispatch=X86_V3`. A
behavior-preserving change must leave them untouched; an intended model change re-records
them with `make golden` and says so in the commit. On another numeric platform they skip.

Then pick up at **Section 10, Recommended next steps**.

---

## 2. Decisions made (and why)

| Decision | Reason |
|---|---|
| Package is `madexplorer`, not the spec's working title `socioecology_sim`; CLI is `madexplorer` | Matches the repository name |
| Python 3.13 (spec says 3.12+) pinned in `.python-version`; uv manages it | Widest library support at the time |
| World is procedural with its own seed `world.topology.seed`, separate from `simulation.seed` | Ensembles over run seeds share one map; founders' cells stay valid |
| Species parameters have **no defaults in code**; they live in `species/*.yaml` | §5: humanity must be a profile, not hidden constants |
| Technology tree is data (`technologies/*.yaml`); the engine knows only 4 *capabilities* | Tech trees are hypotheses (§2.2); they can be swapped or ablated without code changes |
| MVP 1 scenario keeps all MVP 2 mechanisms (and crowding mortality) switched off | Keeps it a pure foraging sandbox |
| Annual timestep only (`timestep_years: 1`) | §19 allows annual for MVP; seasonal resolution deferred |
| Units hold exact age×sex cohort vectors instead of distributions | Exact conservation and cheap vectorized demography for MVP 1-2; strata arrive in MVP 3 |
| **MVP 2 reference calibration mode is aggregation OFF** (`scenarios/mvp2_neolithic.yaml`) | Coarsening to 3 units/cell measurably changes outcomes (Section 7.1); 8 units/cell matches the reference within noise |
| Migration uncertainty comes only from beliefs; no per-candidate noise | Removes the best-of-many-noise bias (Section 4, item 1) |
| Three test classes: `tests/regression/`, mechanism tests (default), `tests/statistical/` | §29; exact replay, local causal claims, and distributional claims are different kinds of evidence |

---

## 3. What is implemented

### 3.1 Engine and infrastructure (spec §19-§24, §28-§30, §39)

- **Staged evaluate/apply loop** (`core/subsystem.py`, `core/simulation.py`). Order, documented
  in `build_pipeline()`: climate → ecology → perception → belief sharing → farming → foraging →
  trade → energetics → demography → extinction → field planning → learning → diffusion →
  innovation → fission → fusion → migration → coarsening.
- **Named RNG streams, one per stochastic mechanism** (`core/rng.py`): world, initialization,
  environment, perception, knowledge_sharing, demography, fission, fusion, migration,
  innovation, technology_adoption, trade. Streams are seeded by a stable hash of their names.
  `RngManager.keyed(mechanism, *keys)` gives a generator that depends only on its keys (e.g.
  year and unit id); it is ready for MVP 3, where adaptive splitting would otherwise reorder
  draws, but no subsystem uses it yet (one generator per call is slow).
- **Invariants checked every step** (`core/invariants.py`): population accounting, nonnegative
  cohorts, reserves and stocks, valid cells.
- **Governance registry** (`core/governance.py`): 43 `@model_rule`s with rationale, source type,
  parameters, domain and limitations.
- **Provenance**: git commit, dirty flag, **source-tree SHA-256**, config hash, seeds, model
  version, uv.lock hash, Python/NumPy versions, timestamp, runtime.
- **Merge/split semantics in one place** (`population/composition.py`): every `PopulationUnit`
  field has a declared merge rule and split rule (`FIELD_RULES`); a test fails if a new field
  lacks one. `absorb()` merges and rewires the trade network; `split_off()` divides a unit.
- **Ablation switches**: `mechanisms:` has 14 booleans (new: `crowding_mortality`).
- **CLI**: `validate`, `run`, `ensemble` (`--seeds`, `--jobs`, `--years`, `--set path=value`,
  `--save-runs`), `compare` (paired differences over shared seeds), `inspect`, `rules`.
- **Parameter overrides** without editing files: `Scenario.with_settings({...})` takes dotted
  paths into the scenario (`resolution.max_units_per_cell`), a species
  (`species.human.cognition.observation_noise_sigma`) or the knowledge system
  (`knowledge.innovation.baseline_logit`); unknown paths are errors.
- **Ensemble outputs** (`experiments/ensemble.py`) in `ensembles/<name>/`: `runs.csv` (one row
  per seed: milestones such as first cultivation / first year of each technology / year farming
  first reaches 10, 25, 50% of food; final population, peak, migration rate, sedentary and farm
  shares, soil, crowding hazard and death share, technology prevalence, runtime),
  `summary.csv/json` (n, share of runs reaching each milestone, mean, sd, min, q05-q95, max),
  and `manifest.json`.

### 3.2 MVP 1: ecological-demographic sandbox (complete)

| Area | Implementation | Source type |
|---|---|---|
| Terrain | spectral-noise elevation, sea-level quantile, slope | — |
| Hydrology | priority-flood depression filling, D8 flow accumulation, rivers, freshwater access | theoretical |
| Climate | latitude and lapse-rate temperature, lognormal coastal rainfall, AR(1) global anomalies plus a regional rainfall field | empirical / heuristic |
| Ecology | Miami-model NPP → edible plant and game capacities; logistic regrowth with recolonization | empirical / placeholder |
| Life history | Siler mortality (Gurven & Kaplan forager averages), beta-shaped fertility normalized to TFR, need and labor by age | empirical / heuristic |
| Energetics | pooled sharing, body reserves (60-day cap), thermoregulation cost, travel energy | heuristic |
| Demography | binomial deaths/births per cohort; hazards add by cause (baseline × starvation factor + crowding); fertility falls with food ratio; births need a fertile male in the cell | heuristic |
| Foraging | diminishing returns `A(1−e^{−rE/A})`, satisficing to need +20%, shared pools under crowding, familiarity learning | heuristic |
| Perception | vegetation-occluded radius, noisy observations, memory horizon, neighbor belief sharing | heuristic |
| Migration | perceived utility (log food per head, water, path cost, staleness) of believed cells; argmax destination; one logistic move hazard on its advantage over staying | heuristic |
| Group dynamics | fission hazard (size per group, food stress), fusion hazard (small size, lacking a mate) | heuristic |
| Movement | friction = slope × vegetation; walkers can't cross water; swimmers and fliers supported | heuristic |

### 3.3 MVP 2: agriculture and technology

| Area | Implementation |
|---|---|
| Knowledge | Vector per domain (ecology, agriculture, storage, construction). Per year: `K += a·s·log1p(N·s/n0) − δK`, where `s` is practice from activity shares. |
| Technologies | 6 in `technologies/neolithic.yaml` with knowledge prerequisites, required technologies, a need signal and capability effects. |
| Innovation | Per-candidate hazard = sigmoid(baseline + need + log(K/K_min) + log1p(N/25) + connectivity + surplus − instability + propensity). **Candidates compete as independent risks**: P(any) = 1 − exp(−Σλ), λ = −ln(1 − p); the invented one is chosen with probability λ_i/Σλ. File order is irrelevant. |
| Diffusion | Knowledge flows down gradients from contacts (same cell 1.0, adjacent 0.3, trade ties); adoption at ≥50% of prerequisites, loss below 25% with dependency cascades. |
| Cultivation | Crop harvest before foraging; clearing labor amortized over expected tenure; fields displace wild food; fields expand when farming beats marginal foraging, capped at need +20%. |
| Soil | `soil_nutrients` is the **fertility of the cell's cultivated land**: while cultivated, `S -= d(1−m)S` and slow natural inputs add `r_c(1−S)` (equilibrium `r_c/(r_c + d(1−m))`, 0.2 unmanaged, 0.33 with fallow rotation); when cultivation stops, fallow recovery `r(1−S)`. The farmed share of the cell no longer matters. |
| Storage | Surplus fills body reserves, then stores; stores spoil by `1 − retention` per year; moving abandons stores beyond carrying capacity and all fields. |
| Trade | 30% of surplus offered to nearby groups in deficit; transport loss `exp(−cost/60 km)`; ties decay by 0.7 per year and carry knowledge. |
| Settlement health | `population/health.py`: additive crowding hazard `k·s·log(1 + N_contact/N0)` (Section 4, item 5). |
| Aggregation | Optional coarsening of similar co-located units (off in the reference mode). |

---

## 4. MVP 2 cleanup: changes made

Every entry lists the problem, why the old mechanism was wrong, what changed, the new
assumptions, the tests, whether seeded results change, and the kind of change.

### Item 1. Migration choice (model change)

- **Problem.** About half of all groups moved every year at saturation (0.43 moves per unit-year
  in MVP 1).
- **Why it was wrong.** Each candidate cell got independent Gumbel noise, the best noisy
  candidate was taken, and then a second logistic hazard decided whether to move. The maximum
  of ~40 noise draws is large even when every option equals staying, so the move probability
  rose with the *number* of candidates.
- **Change.** `mobility/migration.py`: utility is computed from beliefs only; the destination
  is the argmax (exact ties broken uniformly with the migration stream); one move/stay draw
  with `P = σ(d·(U* − U_stay) − inertia)`. `migration.perception_noise` was removed from the
  species schema and `species/human.yaml`. `MigrationSubsystem.decide()` exposes the decision
  for testing.
- **Assumption.** Uncertainty lives in the belief system (noisy, aging observations).
- **Tests.** `tests/test_migration.py`: identical alternatives give the same hazard for 1 to
  ~40 candidates; a better destination raises it; higher inertia lowers it; observed move
  frequency matches the hazard; the fast score equals the component sum exactly.
- **Seeded results.** Change. MVP 1 mobility 0.43 → 0.19 moves per unit-year.
- **Known limitation.** Beliefs are themselves noisy, so the best-*believed* of many cells still
  carries a winner's-curse bias. This is now a property of the perception model, and it is
  large: see the noise experiment in Section 7.2.

### Item 2. Soil semantics (model change)

- **Problem.** Mean farmed soil stayed ~0.94 under continuous cropping.
- **Why it was wrong.** One cell value was depleted in proportion to the cultivated *share* and
  recovered in proportion to the uncultivated share, so a small plot got free fallowing from
  the unfarmed rest of the cell.
- **Change.** `economy/agriculture.py` `update_soil_nutrients` v2.0 as in Section 3.3; new
  parameter `agriculture.soil_cultivated_recovery_rate: 0.02` (placeholder; natural inputs
  under continuous cropping, so unmanaged fields settle near 20% rather than 0). Depletion rate
  was not raised.
- **Metrics.** `mean_soil_nutrients_farmed` is now weighted by cultivated area (NaN when nothing
  is farmed, instead of a misleading 1.0). New: `arable_utilization` (cultivated / arable ha in
  farmed cells), `cultivated_ha_per_capita`, `farm_hours_per_capita`, `crop_kcal_per_farm_hour`,
  `farmed_cell_population_density`, `farmed_density_p50/p90`, `occupied_density_p50/p90`.
- **Tests.** `tests/test_agriculture.py`: sustained cultivation declines monotonically to the
  analytic equilibrium; fallow recovers; management slows depletion and raises the equilibrium;
  fertility is independent of how much of the cell is farmed; farming metrics are identical for
  one doubled unit and two identical copies.
- **Seeded results.** Change.

### Item 3. Behavior-preserving performance (optimization)

- **Problem.** Late MVP 2 steps took ~1.1 s with ~900 units; belief sharing was 60% of run time.
- **Changes.** All exact (golden fixtures unchanged, metrics hashes identical):
  - `WorldGrid.cells_within` / `land_cells_within` cache static neighborhoods.
  - Migration scores candidates as floats with the same terms and `sum()` order (Python ≥ 3.12
    `sum` is compensated, so a running `+=` would *not* be bit-identical), iterates the small
    reachable set, and builds component dicts only for traced units.
  - Belief sharing collects partners in the same RNG order and keeps, per cell, the first
    freshest partner observation (as before); perception and sharing both emit a
    `BeliefUpdate` with a new map. A Hypothesis test checks equality with the original
    dictionary merge.
  - **Beliefs are dense per-unit arrays** (`population/unit.py` `BeliefMap`: observation year,
    food, water, population per cell; `NEVER_OBSERVED` marks unknown cells). Maps are never
    modified after construction: perception, sharing and merging build new ones, so staged
    evaluation stays valid and maps can be shared on fission. Perception forgets and writes
    cells with array operations; sharing compares year arrays directly; migration reads only
    the reachable candidates (cached as arrays per origin). Memory: 32 bytes × cells per unit
    (~51 kB on 40×40; ~60 MB at 1,200 units), which grows with cells × units.
  - `PopulationUnit` uses a descriptor on `females`/`males` instead of a `__setattr__` hook
    (11.6M hook calls per run), and caches cohort-weighted sums (`weighted_count`, used for
    need and labor) until a cohort array is replaced.
- **Measured.** Same seed, same outputs throughout (golden fixtures and per-seed ensemble rows
  identical):
  - first round (caches, migration fast path, sharing arrays, cohort descriptor): 1,000-year run
    (aggregation 3) 400 s → 326 s; late step (920 units) 1.13 s → 0.76 s;
  - dense belief maps: late step 0.76 s → 0.40 s (sharing 293 → 98 ms, perception 175 → 44 ms);
    4 seeds × 600 years in reference mode 250 s → 175 s (−30%); 1,000-year seed 0 in reference
    mode 421 s → 212 s (−50%);
  - tensorized diffusion (one knowledge matrix, contact edge list, per-receiver sums with
    numpy's own reduction so results stay bit-identical, all-units × technologies support
    check) and sharing (stacked partner years, `argmax` = first freshest partner; int32
    observation years): diffusion 68 → 27 ms per late step; 1,000-year seed 0 212 s → 181 s.
- **Tried and reverted** (no measurable gain): vectorizing the metrics recorder's mean age and
  technology shares, and the per-unit invariant check. Their remaining cost (~11 ms and ~4 ms
  per late step) is per-unit Python overhead; stacking ~900 small arrays costs as much as the
  loop. `--set debug.check_invariants=false` saves the ~4 ms (~1%) in production ensembles.
- **Vectorized with rounding-level changes** (accepted explicitly): migration utilities for all
  candidates of all units in one numpy pass (`candidate_utilities`; per-unit choice, tie
  draws and move draws keep their order), and crowding hazards for all units at once
  (`np.bincount` per (cell, species) pool, `-expm1` for sedentism). Differences from the scalar
  rules are at most ~1e-15 relative (crowding) and ~1e-12 (migration utilities near zero);
  tests check agreement to 1e-12 / 1e-9. Late step 0.37 → 0.31 s (migration 50 → 34 ms,
  demography 22 → 16 ms); 1,000-year seed 0 181 → 178 s.
- **Consequence: exact seeded output is platform-specific.** numpy picks SIMD kernels by CPU
  feature, so another machine may differ in the last bit and seeded runs can diverge. Golden
  fixtures record a numeric-platform signature (numpy version, machine, active SIMD dispatch);
  on a different platform the exact comparison is *skipped* with instructions, never failed.
  All other tests are platform-independent. Fixtures were re-recorded for this change
  (4 of 5 changed; MVP 1, which has crowding off, did not).
- **Not done, deliberately.** A cached `units_by_cell` / `cell_population` index with
  invalidation: measured at 0.26 ms and 0.58 ms per call with 920 units (~4 ms per step, 0.5%),
  not worth the stale-cache risk. Belief pruning: a model change, not done.

### Item 4. Ensemble tooling (implementation)

`madexplorer ensemble` / `compare` and `experiments/ensemble.py` as described in Section 3.1.
Process-based parallelism (`--jobs`); rows sorted by seed; parallel equals serial.
`tests/test_ensemble.py` covers settings overrides, serial/parallel equality, aggregation and
paired statistics, and the CLI outputs.

### Item 5. Settlement crowding mortality (model change)

- **Problem.** Farming populations had no health cost of settling densely (old Issue 1).
- **Change.** `population/health.py`, switch `mechanisms.crowding_mortality` (on by default, off
  in MVP 1), species section `health:`:
  - sedentism `s = 1 − exp(−residence_years/τ)`, τ = 5 years, reset by moving;
  - contact population = own settlement (people per social group) + `w` × other settled people
    in the cell, `w = min(1, π r² / cell area)`, r = 2 km;
  - pressure `C = log(1 + N_contact/50)`; adult hazard `h = 0.005 · s · C`, ×2 for children
    under 5 and adults over 60;
  - total hazard `h_baseline·exp(starvation) + h_crowding` (cause-specific, additive).
  - Metrics `mean_crowding_hazard` and `crowding_death_share` (expected deaths attributable to
    crowding / all deaths).
- **Assumptions.** All magnitudes are placeholders (a settled group of ~500 in contact adds
  about one adult baseline hazard). No sanitation technology, immunity or epidemics yet.
- **Tests.** `tests/test_health.py`: concentrated > dispersed; more settled neighbors raise the
  hazard; recently moved and mobile groups avoid most of it; crowding raises death
  probability; a 20 km cell with four villages differs from four 10 km cells by < 10% (counting
  the whole cell as one settlement would nearly double it); a 3-group merged unit gets the
  same hazard as three separate units. Statistical: crowding lowers population across seeds.
- **Seeded results.** Change. It is **not** calibrated to produce a plateau.

### Item 6. Aggregation-resolution sensitivity (experiment; see Section 7.1)

Coarsening at 3 units per cell changes outcomes materially; the MVP 2 scenario now runs with
aggregation off. `max_units_per_cell: 1` nearly stops colonization.

### Items 7-8. Merge/split semantics and network rewiring (implementation fix)

- **Problem.** Merging was ad hoc in `merge_into`; fission copied a hand-picked subset of fields;
  trade ties *pointing at* an absorbed unit silently vanished (only its outgoing ties were
  copied), so coarsening destroyed connectivity.
- **Change.** `population/composition.py` (`FIELD_RULES`, `merge_state`, `absorb`, `split_off`,
  `rewire_ties`). Fusion, coarsening and fission all go through it. Rules: extensive
  quantities (stores, fields, debts, this year's flows) sum on merge and divide in proportion
  to people on split; intensive ones (food ratio, deficit, marginal returns) are
  people-weighted means; harvest history is the people-weighted mean of aligned recent years;
  beliefs keep the freshest observation per cell; incoming ties are redirected, duplicate
  edges add (tie strength is accumulated exchange), the internal edge is dropped.
- **Behavior differences.** Fission now splits energy and labor debts proportionally (the
  daughter used to start with none); merged units keep people-weighted flows and history
  instead of the target's; duplicate ties add instead of taking the max.
- **Tests.** `tests/test_composition.py`: rule completeness, Hypothesis split-then-merge
  conservation of people, reserves, stores, fields and debts, incoming-tie rewiring,
  duplicate-edge combination, no self-edges, tie weight conserved except the internal edge.
- **Seeded results.** Change.

### Item 9. RNG isolation (implementation fix)

- **Problem.** Perception and belief sharing shared one stream; fission and fusion shared
  `social`; technology adoption used `knowledge`. Changing one mechanism's draw count shifted
  another's draws.
- **Change.** One stream per mechanism (Section 3.1) plus `RngManager.keyed`.
- **Tests.** `tests/test_rng.py`: switching knowledge sharing, fusion, migration or fission off
  leaves the perception, fission and demography streams in the same state after a year
  (the tests fail when the old shared names are restored); keyed streams depend only on keys.
- **Seeded results.** Change (different streams).

### Item 10. Innovation order bias (model change)

- **Problem.** Candidates were tried in file order and the first success stopped the loop, so
  earlier technologies in the YAML had an advantage.
- **Change.** `choose_invention` (competing risks, Section 3.3); candidates are sorted by id
  before drawing, so file order does not even change seeded runs. One uniform draw per group.
- **Tests.** Choice frequencies proportional to λ and total rate `1 − ∏(1 − p)`; a run with the
  technology list reversed produces the identical invention sequence (fails on the old code).
- **Seeded results.** Change.

### Refactor after the speed-ups (no behavior change)

Removed scalar duplicates that survived only as test references: `destination_score` /
`_utility` (migration now has the documented component rule plus the vectorized
`candidate_utilities`), the per-unit `diffusion_gain` (the rule now lives on
`diffusion_gains`), `mortality_probability`, `unit_field_names`, `BeliefMap.known_cells`,
the `SharedKnowledge` proposal (same as `BeliefUpdate`), and the list-returning
`land_cells_within` (now one cached array function). The health rules (`sedentism`,
`settlement_crowding_pressure`, `crowding_mortality_hazard`) work elementwise on scalars or
arrays and `crowding_hazards` is built from them, so the formulas exist once.
`KnowledgeModel.unsupported` delegates to the batched `knowledge_supported`. Net −150 lines;
golden fixtures unchanged.

### Item 11. Test classes (implementation)

- `tests/regression/`: golden fingerprints (final state, flow totals, SHA-256 of all metrics
  and events) for MVP 1 150 y, MVP 2 250 y × 2 seeds, a small forager world and a small
  farming world; exact in-process replay; seed divergence.
- Mechanism tests: everything else under `tests/` (marked automatically).
- `tests/statistical/`: 8 paired seeds on a 16×16 world over 900 years: agriculture raises
  population over the forager-only baseline; crowding lowers it; storage pits and cultivation
  appear in ≥ 50% of runs within broad year ranges; 8-units-per-cell aggregation stays within
  tolerance of the reference. Excluded from `make test` (`-m 'not statistical'`). The
  agriculture test is a strict `xfail` (open issue 1).
- 113 fast tests + 5 statistical (4 pass, 1 expected failure).

---

## 5. Earlier bugs found and fixed

| Bug | Symptom | Fix |
|---|---|---|
| `Scenario.with_overrides` dropped the knowledge system | MVP 2 runs silently ran without technology | Pass `knowledge` through; regression test |
| Technology loss check passed an empty held set | ≈32k spurious losses per run | `KnowledgeModel.unsupported()`; test |
| Field expansion unbounded | 794k people by year 1,000 | Fields capped at need × (1 + surplus_target) / yield |
| D8 flow terminated in noise pits | 2 river cells on 64×64 | Priority-flood fill before routing |
| Latitude gradient 0.6 °C/deg | Sea level at 50°N below freezing | 0.4 °C/deg |
| Premature cultivation by mobile bands | Early growth ~20% lower | Clearing amortized over expected tenure |
| Ecology knowledge efficiency 0.83 for expert founders | Stalled growth | `half_efficiency_level: 0.05` |

---

## 6. Performance now

| Run (2-core codespace) | Runtime |
|---|---|
| MVP 1, 64×64, 450 years | ~8-20 s |
| MVP 2, 40×40, 600 years, aggregation off (16-seed ensemble, `--jobs 2`) | median ~45 s per run, ~7 min per ensemble |
| MVP 2, 40×40, 600 years, reference mode, 4-seed ensemble (`--jobs 2`) | 25-67 s per run, 1.5 min wall |
| MVP 2, 40×40, 1,000 years, reference mode, seed 0 (one of the slowest seeds) | 178 s |
| Estimated baseline, 1,000 years, `--jobs 2`: 8 / 16 / 32 seeds | ~6 / ~13 / ~25 min (range 5-9 / 9-17 / 20-33) |

A late step (920 units) is now ~0.31 s: sharing ~99 ms, foraging ~38, perception ~35,
migration ~34, diffusion ~24, demography ~16, field planning ~14, learning ~16, plus ~15 ms of
metrics and invariant checks. Belief sharing still relays observations until every unit knows most of the
map (median 786 cells at year 850); a spatial memory limit would cut this further but is a
model change.

---

## 7. Experiments after the cleanup

All on `mvp2_neolithic` (40×40), seeds 0-15 paired, 600 years, unless noted. "d/sd" is the
paired mean difference divided by the reference standard deviation; "material" means
|d/sd| > 0.25 and more than 2 standard errors from zero.

### 7.1 Resolution invariance (item 6)

Reference: aggregation off.

| Setting | Final population | Migration rate | Inventions | Units | Verdict |
|---|---|---|---|---|---|
| aggregation off (reference) | 11,080 | 0.217 | 6.9 | 413 | — |
| max 8 units/cell | +0.9% (d/sd 0.03) | −0.7% (0.08) | +3% (0.08) | same | within noise |
| max 3 units/cell (old default) | −11% (−0.34) | −7% (−0.69) | +24% (+0.70) | −19% | **material** |
| max 1 unit/cell | −97% (326 people) | +26% | −34% | 6.5 | **breaks colonization** |

Technology milestone years (first storage pits, first cultivation) are identical across
off / 8 / 3 because, over 600 years, the first inventions happen before any cell exceeds 3
units. On seed 0 over 1,000 years the difference is large: aggregation 3 gave 50.1k people and
~40% farmed food, aggregation off 29.8k people and no farming. Mechanisms behind the bias:

- innovation and learning use the unit's head count, so a merged 3-group unit innovates and
  learns like one group three times larger (inventions +24%);
- a merged unit migrates as one actor (migration −7%);
- a group that buds off is merged straight back into its parent at the end of the step unless
  it moved that same year; at 1 unit per cell this almost stops dispersal.

The statistically correct fix (group-level hazards inside multi-group units, selective
emigration) belongs to MVP 3's stratified units. Until then the reference mode has no
aggregation; `aggregation: true, max_units_per_cell: 8` is an accepted approximation.

### 7.2 Perception noise (rerun of the old experiment, item 1)

Aggregation at 3 (runs made before the reference-mode switch; paired, so the comparison
holds).

| `cognition.observation_noise_sigma` | Migration rate | Sedentary share | Final population | Crowding share of deaths | Runs with ≥ 10% food farmed by year 600 |
|---|---|---|---|---|---|
| 0.1 | 0.138 | 0.275 | 12.0k | 4.0% | 1 / 16 (year 582) |
| 0.3 (default) | 0.202 | 0.141 | 9.8k | 2.8% | 0 / 16 |
| 0.5 | 0.256 | 0.079 | 6.6k | 2.1% | 0 / 16 |

Perception noise still strongly controls mobility and sedentism (through the winner's curse on
noisy beliefs) but barely moves invention timing, and it no longer produces early farming.
**The old conclusion ("low noise → sedentism before farming, farming by ~year 290") does not
survive the migration fix**; it depended on the Gumbel artifact.

### 7.3 Small-world checks (16×16, 900 years, 8 seeds)

With aggregation at 3 (before the reference-mode switch):

| Variant | Median final population | Final farm share | Sedentary share | Crowding share of deaths |
|---|---|---|---|---|
| default | 5,548 | 0.17 | 0.32 | 3.7% |
| no cultivation | 4,250 | 0 | 0.10 | 1.7% |
| no crowding mortality | 6,876 | 0.33 | 0.44 | 0 |

In the reference mode (aggregation off) the farming advantage disappears: paired log ratio of
final population, cultivation vs. no cultivation, is ≈ 0 (mean 0.0003; 3 of 8 seeds
positive). The statistical test `test_agriculture_supports_higher_population_than_foraging_alone`
is therefore a strict `xfail` pointing at open issue 1. The other statistical tests pass:
crowding lowers population, technologies appear within broad ranges, 8-units-per-cell
aggregation stays within tolerance of the reference.

---

## 8. Open issues and known problems

1. **Farming rarely takes hold within 1,000 years in the reference mode, and does not raise
   population.** Cultivation technology appears early (median year ~120) but farming stays
   below 10% of food in the 600-year ensembles and in the 1,000-year seed-0 run, and on the
   small world cultivation gives no population gain over foraging alone (Section 7.3). The
   earlier farming transition was substantially an aggregation artifact. See the baseline
   (Section 9) for the distribution. This is the main calibration question for the start of MVP 3 and should
   be investigated as a mechanism question (returns to farming vs. marginal foraging, clearing
   costs, soil equilibrium without fallow rotation, crowding cost of settling), not tuned to a
   target.
2. **Winner's curse through noisy beliefs.** The destination is the best of many noisy
   observations, so mobility depends on observation noise and on how many cells a group knows.
   A proper fix is belief-level uncertainty (e.g. shrinking observations toward a prior, or
   discounting by known noise).
3. **Map-wide belief maps**: units learn most of the map through relayed gossip; memory now
   scales with cells × units (Section 6).
4. **Aggregation is not sociologically neutral** (Section 7.1).
5. Modelling simplifications carried over: static vegetation, no seasons, species in one cell
   forage in id order, equal food sharing inside groups, whole-group migration only, one-good
   trade, group-level knowledge (no specialists or archives), verbose adoption events.
6. Small nits: soil state is one pool per cell (newly cleared land inherits it); perception is a
   Chebyshev square; `README.md` still describes the pre-cleanup status.

---

## 9. MVP 2 baseline (item 12)

**Not yet recorded.** Canonical `scenarios/mvp2_neolithic.yaml`, reference mode, 1,000 years.
After the speed-ups, the estimated wall time on the 2-core codespace is ~13 min for
seeds 0-15 and ~25 min for seeds 0-31 (the earlier "2 hours" assumed every seed was as slow as
seed 0 before the speed-up). Command, once approved:

```bash
uv run madexplorer ensemble scenarios/mvp2_neolithic.yaml --seeds 0:31 --jobs 2 --out baselines/mvp2
```

The manifest records `source_tree_sha256`, so commit (or at
least freeze) the code before recording.

---

## 10. Recommended next steps (in order)

1. **Record the MVP 2 baseline** (Section 9).
2. **Belief memory range** (optional model change): forgetting observations beyond a few
   relocation ranges would bound memory (dense maps scale with cells × units) and cut sharing
   cost further; evaluate with paired ensembles before adopting.
3. **Investigate issue 1** (farming transition) with paired ensembles and `--set` sweeps.
4. **MVP 3: distributional society** (§33), built on the composition rules:
   - each large `PopulationUnit` holds ~8-16 weighted strata sharing wealth, health, risk
     tolerance, autonomy, occupation and status, extending cohorts to `N[sex, age, stratum]`;
     strata keep correlations that separate marginals would lose (§7.3);
   - initial wealth support from deterministic quantiles of lognormal body + Pareto tail;
   - selective migration `n_move,i ~ Binomial(n_i, p(move | stratum))`, which also fixes the
     aggregation bias in 7.1 (groups inside a unit decide separately);
   - health as a pathway from wealth (§8.3), adult height from childhood stress (§8.5),
     building on `population/health.py`;
   - every new field must be added to `FIELD_RULES`;
   - switch subsystems to `RngManager.keyed` where split/merge would reorder draws.
5. Afterwards, MVP 4 (factions, appropriation, state capacity) and MVP 5 (fantasy and
   multi-species worlds).

---

## 11. Map of the code

```
src/madexplorer/
  config/        schema.py (scenario models), loader.py (Scenario, overrides, with_settings, hashing)
  core/          simulation.py, state.py, subsystem.py, rng.py, ids.py, events.py, invariants.py,
                 governance.py, provenance.py
  world/         grid.py, generation.py, hydrology.py, climate.py, subsystems.py
  ecology/       resources.py, subsystems.py
  species/       profile.py (SpeciesProfile, incl. Health), life_history.py (LifeTables)
  population/    unit.py, composition.py (merge/split rules), health.py (crowding),
                 energetics.py, demography.py, groups.py, initialization.py
  economy/       foraging.py, agriculture.py, trade.py
  mobility/      movement.py, exploration.py (perception, belief sharing), migration.py
  knowledge/     system.py, learning.py, diffusion.py, innovation.py
  resolution/    coarsening.py
  experiments/   ensemble.py (ensembles, summaries, paired comparisons), benchmark.py
  metrics/       recorder.py
  persistence/   output.py
  cli/           main.py
scenarios/       mvp1_sandbox.yaml, mvp2_neolithic.yaml
species/         human.yaml
technologies/    neolithic.yaml
tests/           mechanism tests; regression/ (golden fixtures); statistical/ (make test-stat)
benchmarks/perf/ benchmark reports (JSON), p0_pre_reform_* = pre-stabilization reference
baselines/       mvp2/ (planned: frozen MVP 2 ensemble; not recorded yet)
```

### Conventions to keep

- A new mechanism gets a pure function decorated with `@model_rule`, a subsystem with
  `evaluate()` → proposals → `apply()`, a `mechanisms:` switch, a metric, mechanism tests, and
  (if it changes results) re-recorded golden fixtures.
- A new `PopulationUnit` field gets merge and split rules in `population/composition.py`.
- Each stochastic mechanism draws from its own named stream, in deterministic order.
- Units are in field names (`_km`, `_kcal`, `_years`, `_c`, `_mm`, `_ha`).
- Never mutate cohort arrays in place; assign new arrays (the descriptor clears caches).
- Compare model variants with paired ensembles (`ensemble` + `compare`), never one seed.
