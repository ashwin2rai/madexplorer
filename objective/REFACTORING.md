# Refactoring and Simplification Log

**Started:** 2026-10-07, during MVP 3 Stage 4E\
**Role:** what we learned about where code and documentation accumulate, which
simplifications are safe, the agreed plan, and its progress. Scientific intent stays in
`SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; stage findings stay in the MVP 3 design document.

## 1. Rules for simplifying this codebase

1. **Classify every change first** (status §7): pure deletion of unreferenced code, exact
   refactor (cannot change floats or RNG), or a change that can move results. Only the
   first two are refactoring; the third is a model or provenance change and needs its own
   decision.
2. **"Unreferenced" means grep-verified** across `src`, `tests`, `scripts`, `scenarios`,
   `species`, `Makefile`, `baselines` and `objective/`. A name that appears only at its
   definition and in a docstring of its replacement is dead.
3. **Keep the independent oracles.** These look like duplication but are the validation
   design (objective §4.4): the object engine (`unit_table=False`) with
   `population/composition.py`, `_evaluate_reference` beside compiled kernels,
   `coalesce_to_capacity_reference`, the dense belief backend, and the single-unit
   test-only wrappers (`food_prior`, `select_reports`, `report_pool`, ...). Share only
   plumbing between a pair (integer indexing, sorting), never the arithmetic the pair
   cross-checks.
4. **Anything hashed is provenance.** Removing a field the exactness oracle digests
   (`move_hazard`) or a config field that enters `model_dump` (`timestep_years`,
   `age_structure`, coarsening's `ResolutionConfig`) changes `config_hash` or the frozen
   oracle even when no arithmetic changes. Not a refactor.
5. **Verify every batch** with `make check`, `make test-stat`, both MVP 2.1 oracles
   (`scripts/perf/exactness_oracle.py [--logical]`), the strata fixtures and
   `git diff --check`. Never `make golden`.
6. **Do not refactor what a running experiment imports.** Probes import each other
   (§3); consolidate them only between experiments.
7. **Git is the archive.** Retired probes, benchmark JSON and superseded stage write-ups
   are recoverable (last commit before cleanup: `aae0974`); documents keep the
   conclusion plus the command or commit that regenerates the evidence.

## 2. Where accretion came from (lessons)

- **Batched rewrites left their one-unit predecessors behind.** Performance Hardening
  replaced per-unit proposal classes with columnar plural ones (`EnergyUpdates`,
  `FieldPlans`, ...); the singular classes stayed, referenced only by the plural class's
  docstring ("equivalent to one X per row"). Delete the predecessor when its replacement
  is validated, and say what the replacement does instead of what it is equivalent to.
- **Phase aliases outlive phases** (`detach_beliefs`, "the PH3a name").
- **Each stage probe copied helpers from the previous one** (`drive`, digests, `w1`,
  weighted quantiles, formatters: 3-4 copies each) and imported the rest from older
  probes, so the probes form a chain (`strata_review` → `strata_capacity` →
  `store_access_counterfactual` → `store_release` / `field_control`). A shared
  `_common.py` from the start would have avoided both.
- **Benchmark JSON was kept per phase** (98 files) although only six are cited by a
  manifest or the oracle script.
- **Documents grew by appending stage reports.** `status.md` repeated each stage's design
  section as a handoff; the design document kept its Stage 0 plan (§A-§K) after later
  stages superseded parts of it (S_max = 8, `field_entitlement_weight`, rule names in §I
  that were never built). About 25 code comments still cite a "spec §x" that no longer
  exists.

## 3. Inventory (2026-10-07)

`src` 15.5k lines, `tests` 7.8k, `scripts` 4.4k; `objective/` 28k words (design 15.6k,
status 6.6k, objective 5.6k). Probe imports: `strata_review` (SEEDS, `scenario_for`,
`Observer`, `drive`) and `strata_capacity` (`physical_digest`) and
`store_access_counterfactual` (`strata_digest`, `drive`) are used by the later probes; no
test imports a probe.

## 4. Agreed plan and progress

Accepted 2026-10-07: tiers 1-2, scripts/benchmarks cleanup, documentation restructure.
Tier 3 needs an explicit decision.

### Tier 1 — delete unreferenced code (done 2026-10-07, −226 lines; pending validation)

- [x] `FarmHarvest`, `FieldPlan` (economy/agriculture.py), `CellHarvest`
  (economy/foraging.py), `EnergyUpdate` + `_commit_energy` (population/energetics.py),
  `DemographicUpdate` (population/demography.py): superseded one-unit proposals.
- [x] `KnowledgeLevels`, `activity_shares_batch` (knowledge/learning.py),
  `SpatialIndex.rows_in`, `is_registered`, `SPARSE_ENTRY_BYTES`,
  `StrataTable.is_neutral`.
- [x] `detach_beliefs` alias (test switched to `detach_unit`).
- [ ] Optional, small: `MigrationDecision.candidates` (set, never read); benchmark
  `count_calls` (never passed).

### Retire files (blocked on permission: tracked-file deletion needs the user's approval)

```bash
cd benchmarks/perf && ls | grep -vxE 'oracle_mvp2_1(_logical)?\.json|oracle_ph0\.json|oracle_ph4b_logical\.json|mvp2_freeze_(seed0_600y|synthetic)\.json' | xargs git rm -q
git rm -q scripts/perf/ph5_scale.py scripts/perf/ph5_steady.py \
  scripts/probes/pressure_validation.py scripts/probes/demography_audit.py \
  scripts/probes/crop_attribution_sensitivity.py scripts/probes/food_flow_audit.py
