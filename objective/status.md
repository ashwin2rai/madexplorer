# Implementation Status

**Updated:** Simulation V1 strategy adoption (documentation-only handoff; prior Stage 6B-P4 record retained below)\
**Scientific base:** MVP 2.1, frozen (`baselines/mvp2_1/`), still the repository default.
MVP 2.2 (`baselines/mvp2_2/`, opt-in) is the scientific reference, selected explicitly through
`scenarios/mvp2_2_*.yaml`. Its fertility mechanism is scientifically accepted; its manifest
still reads CANDIDATE (administrative baseline state, unchanged).\
**Current milestone:** Simulation V1 strategic plan **adopted**, functional milestones
**not yet implemented**. Original MVP 3 strata investigations remain a preserved scientific
record; Stage 6C is not started. See `objective/SIMULATION_V1_ROADMAP.md` and
`objective/SCIENTIFIC_DEBT_REGISTER.md`.

How to read this file: the adopted V1 handoff first, the historical Stage 6B-P4 handoff,
what MVP 3 established, then the MVP 2.1 base. Scientific intent lives in
`SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`; the new near-term roadmap and documented
simplifications live in `SIMULATION_V1_ROADMAP.md` and `SCIENTIFIC_DEBT_REGISTER.md`;
equations and stage evidence remain in the MVP 3 design and Stage 6B review;
**executable truth** remains in code, scenarios, tests and model rules
(`madexplorer rules -v`). Older stage handoffs are in git (before `aae0974` the full
per-stage text; before `53c0491` the detailed MVP 2.1 and Performance Hardening logs; the
Stage 5J handoff at `204e413`; Stage 6A at `cabe833`; Stage 6B at `56a5122`; 6B-P1 at
`8dfe4df`; 6B-P3 at `11febe2`, closure `efe2603`).

## 1. Current handoff

### Strategic decision: 6B-P5 roadmap reassessment adopted

**Decision:** pursue **Simulation V1 first**, using progressive scientific fidelity built
around one complete ecological-demographic-social-institutional feedback loop. Preserve
the long-term scientific goal and the findings of Stages 5-6B. The new roadmap is a
**planning decision**, not permission to activate C1 or other unreviewed code.

**Three accepted V1 simplifications:**

1. Population units are collective social decision-makers. V1 can examine material and
   organizational inequality **between units**; active inequality **within units** is
   deferred. The current strata stay passive and their existing representation gate still
   applies if later activated.
2. Political capabilities are initially **bounded and reversible** delegated decision
   rights. Coercion, conquest, inherited offices, and states are beyond V1's claim scope.
3. The feasible **repertoire of institutional rules is assumed**, while selection,
   persistence, revision and dissolution may be conditional outcomes. V1 does not explain
   the original invention of the repertoire.

Additional simplifications (contact, donor offers, choice heuristics, memory, temporal and
ecological scale) are recorded individually, including bias, evidence limits and
replacement triggers, in `SCIENTIFIC_DEBT_REGISTER.md`.

**Next work:** V1-0, an implementation-neutral, testable V1 contract, then separate
reviewable implementation stages V1-1 through V1-5. V1-1 should consider a **minimal
necessary** local participation protocol; C1 is a candidate, not an automatic scientific
prerequisite. Original Stage 6C remains unstarted. Multi-seed, multi-topology feedback
and an adequacy check on zero-arable agricultural outside options are required before
V1's relevant claims. Do not activate mechanisms or change defaults without a specific
implementation review and version decision.

**What this documentation update does not change:** the supplied simulator code,
existing baseline manifests, opt-in 2.2 scenarios, production default, exactness oracles,
scientific results of Stages 5-6B, or passive strata state. No tests or historical
experiments have been rerun for this documentation-only adoption.

**Separate progress dimensions:** track each capability as absent / represented / active /
integrated, alongside a qualitative scientific-fidelity record with evidence and explicit
limits. Do not assign an unsupported numerical completeness/validity percentage. Each
future milestone has a functional gate and an independent minimum scientific-fidelity
gate, with a stop/defer decision to avoid recurring prerequisite research loops.

### Previous handoff: Stage 6B-P4 (historical recommendation under earlier sequencing)

**Stage 6B-P4 — scientific synthesis and Stage 6C decision gate. COMPLETE, PAUSED FOR
SCIENTIFIC REVIEW (uncommitted; documentation only).** Fourth of the five corrective
substages (P1 `8dfe4df`; P2 `b4b585d`, `36c5a72`; P3 `11febe2`, `efe2603`; P4 review §18;
P5 roadmap).

**Historical next step:** 6B-P5 strategic roadmap reassessment. That decision has now
been adopted above; Stage 6C remains unstarted and is not automatically authorized. The
P4 C1 selection remains useful evidence and a candidate design, not the V1 critical path.

