# MVP 3 — Socioeconomic Strata: Design

**Status:** Stage 0 design, approved with resolved decisions (2026-10-02). Governs MVP 3
Stages 1–6 unless revised here.\
**Base:** MVP 2.1 frozen (`baselines/mvp2_1/`), post-consolidation architecture
(`PopulationStore`, `population/fields.py`).

A **stratum** is one component of an adaptive mixture approximation of a unit's
socioeconomic distribution. It has a population weight, a small vector of socioeconomic
quantities and an opaque identity, and no label. "Elite", "farmer", "class" and similar
words are descriptions an analysis may derive from simulated data; they never enter causal
state (objective §2.7).

---

## 1. Decisions in one page

1. **Minimal `[U,S]` state (§A):** the population weight `share`, plus two
   entitlement/control shares over unit-level physical stocks: `field_claim` and
   `store_claim`. Nothing else is added until a stage needs it.
2. **Physical stock at `[U]`; control/access at `[U,S]`.** Claims are relative shares of
   the unit's `fields_ha` and `stores_kcal`, not duplicated stocks. The socioeconomic
   positions are the intensive ratios `claim / share`, where 1 means a proportional
   per-capita position.
3. **Demography stays `[U, sex, age]` (canonical).** A stratum has `share × N` people with
   the unit's age–sex structure. The model does not invent correlations between position
   and age, and there is no `[U,S,sex,age]` (§C).
4. **Storage:** `StrataTable` owned by `PopulationStore`, row-aligned with `UnitTable`
   slots, with padded `[capacity, S_max]` columns and its own column schema (§D).
   `S_max = 8` is a numerical resolution limit.
5. **Stages 1–4 are an accounting overlay.** No `[U]` mechanism reads strata state, so the
   MVP 2.1 raw and logical oracles stay identical. The first stage in which socioeconomic
   state intentionally affects existing behavior establishes a new, versioned baseline (§E).
6. **Strata outputs go to a separate sidecar stream,** keyed by year, unit and stratum ID.
   The frozen metrics rows and event log are unchanged, and the sidecar never feeds back.
7. **The first causal mechanism (Stage 3)** makes crop entitlement depend on field claims
   through a weight that defaults to its neutral value 0 (`field_entitlement_weight`).
   Nonzero values are explicit hypotheses and sensitivity cases, never tuned. Fusion of
   groups with different resources per person is the existing source of initial
   differentiation; no noise is injected.
8. **Creation is mechanism-driven.** A new stratum appears only when a causal mechanism
   treats part of a represented population differently enough that a distinct state must
   be represented. There is no statistical split test.
9. **Capacity coalescence (Stage 2) is not adaptive merging (Stage 4).** The first keeps a
   unit within `S_max`; the second merges behaviorally indistinguishable components.

---

## A. Minimal stratum state vector

### Semantics

| Field | Definition | Range | Constraint |
|---|---|---|---|
| `share` | represented population mass of the stratum / unit population | (0, 1] | Σ_s share = 1; never 0 |
| `field_claim` | the stratum's entitlement/control share of the unit's cultivated land (`fields_ha`) | [0, 1] | Σ_s field_claim = 1 |
| `store_claim` | the stratum's entitlement/control share of the unit's stored food (`stores_kcal`) | [0, 1] | Σ_s store_claim = 1 |
| `stratum_id` | opaque identity for sidecar persistence and mobility tracking | int64 | never read causally |

- **`share` is a mixture weight,** not a socioeconomic characteristic.
- **Claims are relative control/entitlement shares** over physical stocks that stay
  `[U]`. They do not duplicate the stock: hectares controlled are `field_claim × fields_ha`
  and stored kcal held are `store_claim × stores_kcal`.
- **Socioeconomic position** is intensive:

  ```text
  relative_field_position = field_claim / share
  relative_store_position = store_claim / share
  ```

  A value of 1 is a proportional (equal per-capita) position; above or below 1 is relative
  advantage or disadvantage. These positions, not the raw fractions, are the basis for
  similarity and merge distance.
- **Neutral (homogeneous) allocation:** `field_claim = store_claim = share`.
- **No zero-population strata:** a stratum whose share would reach 0 is removed.

### Why each field varies within a unit

`share` defines the mixture. Fields and stores are the only MVP 2.1 stocks that are
durable, appropriable and transferable: they persist across years, can pass down a lineage,
and arrive unequally when groups fuse. Body reserves, food ratio, knowledge and technologies
do not meet that test today (§B).

### Readers and writers