```

- [ ] 92 of 98 `benchmarks/perf/*.json` (historical `p0_*`, `p1_*`, `p2_*`, `p4_*`,
  `ph0_*`-`ph5_*`; none referenced). Keep the six cited by manifests or the oracle script.
- [ ] Probes/perf scripts whose findings are recorded and which nothing imports (~1,050
  lines). Update their citations in `objective/` to "git `aae0974`".
- [ ] `baselines/mvp2/golden/` (an MVP 2 copy of the regression goldens; history only).

### Tier 2 — exact refactors (after the Stage 4E experiments finish)

- [ ] Shared merge helpers for `move_hazard`, harvest history and residence used by both
  `lifecycle.merge_units` and `composition.merge_state` (same operand order).
- [ ] One `unassigned_ids` helper (composition.py, store.py, `StrataBlock.unassigned_copy`).
- [ ] Move `log_normalization` to strata.py (removes the lazy import in store.py).
- [ ] Import `GROWTH_FRACTION` / `MIN_CAPACITY` in beliefs.py instead of redefining them;
  replace `EXTERNAL_FIELDS` alias; fold `crowding_hazards` / `crowding_hazard_array`.
- [ ] migration.py: one saturation recorder for both paths; split the 140-line `evaluate`
  into scalar / scoring / draw helpers (code motion only).
- [ ] diffusion.py: one adoption-loop helper (draw order unchanged); inline
  `_commit_diffusion`.
- [ ] metrics/recorder.py: one formula set for `record` and `_record_light`.
- [ ] exploration.py: reuse `report_pool`; share only the sort/dedupe plumbing of the
  batch/packed report pairs (they are a differential pair).
- [ ] scripts/probes/_common.py for the shared helpers (vectorized `w1`, quantiles,
  `drive`, digests, `scenario_for`); then retire `strata_review` and `strata_capacity`
  (~1,250 lines) once their findings are only cited.
- [x] tests/conftest.py `make_unit` replaces five `_unit` builders (−21 lines; done
  2026-10-07). Remaining: engine-pair `_sims`, `_farming`, `_authoritative`, `_digest`
  (~100 lines), deferred because Stage 4E requires the Stage 4C/4D and regression test
  files to stay unchanged.

### Tier 3 — needs a decision (changes oracle hash or config hash)

- [ ] `move_hazard`: write-only state kept because the oracle hashes it (~60 lines).
- [ ] Coarsening (`resolution/`, `ResolutionConfig`): disabled everywhere; policy choice.

### Documentation (after Stage 4E is written up)

- [ ] `status.md` → current handoff, locked decisions, do-not-forget list, condensed MVP
  2.1 base (~1.5k words).
- [ ] Design document → current contract (state, semantics, lifecycle, accounting as
  built, invariants, gate) + findings register (one conclusion per stage with the probe
  command or commit) + open questions (~5k words). Keep the section labels the code cites
  (§L, §M, §M2, §M6, §N7, §Q, §R) or update those comments.
- [ ] Objective document: remove repetition between §2, §12 and §18 and the status
  narrative in §3 (~3k words).
- [ ] Retarget or drop the ~25 "spec §x" comments in `src`.
