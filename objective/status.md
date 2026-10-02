# Implementation Status — MVP 3 (staged)

**Updated:** 2026-10-02\
**Current scientific base:** MVP 2.1 frozen; pre-MVP 3 consolidation complete\
**Current milestone:** MVP 3 — staged socioeconomic differentiation

## MVP 3 stage handoff

**Completed stage:** Stage 2.1 — exact strata compaction (on top of Stage 2, passive
heterogeneous strata, and Stage 1, neutral representation; design:
`objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`).

**Stage 2.1 in brief.** Within one unit, components at exactly the same position
(`claim/share`, bit-identical) are one stratum: `compact_exact_strata` sums them (fresh id;
rule `strata_exact_compaction`, a lossless representation identity). Passes repeat until no
exact duplicate remains, because a merged position can shift by a last bit.
`normalize_strata` = exact compaction → (only above `S_MAX`) one capacity coalescence →
compaction again. It runs at fusion (both engines), `replace_strata`, and the zero-stock pass.
The per-step invariant now also rejects exact duplicates. Three distinct concepts:

| Concept | Stage | Nature |
|---|---|---|
| exact compaction | 2.1 | lossless |
| capacity coalescence | 2 | numerical, only above `S_MAX` |
| adaptive merge | 4 | not implemented |

Saturation diagnostic (neolithic seed 0, 400 y):

| | Before | After |
|---|---|---|
| Units at `S_MAX` | 152/246 | 8/246 |
| Capacity coalescences | 884 (653 exact duplicates) | 36 |
| Exact compactions | — | 213 |

The remaining 28 of those 36 coalescences merge last-bit near-duplicates (positions
mathematically equal, rounding history different), which stay separate below `S_MAX` by
design; 8 are genuine approximations. At year 400, 173 near-duplicate pairs remain (Stage 4
territory).

**What now exists**
- **Multiple components per unit** (1..`S_MAX = 8`) in `StrataTable` (257 B/row) and
  `StrataBlock`. Composition math is defined once in `population/strata.py` and applied by
  both engines (`lifecycle` for table rows, `composition` for objects):
  - `fuse_strata` (rule `strata_fusion_inheritance`): concatenation; shares from
    `share × N`; claims from `claim × predecessor stock` read before stocks combine,
    renormalized; zero fused stock → shares; predecessors without people drop out;
    predecessor ids persist.
  - `coalesce_to_capacity` (rule `strata_capacity_coalescence`, numerical): above `S_MAX`,
    the greedy cheapest pair by `s_i s_j/(s_i+s_j)·|p_i − p_j|²` in position space
    `(field_claim, store_claim)/share` is summed into a fresh-id component. Pairs are
    compared in canonical state order, never by id or slot.
  - `claims_on_empty_stocks` (rule `claim_zero_stock`), applied by
    `PopulationStore.settle_empty_claims()` after every subsystem: claim = share where
    `fields_ha` / `stores_kcal` is 0; positive stocks carry fractions forward.
- **Fission** copies the parent's strata as new components (fresh ids): the representative
  assumption.
- `PopulationStore.replace_strata(unit, block, coalesce=False)`: validated fixture API
  (finite, shares > 0, claims ≥ 0, sums within 1e-12, count ≤ S_MAX unless coalescing);
  fresh ids; nothing changes on rejection.
- **Sidecar (opt-in, `Simulator(record_strata=True)`):**
  - `SimulationResult.strata_rows` keyed `(year, unit_id, stratum_id)` with shares, claims
    and relative positions;
  - `strata_events`: `fusion_inheritance`, `capacity_coalescence` (with cost),
    `fission_copy`;
  - saved as `strata.csv` / `strata_events.jsonl`;
  - removal events deferred.
- Canonical runs now contain heterogeneous strata (neolithic seed 0, year 400: 152 of 246
  units at 8 strata; 246 fusion inheritances, 884 coalescences; positions 0–12), all
  passive.

**Scientific feedback (Stages 1–2.1):** none. No mechanism reads strata; no RNG; unit ids untouched; the
frozen metrics and events are unchanged (checked with recording on and off).

**Important assumptions:**
- fission is socioeconomically representative;
- whole-unit migration preserves composition;
- positive-stock claim fractions persist passively;
- zero stock resets claims to shares;
- capacity coalescence is numerical, not sociological;
- shared age–sex structure.

**Validation (Stage 2.1):** `make check` 614 passed; `make test-stat` 3/3; raw and logical
MVP 2.1 oracles IDENTICAL; golden fixtures unchanged; `git diff --check` clean. 400-y
neolithic run 4.4–5.0 s (4.6 s before); `bench-quick` 97–107 ms CPU/tick (noise).

**Validation (Stage 2):**
- `make check` 602 passed; `make test-stat` 3/3 (strict xfail unchanged); `git diff --check`
  clean.
- Raw and logical MVP 2.1 oracles IDENTICAL; golden fixtures unchanged.
- Tests (`tests/test_strata_composition.py` plus updated `tests/test_strata.py`):
  - the inheritance formulas (equal/unequal populations, land, independent stores,
    zero-stock cases, multi-strata, over capacity);
  - capacity coalescence (exactly S_MAX, S_MAX + 1, conservation, closest pair, centroid,
    cross-cutting positions, order/id independence);
  - fixtures and their rejection;
  - table vs object agreement (direct operations and 25 ordinary steps, events included);
  - differentiated fission; zero stock; migration;
  - mid-run id renumbering (bit-identical) and storage reordering (unit state
    bit-identical, strata within 1e-12);
  - sidecar opt-in neutrality.
- Memory: unchanged from Stage 1 (257 B/row; ≈0.6 MB at 2k units, ≈13 MB at 50k).
- Costs:
  - zero-stock pass ≈ 13 µs per call at 2k single-stratum units (≈141 µs with 8 strata
    each);
  - fuse 8+8 and coalesce to 8 ≈ 0.6 ms (pure Python; rare);
  - `bench-quick` 99–106 ms CPU/tick against 96–98 before (noise to a few %).

**Next stage:** Stage 3 — first causal economic differentiation. Starts only on explicit
approval. Stage 3 must decide:
- the allocation/control of newly cleared land;
- the allocation/control of newly stored surplus;
- the exact meaning and sensitivity of `field_entitlement_weight` (neutral 0);
- how food pooling becomes an explicit recorded transfer.

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

**Known limitations**
- Passive representation only: strata have no causal effect yet.
- Stratum ids are per-store handles: a unit removed and re-inserted gets new ids.
- Positions equal only up to rounding (e.g. after fission's proportional stock split)
  stay separate below `S_MAX`; merging them is Stage 4.
- Capacity coalescence is greedy and pure Python (O(n³) for one fusion; n ≤ 16).
- The object (reference) engine keeps strata on unit objects; the table engine in
  `StrataTable`. Both allocate the same id sequence (checked by the differential tests).

**Do not forget**
- No named classes; no arbitrary inequality targets.
- `field_entitlement_weight` = 0 remains the legacy neutral limit.
- Stage 4 adaptive merging has not been implemented; neither exact compaction nor capacity
  coalescence is it.
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
