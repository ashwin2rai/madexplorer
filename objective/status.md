# Implementation Status — MVP 3 (staged)

**Updated:** 2026-10-02\
**Current scientific base:** MVP 2.1 frozen; pre-MVP 3 consolidation complete\
**Current milestone:** MVP 3 — staged socioeconomic differentiation

## MVP 3 stage handoff

**Completed stage:** Stage 1 — neutral strata representation (Stage 0 design:
`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`).

**What now exists**
- `population/strata.py`: the stratum column schema (`StratumField`: `share`,
  `field_claim`, `store_claim`, each a partition of unity); `StrataTable` (padded
  `[rows, S_MAX = 8]` float64 columns + `int64` ids + `int8` count, row = unit slot);
  `StrataBlock` (detached / object-engine form); `neutral_strata()` with the
  `stratum_composition` model rule.
- `PopulationStore.strata` (present exactly with the unit table) and a per-store stratum-id
  counter (`new_stratum_ids`). Binding a unit gives its strata fresh ids; the unit
  `IdAllocator` is untouched.
- `fields.py` has one `strata` entry (`Storage.STRATA`); the stratum columns are not unit
  fields.
- Lifecycle:
  - founding and creation give one neutral stratum;
  - fission copies the parent's strata as new components (fresh ids);
  - fusion keeps the target's single neutral stratum, and fusion of differentiated strata
    raises `NotImplementedError` before any change;
  - removal resets the row; slot reuse starts fresh; detach and rebind round-trip the
    values; deepcopy is independent.
- Per-step invariant check (`check_state_units`): every live unit has 1..S_MAX strata,
  shares > 0, columns sum to 1 (≤ 1e-12), zero padding, assigned ids.

**Scientific behavior:** none. No mechanism reads strata; no RNG; no new metrics or events.

**Validation (Stage 1):** `make check` 567 passed; `make test-stat` 3/3 (strict xfail
unchanged); raw and logical MVP 2.1 oracles IDENTICAL; golden fixtures unchanged;
`git diff --check` clean. Tests: `tests/test_strata.py`, plus strata (values and ids) in the
table-vs-object differential `unit_state`. Memory: 257 B per strata row (0.61 MB at 2,000
units ≈ +15% of the unit table; ≈ 13 MB at 50k). `bench-quick` 95.9–104.9 ms/tick against
a 98.1 baseline (noise).

**Next stage:** Stage 2 — socioeconomic quantities / controlled heterogeneous
representation. Starts only on explicit approval:
- fusion inheritance (concatenate strata, absolute positions renormalized; zero-stock
  fallback);
- deterministic capacity coalescence above `S_MAX` (ties by state, never id or position);
- migration and zero-stock handling of claims;
- the sidecar strata stream keyed by `(year, unit_id, stratum_id)`;
- controlled heterogeneous fixtures;
- provenance (`strata_fusion_inheritance`, `claim_zero_stock`,
  `strata_capacity_coalescence`);
- MVP 2.1 oracles still identical.

**Scientific decisions locked in**
- A stratum is a label-free mixture component: `share` (population weight), entitlement
  and control shares over unit-level physical stocks (`field_claim`, `store_claim`), and
  an opaque id. No class types or societal states as causal switches.
- Physical stock stays `[U]`; control stays `[U,S]`. Socioeconomic position is
  `claim / share` (1 = proportional). Neutral allocation is `claim = share`. If a stock is
  zero, claims equal shares (no NaNs, no invented inequality). There are no zero-population
  strata.
- Fusion inherits prior absolute positions (`claim × unit stock`, renormalized by the new
  total), with neutral fallback at zero total. Fission copies.
- A mechanism that creates new stock must state who controls it. Claims are never silently
  preserved or diluted.
- Strata share the unit's age–sex structure (canonical); no `[U,S,sex,age]` until a
  mechanism creates demographically meaningful stratum differences.
- Strata metrics and events go only to a sidecar stream keyed by
  `(year, unit_id, stratum_id)`, which never feeds back. The frozen MVP 2.1 metrics and
  event schemas are unchanged.
- Through Stage 4 no `[U]` mechanism reads strata, so the MVP 2.1 oracles stay identical.
  A new versioned baseline comes only when socioeconomic state intentionally affects
  existing behavior.
- Creation is mechanism-driven; there is no statistical split test.
- Stage 2 adds capacity coalescence (deterministic, numerical, ties broken by state);
  Stage 4 adds adaptive merging of indistinguishable components.
- Stage 3 entitlement weight (e.g. `field_entitlement_weight`): neutral 0 = the legacy
  equal-pooling limit. Nonzero values are hypotheses and sensitivity cases, never tuned. A
  reference value is set only with an MVP 3 baseline.
- Neutrality: ID renumbering is bit-exact; reordering holds within a strict float
  tolerance; conserved totals use the tightest invariant. Stochastic mechanisms must never
  depend on stratum IDs or storage order.
- `S_max = 8` is a numerical resolution limit, not a number of classes. Test sensitivity
  once adaptive strata are behaviorally active.

**Open questions**
- Stage 3: the explicit allocation rule for newly cleared land and newly stored surplus
  (proposed: ∝ share plus the §F attribution).
