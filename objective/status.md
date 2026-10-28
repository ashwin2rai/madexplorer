# Implementation Status

**Updated:** 2026-10-28 (MVP 3 Stage 6B-P2, reproducibility and audit integrity; pause for review)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`), still the repository default.
MVP 2.2 (`baselines/mvp2_2/`, opt-in) is the scientific reference, selected explicitly through
`scenarios/mvp2_2_*.yaml`. Its fertility mechanism is scientifically accepted; its manifest
still reads CANDIDATE (administrative baseline state, unchanged).\
**Current milestone:** MVP 3, staged socioeconomic differentiation
(`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`)

How to read this file: the current handoff, then what MVP 3 has established, then the MVP
2.1 base. Scientific intent lives in `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; equations and
stage evidence in the MVP 3 design document; executable truth in code, tests and model
rules (`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs; the
Stage 5J handoff at `204e413`; Stage 6A at `cabe833`; Stage 6B at `56a5122`; 6B-P1 at
`8dfe4df`).

## 1. Current handoff

**Stage 6B-P2 — experimental reproducibility and audit integrity. COMPLETE, PAUSED FOR
SCIENTIFIC REVIEW.** Second of the five corrective substages after the Stage 6B review
(P1 measurements, approved and committed at `8dfe4df`; P2 integrity; P3 provisioning supply,
demand and feasibility; P4 synthesis and the Stage 6C decision gate; P5 roadmap).

**Next: 6B-P3** (not started). P4, P5 and Stage 6C are not started. Decision D / pathway C
stays **provisional** until P4. P2 issues no scientific decision.

**Starting commit:** `8dfe4df` (6B-P1 committed), clean worktree.

**What P2 found and corrected** (details in review §16):
- *Reuse by filename.* The three Stage 5H–6B probes (`opportunity_audit`,
  `donor_offer_audit`, `provisioning_counterfactual`) skipped any existing `NAME_SEED.pkl`
  and analysed every `*.pkl` in a directory, with no provenance. Now each recording embeds
  its provenance and a data checksum, is written atomically, is reused only if intact and
  matching (else `record` stops; `--replace` overwrites), and `analyse` loads exactly the
  requested runs (duplicates, unexpected, missing, mixed sources and wrong identities are
  errors; `--seeds` gives an explicit subset).
- *Weak neutrality check.* `physical_digest` misses ecology, trade ties, beliefs and the id
  allocator (demonstrated in a test). New: an audit-only state fingerprint over every
  declared unit field (`population.fields.UNIT_FIELDS`, read through authoritative storage;
  beliefs in logical form), ecology, climate, world, RNG streams, id allocator, events and
  strata sidecars, compared with an uninstrumented twin stepped in lockstep every 25 years
  and at the end.
- *Global hooks.* Observers replaced class methods (leaks into later runs in the same
  worker were possible). Now hooks sit on the simulator's own subsystem instances; the two
  module functions that must be observed (`agriculture_kernel.plan_fields`,
  `migration.gather_candidates`) are swapped only for the instrumented call (`try/finally`).
- *No realized transfers in 6B.* The opportunity probe now records the authoritative
  transfers (donor, recipient, shipped, delivered, need) and the trade ledger, joined by
  `(year, unit id)`. `provisioning_counterfactual` records MVP 2.1 runs, so it could not
  have been joined to the MVP 2.2 6B recordings.
- *No earlier result is now uncertain:* the new recordings reproduce every P1 data field
  exactly (8 / 8 runs), so every P1 figure stands.

**P1 findings carried to P4 / P5** (accepted; review §15–15.1; neolithic · pressure):
- Remaining foraging target met 74.0 % · 29.3 %; under pressure 63 % of eligible unit-years
  are in groups that exhausted labor, which is not proof that labor is the binding margin
  (elasticity p50 0.76 · 0.70).
- Collective cell utilization > 0.5 in 4.0 % · 28.8 % of foraging cell-years (descriptive,
  not stock limitation); rivalry consequential (+2.5 % · +4.3 % of need).
- Arable land (pressure): allocation limited by the cap in 1,953 / 58,716 farming
  cell-years; land *unavailable* (zero arable, desired fields > 0) in 1,928, 2,803
  unit-years, 221 units, p50 6 and up to 136 years each; *competition* in 25 / 56,788
  positive-arable cell-years; no exclusion mechanism. Migration does not consider arable
  land: a possible missing feedback, not proof that considering it would cause migration.
- Provisioning: nearby surplus is hypothetical and multiply counted, potential role
  reversal is not reciprocity, reach is not contact, knowledge or willingness.

**Files changed (all uncommitted, NOT ACTIVE):**
- `scripts/probes/_integrity.py` (new): provenance, atomic container, reuse and analysis
  selection, instance hooks, lockstep neutrality, state fingerprint.
- `scripts/probes/opportunity_audit.py`: schema 2 (transfers, trade ledger), instance hooks,
  provenance, validated record/analyse, transfer integrity checks.
- `scripts/probes/donor_offer_audit.py`, `scripts/probes/provisioning_counterfactual.py`:
  schema 1, instance hooks, provenance, validated record/analyse.
- `tests/test_probe_integrity.py` (new, 21 tests); `tests/test_opportunity_audit.py`
  (2 transfer tests, fingerprint instead of digest).
- Review §16; this file.

**Production default:** unchanged. No file under `src/` was modified; `config_hash` and
the source-tree hash of the P1 recordings are unchanged.

**Validation** (reference demonstration in review §16):
- 8 / 8 full reference runs recorded twice (`--jobs 2`: 183 s; `--jobs 1`: 239 s), all
  neutral; data bytes identical; P1 data reproduced exactly; reanalysis identical.
- Probe tests: 71 pass (`test_probe_integrity` 21, `test_opportunity_audit` 24,
  `test_donor_offer` + `test_provisioning_counterfactual` 26).
- Oracles: MVP 2.1 raw and logical IDENTICAL; MVP 2.2 raw and logical IDENTICAL.
- `make check`: lint, format, mypy (142 files) and 964 tests pass. `make test-stat`: 3 passed.
- `git diff --check`: clean. No golden regenerated, no RNG change, no default activation.

**Reproduce:**

```bash
uv run pytest tests/test_probe_integrity.py tests/test_opportunity_audit.py -q
uv run python scripts/probes/opportunity_audit.py record --jobs 2 --out runs/stage6b_p2/record_a
uv run python scripts/probes/opportunity_audit.py analyse --load runs/stage6b_p2/record_a --jobs 2
# pre-6B-P2 recordings (no provenance), explicitly unverified:
uv run python scripts/probes/opportunity_audit.py analyse --load runs/stage6b_p1/record --legacy-unverified
```

Never run `make golden`, and never overwrite any `*mvp2_1*` or `*mvp2_2*` artifact.

**Carried to later substages:**
- P3: joint feasibility of multiply counted surplus, now against the recorded realized
  transfers; the zero-arable demand (blocked units that never relocate).
- P4: the cross-pathway synthesis, including whether A's rivalry, the pressure-scenario
  target shortfalls and land unavailability change the ranking.
- P5: roadmap and MVP realignment.

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
| 6A | Donor offers: D0 exact from raw inputs (4,000 / 4,000); unused offers never withholding; offer binds in 64 % of pressure donor-years; delivered food ≈ ∝ φ; a given kcal costs ≈ `r` kcal of next year's stores, of which ≈ 1–2 % would ever buffer the donor's later shortage; willingness unexplained (φ exogenous; no reciprocity, insurance or directional memory); security cap rejected (unanchored); B, nothing implemented (audit + static counterfactual) | §AD |
| 6B | Comparative review (A access, B coordination, C risk pooling; several figures corrected in 6B-P1): land never binds, resources diffuse, outside options open and known (A not identifiable); pooled vs independent ≈ 1 % (B rejected); surplus in reach for 99.7–99.9 % of short units, bilateral reversal feasible 63–69 % (C strongest); D (provisional since 6B-P1): substrate present, actor-level interaction missing; 6C = local need requests with proportional rationing | §AE, review |
| 6B-P1 | Measurement corrections: remaining foraging target met 74 % · 29 % (not 90 % · 77 %; crops counted twice); land rationing rare and local (pressure 0.044 %, plus zero-arable demand), not "never"; collective cell utilization separated from individual share; role reversal is potential, not observed transfers (51–69 %); reachable surplus hypothetical and multiply counted; decision D provisional until P4 | §AE, review §15 |
| 6B-P2 | Recording integrity: provenance container with data checksum and atomic writes; reuse and analysis only of intact, matching, requested runs (legacy recordings only with `--legacy-unverified`); state-fingerprint neutrality against a lockstep twin; instance-level hooks; authoritative transfers recorded in the opportunity probe; P1 data reproduced exactly (8 / 8); serial = parallel bit for bit | review §16 |

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
  `economy/provisioning_counterfactual.py`, `economy/donor_offer.py` and
  `economy/opportunity_audit.py` are NOT ACTIVE: nothing in the simulator calls
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
