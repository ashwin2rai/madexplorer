# Implementation Status

**Updated:** 2026-10-09 (MVP 3 Stage 5C, awaiting review)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`)\
**Current milestone:** MVP 3, staged socioeconomic differentiation
(`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`)

How to read this file: the current handoff, then what MVP 3 has established, then the MVP
2.1 base. Scientific intent lives in `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; equations and
stage evidence in the MVP 3 design document; executable truth in code, tests and model
rules (`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs).

## 1. Current handoff

**Completed:** Stage 5C, entry costs and participation continuity (design §V), a
counterfactual. **PAUSE FOR SCIENTIFIC REVIEW.**

**Production behavior:** unchanged. `population/entry_cost.py` is not called by the
simulator, has no scenario setting and registers no model rule. Both MVP 2.1 oracles are
identical.

**Starting HEAD:** `eeb431f` (Stage 5B). Real runs at `15e06f0`.

**Done:**
- **Pure module** `population/entry_cost.py` (NOT ACTIVE): entry-cost factor by memory
  (window, decay), minimum-entry allocation with proportional ties, history-blind
  allocations (proportional, rotation), status-quo retention, participation split, history
  advance, and turnover.
- **Tests:** `tests/test_entry_cost.py`, 27 passing, including the corner, tie neutrality,
  infeasibility, conservation, and an observer-neutrality run.
- **Probe:** `scripts/probes/entry_cost_counterfactual.py` (`controlled`, `runs`,
  `report`): 15 controlled cases, a hysteresis cycle and 13 real-run shadows.

**Candidate mechanism:** entry and re-entry costs (`e` hours per entering
labor-equivalent; a probe input, no canonical value) and path-dependent participation.

**Does it explain initial differentiation?** No.
- First entry is §U's corner: `f* = P/(B − eL)` for every `e > 0`, and indifference at 0.
- The cost decides how many enter, not who.
- A strict subset enters only under a myopic unit-level coordination assumption. Over
  real histories, universal participation costs the same entry labor (neolithic) or half
  (pressure).

**Does it explain continuity?** Partly.
- Incumbents come before newcomers. That saves 70–85 % of rotation's entry labor (about
  0.5 % of capacity at `e = 50`).
- When incumbents exceed need, how many to keep is indifferent. The outcome then depends
  on the memory form and the tie convention: allocation hysteresis is convention-made
  except under decaying memory.

**Mathematical result:** minimum entry fills components in ascending entry factor (greedy
is optimal). Corner at initiation; an indifference interval `[P/B, h]` when incumbents
suffice; all incumbents plus `(P − hB)/(B − eL)` entrants otherwise. Entry cost locks in
whatever the first allocation was.

**Competence effect:**
- With one-year memory, identical to §U's continuity: median E-gap 0.021 / 0.006, median
  yield effect 1.2 % / 0.2 %.
- Decaying memory raises the median yield effect to 2.9 % / 0.4 %. The size of `e` is
  irrelevant to competence.
- Competence assignment remains larger (4.1 % / 1.1 %).

**Representation pressure:**
- Continuity halves rotation's splits (6.8 vs 13.4 per unit-year); `retain` cuts them 12×
  by locking in cores.
- Every rule fills the capacity except a τ = 0.05 divergence merge (5.0 / 3.4
  components).
- Under 10-year memory, near-equal competence with a different entry-cost class is common
  (0.2 pairs per unit-year), so a merge metric must respect history.

**Population-turnover limitation:**
- About 3 % of labor is new to work each year, so half of a participating component is
  its members' successors after about 22 years.
- Turnover changes gaps by about 12 %, but any persistence beyond about a generation is
  hereditary by representation in anonymous strata.

**Resolution 16 vs 32:** identical gaps, yield effects and persistence; dispersion within
3 %. Capacity changes only churn.

**Scientific recommendation: B** (explains continuity, not initiation), with a D caveat
on magnitude.

**Unexplained:**
- why a subset rather than everyone starts;
- how many incumbents to keep;
- which memory form is real;
- the physical cost of infeasible entry (6.2 % of pressure farming unit-years under
  minimal continuity).

**Next:** PAUSE FOR SCIENTIFIC REVIEW. Do not begin Stage 5D without it.

**Physical-feedback gate:** closed.

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
- `strata_access.py`, `store_release.py`, `field_control.py`, `practice_concentration.py`
  and `entry_cost.py` are NOT ACTIVE. Nothing in the simulator calls them, and their
  parameters are not scenario settings.
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
