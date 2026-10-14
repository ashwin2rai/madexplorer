# Implementation Status

**Updated:** 2026-10-14 (MVP 3 Stage 5I, awaiting review)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`)\
**Current milestone:** MVP 3, staged socioeconomic differentiation
(`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`)

How to read this file: the current handoff, then what MVP 3 has established, then the MVP
2.1 base. Scientific intent lives in `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; equations and
stage evidence in the MVP 3 design document; executable truth in code, tests and model
rules (`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs).

## 1. Current handoff

### Stage 5J: IN PROGRESS (re-deployment runbook)

Stage 5J is not finished. This block records what has been done and the exact commands to
reproduce or resume it if the codespace stops. The Stage 5I handoff below is still the
last completed stage.

**Starting commit:** `7177e57` (Stage 5I), clean worktree. Changes are uncommitted.

**Code changes made so far (uncommitted):**
- `src/madexplorer/config/schema.py`: `mechanisms.dietary_intake_fertility: bool = False`.
  The default is MVP 2.1; MVP 2.2 switches it on.
- `src/madexplorer/core/state.py`: transient `StepContext.dietary_intake`, a dict from
  unit id to ratio.
- `src/madexplorer/population/energetics.py`: when the switch is on, computes
  `dietary_intake_ratio(need, harvest, stores)` and puts it on `ctx.dietary_intake`.
- `src/madexplorer/population/demography.py`: `fertility_input()` returns `food_ratio`
  for MVP 2.1 and the intake for MVP 2.2. It raises if MVP 2.2 has no intake for a
  populated unit.
- `src/madexplorer/population/dietary_intake.py`: registers the rule `dietary_intake`
  (MVP 2.2 candidate).
- `scenarios/mvp2_2_neolithic.yaml`, `scenarios/mvp2_2_pressure.yaml`: copies of the MVP 2.1
  files with only the name and the switch changed.
- `scripts/perf/exactness_oracle.py`: `--model mvp2_2` selects the MVP 2.2 scenarios. The
  default is unchanged (MVP 2.1).
- `scripts/probes/fertility_version_comparison.py`: equivalence, paired runs, analysis.
- `tests/test_model_versions.py` (new); `tests/test_dietary_intake.py` (inactivity test
  updated).

**Results obtained so far:**
- MVP 2.1 raw and logical oracles: **IDENTICAL** with the change in place.
- Equivalence: production MVP 2.1 equals experimental H0, and production MVP 2.2 equals
  experimental H1, **bit-identical every year** in 32 / 32 comparisons (seeds 0–7, both
  scenarios; about 8 min).
- New and updated tests: 23 passed.

**Prespecified paired experiment** (defined before results; do not change):
- Seeds 0–31.
- Neolithic `scenarios/mvp2_neolithic.yaml` vs `scenarios/mvp2_2_neolithic.yaml`, 600 years.
- Pressure + cultivation `scenarios/mvp2_pressure.yaml` vs `scenarios/mvp2_2_pressure.yaml`
  with `mechanisms.cultivation=true`, 400 years.
- Production code only. 128 runs in total.
- Outcomes:
  - population, births, deaths, reproductive-age females, extinctions, units;
  - fissions, fusions, migrations;
  - cultivated ha, food production, harvest/need, stores, energy deficit, trade volume;
  - inventions, adoptions, technology first years (granaries), ecological stocks.
- Statistics: paired median/mean/IQR/range, share H1 > H0, bootstrap 95 % intervals over
  seed pairs, exact McNemar for granaries; outliers kept.
- Status when written: running (about 54 of 128 runs done). Its output is in
  `/tmp/claude-1000/...` (the session scratchpad), which does **not** survive a codespace
  restart.

**To resume or re-run** (use `runs/`, which is gitignored and survives restarts; finished
runs are skipped automatically):

```bash
# 0. sanity: unit tests for the version boundary and intake rule
uv run pytest tests/test_model_versions.py tests/test_dietary_intake.py -q

# 1. MVP 2.1 must stay exact (legacy gate)
uv run python scripts/perf/exactness_oracle.py benchmarks/perf/oracle_mvp2_1.json
uv run python scripts/perf/exactness_oracle.py --logical benchmarks/perf/oracle_mvp2_1_logical.json

# 2. production versions vs the Stage 5I experimental branch (expect EQUIVALENCE IDENTICAL)
uv run python scripts/probes/fertility_version_comparison.py equivalence --jobs 2 --seeds 0 1 2 3 4 5 6 7

# 3. prespecified paired experiment, 128 runs (~25-30 min with 2 jobs; resumable)
uv run python scripts/probes/fertility_version_comparison.py run --jobs 2 --out runs/stage5j/paired
uv run python scripts/probes/fertility_version_comparison.py analyse --load runs/stage5j/paired > runs/stage5j/analyse.txt
```

**Remaining Stage 5J steps (not yet done):**

```bash
# 4. candidate MVP 2.2 oracles (record once, then reproduce in a fresh process)
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 --record benchmarks/perf/oracle_mvp2_2.json
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 --logical --record benchmarks/perf/oracle_mvp2_2_logical.json
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 benchmarks/perf/oracle_mvp2_2.json
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 --logical benchmarks/perf/oracle_mvp2_2_logical.json

# 5. candidate MVP 2.2 reference runs (same layout as baselines/mvp2_1/)
uv run madexplorer ensemble scenarios/mvp2_2_neolithic.yaml --seeds 0:3 --years 600 --jobs 2 --out baselines/mvp2_2/neolithic_4x600
uv run madexplorer ensemble scenarios/mvp2_2_pressure.yaml --seeds 0:3 --years 400 --jobs 2 --set mechanisms.cultivation=true --out baselines/mvp2_2/pressure_4x400_cultivation_true
uv run madexplorer ensemble scenarios/mvp2_2_pressure.yaml --seeds 0:3 --years 400 --jobs 2 --set mechanisms.cultivation=false --out baselines/mvp2_2/pressure_4x400_cultivation_false

# 6. full validation
make check
make test-stat
git diff --check
```

7. Then:
   - write `baselines/mvp2_2/freeze_manifest.json` (candidate, with provenance);
   - add §AC to the design document (draft: experiment results, baseline, Stage 5A–5J
     decision record, closure gates);
   - replace this runbook with the Stage 5J handoff.

Never run `make golden`, and never overwrite any `*mvp2_1*` artifact.

---

**Completed:** Stage 5I, food-energy semantics and nutritional fertility, with a
controlled demographic branch (design §AB). **PAUSE FOR SCIENTIFIC REVIEW.**

**Starting commit:** `7f54c09` (Stage 5H), clean worktree. The Stage 5H files and results
remain part of the scientific history (§AA).

**Files changed:**
- New: `src/madexplorer/population/dietary_intake.py` (NOT ACTIVE).
- New: `scripts/probes/fertility_intake_experiment.py` (EXPERIMENTAL / OPT-IN / NOT
  CANONICAL).
- New: `tests/test_dietary_intake.py` (12 tests).
- Updated: the design document (§AB) and this file.

**Production default:** unchanged.
- No production file, rule, RNG stream, fixture or baseline was modified.
- The branch replaces subsystem *instances* in one `Simulator`, never classes or the
  default pipeline.

**Food-energy semantics:**
- `food_ratio = H/N` (harvest after trade) is harvest adequacy.
- Dietary intake is `(min(H, N) + X)/N`, where `X` is stores eaten.
- Physiological sufficiency is `1 − deficit`, which includes reserve drawdown.
- All three are exactly reconstructible from the energetics inputs.
- Readers of `food_ratio`:
  - fertility: the documented mechanism is intake, so intake is needed;
  - innovation need and surplus: production and economic quantities, so H0 is coherent;
  - fission food stress: ambiguous;
  - telemetry.
  - Migration uses its own function.

**H0 / H1:**
- H0 = `fertility_multiplier(food_ratio)`.
- H1 = `fertility_multiplier(dietary_intake_ratio)`.
- Same function and parameters, no new state, no RNG. H1 excludes body reserves; H2 =
  `1 − deficit` is a diagnostic only.
- **Source invariance:** equal intake from harvest or stores gives an equal H1 multiplier
  (H0: 1.0 vs 0.135).

**Same-state diagnostic** (neolithic · pressure, 8 seeds):
- H0 reconstruction is exact.
- The multiplier changes by more than 0.01 in 3.2 % · 5.3 % of unit-years, and by more
  than 0.10 in 1.4 % · 1.5 %. These are concentrated on recipients (33 % · 12 %) and on
  store-using non-traders under pressure.
- Expected births on fixed states: +0.38 % · +0.42 %.
- §AA reconciliation: its strict figure undercounted stores that close the gap exactly.
  With a 1e-12 tolerance it is 4.0 % · 4.4 %; the rest of the 4.4 % · 9.0 % is reserve
  compensation.

**Branched simulation** (8 paired seeds per scenario):
- Experimental H0 is bit-identical to canonical in 16 / 16 runs (digest, per-year
  component hashes, metric rows).
- H1's first divergence is always a birth difference in a unit whose multiplier changed,
  with identical energetics in that year.
  - Neolithic: years 142–262. Pressure: years 3–41.

**Downstream demographic effects:**
- Neolithic: none detectable (final population ratio median 0.99, range 0.90–1.12, mixed
  signs).
- Pressure: year-400 population +5.9 % median, positive in 8 / 8 seeds (+0.5 % to +52 %).
  - Outliers are seeds reaching granaries (H1 3 / 8 vs H0 1 / 8; unresolved, p ≈ 0.57).
  - Seeds in the same storage regime under both inputs: +2.5 % median, all positive.
- Births and deaths rise together; deficits show no consistent change.
- Fission, trade and innovation change only through population.

**Raw / logical oracles:** IDENTICAL (default mode).

**Scientific decision: A.** H1 is the better implementation of the stated mechanism.
- Recommend a separate, versioned change of the fertility input only, with the ten
  requirements in §AB.8.
- Not activated; no baseline created.

**Physical-feedback gate:** closed.

**Next recommended stage:** the versioned fertility-input change (e.g. MVP 2.2), if
approved:
- an explicit dietary-intake quantity computed in energetics;
- tests for source invariance and reserve exclusion;
- 16–32 seeds per scenario, including the granaries-regime frequency;
- new oracles and goldens under the new version;
- MVP 2.1 kept unchanged.

Outstanding and separate: dust transfers (§AA) and fission food-stress semantics.

**Next:** PAUSE FOR SCIENTIFIC REVIEW.

## 2. MVP 3 so far

| Stage | Result | Design |
|---|---|---|
| 0 | Strata design: label-free mixture components `share`, `field_claim`, `store_claim` | header, contract |
| 1–2.1 | Passive `StrataTable`; fusion inheritance; capacity coalescence; exact compaction | contract |
| 3A–3C | Neutral food and land accounting; crop attribution weight `w` (`strata.field_output_claim_weight`, default 0) | §L |
| 3D | Fusion is the only source of differentiation; differences decay (stores about 2 y, fields with expansion); coalescence lets `w` leak into field representation | §M |
| 4A | No modeled reason for stratum-differentiated labor; resolution gate locked | §N |
| 4B / 4B.1 | Configurable `strata.max_strata`, default 16 (8 historical, 32 sensitivity); vectorized coalescence; per-dimension error | §O, §P |
| 4C | Claim-sensitive access to stored food: small and one-shot per store cycle under the MVP 2.1 withdrawal rule (counterfactual) | §Q |
| 4D | Store release `X = min(D, K)` is kcal-optimal under current physics; reserve targets rejected (counterfactual) | §R |
| 4E | Control over new fields: H2 = H1; continuity preserves but never amplifies (counterfactual) | §S |
| 5A | Endogenous differentiation audit: recommend practice concentration under finite demand with learning-by-doing (design only) | §T |
| 5B | Participation overhead: corner solution for any o > 0; small consequence under continuity; assignment matters more than degree; B confirmed (counterfactual) | §U |
| 5C | Entry costs: initiation is the same corner; incumbents before newcomers explains continuity relative to rotation; how many to keep is indifferent; one-year memory reproduces 5B; turnover makes long incumbency hereditary by representation; B (counterfactual) | §V |
| 5D | Opportunity audit: no within-unit opportunity differentiation exists; best-grounded origin is partial exposure at technique acquisition, but knowing precedes practice by 8–16 y (p50); D, falsification test proposed (design only) | §W |
| 5E | Partial knowledge exposure: exists at every acquisition but binds cultivation materially in < 1 % of farming unit-years under model-consistent spread (T50 ≲ 5 y); only near rare inventions or with slow spread (then untaught new workers); B (counterfactual) | §X |
| 5F | Fusion-born knowledge heterogeneity: real (≈ 7 % of fusions ΔE ≥ 0.01, from different productive histories), slow to decay in K (34 y), but static consequence ≈ 0.004 % of harvest even with indefinite retention; K's ontology is mixed; B (audit + counterfactual) | §Y |
| 5G | Causal-structure review: no within-unit initiator has substrate; between-unit provisioning is grounded and consequential (recipients' fertility and starvation), with reliance on the local pool rather than partners (ties unread by trade); compartments are the exact finite representation, mixtures miss threshold tails, marginals miss correlation; A (review + read-only audit + benchmark) | §Z |
| 5H | Provisioning: exact replay; donor choice exists but competition halves substitutability under pressure; ties add no allocation information beyond recurring material configuration; tie routing relabels donors with ≤ 0.5 % change in delivered food; food_ratio excludes store consumption despite an intake rationale; B (+ D) (audit + counterfactual matching) | §AA |
| 5I | Food-energy semantics: fertility's documented mechanism is intake but its input is harvest adequacy; dietary intake (H1) is exactly reconstructible, source-invariant, excludes reserves; experimental H0 branch bit-identical; H1 neutral in neolithic, +5.9 % population under pressure (granaries-regime outliers); A: separate versioned fertility-input change recommended (audit + controlled branch) | §AB |

**Locked decisions** (details in the design document):
- **No invented social categories.**
  - A stratum is a label-free component. There are no named classes, no inequality
    targets, no random differentiation, and no statistical split test.
  - Strata are created only by mechanisms; fusion is the only current source.
- **Representation.**
  - Physical stocks stay `[U]`; control stays `[U,S]`.
  - A claim on a zero stock equals the population share.
  - A mechanism that creates new stock must state who controls it.
- **No stratified demography yet.** Strata share the unit's age–sex structure; there is
  no `[U,S,sex,age]` until a mechanism creates demographically meaningful differences.
- **Strata are passive.** No `[U]` mechanism reads strata state, and strata outputs go
  only to the sidecar. The MVP 2.1 oracles therefore stay identical. A new versioned
  baseline comes only when strata intentionally change unit outcomes.
- **No canonical nonzero values.** `w` and the counterfactual parameters (`a`, `b`, `p`)
  have none; they are sensitivity cases, never tuned.
- **Gate (§N7):** no physical mechanism reads stratum socioeconomic state until the
  resolution policy is shown stable for the information it uses. Status: closed.

**Do not forget:**
- `strata_access.py`, `store_release.py`, `field_control.py`, `practice_concentration.py`,
  `entry_cost.py`, `knowledge_exposure.py`, `fusion_competence.py`,
  `economy/provisioning_counterfactual.py` and `dietary_intake.py` are NOT ACTIVE; the 5I
  branch (`scripts/probes/fertility_intake_experiment.py`) is experimental and opt-in.
  Nothing in the simulator calls them, and their parameters are not scenario settings.
- Capacity coalescence is numerical, and its equal-weight metric is mechanism-agnostic.
  Revisit it (§M6) before anything reads claims.
- Never use strata to brake population growth (§4 below).
- Leave changes uncommitted, and stop after each stage for review.

## 3. MVP 2.1 base: artifacts and architecture

| Artifact | Location |
|---|---|
| Manifest (frozen results and validation record) | `baselines/mvp2_1/freeze_manifest.json` |
| Golden fixtures | `tests/regression/golden/` (strata fixtures: `tests/regression/golden_strata/`) |
| Raw-byte oracle (dense beliefs) | `benchmarks/perf/oracle_mvp2_1.json` |
| Logical oracle (any backend) | `benchmarks/perf/oracle_mvp2_1_logical.json` |
| Canonical scenarios | `scenarios/mvp2_neolithic.yaml`, `scenarios/mvp2_pressure.yaml` |
| MVP 2 history | `baselines/mvp2/` |

- **Which source counts as MVP 2.1.** The manifest's source-tree hash identifies the
  *original* frozen implementation, and the current tree no longer matches it. The current
  code counts as MVP 2.1 because it reproduces the goldens, both oracles and the neolithic
  4 × 600 reference runs.

**Architecture to preserve:**
- **One owner of population state.** `PopulationStore` owns:
  - the unit registry;
  - the `UnitTable`;
  - the belief store;
  - the `StrataTable`;
  - slot allocation.

  `SimulationState` exposes them read-only. A unit belongs to at most one store.
- **One declaration per unit field** (`population/fields.py`). New `[U]` state is declared
  there first. Stratum columns have their own schema in `population/strata.py`.
- **Two engines, used as mutual oracles.**
  - The table engine is authoritative. The object engine (`unit_table=False`) with
    `composition.py` is the independent reference for `lifecycle.py`.
  - `_evaluate_reference` paths sit beside the compiled kernels.
  - The dense belief backend is the reference for the sparse one.
  - Share plumbing between paired implementations, never the arithmetic they cross-check.
- **Sparse beliefs in production.**
- **Static, compiled and dynamic state stay separate.**
- **Step order is scientific semantics.**
- **Evaluate draws, apply commits.** RNG streams are named, and draws stay outside
  compiled kernels.
- **Migration:** group-level candidate generation (`gather_candidates`) is separate from
  scoring (`best_destinations`). This is the seam for selective migration.

**Performance lessons:**
- **Order of work:** improve representation and dataflow first, then profile again, then
  compile only what stays hot.
- **Float rewrites:** a mathematically equivalent rewrite is not automatically
  bit-identical. Keep both the raw and the logical oracle.
- **Measured scaling:** near-linear at ≈ 95–112 µs per unit-year, with ≈ 2.5 GB RSS at
  50k units. This is historical and machine-specific.
- **MVP 3 memory risk:** demography temporaries multiplied by strata would reach
  multi-GB. Stratified demography must use pre-drawn RNG, a chunked unit × stratum
  kernel, a bounded workspace and direct cohort writes.

## 4. Accepted limitations

- **Aggregation is not scientifically neutral.** Coarsening is off in every canonical
  scenario, and its statistical check stays a strict xfail. Adaptive resolution must
  preserve behaviorally important heterogeneity.
- **Migration utility mixes wild-food stock and crop flow.**
- **Ecology is simple:** no seasons, little succession, simple soil and exchange.
- **Social state and migration are group-level** (strata are passive).
- **Technologies are Boolean with hard prerequisites** (objective §8.1).
  `plant_cultivation` is an affordance, not a model of domestication.
- **Populations grow close to the life-table ceiling** while territory remains: about
  0.9–1.1 %/y against a 1.24 %/y maximum. Fertility stays high, starvation is negligible,
  and work and mobility carry little demographic cost. This is not a defect (2026-10-02
  audit; probe in git `aae0974`). Later mechanisms may change it only through explicit
  causal pathways, never through a brake added to hit a target.
- **`move_hazard` is written each year but read by no mechanism.** It is kept because the
  exactness oracle hashes it; removing it would change the oracle (§5, tier 3).

**Solved problems; do not reintroduce:**
- candidate-count migration bias;
- map-wide lossless belief synchronization;
- uncertainty-free direct observations;
- hard saturation of food utility;
- permanently inherited familiarity;
- the field-growth bootstrap trap;
- counting field crop twice when leaving;
- innovation ordering bias;
- RNG coupling across mechanisms;
- treating a population plateau as a required outcome;
- treating naive aggregation as neutral.

## 5. Change, validation and simplification discipline

1. **Classify every change:** exact refactor or optimization, numerical reformulation, bug
   fix, or scientific model change. A newly found scientific bug is reproduced in a test,
   versioned and re-baselined, never fixed inside a refactor.
2. **Test with the smallest test that can falsify the change,** and keep `make check`
   green.
3. **Exact work must leave everything identical:** the goldens, the strata fixtures and
   both oracles (`scripts/perf/exactness_oracle.py [--logical]`). Never run `make golden`
   to absorb an unexplained difference. If behavior may change, run `make test-stat` and
   re-baseline deliberately.
4. **Never change RNG semantics or coefficients** to recover an old trajectory.
5. **"Unreferenced" must be grep-verified** across `src`, `tests`, `scripts`, `scenarios`,
   `species`, `baselines`, `Makefile` and `objective/` before code is deleted.
   - Batched rewrites left their one-unit predecessors behind. Delete a predecessor once
     its replacement is validated.
   - Phase aliases outlive their phases.
6. **Anything hashed is provenance.** Removing a field that the oracle digests
   (`move_hazard`), or a config field that enters `config_hash` (`timestep_years`,
   `age_structure`, coarsening's `ResolutionConfig`), is a provenance change, not a
   refactor. These are tier-3 candidates and need an explicit decision.
7. **Do not refactor what a running experiment imports.** Probes use the helpers in
   `scripts/probes/_common.py`. A finished probe is retired once its findings are recorded
   in the design document; git is the archive.
8. **Documents keep conclusions, not appended logs.** Update the current contract and the
   findings register; never append a second copy of a stage.

**Simplifications considered and declined (2026-10-07):**
- **Shared code across paired implementations.** The diffusion adoption loop, the
  migration saturation recorders and the exploration batch/packed report paths are each a
  reference/fast pair. Sharing their arithmetic would void the cross-check.
- **One formula set for `record` and `_record_light`.** The raw oracle hashes the metrics
  rows, and about 15 lines do not justify the risk.
- **Splitting migration `evaluate`.** It saves no lines.
- **Sharing the remaining per-file test helpers** (`_sims`, `_farming`, `_authoritative`,
  `_digest`). They differ in seed, fields and settings, and sharing them would couple
  independent tests.
- **`baselines/mvp2/golden/`** stays, because the frozen MVP 2.1 manifest cites it.

## 6. Open questions

1. **Agriculture representation.** Is the `plant_cultivation` affordance sufficient long
   term, or should local domesticability and domestication become continuous ecological
   and cultural processes (objective §8.2)?
2. **MVP 3 questions** are listed in the design document's open-questions section.
