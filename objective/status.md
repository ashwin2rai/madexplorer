# Implementation Status

**Updated:** 2026-10-14 (MVP 3 Stage 5J; Stage 5 technically complete, pending approval)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`). Candidate MVP 2.2
(`baselines/mvp2_2/`, opt-in) is pending approval.\
**Current milestone:** MVP 3, staged socioeconomic differentiation
(`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`)

How to read this file: the current handoff, then what MVP 3 has established, then the MVP
2.1 base. Scientific intent lives in `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; equations and
stage evidence in the MVP 3 design document; executable truth in code, tests and model
rules (`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs).

## 1. Current handoff

**Stage 5 — technically complete; pending final scientific approval.**

**Completed:** Stage 5J, the versioned fertility correction (candidate MVP 2.2), scientific
validation and Stage 5 consolidation (design §AC). **PAUSE FOR SCIENTIFIC REVIEW.**

**Starting commit:** `7177e57` (Stage 5I), clean worktree. During the stage the user
committed work in progress as `d44d44f` ("wip: socioeco experiments"). Later changes are
uncommitted.

**Files changed in Stage 5J:**
- Production (minimal):
  - `config/schema.py`: `mechanisms.dietary_intake_fertility = False`;
  - `core/state.py`: transient `StepContext.dietary_intake`;
  - `population/energetics.py`: intake computed only when the switch is on;
  - `population/demography.py`: `fertility_input()`;
  - `population/dietary_intake.py`: rule `dietary_intake` registered; docstring.
- Scenarios: `scenarios/mvp2_2_neolithic.yaml`, `scenarios/mvp2_2_pressure.yaml`.
- Tooling: `scripts/perf/exactness_oracle.py --model mvp2_2`;
  `scripts/probes/fertility_version_comparison.py`.
- Tests: `tests/test_model_versions.py` (new), `tests/test_dietary_intake.py` (updated).
- Candidate artifacts: `benchmarks/perf/oracle_mvp2_2.json`, `oracle_mvp2_2_logical.json`,
  `baselines/mvp2_2/` (freeze manifest plus three reference-run directories).
- Docs: the design document (§AC) and this file.

**Expanded stochastic experiment** (prespecified):
- Seeds 0–31 of neolithic (600 y) and pressure + cultivation (400 y), MVP 2.1 vs MVP 2.2,
  production code, 128 runs, none excluded.
- Pressure: final population H1/H0 median **1.071** [bootstrap 95 % 1.022, 1.138],
  H1 > H0 in 81 % of seeds, range 0.76–1.52; births 1.047 [1.021, 1.094].
- Neolithic: **1.033** [0.982, 1.057], 59 % of seeds, range 0.69–1.52 (no clear effect).
- Per-capita food (harvest/need, stores, deficit) unchanged within ±0.5 % in median.
- Granaries not changed (14 vs 12 · 8 vs 10 of 32; McNemar p = 0.79 · 0.75), but
  granaries discordance drives the extreme outcomes in both directions.
- Stage 5I's conclusions survive.

**H0 / H1 implementation status:**
- MVP 2.1 (switch off, the default for every existing scenario) reads `food_ratio`.
- MVP 2.2 (the `mvp2_2_*` scenarios) reads dietary intake `(min(H, N) + X)/N`, computed by
  energetics from its own inputs and passed through the transient context.
- No `food_ratio` mutation, no persistent state, no new RNG draw.
- Fission, innovation and starvation are unchanged.
- Production MVP 2.1 = experimental H0 and MVP 2.2 = experimental H1, bit-identical every
  year in 32 / 32 comparisons.

**MVP 2.1 exactness:** raw and logical oracles **IDENTICAL**; fixtures unchanged; no MVP 2.1
artifact touched.

**MVP 2.2 candidate reference:**
- Oracles recorded, then **reproduced IDENTICAL** in fresh processes.
- MVP 2.2 checked against the MVP 2.1 oracle is DIFFERENT, as expected.
- Manifest records status CANDIDATE with full provenance. Not promoted.

**Numerical invariants** (tested):
- source invariance at equal intake;
- reserves excluded;
- H1 ≥ H0;
- equal multipliers without stores;
- bounded ratio and multiplier;
- no silent fallback;
- scenarios differ only by name and switch;
- first-year energetics identical across versions;
- divergence only through births.

**Scientific interpretation:**
- The correction implements the documented intake mechanism.
- Its consequence is a modest population increase under storage-reliant pressure, and no
  clear change in neolithic.
- Rare technology events amplify divergence.
- No numerical instability was found.
- Biological limits: no body condition, duration, lactation or age sensitivity.

**Closure gates:** scientific, engineering and research gates all **passed** (§AC).
Candidate approval and formal closure are the reviewer's decision.

**Remaining issues (prioritized register in §AC):**
- fission food-stress semantics;
- knowledge ontology;
- centralized labor;
- unconditional 30 % sharing;
- most-severe-first priority;
- cooperative foraging stop;
- control without consequences;
- dust transfers and their adoption-RNG side effect;
- merge accuracy for future causal state.

**Recommended next research milestone** (not started; needs authorization):
- Make the provisioning decision the first active socioeconomic mechanism: who offers,
  with what information, constraints and consequences.
- Start with an audit and counterfactual of the fixed 30 % offer under scarcity, with
  dependency measured, not targeted.
- Prerequisites: MVP 2.2 approval; optionally a versioned dust-transfer fix.

**Reproduce Stage 5J** (`runs/` is gitignored; `run` resumes):

```bash
uv run pytest tests/test_model_versions.py tests/test_dietary_intake.py -q
uv run python scripts/perf/exactness_oracle.py benchmarks/perf/oracle_mvp2_1.json
uv run python scripts/perf/exactness_oracle.py --logical benchmarks/perf/oracle_mvp2_1_logical.json
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 benchmarks/perf/oracle_mvp2_2.json
uv run python scripts/perf/exactness_oracle.py --model mvp2_2 --logical benchmarks/perf/oracle_mvp2_2_logical.json
uv run python scripts/probes/fertility_version_comparison.py equivalence --jobs 2 --seeds 0 1 2 3 4 5 6 7
uv run python scripts/probes/fertility_version_comparison.py run --jobs 2 --out runs/stage5j/paired
uv run python scripts/probes/fertility_version_comparison.py analyse --load runs/stage5j/paired
```

Never run `make golden`, and never overwrite any `*mvp2_1*` artifact.

**Physical-feedback gate:** closed.

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
| 5J | Versioned correction: MVP 2.2 candidate (`mechanisms.dietary_intake_fertility`); MVP 2.1 exact; production = H1 (32 / 32); 32-seed paired: pressure +7.1 % [2.2, 13.8], neolithic +3.3 % [−1.8, 5.7]; granaries unchanged; candidate oracles reproduce; Stage 5 technically complete, pending approval | §AC |

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
  `entry_cost.py`, `knowledge_exposure.py`, `fusion_competence.py` and
  `economy/provisioning_counterfactual.py` are NOT ACTIVE: nothing in the simulator calls
  them, and their parameters are not scenario settings.
- `dietary_intake.py` is active only in the MVP 2.2 candidate
  (`mechanisms.dietary_intake_fertility`). The Stage 5I branch
  (`scripts/probes/fertility_intake_experiment.py`) remains its independent experimental
  reference.
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