| | Stage 1 | Stage 2 | Stage 3 (first mechanism) | Later |
|---|---|---|---|---|
| `share` | lifecycle | lifecycle, capacity coalescence | ledger weights (labor, need) | transfers between strata (Stage 4) |
| `field_claim` | — | lifecycle | crop entitlement | influence over field decisions (Stage 5) |
| `store_claim` | — | lifecycle | store ledger | food access (Stage 6A) |

### Zero-stock convention

There are no NaNs and no undefined social state. If the relevant unit-level physical stock
is zero, there is nothing from which inherited claims can be determined, so the claim
equals the neutral allocation (`claim_i = share_i`) unless a later explicit institution
provides another rule. The representation never invents inequality. The engine applies this
rule after every subsystem's apply (`PopulationStore.settle_empty_claims`), the granularity
at which stocks change.

### Changing physical totals

Claims are entitlement shares, so a change in the physical total does not by itself say who
controls the change.

- **Proportional losses** (spoilage, carrying limits, trade drawn from stores, fields
  shrinking at a uniform rate) act on everyone's holdings alike, so the shares are
  unchanged.
- **Newly produced or created stock** (stored surplus, newly cleared hectares) must have its
  allocation rule stated explicitly by the mechanism that creates it. It is not silently
  assumed to preserve existing unequal claims once socioeconomic dynamics are active.
- **Before Stage 3,** no such mechanism exists, so claims stay neutral except for fusion
  inheritance.

### Lifecycle rules

- **Initialization:** a founded unit has one stratum with `share = field_claim =
  store_claim = 1`.
- **Unit fission:** the daughter copies the parent's strata. Physical totals are divided in
  proportion to people, so every relative position is unchanged on both sides. This is
  neutral.
- **Unit fusion (and aggregation):** prior absolute positions are inherited. For each
  stratum of either unit:

  ```text
  absolute field claim = field_claim × that unit's fields_ha
  field_claim'         = absolute field claim / fields_ha after fusion
  ```

  The same applies to stores, and `share' = share × N_unit / N_total`. If the total after
  fusion is zero, the neutral fallback applies. The strata of the two units are
  concatenated, not averaged: a merger between groups with different resources per person
  is one legitimate source of initial differentiation. Capacity coalescence (§G) follows if
  needed.

### Deliberately not in the minimal vector

- **Labor allocation:** every stratum supplies labor in proportion to `share`, because the
  age structure is shared. MVP 2.1 gives subgroups no reason to allocate labor differently.
- **Decision influence:** Stage 5, and defined only relative to a named collective choice.
- **Consumption / food access:** pooled; this is the Stage 6A candidate.
- **A separate wealth scalar:** holdings are the claims, and there is no other good.

## B. State that stays `[U]`

From `population/fields.py`:

- **Location, identity, lineage:** `cell`, `species_id`, `id`, `parent_id`, `founded_year`.
- **Information:** `beliefs`, `food_log_prior`, `food_log_signal_var`, `report_cells`,
  `recent_residence`, `familiarity`. These are shared perception and memory.
- **Culture and technique:** `knowledge`, `technologies`. These are shared affordances;
  specialist knowledge is not modeled.
- **Physical stocks:** `fields_ha`, `stores_kcal`. Control over them is `[U,S]`.
- **Demography:** `females`, `males`. This is the shared age–sex structure (§C).
- **Pooled flows:** `harvest_kcal`, `farm_harvest_kcal`, `forage_harvest_kcal`,
  `farm_hours`, `forage_hours`, `clearing_hours`, `labor_debt_hours`, `stored_kcal`,
  `energy_debt_kcal`. Stage 3 *attributes* these flows; it does not stratify them.
- **Nutrition outcome:** `food_ratio`, `energy_deficit`, `reserve_kcal_per_capita`. These
  stay `[U]` while consumption is pooled. They are the first candidates to become `[U,S]`
  if Stage 6A makes food access depend on claims.
- **Decisions and network:** `move_hazard`, `residence_years`, `groups`, `harvest_history`,
  `trade_ties`. Migration stays a whole-unit decision until a selective-migration stage.

Rule: a field becomes `[U,S]` only when a mechanism needs different values for different
parts of a unit to produce different outcomes.

## C. Population accounting

- **Canonical representation:** `P(age, sex, stratum) = P(age, sex) · share`. Cohorts stay
  `[U, sex, age]` and integer, with exact binomial demography unchanged. The model does not
  invent correlations between socioeconomic position and age structure.