- Stage 4: the adaptive-merge criterion and tolerance in relative-position space.

**Known limitations (Stage 1)**
- Passive representation only; no heterogeneous socioeconomic state yet.
- Stratum ids are per-store handles: a unit removed and re-inserted gets new ids.
- The object (reference) engine keeps strata on unit objects; the table engine in
  `StrataTable`. Both allocate the same id sequence (checked by the differential tests).

**Do not forget**
- Stage 2 introduces representational heterogeneity, not hierarchy; there is still no
  causal socioeconomic feedback.
- Capacity coalescence belongs to Stage 2; adaptive merging to Stage 4.
- Never `[U,S,sex,age]` or `[U,S,S]` without a demonstrated need; no per-stratum Python
  objects in hot paths; do not flatten stratum columns into the unit-field ontology.
- Do not use strata to brake population growth (§4 known demographic simplification).
- Leave changes uncommitted; stop after each stage.

---

## MVP 2.1 base handoff

A short, durable handoff: current state, what to preserve, accepted limitations, lessons
and open questions. Read other artifacts by role:

- `objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`: scientific intent and architectural constraints;
- `baselines/mvp2_1/freeze_manifest.json`: the frozen baseline and its validation record;
- source, scenarios, tests and model rules (`madexplorer rules -v`): executable semantics;
- `benchmarks/perf/`: retained performance evidence.

---

## 1. Current state

- MVP 1, MVP 2 and Performance Hardening are complete.
- MVP 2.1 is frozen and is the base for future science. Its only semantic difference from
  MVP 2 is **B1**, the merge-familiarity decay-year fix.
- The pre-MVP 3 consolidation is complete: an exact, semantics-preserving refactor (§2).
- MVP 3 has started (stage handoff above).

### Frozen artifacts

| Artifact | Location |
|---|---|
| Manifest | `baselines/mvp2_1/freeze_manifest.json` |
| Golden fixtures | `tests/regression/golden/` |
| Raw-byte oracle (dense beliefs) | `benchmarks/perf/oracle_mvp2_1.json` |
| Logical oracle (any backend) | `benchmarks/perf/oracle_mvp2_1_logical.json` |
| Canonical scenarios | `scenarios/mvp2_neolithic.yaml`, `scenarios/mvp2_pressure.yaml` |
| MVP 2 history | `baselines/mvp2/` |

**Source hash.** The manifest's source-tree SHA-256
(`55a9ea94…2845c`) identifies the *original* frozen MVP 2.1 implementation. It is not, and
will never again be, the hash of the current tree. The current code is MVP 2.1 because it
reproduces the golden fixtures and both oracles exactly, and the neolithic 4 × 600 reference
runs (final populations, first-cultivation and 25%-farm-share years per seed), not because
of that hash.

---

## 2. Architecture to preserve

- **One owner of population state.** `PopulationStore` (`population/store.py`) owns the
  unit registry (identities, processing order), the `UnitTable`, the belief store and slot
  allocation. `SimulationState.units/table/belief_store` are read-only views. A unit
  belongs to at most one store: inserting a unit bound to another store raises before
  anything changes; ownership moves only by explicit removal then insertion. MVP 3's
  `StrataTable` joins this owner; it must not become an independently mutable sibling.
- **One declaration per unit field.** `population/fields.py` declares each field's storage
  and merge/split rule. Table columns, row descriptors, `FIELD_RULES` and the
  extensive/intensive groups derive from it; a test checks it against the dataclass. New
  state (wealth, health, …) must be declared there first.
- **Table-authoritative production, object-authoritative reference.** `UnitTable` is the
  numeric authority; the object engine (`unit_table=False`) and `composition.py` remain
  independent oracles for `lifecycle.py` row operations. Duplicate *implementations* where
  independence is useful; never duplicate the *definition* of what state means.
- **Sparse beliefs in production**, dense as the exactness reference.
- **Static / compiled / dynamic separation** (`StaticContext`, `CompiledScenario`, state).
- **Step order is scientific semantics.**
- **evaluate draws, apply commits.** Every stochastic decision (including fission's departing
  cohorts) is made in `evaluate` on named streams; `apply` is deterministic.
- **Named RNG streams**: draw count, order, independence and meaning never change by
  accident. Stochastic draws stay outside compiled kernels: named stream → pre-draw →
  kernel → state update.
- **Group-level candidate generation** for migration (`gather_candidates`) is separate from
  scoring and choice (`best_destinations`): the seam for MVP 3 selective migration.

## 3. Lessons from Performance Hardening

- Improve representation and dataflow before compiling kernels; profile again after each
  structural change (hotspot rankings expire quickly).
- Compile scenario data once; keep hot state columnar and sparse state sparse; batch
  regular work; compile only what stays hot.
- Scaling at fixed density was near-linear (≈95–112 µs per unit-year from ~2k to ~50k
  units on the campaign machine; ~2.5 GB RSS at ~50k units). Historical, machine-specific.
- A mathematically equivalent float rewrite is not automatically bit-identical; keep raw
  and logical oracles for the two equivalence levels.
