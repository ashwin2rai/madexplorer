# Implementation Status

**Updated:** 2026-10-14 (MVP 3 Stage 5H, awaiting review)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`)\
**Current milestone:** MVP 3, staged socioeconomic differentiation
(`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`)

How to read this file: the current handoff, then what MVP 3 has established, then the MVP
2.1 base. Scientific intent lives in `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; equations and
stage evidence in the MVP 3 design document; executable truth in code, tests and model
rules (`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs).

## 1. Current handoff

**Completed:** Stage 5H, material provisioning, donor choice and dependency validation
(design §AA). **PAUSE FOR SCIENTIFIC REVIEW.**

**Production behavior:** unchanged.
- `economy/provisioning_counterfactual.py` (NOT ACTIVE) is not called by the simulator,
  registers no rule and has no setting.
- Probe `scripts/probes/provisioning_counterfactual.py` (`record` about 2 min for 8 runs,
  `analyse` about 1 min, `controlled`).
- Tests `tests/test_provisioning_counterfactual.py` (11).

**Starting commit:** `babc078` (Stage 5G), clean worktree.

**Trade allocation audit** (`economy/trade.py`):
- Surplus is `H + stores − need`; the offer is 0.3 × surplus (a behavioral hypothesis).
- Deficit units are served by ascending `(balance/need, id)`; donors in range by ascending
  `(path cost, id)`. Both orders are deterministic and break ties by unit id.
- Transport: `exp(−cost/60 km)`. Donors pay from harvest, then stores.
- Ties are symmetric `+received/need`, decay × 0.7, are pruned ≤ 1e-3, rewired on fusion,
  and absent in daughters.
- Ties are read by diffusion and innovation only, never by trade.
- Newly recorded: floating-point dust transfers (0.7–1.5 % of transfers, ~1e-7 kcal)
  create transient near-zero ties.

**Baseline replay:** exact.
- Every authoritative transfer is reproduced bit for bit in 4,000 / 4,000 trade years
  (131,400 transfers).
- The energetics recomputation is exact, and the shadow ties at weight 0 are exact.
- All runs are observer-neutral.

**Meaningful donor choice** (neolithic · pressure):
- Nominal choice in 0.96 · 0.89 of served recipient-years.
- ≥ 2 donors able to deliver ≥ 25 % of the deficit: 0.79 · 0.46.
- ≥ 2 donors that could each cover the whole deficit: 0.43 · 0.13.
- Unserved deficit units always had no candidate left (exhausted supply).

**Donor substitutability:**
- Local replacement of the primary donor: full 0.90 · 0.72.
- Network rematch (competition respected): full 0.80 · 0.40, none 0.16 · 0.50.
- Under pressure, competition halves real replaceability.

**Trade ties beyond geography:**
- Lagged ties predict transfers (+0.08 · +0.11 within rank × cover × adequacy strata).
- But H0 never reads them, and the decision state determines the donor set (99.5–99.9 %;
  the rest are dust residues).
- The predictive power is the recurrence of geography, surplus, need and competition, not
  preference.
- Pairs are rarely two-way (9 %). A past reverse flow has no consistent effect.

**Static alternative routing** (H1 = tie first; H2 interpolates; λ = 0 equals H0 exactly):
- H1 changes the primary donor for 31 % · 15 % of recipients.
- Delivered food +0.4 % · −0.5 %; shipped +4.8 % · +1.5 %; loss share +2.5 · +1.1 points;
  unmet deficit −1.0 % · +0.3 %.
- It relabels donors and raises transport loss and donor burden. Welfare proxies move in
  the third decimal.
- Shadow tie history (physical history conditioned): recurrence 0.38 → 0.57 · 0.37 → 0.45;
  pairs ≥ 5 y 1.6 → 2.5 %.
  - The feedback is mechanical and weak, and insensitive to decay and initial ties.

**Material provisioning consequences:** reliance is real (§Z). Partner-specific
dependency is rare in neolithic and common under pressure (50 % irreplaceable after
rematching), caused by scarcity and competition, not by relationships.

**Food-ratio / fertility accounting:**
- `food_ratio = H/need` (harvest after trade) excludes store consumption.
- `nutritional_fertility` states an intake mechanism: "food intake falls below
  requirement".
- The same intake can give fertility 1.0 (all harvest) or 0.135 (60 % harvest + 40 %
  stores). Abundant stores with a poor harvest give 0.008.
- In real runs, `food_ratio` < 1 with no deficit occurs in 4.4 % · 9.0 % of unit-years
  (recipients 42 % · 21 %; donors 9 % · 4 %; non-traders 1.5 % · 12.5 %). Fertility gap
  p90 0.17 · 0.12.
- This is a property of the rule, not of trade. It is an unresolved semantic mismatch with
  strong evidence for interpretation A.
- Readers: fertility, fission and innovation. Nothing changed.

**Scientific decision: B primary, D secondary.**
- Do not introduce tie preference.
- Review the food-ratio semantics in a separate, versioned stage before any provisioning
  behavior.

**Population representation:** unchanged.

**Physical-feedback gate:** closed.

**Recommended next stage:** a food-accounting and fertility semantics review. It would
decide per reader (fertility, fission, innovation) between intake and production-stress
semantics, run a branched comparison against MVP 2.1, and set a new invariant and baseline
if approved.

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
  `economy/provisioning_counterfactual.py` are NOT ACTIVE.
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