- **Stratum population** is `share × N_u`, a real number. Integer persons per stratum are
  not tracked.
- **Births and deaths do not change shares.** Shares change only through explicit
  structural operations (fusion, capacity coalescence, Stage 4 transfers).
- **Inheritance is implicit:** a stratum behaves like a lineage, and its claims pass to its
  descendants because the stratum persists.
- **When to revisit:** stratified demography is reconsidered only when an implemented
  mechanism produces scientifically meaningful stratum differences in fertility conditions,
  mortality exposure, food access relevant to fertility or mortality, workload with
  demographic consequences, or another explicit demographic input. Model need justifies
  it, completeness does not. The options then are:
  - (a) per-stratum vital-rate effects acting on `share`;
  - (b) `[U,S,sex,age]` cohorts (§J).

## D. Storage layout

```text
PopulationStore
    units       UnitRegistry       identities, processing order
    table       UnitTable          [U] hot state            (slot rows)
    strata      StrataTable        [U,S] state              (same slot rows)
    beliefs     BeliefStore
```

- **`StrataTable`:** padded columns `share`, `field_claim`, `store_claim` (`float64`) and
  `stratum_id` (`int64`), each `[capacity, S_max]`, plus `n_strata[capacity]` (`int8`).
  Row `r` belongs to the unit in slot `r`, so there is no unit↔stratum map to maintain.
  `ensure`, `reset`, `copy_row` and `load`/`unload` mirror `UnitTable`, and
  `PopulationStore` allocates the rows together.
- **Schema boundary:** stratum columns have their own declared schema (name, dtype, meaning,
  constraint, merge/split rule) inside the strata module. They are not `UnitField`s and are
  not flattened into the unit-field ontology. `fields.py` gains at most one unit field,
  `strata` (`Storage.STRATA`), so that the unit-level lifecycle completeness test still
  covers the whole block.
- **Active strata** of slot `r` are columns `0 … n_strata[r]−1`, kept compacted, with zero
  padding. Iteration is vectorized over `(slots, S_max)` with a mask.
- **`S_max = 8`** by default: *a numerical socioeconomic-resolution limit, not a scientific
  claim about the number of classes in a society.* Results should eventually be tested for
  sensitivity to `S_max` once adaptive strata are behaviorally active, but not in Stage 0.
- **IDs:** a per-store `int64` counter in `StrataTable`. It never uses `IdAllocator`, so unit
  IDs are unchanged.
- **Object (reference) engine:** a detached `PopulationUnit` holds a small `StrataBlock` of
  arrays. While the unit is registered, the block is a view of its slot row.
- **Lifecycle:** `split_unit` copies the parent's row; `merge_units` concatenates;
  `discard`/`reset` zero the row, so no stale strata leak into a reused slot. Deepcopy
  follows the existing `UnitRegistry.__deepcopy__` path.
- **Rejected alternatives:**
  - a flat stratum pool with a CSR index: needs re-indexing after every structural event;
  - per-stratum objects: hot-loop cost;
  - `[U,S,S]` relationships: no mechanism needs them.

## E. Neutrality and exactness contract

- **Homogeneous** means one stratum per unit with `share = field_claim = store_claim = 1`.
  This is all of Stage 1.
- **Foundational test:** with strata enabled, the MVP 2.1 raw and logical oracles and the
  golden fixtures are identical. This holds as long as:
  - (i) no `[U]` mechanism reads strata state;
  - (ii) strata consume no random numbers;
  - (iii) strata do not use the unit `IdAllocator`;
  - (iv) strata outputs go only to the sidecar stream.
- **Through Stage 4:** because of (i), the oracles stay identical even with heterogeneous
  strata. Stages 3–4 may add targeted fixtures and tests for sidecar state without replacing
  the MVP 2.1 scientific oracle.
- **New baseline:** the first stage in which socioeconomic state intentionally affects
  existing simulation behavior records a new versioned baseline (`baselines/mvp3_x/`, new
  oracles). MVP 2.1 artifacts remain historical evidence.

**Neutrality tolerances:**

| Transformation | Contract |
|---|---|
| Renumbering opaque `stratum_id`s | **Bit-exact.** IDs never enter equations, RNG, tie-breaking or processing decisions. |
| Reordering strata within a unit | Strict floating-point tolerance, because reduction order makes bit identity unreasonable. |
| Conserved totals (Σ shares, Σ claims, physical totals) | The tightest practical invariant; they must not drift merely because components were reordered. |