- No dominant kernel remains; optimize future bottlenecks only when measured.
- **MVP 3 memory risk:** demography's temporaries (~9.4 kB per unit per tick) multiplied by
  8–16 strata would reach multi-GB working sets at scale. Design stratified demography as
  pre-drawn RNG → fused/chunked unit × stratum kernel → bounded workspace → direct cohort
  writes.

## 4. Accepted limitations

- **Aggregation/coarsening is not scientifically neutral.** Off by default and in every
  canonical scenario; the coarsening statistical check stays a strict xfail. MVP 3 adaptive
  resolution must preserve behaviorally important heterogeneity.
- **Migration utility mixes wild-food stock and crop flow** (an accepted approximation).
- **Ecology is simple:** no seasons, little succession, simple soil and exchange.
- **Social state and migration are group-level:** no within-unit wealth, health, occupation,
  status or selective emigration (MVP 3).
- **Technologies are Boolean with hard prerequisites** — a coarse MVP 2 hypothesis
  (objective §8.1). `plant_cultivation` is an affordance (crop capability > 0), not a model
  of domestication.
- **Known demographic simplification.** Populations that stay adequately fed grow close to
  the life-table ceiling while unoccupied territory remains. The frozen reference runs grow
  ~0.9–1.1%/yr over 600 years against ~1.24%/yr for the unconstrained life table: fertility
  stays near its maximum, mortality near baseline, starvation mortality is negligible, and
  expansion keeps local crowding low. Extra work effort and mobility carry little direct
  demographic cost. Farming is not the main cause (growth is already ~1%/yr before
  agricultural dependence). Not an implementation defect (2026-10-02 audit,
  `scripts/probes/demography_audit.py`). Later social, epidemiological, economic and
  territorial mechanisms may change food access, workload, exposure, mobility costs,
  conflict, fertility and mortality — **through explicit causal pathways, never as a brake
  added to force population toward a desired number.**
- `move_hazard` is recorded each year but read by no mechanism since the expected-tenure
  experiment was removed; it is kept because the exactness oracle hashes it.

## 5. Solved problems not to reintroduce

Candidate-count (best-of-many) migration bias; map-wide lossless belief synchronization;
uncertainty-free direct observations; hard saturation of food utility; permanent inherited
familiarity; the field-growth bootstrap trap (proportional growth from a tiny first plot,
now removed); counting field crop twice when leaving (the legacy penalty, now removed);
innovation ordering bias; RNG coupling across mechanisms; treating a population plateau as a
required outcome; treating naive aggregation as neutral. Revisit any of these only for a
concrete scientific reason, after understanding why the current mechanism exists.

Removed as project history (2026-10-02): `mechanisms.expected_tenure` (rejected),
`mechanisms.field_growth_to_target` and `mechanisms.field_replacement_cost` (accepted
behavior now unconditional), species parameters `initial_plot_ha` and
`abandoned_fields_weight`.

## 6. MVP 3 constraints

```text
shared group state       [U]          location, species, beliefs, familiarity, most
                                      culture/knowledge, technologies, network, candidates
distributional state     [U, S]       only what a mechanism needs by stratum
demographic cohorts      [U, S, sex, age]
```

- Joint weighted strata, not independent marginals; only distribution-sensitive mechanisms
  pay for `S`.
- Bounded demographic workspace (§3). Cohorts may move to `int32` (totals `int64`) only as
  a separate, benchmarked, validated change.
- Keep backend portability possible: explicit arrays, explicit random inputs, bounded
  kernels; no Python-object or Numba behavior inside the scientific definition. No backend
  framework until a backend exists.

## 7. Change and validation discipline

1. Classify each change: exact optimization/refactor, numerical reformulation, bug fix, or
   scientific model change.
2. Use the smallest test that can falsify it; keep `make check` green.
3. Exact work: golden fixtures and both oracles must stay identical
   (`scripts/perf/exactness_oracle.py [--logical]`). Never run `make golden` to absorb an
   unexplained difference.
4. Behavior may change: run `make test-stat`; version and re-baseline deliberately.
5. Never change RNG semantics or coefficients to recover an old trajectory.
6. A newly found scientific bug is classified, reproduced in a test, versioned and
   re-baselined — never fixed silently inside a refactor.

## 8. Open scientific questions

These are questions, not bugs or blockers. Answer them with experiments and versioned model
changes, not by tuning inside a refactor.

1. **Agriculture representation.** Is the zero-crop-capability → `plant_cultivation`
   affordance sufficient long term, or should a later milestone model local domesticability
   and biological domestication as continuous ecological/cultural processes
   (objective §8.2)?

## 9. Historical references

Comments citing stabilization items (P1–P7), hardening phases (PH0–PH5) or numbered
`status.md` sections refer to the pre-consolidation records in git history:
`git show 53c0491:objective/status.md` (the detailed MVP 2.1 status, including the defect
audit the manifest cites) and the retired Performance Hardening log (in git history before
commit 2ada934).

## 10. Handoff

> **MVP 2.1 is frozen and consolidated. MVP 3 proceeds stage by stage from
> `objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`; see the stage handoff at the top.**