**What P4 recommends** (review §18):
- *Symmetric comparison* (same level for all pathways: a consequential interaction and the
  smallest new unit-level decision). A, B and C all have a causal foundation. Exhausted
  labor removes A's effort margin, not its choice among rival cells; the pooling test
  (1.010–1.017 in all 8 runs) bounds only the stopping rule, not choice among cells (A) or
  untested coordination of access, timing or distribution (B).
- *Decision: pathway C, as C1* (local contact, requests and donor rationing; φ = 0.3 fixed),
  by a narrower margin than in 6B: its first question is exactly identifiable in static
  counterfactuals within one step against the P3 ceiling, and it replaces a non-actor
  implementation (global matcher, global visibility) of an already active interaction.
  A1's margin is unmeasured, not small. "Decision D" was 6B's option label for choosing C.
- *6C evaluation:* arms S (severity matching), R (random priority), G_S / G_R (centralized,
  severity / random, on the 6C contact graph), L (local requests, same graph), F (P3 ceiling
  on that graph: bounds G, L and other graph-restricted allocations, not S or R unless the
  graphs coincide), plus scheduling noise. Allocation policy is isolated only against
  contact-matched controls (L vs G_S, G_R). Proceed if differences are scientifically
  meaningful and interpretable across seeds, with uncertainty and heterogeneity reported,
  traceable to a named assumption, invariant to K and ids, and not reducible to a priority
  change; better delivery is not a criterion. A well-measured null is a useful result; stop
  at 6C-2 if contact cannot be grounded (pathway then conditional). Repeated dyads are
  tested against a contact-matched null. 6C-1 must check the termination rule against
  requesters with untried contacts.
- *Fallback:* A1, choice among rival resource-use opportunities with crowding and arable
  land in view; first step read-only. P5 may also prioritize it as a model correction.
- *Literature* re-verified (§18.3): no source shows provisioning rules emerging; Moritz et
  al. 2018 (PNAS, open regimes) and 2019 (Curr. Anthropol., no support for economic
  defensibility; title level only) are distinct; Aktipis 2016's threshold concerns the
  probability of honoring affordable requests, not the amount offered; Jaeggi & Gurven pool
  32 human and primate populations; coordination literature is an evidence gap.
- *Corrected citation:* 6B coverage medians are 22.5 · 13.7 (all recipient-years), 22.8 ·
  13.8 (with a reachable offering donor).
- *P4 checks:* per-seed A and B measures on fresh verified opportunity recordings (8 / 8
  neutral) and 6B medians on the P3 recordings, by scratch scripts using existing probe
  functions; no repository code, test or baseline changed; tests and oracles not rerun.

**Previous handoff — 6B-P3 (committed):**

**What P3 established** (review §17; kcal summed over seeds 0–3 and all trade years, % of
the total pre-trade deficit; neolithic · pressure):
- The production matching is reconstructed exactly from verified pre-trade inputs in every
  trade year (2,400 · 1,600); Stage 6A (71.5 % of recipient-years short, 72.4 % of offers
  shipped) and 6B (reachable full surplus p50 22.5 · 13.7 × deficit over all recipient-years;
  22.8 · 13.8 with a reachable offering donor, corrected in P4) reproduce.
- Delivered: matching 62.6 · 44.0; simultaneous optimum under the same offers, reach and
  transport 65.0 · 50.2 (+2.4 · +6.2 points; 3.9 % · 14.2 % of what the matching delivers).
  Unmet even under the optimum, given offers, reach, transport and a one-year horizon:
  35.0 · 49.8 (not physical inevitability).
- Bottlenecks are conditional, not additive. Neolithic: geography and transport (lossless
  +15, all pairs +20), not supply (offers 9 × deficits) or matching. Pressure: all bind;
  offer cap +37 (with transport), transport +21, reach +10, matching +6.
- Years are solved separately (no food crosses years). Cumulative offers 933 · 115 % of the
  deficit, but yearly offers fall short in 1.0 · 35.0 % of years; the annual aggregate offer
  gap (deficit − H) is 0.04 · 18.1 %, reach and transport given the offers (H − B) 34.9 ·
  31.7 %. Full surplus is almost never short within a year (E 100 · 99.9), but that ceiling
  removes the offer cap.
- Apparent surplus is multiply counted (claimed / distinct offers 1.6 · 4.0). Networks with
  every deficit simultaneously satisfiable: 74.5 % · 15.2 % of network-years, but only
  25.4 % · 2.0 % weighted by recipients and 15.6 % · 1.1 % by deficit (small networks
  dominate the count).
- The optimum's distribution is not unique (two labelled tie-breaks differ for 18.6 % ·
  26.4 % of recipient-years). Robust across the three optima examined: more full relief
  (pressure 28.5 → 50.5–53.7 %) and fewer with nothing. Pressure intake p1 is lower under all
  three (0.444 → 0.366–0.386), which is not tested for every optimum; neolithic p1 depends on
  the tie-break. Removing the severity priority (random recipient order) reassigns 15 % ·
  31 % of delivered food at ±1.4 % total: a policy change. Arbitrary ids have no effect (no
  severity ties; equal-cost ties are interchangeable same-cell donors).