Future stochastic mechanisms must not make outcomes depend on arbitrary stratum IDs or
storage order (for example, draws keyed or ordered by stratum position).

## F. First causal mechanism (Stage 3)

**Crop entitlement that depends on field claims, with intra-unit pooling made explicit.**

MVP 2.1 pools within a unit: everyone works, eats and stores together. Stage 3 changes no
`[U]` flow. It attributes the unit's realized store change to strata each year, after
energetics:

```text
ΔK_s = share_s · ΔK  +  w · Y_farm · (field_claim_s − share_s)     (Σ_s of the w term = 0)
store_claim'_s ∝ max(store_claim_s · K_before + ΔK_s, 0)           holdings floored at zero
pooling transfer = Σ_s max(−(store_claim_s · K_before + ΔK_s), 0)  covered pro rata by others
```

- `Y_farm` is this year's crop. `w` is the share of crop output that accrues according to
  field claims rather than to labor, which is supplied in proportion to `share`. Its name is
  chosen at implementation, e.g. `field_entitlement_weight`.
- **No canonical nonzero value.** `w = 0` is the neutral value: the legacy equal-pooling
  limit, not a claim about historical societies. Any `w > 0` is a substantive hypothesis
  about entitlement to the output of pooled labor, and Stage 3 evaluates it as explicit
  sensitivity cases. It is never tuned to manufacture inequality. A reference value is set
  only when an MVP 3 scientific baseline is deliberately established.
- **Neutral limits:** `w = 0`, or `field_claim = share`, keeps every position at 1.
- **Heterogeneity source:** fusion inheritance (§A). A resident group with established
  fields absorbing a group without them gives a relative field position above 1 for the
  residents. No random differentiation.
- **New hectares:** the allocation rule is part of the mechanism. The proposed starting
  point is in proportion to `share` (labor clears land), which is an explicit hypothesis.
  Abandonment empties `fields_ha`, so the zero-stock convention applies.

*Why this mechanism:* it uses the only durable, appropriable stocks MVP 2.1 already
simulates (objective §7: surplus alone must not imply hierarchy). It has explicit conserved
flows, one weight with a neutral limit, and leaves `[U]` dynamics exactly unchanged.

Rejected for now:

- **unequal labor allocation:** no reason for it exists without specialization returns;
- **redistribution/extraction:** presupposes power, which is Stage 5;
- **influence:** Stage 5.

*Expected behavior, to be tested rather than assumed:* differentiation is persistent but
bounded, because claims spoil, deficits are pooled and new land is attributed by labor. It
compounds only once positions feed back into decisions or access (Stages 5–6). If it does
not appear, diagnose the mechanism; do not add noise.

## G. Stratum dynamics

| Event | Rule | Stage |
|---|---|---|
| Creation | Only when a causal mechanism treats part of a represented population differently enough that a distinct state must be represented (fusion inheritance; later explicit transfers such as an inheritance partition). No statistical split test: a stratum is a point and holds no internal distribution. Reconsider only if a future model stores within-stratum moments. | 2+ |
| Divergence | Only through explicit flows (§F). | 3 |
| **Exact compaction** | Components of one unit at exactly the same position (`claim/share` for every claim, bit-identical) are one represented stratum: summed share and claims, fresh id. Lossless representation identity, no tolerance; runs before capacity coalescence and repeats until no exact duplicate remains. Positions equal only up to rounding stay separate (Stage 4). | 2.1 |
| **Capacity coalescence** | If `n_strata > S_max`, deterministically coalesce the closest pair in relative-position space (`field_claim/share`, `store_claim/share`) until representable. Shares and claims add, which is exactly conservative. Ties are broken by state values, never by ID or storage position. This is numerical resolution management, not a sociological event, and the approximation error is recorded in the sidecar. | 2 |
| **Adaptive merge** | Merge behaviorally indistinguishable components even below `S_max` (criterion in relative-position space; identical-merge neutrality tests). | 4 |
| Population transfer between strata | Only via a named mechanism that states which claims move with people. | 4 |
| Extinction | A stratum whose share would reach 0 is removed and the row compacted. Unit extinction removes the row. | 1+ |
| Unit fission | The daughter copies the parent's strata. Fission along strata lines is a later selective mechanism. | 1+ |
| Unit fusion / aggregation | Concatenate with inherited absolute positions (§A), then capacity coalescence. In Stage 1, where everything is homogeneous, this reduces to one stratum. | 1+ |
| Migration | Whole unit. Field claims follow the zero-stock convention when the fields are abandoned; store claims are unchanged by proportional abandonment. | 2+ |