- One world topology per scenario (worlds 7 · 3); robust across the four seeds.

**Files changed (NOT ACTIVE):**
- `src/madexplorer/economy/provisioning_feasibility.py` (new): the LP, its independent
  feasibility and duality checks, components, edges.
- `scripts/probes/provisioning_feasibility.py` (new): analysis of the donor-offer recordings,
  join with the opportunity recordings, benchmarks, distribution and order sensitivity.
- `tests/test_provisioning_feasibility.py` (new, 18 tests after the interpretation check); `tests/test_provisioning_counterfactual.py`
  (the new inactive module may name `provisioning_counterfactual`).
- `pyproject.toml`, `uv.lock`: SciPy 1.18.1 in the dev group (HiGHS); mypy ignores its
  missing stubs. numpy and numba unchanged; numba imports SciPy at import time for a
  version check; no model code uses it.
- Review §17; this file.

**Production default:** unchanged. Simulation code untouched; the re-recorded
opportunity data are byte-identical to the P2 recordings.

**Validation:**
- 16 / 16 reference runs recorded (donor offer and opportunity), all observer-neutral, one
  execution environment; join identical in 8 / 8; reanalysis identical (`--jobs 2` and 1).
- `tests/test_provisioning_feasibility.py`: 17 pass. `make check`: lint, format, mypy (144
  files) and 989 tests pass. `make test-stat`: 3 passed.
- Oracles: MVP 2.1 raw and logical IDENTICAL; MVP 2.2 raw and logical IDENTICAL.
- `git diff --check`: clean. No golden regenerated, no RNG change, no default activation.
- Interpretation check (2026-10-29): 8 / 8 donor-offer runs re-recorded from `11febe2`,
  observer-neutral, one environment; every §17 number reproduced; replay exact in all years.
  18 feasibility tests, `make check` (990 tests), `make test-stat` (3), four oracles
  IDENTICAL, `git diff --check` clean. Diagnostics added to the probe report only.

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

**Reproduce:**

```bash
uv run pytest tests/test_provisioning_feasibility.py -q
uv run python scripts/probes/donor_offer_audit.py record --jobs 2 --out runs/stage6b_p3/donor
uv run python scripts/probes/opportunity_audit.py record --jobs 2 --out runs/stage6b_p3/opportunity
uv run python scripts/probes/provisioning_feasibility.py analyse --load runs/stage6b_p3/donor --opportunity runs/stage6b_p3/opportunity
```

Never run `make golden`, and never overwrite any `*mvp2_1*` or `*mvp2_2*` artifact.

**Carried into the adopted V1 roadmap and debt register** (review §18.9):
- zero-arable cultivation (221 units, up to 136 years): field planning and migration do not
  share arable information; a model-adequacy question, not a migration feature request;
- shared-resource rivalry as a substrate for later access decisions, without ownership;
- passive strata: representation is not mechanism;
- provisioning premises (φ, central matching, global priority, geographic contact);
- verification vs scientific validation;
- the order of between-unit interaction and internal differentiation in the MVP sequence;
- missing model capabilities (within-year timing, joint production, clumped resources, one
  topology per scenario).

## 2. MVP 3 so far

This table preserves completed investigations and their findings. It is **not** the new
critical path for V1; in particular, active within-unit strata are deferred while minimal
interunit arrangements and decision rights are developed (see roadmap §1 and §9).

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
| 6B-P3 | Provisioning feasibility: matching reconstructed exactly; simultaneous LP optimum (HiGHS, duality-certified) delivers 65.0 · 50.2 % of the deficit vs matching 62.6 · 44.0 %; neolithic limited by geography and transport, pressure by offer cap, transport, reach and matching together; annual aggregate offer gap 0.04 · 18.1 % (full surplus almost never short within a year); apparent surplus multiply counted (1.6 · 4.0); networks jointly satisfiable 74.5 · 15.2 % by count, 15.6 · 1.1 % by deficit; optimum distribution not unique (pressure p1 lower under the three optima tested) | review §17 |
| 6B-P4 | Synthesis and decision gate: pathways compared at the same level; A, B and C all have causal foundations (pooling test bounds only the stopping rule, 1.010–1.017); pathway C retained as C1 (local contact, requests, donor rationing, φ fixed) by a narrower margin, for identifiability and the actor-semantics gap; 6C judged by distinguishable, interpretable consequences against centralized controls on the same contact graph and the P3 ceiling, no expected direction; fallback A1 (choice among rival opportunities); zero-arable, rivalry, strata and premises reserved for P5 | review §18 |

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

For V1 prioritization, use `SCIENTIFIC_DEBT_REGISTER.md` and the decision rules in
`SIMULATION_V1_ROADMAP.md`. Unresolved questions here remain scientific context but are
not automatic V1 blockers.


1. **Agriculture representation.** Is the `plant_cultivation` affordance sufficient long
   term, or should local domesticability and domestication become continuous ecological
   and cultural processes (objective §8.2)?
2. **MVP 3 questions** are listed in the design document's open-questions section.