## H. Sidecar observational stream and derived metrics

```text
existing unit metrics/events   frozen MVP 2.1-compatible stream (unchanged schema)
strata metrics/events          separate variable-cardinality sidecar
```

- Sidecar rows are keyed by `(year, unit_id, stratum_id)` for stratum state, and by
  `(year, unit_id)` or `year` for aggregates. Sidecar events record structural operations
  such as creation by fusion, capacity coalescence (with its error) and removal.
- The sidecar is written only to outputs and is never read by the simulation.

Derived measures (analysis only):

- **Inequality:** people-weighted Gini and Theil T of the relative field and store
  positions. Theil decomposes into within-unit and between-unit parts.
- **Concentration:** claims held by the smallest set of strata containing ≤ 10% of people.
- **Resolution:** distribution of `n_strata`; coalescence events and their errors.
- **Pooling (Stage 3):** annual intra-unit pooling transfer (kcal) and entitlement-driven
  flows.
- **Persistence:** year-to-year rank correlation of positions by `stratum_id`.
- **Mobility (Stage 4+):** population flows between strata.
- **Later:** influence concentration and its covariance with positions (Stage 5).

Labels such as "elite-like concentration" live only in analysis tooling.

## I. Model provenance (new `ModelRule`s)

| Rule | Stage | Explicit assumption |
|---|---|---|
| `stratum_composition` | 1 | All strata share the unit's age–sex structure; shares are unchanged by births and deaths. |
| `strata_fusion_inheritance` | 2 | Fused groups keep their prior absolute positions as distinct components. |
| `claim_zero_stock` | 2 | Claims on an empty stock equal population shares. |
| `strata_exact_compaction` | 2.1 | Strata encode positions, not lineages: exact duplicate positions are one component (lossless representation identity). |
| `strata_capacity_coalescence` | 2 | Above `S_max`, the closest components are coalesced (numerical approximation, recorded error). |
| `new_field_claims` | 3 | The stated allocation rule for newly cleared land (proposed: ∝ share). |
| `field_entitlement` | 3 | A weight `w` of crop output accrues by field claim; neutral at 0; nonzero values are hypotheses. |
| `intra_unit_pooling` | 3 | Consumption is pooled; deficits beyond a stratum's own holdings are covered pro rata by others (a recorded transfer). |
| `strata_adaptive_merge` | 4 | Merge criterion for indistinguishable components. |

Each rule is heuristic unless a source is cited, and each must be ablatable through a switch
or its neutral parameter value.

## J. Performance

Per unit, persistent:

| Representation | Bytes per unit (S_max = 8) | 50k units |
|---|---|---|
| `StrataTable` (3 × f64 + i64, padded) + `n_strata` | ≈ 260 B | ≈ 13 MB |
| Existing cohorts alone (`2 × 91 × i64`) | ≈ 1.5 kB | ≈ 73 MB |
| **Rejected:** `[U,S,sex,age]` cohorts | ≈ 11.6 kB | ≈ 580 MB, plus demography temporaries ≈ 75 kB/unit/tick (≈ 3.8 GB) |
| **Rejected (scientifically):** dense `[U,S,S]` relations | ≈ 0.5 kB | ≈ 26 MB |

The Stage 3 ledger and capacity coalescence are O(U·S_max) vectorized work per tick.
Python-object-per-stratum loops are ruled out for hot paths.

## K. Resolved decisions and remaining questions

**Resolved (2026-10-02):**

1. No canonical nonzero entitlement weight. `w = 0` is the neutral legacy limit; nonzero
   values are hypotheses and sensitivity cases (§F).
2. Separate sidecar stream for strata metrics and events (§H).
3. Mechanism-driven creation; no statistical split test (§G).
4. Capacity coalescence in Stage 2, distinct from Stage 4 adaptive merging (§G).
5. ID renumbering is bit-exact neutral; reordering is neutral within a strict float
   tolerance; conserved totals use the tightest invariant (§E).
6. A shared age–sex structure is canonical; no `[U,S,sex,age]` until a mechanism needs it
   (§C).

**Remaining open questions** (decide when the stage arrives):

- **Stage 3:** the allocation rule for newly cleared hectares and newly stored surplus. The
  proposed starting point (∝ share, and the attribution formula in §F) must be confirmed
  as the mechanism's explicit hypothesis.
- **Stage 4:** the adaptive-merge criterion and tolerance in relative-position space, and
  how the representation error is bounded.
