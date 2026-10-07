# MVP 3 — Socioeconomic Strata: Design

**Status:** Stage 0 design, approved with resolved decisions (2026-10-02). Governs MVP 3
Stages 1–6 unless revised here. Latest stage: 4E (§S, 2026-10-07).\
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
   `S_max = 8` is a numerical resolution limit (now `strata.max_strata`, default 16 since
   Stage 4B.1, §P).
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

---

## L. Stage 3 economic accounting (Stage 3A audit and Stage 3B specification)

Audited from the code, and verified by `scripts/probes/food_flow_audit.py` (neolithic seed 0
× 400 y and pressure seed 1 × 300 y: every check passes; the probed run is identical).

### L1. Food flows in one step (actual code)

```text
Farming      FarmHarvests.apply     farm_harvest_kcal = Y          (crop; fields worked by pooled labor)
Foraging     ForageHarvests.apply   forage_harvest_kcal = W,       harvest_kcal = H0 = Y + W   (bitwise)
                                    (foraging targets need·(1+surplus) − Y: it adjusts to the crop)
Trade        TradeRound.apply       donor (balance > 0):  H = H0 − D_h; stores −= S_out (only if sent > H0)
                                    recipient (< 0):      H = H0 + R          (a unit is never both)
Energetics   EnergyUpdates.apply    K0 = stores after trade, r = storage_retention, cap = reserve cap
               fed   (H ≥ need):    reserve += Δres ≤ cap; leftover L = H − need − Δres;
                                    stored A = L if r > 0 else 0 (rest spoils); K1 = (K0 + A)·r
               short (H < need):    withdrawn X = min(need − H, K0); then reserves; K1 = (K0 − X)·r
                                    (never both A > 0 and X > 0 in one year)
Migration    Relocation.apply       stores −= max(stores − carry, 0)    (abandonment)
Lifecycle    fission (∝ people) / fusion, aggregation (sum)   — strata rules exist (§A, §G)
```

Consumption is not a fungible mixed pool: fed units eat from harvest and store only the
leftover; short units eat all harvest, then stores, then body reserves. `TickLedger` keeps
only scalar totals (harvest, need, farm harvest, spoilage, trade volume, transport loss,
abandoned stores). Per unit, `farm_harvest_kcal`, `forage_harvest_kcal`, `harvest_kcal`
(post-trade) and `stored_kcal` persist; `K0`, `X`, `S_out` and `L` are not recorded.

### L2. Cultivated land (actual code)

`fields_ha` changes only in:
- `FieldPlans.apply` (field planning: expansion by clearing, shrinking, arable sharing
  within a cell, zeroing below 0.05 ha), which has `F0` and `F1` at hand;
- `Relocation.apply` (migration: `F1 = 0`);
- fission (∝ people) and fusion/aggregation (sum), which have strata rules already.

Farming and soil never change `fields_ha`. New land is cleared in year t and first harvested
in year t + 1.

### L3. Land claims (Stage 3B)

Ordinary field change in `FieldPlans.apply`, per unit with `ΔF = F1 − F0`:

```text
F1 == 0:        field_claim = share                                  (claim_zero_stock)
F1 <  F0:       field_claim unchanged                                (proportional loss)
F1 >  F0:       a_i = field_claim_i·F0 + share_i·ΔF                  (new land ∝ share)
                field_claim_i = a_i / Σ a                            (normalize by Σ a, not F1)
```

New land ∝ `share` is the least assumptive rule without an explicit institution or
differentiated labor: labor clears land, and labor is ∝ share. It is not a claim that
tenure was egalitarian. Normalizing by `Σ a` keeps a single stratum at exactly 1.

### L4. Crop-output attribution: `field_output_claim_weight` (w)

Recommended name: `field_output_claim_weight`. It is preferred to `field_entitlement_weight`,
which suggests an institution the model does not contain.

```text
crop_output_share_i = (1 − w)·share_i + w·field_claim_i          0 ≤ w ≤ 1
```

- `w` is the fraction of crop-output *attribution* (before pooling) that follows field
  control rather than the neutral labor baseline (∝ share while labor is undifferentiated).
- `w` is not an extraction rate: nothing is taken from anyone, and consumption stays pooled.
- `w = 0` is the neutral legacy limit. Probes use `w ∈ {0, 0.25, 0.5, 1}`.
- No canonical nonzero value; one is chosen only with an MVP 3 baseline and its provenance.

### L5. Pre-pool attribution of food and pooling transfers

Pre-pool attribution by source:

| Source | Attribution | Heterogeneous only with |
|---|---|---|
| foraging `W` | ∝ share | differentiated labor or access |
| crop `Y` | ∝ crop_output_share (L4) | — |
| trade received `R` | ∝ share | stratum-level exchange ties |
| trade given from harvest `D_h` | ∝ the unit's pre-trade harvest attribution | stratum-level exchange decisions |
| trade given from stores `S_out` | ∝ store_claim (proportional loss) | stratum-level exchange decisions |
| store withdrawal `X` | ∝ store_claim (proportional loss) | differentiated access (Stage 6A) |
| body reserves | ∝ share (physically per capita) | — |

Post-trade harvest attribution, in a numerically stable form:

```text
g = min(1, H / (Y + W))        (fraction of own harvest kept; 0 if Y + W = 0)
H·h_i = H·share_i + g·w·Y·(field_claim_i − share_i)          Σ_i of the second term = 0
```

Post-pool allocation stays the MVP 2.1 behavior: need and reserve top-up ∝ share.

**Pooling transfer** (observational, kcal, per stratum per year):

```text
pool_transfer_i = post_pool_allocation_i − pre_pool_attribution_i        Σ_i = 0
short year:  H·(share_i − h_i) + X·(share_i − store_claim_i)
fed year:    L̃_i − ℓ_i      (ℓ_i the stratum's pre-pool leftover and L̃_i its allocation; see L6)
```

- Positive means the stratum receives more from pooling than it contributes.
- It is not labeled tax, rent or tribute.
- Recorded combined per stratum (one quantity), with the unit total `Σ|transfer|/2`. A split
  by source is not needed while consumption is pooled.

### L6. Store claims from gross flows

Existing stores (`K0`, `store_claim`) lose `S_out`, `X`, spoilage `(1 − r)` and migration
abandonment proportionally, so depletion never changes fractions. New stored food appears
only in fed years:

```text
pre-pool leftover    ℓ_i = L·share_i + g·w·Y·(field_claim_i − share_i)    Σ ℓ_i = L = A + spoiled
allocated leftover   L̃_i = L · max(ℓ_i, 0) / Σ_j max(ℓ_j, 0)             (negative ℓ covered pro rata)
new stores           A_i = A · L̃_i / L
store_claim_i'       = (store_claim_i·K0 + A_i) / Σ_j (store_claim_j·K0 + A_j)    (then ·r cancels)
K1 == 0:             store_claim = share                                  (claim_zero_stock)
```

- At `w = 0`, `ℓ_i = L·share_i`, so new stores ∝ share, and existing store differences decay
  as stores turn over.
- This changes one Stage 2 passive convention: positive stock growth carried fractions
  forward, which implicitly gave new stores ∝ existing claims. Stage 3B makes the
  allocation explicit, so it changes strata state even at `w = 0`. Unit state is unchanged.
- Needed instrumentation, read-only: per-unit `K0`, `A`, `X`, `L`, `S_out` for the year. The
  proposal objects already hold them (`EnergyUpdates`, `TradeRound`). Record them in a
  per-step `FoodAccounts` (per-unit arrays) beside `TickLedger`, written by those `apply`s
  and read by a passive strata-accounting step right after energetics. The physical
  equations are not touched. Inferring `A` from `K1 − K0` is not used.

### L7. Numerical requirements (no amplification of last-bit differences)

- Every update is a convex combination or a ratio normalized by its own sum, so a single
  stratum stays exactly at 1 and the column totals stay within 1e-12.
- Deviations are computed in difference form (`field_claim − share`), never as differences of
  large attributions.
- There are no thresholds or branches on positions. `max(ℓ, 0)` is continuous, and its sign
  is decided at magnitude `L`, not at last-bit scale.
- Updates are Lipschitz in positions: two strata a few ulps apart stay a few ulps apart.
  Test it.
- Exact compaction (`normalize_strata`) runs after each accounting update. There is no
  approximate merge.

### L8. Composition with lifecycle

- Accounting happens at fixed points: land in field planning, food after energetics.
- Fission, fusion, migration, exact compaction and capacity coalescence later in the step act
  on the updated claims with the existing rules.
- Fusion inheritance already weights claims by predecessor stocks, which is consistent with
  absolute holdings.
- Representative fission copies fractions, and stocks split ∝ people: consistent.
- Migration empties fields (zero-stock rule) and scales stores proportionally: consistent.
- No inconsistency found.

### L9. Recommended Stage 3B scope (and split)

| Item | Kind | Assumptions |
|---|---|---|
| land accretion (L3) | neutral convention | new land ∝ share |
| `FoodAccounts` gross flows | instrumentation | none (read-only) |
| store accretion (L6) | neutral convention | new stores ∝ pre-pool leftover; deficits pooled pro rata |
| pooling transfers (L5) | observation | none |
| `field_output_claim_weight` > 0 (L4) | **scientific hypothesis** | crop attribution follows field control |

The items are coherent together, but `w > 0` is the only substantive hypothesis.
Recommended:
- **Stage 3B:** the neutral accounting rows, with `w` present but fixed at 0. This is
  falsifiable on its own: reconciliation, neutrality, decay of fusion-born store differences.
- **Stage 3C:** activate `w` as explicit sensitivity cases (0, 0.25, 0.5, 1) with provenance.

Caloric access, food ratio and demography stay pooled and unchanged throughout.

### L10. Baseline policy

- The MVP 2.1 raw and logical oracles stay frozen and must stay identical through Stage 3B/3C,
  because claims still feed no unit mechanism.
- New targeted, versioned sidecar fixtures cover strata state and flows (e.g. a small
  heterogeneous scenario's `strata_rows`/flows digest per `w`). They are not a full
  scientific baseline.
- The next full baseline (`baselines/mvp3_x/`) comes only when strata change existing
  outcomes (Stage 5/6).

### L11. Provenance (Stage 3B/3C model rules)

| Rule | Class | Notes |
|---|---|---|
| `field_claim_accretion` | neutral accounting convention | new land ∝ share; loss proportional |
| `store_claim_accretion` | neutral accounting convention | proportional depletion; new stores ∝ allocated leftover |
| `food_pooling_transfer` | accounting identity (observational) | makes MVP 2.1 equal pooling explicit |
| `crop_output_attribution` | **scientific hypothesis** (3C) | `w`; heuristic, no empirical value; neutral at 0 |
| shared-age-structure ∝ share | MVP simplification | already `stratum_composition` |

### L12. Stage 3B/3C controlled scenarios (deterministic, no random strata)

- **Neutral:** `share = field_claim = store_claim`. Claims stay exactly neutral at every
  `w`, and transfers are 0.
- **Fusion-born field inequality:** fields per person 10 vs 2. At `w = 0` store claims follow
  share; at `w > 0` the field-rich stratum's store position rises while crop exists, and
  transfers are nonzero.
- **Cross-cutting:** field-rich A, store-rich B. Track both positions separately (no single
  rank).
- **No farming** (`Y = 0`): no `w` effect at any `w`.
- **Zero to positive stores:** the first additions follow L6.
- **Depletion with stores remaining positive:** fractions unchanged.
- **Exhaustion:** claims = share.
- **Land:** expansion (∝ share), shrink (unchanged), zeroing (share).
- **Reconciliation:** gross flows reproduce `K1` and `F1` per unit; transfers sum to 0.
- **Sensitivity:** `w ∈ {0, 0.25, 0.5, 1}`, comparing the distributions over time (no
  targets).
- **Exactness:** MVP 2.1 oracles identical in all of these (strata are passive for `[U]`).

### L13. Open scientific questions

- Should pooled deficits be covered pro rata (as here), or according to some other
  allocation? That is an institution, so it is deferred.
- Should newly cleared land follow labor (∝ share) or, with `w`, follow existing control?
  This is deferred to the labor-differentiation stage.
- Body reserves stay ∝ share, which is exact while access is pooled (Stage 6A will revisit).

### L14. Stage 3B implementation notes (as built)

- `population/strata_accounting.py`:
  - `FoodAccounts` (per unit `K0` opening after trade, `A` stored, `X` withdrawn, `K1`
    closing), recorded by `EnergyUpdates.apply`;
  - `FieldAccounts` (`F0`, `F1`, in unit order), recorded by `FieldPlans.apply`;
  - both are held transiently on `StepContext` and consumed by `account_strata`, which the
    engine runs after every subsystem: accounting, then exact compaction, then
    `settle_empty_claims`.

  Physical code only records; nothing reads the accounts except this hook.
- At w = 0 the §L5/§L6 formulas reduce to the following:
  - `store_claim' = (store_claim·K0 + share·A) / Σ`; with `A = 0`, fractions are kept;
    `K1 = 0` gives share;
  - fed-year and trade transfers are 0;
  - the only nonzero pooling term is `X·(share − store_claim)`.

  The general `g·w·Y` harvest term arrives with Stage 3C.
- Each rule is one function over the strata axis, shared by the object engine (1-D blocks)
  and the table engine (padded rows). Sums over strata are sequential (`cumsum`), so padding
  cannot change rounding. Single-stratum units are skipped (exactly 1 already).
- Zero-sum contract: `|Σ_i pool_transfer_i| ≤ 2e-12 · X` (the partition tolerance of
  `share` and `store_claim`).
- Sidecar: `strata_flows` (`strata_flows.csv`): one row per stratum for unit-years with a
  nonzero pooling transfer. Fields: `share` and `store_claim` as used, `withdrawn_kcal`,
  `pool_transfer_kcal`, `pool_transfer_volume_kcal` (= Σ|transfer|/2). No claim-accretion
  events (the strata rows show them); exact compactions are logged as before.

### L15. Stage 3C implementation notes (as built)

**Parameter.** `strata.field_output_claim_weight` (w), in a one-field `StrataConfig` section
of the scenario (`config/schema.py`).
- Validated to `0 ≤ w ≤ 1`, default exactly `0.0`, no canonical nonzero value.
- Kept out of `agriculture`, because that section feeds `static_key`: w changes no world,
  ecology or agronomy, so runs that differ only in w share one `StaticContext`.
- It does change `config_hash`, so it is recorded in run provenance.
- Read only by `account_strata`.

**Equations** (`population/strata_accounting.py`; per unit, strata on the last axis):

```text
g    = min(1, H / (Y + W))          (0 if Y + W = 0; H after trade, Y crop, W forage)
d_i  = g · w · Y · (field_claim_i − share_i)          crop-control correction, Σ d = 0
q_i  = H · share_i + d_i                               pre-pool attribution, Σ q = H

short year   harvest_transfer_i = −d_i
             store_transfer_i   = X · (share_i − store_claim_i)
fed year     l_i = L · share_i + d_i                    (L = stored + discarded leftover)
             harvest_transfer_i = max(−l_i, 0) − max(l_i, 0) · N / P
                                  (N, P = Σ of the negative / positive parts; = L·max(l,0)/P − l)
             store_transfer_i   = 0                     (X = 0 in a fed year)
pool_transfer_i = store_transfer_i + harvest_transfer_i
new stores   A_i = A · share_i + (A / L) · (harvest_transfer_i + d_i)   (= A · allocated_i / L)
store claim  (store_claim_i · K0 + max(A_i, 0)) / Σ;  K1 = 0 → share
```

**How the equations are applied:**
- Forage, trade received, reserves and store withdrawals never use field claims.
- Field claims (§L3) do not depend on w.
- Discarded leftover (`L > A`) is owned by the same allocation as stored food, so it adds
  no transfer. In the current energetics A is either L (storage capability) or 0 (none);
  partial storage is handled by the same formula and tested directly.
- Every deviation from neutral is in difference form. With `d ≡ 0` (w = 0, Y = 0 or
  `field_claim = share`) all corrections are exactly zero, and the Stage 3B values are
  reproduced bit for bit.
- No thresholds on positions; `max(·, 0)` acts at kcal scale.

**Provenance:**

| Rule | Version | Class |
|---|---|---|
| `crop_output_attribution` | 1.0 | heuristic modeling hypothesis (w) |
| `pooled_leftover_shares` | 1.0 | heuristic accounting convention (pro rata coverage) |
| `store_claim_accretion` | 1.1 | neutral convention; new stores follow allocated leftover |
| `food_pooling_transfer` | 1.1 | accounting identity; harvest and store components |

**Sidecar.** `strata_flows` rows keep the Stage 3B columns in order and append:
- `crop_kcal`, `field_claim`;
- `crop_attribution_correction_kcal` (d_i);
- `harvest_pool_transfer_kcal`, `store_pool_transfer_kcal`.

A row is written when either component is nonzero for the unit-year. In a fed year where
every `l_i ≥ 0`, each stratum keeps its own attributed surplus and no transfer is recorded.

**Grouping of strata.** Field claims are identical across w as a distribution: share by
field position, per unit-year. The *number* of strata can differ:
- exact compaction and capacity coalescence act on joint `(field, store)` positions;
- once w makes store positions differ, components that would coincide at w = 0 stay
  separate (neolithic seed 0, 400 y: 286 compactions at w = 0 vs 253–260 at w > 0;
  coalescences 12 vs 14–16).

Compaction is lossless. Coalescence is the existing numerical approximation. In the probed
runs it never merged different field positions differently, so the field measure matches to
≤ 7e-16. It could do so in principle, because grouping is joint by design (Stage 2).

**Fixtures:**
- `stage3b_seed11_30u_40y.json` is unchanged and authoritative at w = 0. Its flows are now
  digested on the Stage 3B columns, and the appended columns are asserted neutral.
- `stage3c_w0.5_seed11_30u_40y.json` covers the 0.5 sensitivity case. It is not a
  baseline.

---

## M. Stage 3D — scientific and representation review (2026-10-03)

Diagnostic only; production behavior unchanged. Evidence:
`scripts/probes/strata_review.py` (modes `representation`, `nonlinear`, `persistence`,
`sources`, `capacity`, `fieldgap`), run on the frozen reference scenarios (neolithic 600 y,
pressure 400 y with and without cultivation; seeds 0–3) at w ∈ {0, 0.25, 0.5, 1}.

### M1. Representation load (corrects the seed-0 picture of §L15)

| per unit-year | neolithic | pressure + cultivation | pressure, no cultivation |
|---|---|---|---|
| mean strata (w = 0 → 1) | 2.17 → 2.28 | 3.82 → 3.85 | 1.10 |
| median / p90 / p99 | 1 / 6–7 / 8 | 2 / 8 / 8 | 1 / 1 / 3 |
| at `S_MAX` | 9.1–9.9 % | 32–33 % | 0.09 % |
| capacity coalescences | 8 664–9 200 | 9 722–9 778 | 14 |
| merges joining field positions > 1e-9 apart | 82 % | 93 % | 0 |

- **Coalescence is routine, not rare,** in long or dense farming runs. The seed-0, 400-year
  figures (1.6 strata, 12 coalescences) were not representative.
- **Memory does not depend on load:** `StrataTable` is padded, so it is a fixed 257 B per row.
  The accounting hook is 8–13 % of run time. Growth is bounded by `S_MAX`, so it cannot
  become pathological.
- **Distance to each stratum's nearest neighbour in its unit** (neolithic, w = 0):
  - exact duplicates 0 %;
  - ≤ 1e-12 (floating-point dust) 20 %;
  - ≤ 1e-6: 6 %;
  - ≤ 1e-3: 6 %;
  - ≤ 1e-2: 18 %;
  - ≤ 0.1: 40 %;
  - \> 0.1: 11 % (31 % at w = 1).

  Most additional strata are small but modeled differences (1e-3 to 0.1), not dust.

### M2. Adaptive merging (original Stage 4): DEFER

- **It would not reduce information loss.** Coalescence is greedy and picks the cheapest
  pair, so dust pairs are always merged before any real difference is lost. Pre-merging dust
  below `S_MAX` would not reduce coalescence error. A larger tolerance would add loss.
- **No memory benefit** (fixed padding), and the runtime benefit is marginal.
- **The binding constraint is different:** distinct positions exceed `S_MAX` in a third of
  farming-pressure unit-years. That is a resolution-policy question (`S_MAX` sensitivity, an
  error-aware metric; §M6), not an adaptive-merge question.
- **When to revisit:** only when a mechanism defines which differences matter behaviorally.

### M3. Why the pooling response to w is nonlinear (intended mathematics)

With the physical trajectory fixed (it does not depend on w), the harvest pooling volume is
an exact function of w:

```text
V(w) = Σ_short-years  w·gY·Σ|f_i − s_i|/2                            (linear)
     + Σ_fed-years Σ_i max(w·gY·(s_i − f_i) − L·s_i, 0)              (hinges)
crossing at  w*_i = (L / gY) · s_i / (s_i − f_i)
```

- **The curve matches real runs.** Evaluated from the w = 0 records, it reproduces every
  run's sidecar volume within 4e-16 (w = 0.1, 0.25, 0.5, 0.75, 1).
- **Where it bends:** fed units keep a leftover of about 0.35–0.6 of their kept crop (median
  L/gY), so a field-poor majority (s/(s − f) ≈ 2.7) crosses only at w* ≈ 0.75. Seed 0: 72
  crossing stratum-years with median w* = 0.76.
- **Volume by component** (seed 0):
  - short-year, linear: 5.4e6 kcal at w = 1;
  - fed-year hinges: 4e4 at w = 0.1 and 2.1e7 at w = 1.
- **The response is concentrated, not widespread.** The 10 largest unit-years carry 95–100 %
  of fed-year volume for w ≤ 0.7, and 46 % at w = 1. Seeds 1 and 3 have almost no crossings;
  seed 2 crosses at w* ≈ 0 where L = 0, which makes that part linear.
- **Continuity holds** at three crossings (w* ± 0.01):
  - the raw leftover moves in equal linear steps through 0;
  - the volume follows the curve;
  - units, fusions and fissions are identical;
  - no stratum is created.

  Compaction counts vary by ±1–3 for every w step, because store positions coincide
  differently; that is not tied to crossings.
- **Interpretation stays neutral:** the volume is the redistribution implied by pooled
  consumption under an attribution hypothesis, not tax, tribute or welfare.

### M4. Persistence

From the rules (prescribed flows, `persistence` mode):
- **Field deviation** is multiplied by F0/F1 each year:
  - half-life ≈ 15 y at +5 %/y and ≈ 70 y at +1 %/y;
  - persists indefinitely with stable or shrinking fields;
  - erased at once when fields reach 0 (migration, abandonment).
- **Store deviation at w = 0** is multiplied by K0/(K0 + A) each fed year. At observed
  stock-to-flow ratios it halves in 1–2 years. Withdrawals keep fractions; exhaustion resets.
- **At w > 0,** stores track fields: with stable field inequality the store position
  converges to a fixed point away from 1 (minority at field 2.5: store 4.0 at w = 0.5, 5.0 at
  w = 1). Store inequality then persists exactly as long as field inequality does.

In real runs (neolithic, 4 seeds):
- **Field deviations ≥ 0.05:** median halving 11 y (p90 30). Most stratum lineages end
  first, after a median of 8 y (compaction, coalescence, resets).
- **Store deviations at w = 0:** median halving 2 y. At w = 1: 4 y (p90 21).
- **Population level:** time-mean people-weighted |field position − 1| is 0.011 (neolithic)
  and 0.044 (pressure), the same at every w. Store: 0.007 → 0.034 (neolithic) and
  0.022 → 0.17 (pressure) from w = 0 to 1.

### M5. Sources of differentiation

- **Fusion is the only source.** It is the only operation that raises a unit's stratum count:
  - fission copies the count;
  - accounting keeps or compacts it;
  - `replace_strata` is used only by tests.

  Every other rule moves positions toward 1, or (w) maps field differences onto stores.
- **Most fusions bring modest differences:**

  | fusions with resources per person differing | > 1 % | ≥ 2× |
  |---|---|---|
  | fields, neolithic | 64 % | 6 % |
  | fields, pressure | 77 % | 8 % |
  | stores | 56–65 % | 30–32 % |

- **No endogenous differentiation:** with fusion disabled, at w = 1, no unit ever has more than
  one stratum and every deviation is exactly 0. A population that starts homogeneous does not
  differentiate within units under the current rules.
- **Strata therefore mostly hold memory of predecessor groups,** not self-sustaining
  differentiation:
  - stores forget in years;
  - fields forget at the pace of field expansion, or at once on migration;
  - w adds no source; it maps field memory onto store claims.

### M6. Capacity coalescence and w

- **Stress cases** (two 8-strata predecessors, identical field positions, one fed year at
  each w, fused 16 → 8):
  - w changes the represented field distribution in 96 % of cases (1-D Wasserstein distance
    between w = 1 and w = 0: median 0.054);
  - field variance lost to coalescence is a median 0.1 % at w = 0 and 0.3 % at w = 1.
- **Reference runs:** where w redirects a coalescence (12 % of multi-strata unit-years in
  neolithic, 42 % in pressure), the field distribution moves by a 1-D Wasserstein distance of
  0.006 median (p99 0.05 at neolithic, 0.06 at pressure). Relative to the unit's own
  people-weighted |field position − 1|, that is 11 % median, 28 % p90, 42 % p99. Aggregate
  field dispersion is unchanged.
- **This corrects §L15.** "Field claims identical across w" holds for the accounting rules
  and for coalescence-free runs, not for the represented field distribution once capacity
  coalescence occurs. No invariant is violated: totals are conserved, and field claims are
  read only by passive accounting.
- **Coalescence error by dimension** (neolithic, summed over runs, w = 0 → 1):
  - field 0.19 → 0.42;
  - store 0.03 → 1.19.

  The largest single merge removes 18 % (w = 0) to 48 % (w = 1) of its unit's field-position
  variance. Equal Euclidean weighting lets store dispersion, which w inflates, decide which
  field differences are kept.
- **Recommendation C:** replace the metric with mechanism-aware, error-aware resolution once
  downstream mechanisms define which information matters. No dimension weights now. Gate:
  before any physical mechanism reads `field_claim` or `store_claim`, re-evaluate the metric
  and test sensitivity to `S_MAX` (the representation is not comfortably bounded under
  farming pressure).

### M7. Classification of `field_output_claim_weight`

A sensitivity parameter, and an abstraction standing in for missing labor and property
mechanisms:
- under homogeneous labor it has no causal content of its own;
- canonical activation would need empirical or theoretical grounding;
- it should eventually be replaced by explicit stratum-level labor contribution and tenure
  rules.

The default stays 0.0. The parameter is kept for sensitivity analysis.

### M8. Next scientific stage (recommendation; not implemented)

- **A — resource access (claims change calories received):** premature. It would make
  short-lived fusion memory physically consequential immediately, and would drag stratified
  food ratios and demography in with it.
- **C — decision influence:** premature. The positions it would weight are weak and
  transient.
- **B — a persistent-differentiation mechanism:** recommended, as **Stage 4 — Stratum labor
  contribution (design first)**. It is the lower-level process both current conventions rest
  on (new land ∝ share, and w, because labor ∝ share), and the process MVP 3 intends to
  represent (occupation and specialization; objective §5.4, §7).
  - The design must first name a causal reason labor could differ by stratum. Under pooled
    consumption no stratum has a private return to effort, so the design must decide whether
    that requires a minimal access rule first, or a stratum-level capacity or knowledge
    difference.
  - It must not be a rich-get-richer, rent, coercion or inheritance rule.
  - Prerequisite: §M6 gate if the mechanism will read claims.

Stage 4 adaptive merging is renumbered out of the plan until a mechanism creates the need.

---

## N. Stage 4A — stratum labor and resolution design (2026-10-03)

Design and audit only; production behavior unchanged. Evidence: the code audit below and
`scripts/probes/strata_capacity.py` (real runs at `S_MAX` ∈ {4, 8, 16, 32}).

**Principle (locked).** A population that is homogeneous in every modeled causal variable
may stay homogeneous indefinitely. Strata arise only when a modeled mechanism treats part of
a population differently; fusion is such a mechanism. No random differentiation, inequality
targets, hidden traits or class thresholds.

### N1. The labor model as built

```text
cohorts [U, sex, age] × labor_capacity_by_age (onset 6, full at maturation, elders 0.3)
  × foraging_hours_per_day (5) × 365                      = capacity C (h/y)   labor_hours_columns
       │  minus labor_debt_hours D (last year's clearing)
       ▼
Farming (tick: Harvest)   available = (C − D) · max_farm_labor_share (0.9)
                          required  = fields_ha · cultivation_hours_per_ha (600)
                          farm_hours = required · min(1, available / required)
                          crop Y = fields · yield · worked fraction
       ▼
Foraging                  labor = max(C − D − farm_hours, 0); effort = just enough to
                          meet need·(1 + surplus) − Y (shared cell pool); forage_hours;
                          labor_debt_hours := 0
       ▼
Field planning            expansion step limited by next year's (C − ΔF·clearing)·share ≥
                          (F + ΔF)·cultivation; clearing_hours = ΔF · clearing_h_per_ha
                          (vegetation, tools) → labor_debt_hours (charged to next year)
```

| Quantity | Units | Where | Constraint / output | Competes |
|---|---|---|---|---|
| capacity C | h/y | `labor_hours_columns` (agriculture) | constraint | the single pool |
| clearing (debt D) | h | `FieldPlans.apply` → next year | output then constraint | first claim on next year's C |
| cultivation `farm_hours` | h/y | `FarmingSubsystem` | output; capped at 0.9·(C − D) | before foraging |
| foraging `forage_hours` | h/y | `ForagingSubsystem` | output; the remainder | last |
| storage, trade, processing | — | not labor-costed | — | — |
| migration | — | utility terms only; `field_replacement_cost` values abandoned fields in clearing hours | not consumed | — |
| readers | | learning (activity shares), innovation (`clearing_burden`), metrics | | |

- **One pool:** there is one labor pool per unit, drawn in a fixed order (clearing debt,
  then cultivation, then foraging).
- **No cost of work:** food need does not depend on work, and labor has no direct energetic
  or demographic cost.
- **Two agricultural activities:** cultivation (annual, per hectare of existing fields) and
  clearing (one-time per new hectare, in field planning, charged to next year's capacity).
- **Undifferentiated labor:** there is no sexual division of labor and no skill separate
  from labor.

### N2. Labor vocabulary

- **Capacity:** work a population could supply. It is `[U]`, from the shared age structure.
- **Allocation:** division of capacity among activities. It is `[U]` (debt → cultivation →
  foraging).
- **Contribution:** a stratum's part of one activity's actual hours. Not represented;
  implicitly ∝ share.
- **Burden:** contribution per represented person. Implicitly equal.

The first socioeconomic use needs only contribution, per activity, as a per-tick flow.

### N3. Is there already a causal reason for labor to differ by stratum? No.

| Candidate | Why it might change labor | Verdict |
|---|---|---|
| `field_claim` | land controllers work their own land | needs household production (returns to own work); inconsistent with pooled consumption |
| `field_claim` (inverse) | land controllers direct others' labor | needs an authority or obligation institution; not modeled |
| `store_claim` | stored-food holders need to work less | needs private access to stores (Stage 6A); access is pooled |
| fusion origin | groups keep their previous practice | practice and knowledge are `[U]`; no stratum-level practice state |
| age, sex, health | different capacity | the age–sex structure is shared by design (§C) |

- **No differentiated capacity or private return to effort:** under pooled consumption,
  equal-share labor is the consistent rule. Any differentiated rule would bring in an
  unmodeled institution (household tenure without pooling, authority, or private access).
  This is a scientific finding, not a gap to fill with an assumption.

### N4. Candidate first labor quantity (when one is needed)

- **Measured in hours, per activity, as a transient flow:** `cultivation_hours_i` and
  `clearing_hours_i`, with Σ_i equal to the unit's `farm_hours` / `clearing_hours`.
  Intensive form: `relative_burden_i = hours_i / (share_i · hours_unit)`.
- **No occupations or rank:** no "farmer", `labor_rank` or generic labor scalar.
- **Foraging contribution is not needed** while forage is attributed by share.
- **Flow, not state:** a per-tick flow on `StepContext` and the sidecar, not `StrataTable`.
  Persistent practice allocation (option B) would claim that specialization persists, which
  needs its own mechanism; that is not justified now.
- **It cannot create strata:** with one homogeneous stratum, nothing distinguishes a subset
  of its people. This is acceptable: differentiation still enters through fusion. A
  mechanism-driven split would need a named event treating a stated fraction differently.

### N5. Relation to `field_output_claim_weight`

The right conceptual evolution is
`crop_output_share_i = (1 − w)·cultivation_labor_share_i + w·field_claim_i`. Today
`share_i` stands in for labor. With homogeneous labor the two are identical (same values,
no behavior change), and w then reads as "labor versus control" as the basis of
attribution. w is unchanged (default 0).

### N6. New-land claims

"New field control follows clearing-labor contribution" is the causal form of the Stage 3B
rule (whose rationale is already "labor clears land"):
- **Same as today under homogeneous labor:** identical results.
- **A self-reinforcing loop if labor follows control:** if a future rule made clearing
  labor ∝ `field_claim`, new land would follow existing control. Dilution would stop and
  fusion memory would be frozen, which is persistence by assumption.
- **Collective clearing** is the ∝ share case.

Adopt the causal form only together with the cause of the labor contribution.

### N7. Resolution gate (locked invariant)

**No physical mechanism may read stratum socioeconomic state until the resolution policy
has been shown stable enough for the information that mechanism uses.**

Accounting-only flows (sidecar, attribution) may proceed under the current policy.
Production, food access, migration and demography may not.

### N8. Capacity sensitivity (real runs, 4 seeds; cells w = 0 / 1)

| `S_MAX` | 4 | 8 | 16 | 32 |
|---|---|---|---|---|
| neolithic: unit-years at capacity | 16 % | 9 % | 5.7 % | 3.7 % |
| neolithic: capacity coalescences | 7.0k | 8.7k | 11.2k | 14.8k |
| neolithic: coalescence field error (Σ) | 1.3 / 1.7 | 0.19 / 0.42 | 0.034 / 0.073 | 0.006 / 0.012 |
| neolithic: share of unit-years where w moves the field distribution / median 1-D Wasserstein distance | 0.17 / 0.017 | 0.12 / 0.006 | 0.09 / 0.002 | 0.06 / 0.0007 |
| pressure: unit-years at capacity | 41 % | 32 % | 26 % | 21 % |
| pressure: capacity coalescences | 6.2k | 9.7k | 15.6k | 25.3k |
| pressure: coalescence field error (Σ) | 2.0 / 3.7 | 0.35 / 0.89 | 0.065 / 0.21 | 0.012 / 0.045 |
| pressure: share where w moves the field distribution / median distance | 0.45 / 0.023 | 0.43 / 0.009 | 0.35 / 0.004 | 0.31 / 0.001 |
| run time vs 8 (neolithic / pressure) | 1.0 / 0.93 | 1 | 1.08 / 1.33 | 1.53 / 3.0 |
| `StrataTable` bytes/row | 129 | 257 | 513 | 1025 |

- **Raising capacity does not make coalescence rare.** Demand is open-ended: each fusion
  concatenates distinct positions. Coalescences *increase* with capacity, and pressure units
  still sit at 32 a fifth of the time.
- **It does cut representation error:** field error falls by about 6× per doubling, and the
  w-redirection of field representation by about 2.6×.
- **Aggregate observables are flat across capacity:** time-mean |field − 1| is 0.0113 /
  0.044; store dispersion is constant per w.
- **Runtime grows:** pure-Python greedy coalescence is O(n³) per fusion, and the probe's own
  per-year measurement scales with strata. These are upper bounds.

**Memory** (`StrataTable`: 3 × f64 + i64 per slot, plus an `n_strata` i8, i.e. 32·S + 1 B/row):

| `S_MAX` | 2 000 units | 50 000 units | vs ≈ 2.5 GB RSS at 50k |
|---|---|---|---|
| 8 | 0.5 MB | 12.9 MB | 0.5 % |
| 16 | 1.0 MB | 25.7 MB | 1.0 % |
| 32 | 2.1 MB | 51.3 MB | 2.1 % |

- **Persistent memory is cheap.** The transient per-step duplicate check builds
  `[slots, S, S]` boolean arrays: about 3.2 / 12.8 / 51 MB per array at 50k units (several
  are alive at once). At 32 it should be chunked.

**Assessment:**
- **Capacity cannot replace a resolution policy,** because demand is open-ended. It is still
  the cheapest lever on error. 16 is the candidate: field error about 6× lower, field
  representation moved by w about 2.6× less, +1 % memory, modest runtime.
- **The w-leak** can only be removed by a metric that protects the dimensions a mechanism
  reads (§M6 recommendation C). Capacity only shrinks it.

### N9. How to run capacity sensitivity properly

- **Make capacity a run parameter,** not a global: `strata.max_strata` in the existing
  `StrataConfig` (default 8).
  - `StrataTable` width and `normalize_strata` / `validate_block` take it from the
    `PopulationStore`.
  - Fixed-width padded arrays stay; the width is a per-run constant, not compile-time, which
    suits future GPU and client backends.
  - `n_strata` stays int8 (≤ 127).
- **Prerequisites before using larger capacities:**
  - vectorize capacity coalescence (cost matrix per merge, not Python triple loops);
  - chunk the duplicate check.
- **Interim method:** the probe sets the module global per process, which is adequate for
  diagnostics only.

### N10. Why short-lived differentiation is not itself a defect

Temporary differences after groups with different histories merge are a plausible
phenomenon. MVP 3's selective responses (food access, migration, mortality by stratum) can
act on transient differences. Long-lived differentiation is needed only for phenomena whose
own mechanisms are not modeled:
- intergenerational wealth (inheritance, property persistence);
- persistent leverage (institutions);
- occupational specialization (stratum-level practice or skill).

Introduce persistence only with those mechanisms.

### N11. Candidate Stage 4 mechanisms (ranked by simplicity and assumptions, not by inequality produced)

1. **A, observational labor attribution:** fewest assumptions; makes the labor-∝-share
   assumption explicit. Identical values today.
2. **C, labor contribution in crop attribution:** A plus the §N5 generalization. Identical
   values today; clearer meaning of w.
3. **B, new-land claims from clearing contribution:** identical today. Substantive only once
   labor contribution has a cause; risk of the §N6 loop.
4. **D, labor burden changes physical productivity:** physical feedback, gated (§N7); not
   recommended.

None of A–C is a causal socioeconomic mechanism while labor is undifferentiated. The causal
step needs a reason for labor to differ (§N3). The minimal candidate is a private return to
effort, which requires some non-pooled access: a scientific decision for review, not a
default.

### N12. Recommended decomposition (one review boundary each)

- **4B — Resolution hardening (representation only; strata stay passive):**
  - capacity as a run parameter (`strata.max_strata`, default 8);
  - vectorized capacity coalescence;
  - chunked duplicate check;
  - coalescence error recorded by dimension in the sidecar;
  - re-run §N8 to choose a default (16 the candidate).

  Oracles stay identical; the Stage 3B/3C fixtures stay valid at capacity 8.
- **4C — Stratum labor accounting (accounting only):**
  - per-activity hours contributions as transient flows (∝ share);
  - crop attribution (§N5) and new-land claims (§N6) rewritten on contributions;
  - bit-identical to today.

  *Retired as the automatic next step by Stage 4B.1 (§P3).*
- **4D — Decision gate (design review):**
  - what causes labor or access to differ by stratum (private return to effort via a minimal
    access rule, or stay pooled);
  - a mechanism-aware resolution metric for the dimensions that mechanism reads (§N7).

  No physical feedback before 4D is approved.

Deferred: hierarchy and influence, unequal consumption, stratified demography,
approximate adaptive merging (§M2), work-related energetic or demographic costs.

---

## O. Stage 4B — strata resolution hardening (as built, 2026-10-03)

Representation engineering only; no socioeconomic semantics change. At the default capacity
the strata sidecar is bit-identical to Stage 4A: rows, events and flows in six full runs with
19,422 capacity coalescences; the Stage 3B/3C fixtures are unchanged; the MVP 2.1 oracles
are identical.

### O1. Capacity as a run setting

- **Configuration:** `strata.max_strata` in `StrataConfig`; default 8 (16 since Stage 4B.1,
  §P), validated 1..127
  (the active count is int8). It is a numerical resolution limit, not a sociological
  parameter.
  - It is part of `config_hash` (provenance).
  - It is not in `static_key`, so runs differing only in capacity share one `StaticContext`.
- **Ownership:** `PopulationStore.max_strata` owns it, and `StrataTable(max_strata)` uses it
  as its padded width.
  - Both engines' lifecycle paths take it from the store: `normalize_strata(block, ids,
    max_strata)`, `coalesce_to_capacity(block, ids, capacity)`, `validate_block(block,
    max_strata)`, `merge_state` / `absorb(..., max_strata)`.
  - The object-engine invariant uses `StrataBlock.is_valid(max_strata)`.
  - The module global `S_MAX` is gone; `DEFAULT_MAX_STRATA = 8` is only the default.
- **Storage is fixed-width per run:** `[rows, max_strata]` float64 `share`, `field_claim`,
  `store_claim`, int64 `stratum_id`, plus an int8 `n_strata` per row. That is 32·S + 1
  bytes per row, verified: 129 / 257 / 513 / 1025 B at S = 4 / 8 / 16 / 32.
- **Hot paths touch active counts, not the full width:** accounting slices to the rows'
  largest active count (bit-identical, since padding is zero and sums are sequential). The
  duplicate check works per chunk over its largest active count.

| `max_strata` | 2 000 units | 50 000 units | vs ≈ 2.5 GB RSS at 50k |
|---|---|---|---|
| 8 | 0.5 MB | 12.9 MB | 0.5 % |
| 16 | 1.0 MB | 25.7 MB | 1.0 % |
| 32 | 2.1 MB | 51.3 MB | 2.1 % |

(Table rows carry the unit table's growth slack.)

### O2. Bounded exact-duplicate check

`StrataTable.duplicate_rows` compares only rows with at least two strata, in chunks of 1024
rows, over each chunk's largest active count `k`. Temporaries are `[1024, k, k]`, independent
of the number of units. Semantics are unchanged: exact equality, no tolerance. `check`
validates in chunks too. Peak temporary for `check` on 50k rows: 21 MB → 0.7 MB at width 8;
1.3 MB at 16; 4.0 MB at 32.

### O3. Vectorized capacity coalescence (same rule)

- **Each greedy step:**
  - order components canonically by state (`lexsort` on share, field claim, store claim;
    stable);
  - evaluate every pair's `s_i s_j/(s_i+s_j)·((Δp_field)² + (Δp_store)²)` at once over
    `triu_indices` (the reference's nested-loop order);
  - merge the first minimum.
- **Bit-identical to the scalar reference,** which is kept as
  `coalesce_to_capacity_reference`, a differential oracle used by tests:
  - squares go through `pow` (an array exponent), because the reference's Python `x ** 2`
    calls the platform `pow`. That is not always `x * x` (0.08 % of values differ here),
    and NumPy's scalar-exponent path squares by multiplication;
  - the cost sums the two squares in reference order;
  - ties keep the first pair in canonical order.
- **Speed:** 0.45 / 1.16 / 5.8 ms for a 2S → S fusion at S = 8 / 16 / 32, against the
  reference's 0.61 / 4.3 / 34 ms.

### O4. Representation-error diagnostics

- **Per-dimension errors on every merge:** each `Coalescence` carries `field_error =
  w·Δp_field²`, `store_error = w·Δp_store²` and `cost`, the combined error the pair was
  chosen by (= field + store up to rounding), with `w = s_i s_j / (s_i + s_j)`.
- **Sidecar events:** `capacity_coalescence` events add `field_error`, `store_error` and
  `combined_error` (`cost` is kept). The frozen event stream is untouched, and nothing feeds
  back.
- **Probe:** `scripts/probes/strata_capacity.py` aggregates them, now through the real
  setting.

### O5. Capacity sensitivity (neolithic 600 y and pressure + cultivation 400 y, seeds 0–3)

Physical outputs (frozen events, RNG states, unit physical state) are identical across every
capacity and w. Cells: w = 0 / w = 1. "vs 32" compares with the highest tested capacity, a
provisional reference, not truth.

| neolithic | 4 | 8 | 16 | 32 |
|---|---|---|---|---|
| unit-years at capacity | 16 % / 18 % | 9.1 % / 9.9 % | 5.7 % / 6.0 % | 3.7 % / 3.8 % |
| capacity coalescences | 7.0k / 7.3k | 8.7k / 9.2k | 11.2k / 11.8k | 14.8k / 15.5k |
| total error field | 1.32 / 1.66 | 0.19 / 0.42 | 0.034 / 0.073 | 0.006 / 0.012 |
| total error store | 0.32 / 8.3 | 0.034 / 1.19 | 0.005 / 0.21 | 0.0008 / 0.043 |
| per-merge field error p99 | 2.6e-3 / 3.5e-3 | 3.3e-4 / 9.4e-4 | 4.7e-5 / 1.3e-4 | 6.4e-6 / 1.6e-5 |
| field-distribution distance vs 32, p99 | 0.043 / 0.046 | 0.018 / 0.021 | 0.006 / 0.008 | — |
| pooling-volume relative difference vs 32 | 1e-3 / 4e-2 | 7e-5 / 1e-2 | 7e-6 / 1e-3 | — |
| share of unit-years where w moves the field distribution | 0.156 | 0.115 | 0.084 | 0.058 |
| that movement (1-D Wasserstein distance), p50 / p99 | 0.016 / 0.087 | 0.0061 / 0.046 | 0.0023 / 0.020 | 0.0007 / 0.010 |
| run time (Σ 4 seeds; probe overhead included) | 84 s | 79 s | 81 s | 86 s |

| pressure + cultivation | 4 | 8 | 16 | 32 |
|---|---|---|---|---|
| unit-years at capacity | 41 % | 32 % | 26 % | 21 % |
| capacity coalescences | 6.2k | 9.7k | 15.6k | 25.3k |
| total error field | 2.0 / 3.7 | 0.35 / 0.89 | 0.065 / 0.21 | 0.012 / 0.045 |
| total error store | 0.33 / 15.7 | 0.038 / 2.6 | 0.005 / 0.55 | 0.0009 / 0.13 |
| field-distribution distance vs 32, p99 | 0.070 / 0.089 | 0.032 / 0.042 | 0.013 / 0.019 | — |
| pooling-volume relative difference vs 32 | 2e-3 / 0.14 | 4e-5 / 0.034 | 7e-7 / 6e-3 | — |
| share of unit-years where w moves the field distribution | 0.445 | 0.422 | 0.350 | 0.308 |
| that movement, p50 / p99 | 0.022 / 0.13 | 0.0091 / 0.057 | 0.0038 / 0.027 | 0.0014 / 0.012 |
| run time | 36 s | 33 s | 35 s | 41 s |

- **Coalescence frequency still rises with capacity,** because demand is open-ended (§N8).
  Error falls about 6× per doubling.
- **Convergence toward 32 is fast:** pooling totals differ by ≤ 1e-3 relative at 16 for
  w = 0; for w = 1, 1e-3 (neolithic) and 6e-3 (pressure).
- **w coupling is reduced, not removed:** its median falls about 2.5× per doubling. Only a
  mechanism-aware metric removes it (§M6 C); none is introduced here.
- **Cost after hardening:** run time +3 % / +9 % (neolithic) and +6 % / +24 % (pressure)
  at 16 / 32. Stage 4A measured up to 3× with pure-Python coalescence. At 32, coalescence
  is 14 % of a pressure run.
- **Final-year people-weighted dispersion** is stable from 8 up (field 0.042 / 0.072; store
  w = 1: 0.170 / 0.34). Capacity changes representation fidelity, not the aggregate picture.

### O6. Recommendation for the default (decision deferred to review)

**CHANGE TO 16** (not done in 4B):
- representation error is about 6× lower and the w coupling about 2.5× lower;
- pooling totals are within 1e-3 to 6e-3 of the 32 reference;
- cost is +1 % memory at 50k units and +3–6 % run time;
- it leaves headroom for one more socioeconomic dimension.

32 buys another ≈ 6× in error at +9–24 % run time; there is no evidence yet that a mechanism
needs it. Switching changes strata outputs (not physics), so it needs new versioned strata
fixtures at 16 (the 3B/3C fixtures stay at 8).

*Adopted in Stage 4B.1 (§P).*

### O7. Gate status

Not cleared. 4B supplies the tools (configurable capacity, error diagnostics, convergence
measures) and shows capacity reduces but does not remove the w coupling. No physical
mechanism is proposed yet, so stability "for the information it uses" cannot be assessed.
The equal-weight metric stays numerical and mechanism-agnostic (§M6 C, §N7).

### O8. Labor accounting

Stage 4C (accounting-only labor contributions) is not authorized. With no modeled cause for
stratum-differentiated labor (§N3), it would add flows equal to share, with no new
information. Its value is only as a named seam for a future cause, which should be weighed
at review against first deciding that cause (§N12, 4D).

---

## P. Stage 4B.1 — default socioeconomic resolution (as built, 2026-10-04)

A numerical-policy change only. No mechanism, criterion or equation changes.

### P1. Decision

The default `strata.max_strata` is **16** (was 8), from the §O5 evidence, relative to 8:
- field representation error is about 6× lower, and the w-induced coupling into the
  represented field claims about 2.5× lower;
- the field-distribution distance to the 32 run is materially smaller;
- persistent memory at 50k units is 25.7 MB instead of 12.9 MB, about another 0.5 % of a
  ≈ 2.5 GB run;
- run time is about +3–6 % in the measured scenarios.

32 improves representation further but costs +9–24 % run time, pressure runs still spend
much time at capacity, and coalescence does not disappear. The resolution question remains
open at any width.

16 is an engineering compromise, not a scientific claim about the number of social
positions. Higher capacity reduces representation approximation; it does not remove it.
Capacity coalescence (exact compaction first, then the unchanged greedy rule) stays the
fallback above the configured capacity.

| `max_strata` | role |
|---|---|
| 8 | historical, or an explicitly requested lower-resolution representation |
| 16 | current project default |
| 32 | higher-resolution sensitivity comparison, not ground truth |

`field_output_claim_weight` stays 0 by default. The project enters the next design stage at
`max_strata = 16`, `w = 0`.

### P2. Consequences

- **Physical outputs:** unchanged. Strata stay non-causal, the MVP 2.1 raw and logical
  oracles are identical, and capacity stays out of `static_key` (in `config_hash`).
- **Default strata sidecar:** it differs from the old default-8 representation, because
  fewer lossy merges occur. This is intended; default-8 sidecar results are not preserved
  globally.
- **Fixtures:** the Stage 3B/3C fixtures, and the Stage 2–3 targeted composition tests,
  pin `max_strata = 8` explicitly and are unchanged. Default-16 coverage is ordinary tests,
  not a new golden: real construction at width 16 (and 8 when asked), shared static
  context across capacities, and a fusion of 8 + 8 positions that stays lossless while
  8 + 9 coalesces exactly once.
- **Gate (§N7, §O7):** still closed. A better default does not make any future mechanism
  resolution-safe. Any mechanism that reads strata needs the capacity policy tested for the
  dimensions it reads, and an approved causal reason to differ by stratum.

### P3. Labor accounting deferred; next stage is design only

The §N12 Stage 4C, labor accounting, is no longer the automatic next step. Every stratum
shares the unit's age structure, knowledge, technology, pooled consumption and the other
current labor determinants. So each stratum's labor contribution would be exactly its
population share. Explicit runtime state for that would add machinery without adding
modeled information. The statement "labor contribution currently follows population share"
stays documented (§N3, §N4), and the minimum flow is added only when a causal mechanism
needs it.

**Next: Stage 4C — First Causal Differentiation Design (design only, when authorized).**
Purpose: identify the smallest lower-level mechanism that gives people within one population
a causal reason to experience different actions, access, obligations, opportunities or
outcomes. Questions it must answer:

- **A. Is endogenous differentiation needed yet?** Homogeneous units stay homogeneous unless
  fusion brings in several positions. That is acceptable, and strata existing is no reason
  for a new mechanism.
- **B. What concrete process makes existing strata behave differently?** Candidates include
  differential resource access, persistent control of productive assets, differentiated
  labor obligations, specialization, or another explicit institutional mechanism. None is
  selected.
- **C. Can it create a new stratum?** If so, it must say which subset differs, why, how
  large it is, what is conserved, and why a new component is necessary. No random class
  generation.
- **D. Which representation dimensions does it read?** The capacity and coalescence policy
  must be tested for exactly those dimensions before implementation (the gate).
- **E. Does it need new persistent state?** Prefer flows and existing state. Do not add
  wealth, status, occupation or power because they might someday be useful.

Stage 4B.1 does not choose among unequal food access, private stores, property
persistence, labor obligations, specialization, decision influence, inheritance or
redistribution. That needs its own design review.

---

## Q. Stage 4C — counterfactual stored-food access (2026-10-06)

**COUNTERFACTUAL / NOT YET ACTIVE.** A candidate causal mechanism evaluated read-only on
recorded states. No simulator path calls it, it is not a registered model rule, and its
parameter is not a scenario setting. Physical food, reserves, demography and every subsystem
stay MVP 2.1; the MVP 2.1 oracles are identical.

Question: if existing effective control over stored food influenced access during scarcity,
how much would socioeconomic allocation differ from complete pooling, and is that robust to
strata resolution?

### Q1. Semantics

- **`store_claim`** is a share of *continuing effective control over the surviving aggregate
  stored stock*, not an exhaustible calorie account, household inventory, private granary,
  debt, title or inheritance right. Receiving food debits nothing and changes no claim.
  Claims change only through the existing Stage 3B/3C accretion, and reset to share when
  the stores reach zero. Access transfers consumption rights, not control.
- **Scope:** only the internal allocation of a unit's physical store withdrawal `X` that
  covers an existing shortage. It does not touch trade, spoilage, abandonment, new stores,
  harvest or crop attribution, fields, labor or reserves.
- **Timing (locked):** post-trade harvest `H` known → pre-withdrawal `store_claim` → remaining
  deficits `D_i` → the physical `X` (MVP 2.1) → counterfactual allocation of that fixed `X` →
  the simulation continues unchanged → if the stores close at zero, the existing zero-stock
  rule resets the claims afterwards. A depletion year uses the old claims.
- **Remaining external deficit:** with need and harvest by share (shared demography, pooled
  harvest), `D_i = max(Need·s_i − H·s_i, 0)`, computed in the identical factored form
  `max(Need − H, 0)·s_i`, which avoids cancellation when Need ≈ H. `Need` is the energetics
  requirement (including carried energy debt). Body reserves are excluded.

### Q2. Allocator (`population/strata_access.py`, pure)

```text
q_i = s_i + a·(c_i − s_i)                         access priority, a = store_access_claim_weight ∈ [0, 1]
X ≥ ΣD − allowance:  x_i = D_i                    stores cover everyone: claims cannot matter
else water-filling:  R = X; repeat over strata with unmet deficit:
                     offer_i = R·q_i / Σ q (hungry); cap at D_i − x_i; R −= capped room
                     if Σ q (hungry) = 0: weights = remaining unmet need   (zero-priority fallback)
```

- **Neutral limits:** `a = 0` gives `q = s`; `c = s` gives `q = s` for every `a`, bit for bit.
- **Fallback:** the neutral rule when claims give no ranking. Under proportional needs it is
  also the `a → 1` limit, so the allocation stays continuous. Future stratified needs may
  require revisiting it.
- **Derived diagnostics:**
  - `counterfactual_store_access_kcal` = `x_i`;
  - `counterfactual_external_food_allocation_kcal` = `H·s_i + x_i`, and `_ratio` = that
    `/ (Need·s_i)`;
  - `counterfactual_unmet_external_need_kcal` = `D_i − x_i`;
  - `counterfactual_store_access_transfer_kcal` = `x_i − X·c_i`. At `a = 0` this is the
    Stage 3B transfer `X·(s_i − c_i)`;
  - redistribution from pooling `R = ½ Σ|x_i − X·s_i|`, and `R/X`.

  These are candidate socioeconomic allocation before body reserves, not consumption or
  food ratio.
- **Numerical contract (`REL_TOL = 1e-12`, the partition tolerance):**
  - `0 ≤ x_i ≤ D_i` exactly;
  - `|Σx − X| ≤ REL_TOL·X + slack`;
  - at `a = 0`, `|x_i − X·s_i| ≤ REL_TOL·X` and the transfer equals the Stage 3B transfer to
    `REL_TOL·X`.

  `slack = REL_TOL·max(K0, Need)` absorbs the physical `X = K0 − (K0 − X)` rounding. Input
  validation rejects bad lengths, non-finite values, shares that are not positive or do not
  sum to 1, claims outside the simplex, negative deficits, `a ∉ [0, 1]` and `X > ΣD +
  allowance`.

### Q3. A structural finding: under MVP 2.1 the mechanism is one-shot per store cycle

MVP 2.1 energetics withdraws `X = min(Need − H, K0)`. So a withdrawal either covers every
remaining deficit (`X = ΣD`: `x = D`, claims irrelevant) or empties the stores (`X = K0 < ΣD`),
after which the zero-stock rule erases the control relation.

**Claims can matter only in a store-exhaustion year, and only once.** Repeated preferential
access while stores stay positive is consistent with the semantics. The controlled experiment
shows it with prescribed rationed withdrawals: claims persist, the high-control stratum is
favored every year, and the final depletion uses the pre-depletion claim and then resets.
It is physically unreachable without a rationing rule, i.e. a rule that withdraws less than
the deficit while stores remain. Such a rule would decide *how much* to withdraw, which is
out of scope here.

In real runs every mechanism-active unit-year was a depletion year:
- non-neutral claims meeting withdrawals in chains with positive closing stores: 1,973
  events (neolithic) and 577 (pressure); `a = 1` changed none of them;
- chains where non-neutral control persisted through ≥ 2 withdrawal years: 918 / 406, of
  which 344 / 323 end in depletion, where the claim acts once and resets (verified in
  2,602–2,905 multi-strata depletion events per run set, 0 failures, at both capacities and both w).

Caveat: a rounding remnant of stores (≤ 1e-8 kcal) can postpone the reset by a year; those
"dust" withdrawals (X ≤ 1e-9·Need) are excluded from the statistics.

### Q4. Experiment (`scripts/probes/store_access_counterfactual.py`)

**Setup:**
- neolithic 600 y and pressure + cultivation 400 y, seeds 0–3;
- `max_strata` 16 and 32, with physical state identical across capacities and with the
  observer on or off;
- `a ∈ {0, 0.25, 0.5, 1}` evaluated on the same recorded pre-withdrawal state;
- primary `w = field_output_claim_weight = 0`; stress `w = 1`.

**Unit-years by category** (capacity 32; identical across w and capacity):

| | neolithic | pressure + cult |
|---|---|---|
| unit-years / deficit unit-years | 384,074 / 21,290 | 122,326 / 33,013 |
| withdrawals (X > 0) | 15,844 | 7,875 |
| covered (X = ΣD; claims irrelevant) | 14,286 (4,203 of them exactly emptied) | 4,448 (992) |
| partial depletion (X = K0 < ΣD) | 1,061 (30k person-years) | 3,126 (89k) |
| … with non-neutral claims, w = 0 / w = 1 | 245 / 446 | 899 / 2,020 |
| mechanism-active (R/X > 1e-9 at a = 1), w = 0 / 1 | 242 / 443 | 890 / 2,018 |
| dust withdrawals (excluded) | 497 | 301 |

**Mechanism signal** (capacity 32, active unit-years; per unit-year p50 / p90 / p99):

| | w = 0 neolithic | w = 0 pressure | w = 1 neolithic | w = 1 pressure |
|---|---|---|---|---|
| R total / X total, a = 0.25 / 0.5 / 1 | 0.020 / 0.036 / 0.059 | 0.021 / 0.040 / 0.073 | 0.046 / 0.085 / 0.15 | 0.063 / 0.12 / 0.22 |
| R/X at a = 1 | 0.004 / 0.35 / 0.79 | 0.007 / 0.54 / 0.79 | 0.14 / 0.42 / 0.74 | 0.24 / 0.55 / 0.79 |
| W1(a = 0, a = 1) of access ratio | 3e-4 / 0.018 / 0.043 | 4e-4 / 0.013 / 0.039 | 0.009 / 0.042 / 0.079 | 0.009 / 0.037 / 0.069 |
| people below the pooled ratio (a > 0) | 0.55 / 0.78 / 0.88 | 0.55 / 0.77 / 0.88 | 0.53 / 0.74 / 0.88 | 0.54 / 0.73 / 0.86 |
| need caps / fallback (a = 1) | 20 / 14 | 63 / 38 | 81 / 16 | 518 / 90 |

- **W1 values are in units of the access ratio** (fraction of need), so a typical active
  year moves people by about 1–4 % of need, and at most 12 %.
- **Most people lose slightly while a small high-control minority gains.** The
  people-weighted distribution of the access ratio over all active unit-years is almost
  unchanged (p10 / p50 / p90 at w = 0: neolithic 0.501 / 0.932 / 0.990 → 0.501 / 0.932 /
  0.992; pressure 0.760 / 0.940 / 0.990 → 0.758 / 0.939 / 0.993).
- **Small at w = 0:** at depletion, store positions are near 1, because store memory fades
  in about 2 y (§M4). Under w = 1 the signal is about 2–4× larger.

**Resolution, 16 vs 32** (same year, unit and a; signal at 32 vs uncertainty):

| | w = 0 neolithic | w = 0 pressure | w = 1 neolithic | w = 1 pressure |
|---|---|---|---|---|
| Σ R32 (a = 1), kcal | 1.8e7 | 5.6e7 | 7.2e7 | 3.3e8 |
| Σ \|R16 − R32\| / Σ R32 | 2e-16 | 4e-9 | 2e-4 | 4e-3 |
| \|R16 − R32\| / R32, p99 / max | 4e-10 / 1e-8 | 1e-8 / 0.39 (R32 ≈ 0.5 kcal) | 0.006 / 0.033 | 0.081 / 0.33 |
| W1(16, 32) / W1(a = 0, 1), p90 / p99 / max | 5e-12 / 6e-5 / 6e-4 | 4e-6 / 0.022 / 0.39 | 0.002 / 0.095 / 0.14 | 0.062 / 0.21 / 0.80 |
| unit-years where W1(16, 32) > 0.1·signal | 0 / 242 | 2 / 890 | 4 / 443 | 108 / 2,018 |

- **At w = 0 the two capacities agree to rounding,** except in a handful of unit-years with
  negligible signal.
- **Under w = 1, resolution uncertainty is small in aggregate but not negligible in the
  tail:** 5 % of pressure active unit-years have uncertainty above 10 % of their signal.
- **Coalescence association:** the largest-|R16 − R32| decile has recent capacity
  coalescence (same unit id, prior 10 y, capacity 16) 2–5× more often than the rest:
  29 % vs 4 % and 61 % vs 19 % at w = 0; 14 % vs 3 % and 32 % vs 12 % at w = 1. Under w = 1,
  most large differences have no recent same-id coalescence. They are inherited from older
  coalescences or absorbed predecessors and propagated by store accretion, which the
  §M6 w-coupling predicts.

**Audits and cost:**
- `max |ΣD − (Need − H)| / Need ≤ 2.7e-16`;
- `max (X − ΣD) / max(K0, Need) ≤ 8.6e-17`; `X ≤ ΣD` held in every withdrawal at both
  capacities, under both w;
- authoritative state (events, RNG, unit physical state, strata sidecar) identical with the
  observer on and off;
- allocator 30 µs (a = 0) to 80–90 µs (a = 1, 16–32 strata, 5 rounds), ≈ 110 µs per
  (state, a) with derived quantities and audits;
- observer 0.4 s of an 85 s run set; snapshots ≤ 1.4 MB per run.

### Q5. Recommendation: D (with A for resolution at w = 0)

- **Resolution (gate condition for `store_claim`):** adequate for this mechanism at the
  neutral `w = 0`. Under the `w = 1` stress the tail uncertainty (p99 21 % of signal in
  pressure runs) argues for the §M6 mechanism-aware metric before any activation that also
  uses `w > 0`. No metric change is made here.
- **Mechanism:** the effect is small, concentrated and structurally **one-shot**:
  - a few hundred to two thousand unit-years in 4 seeds;
  - about 2–7 % of withdrawn kcal at w = 0;
  - always in a store-exhaustion year, immediately followed by the reset of control.

  The mechanism does not touch the persistent-differentiation question MVP 3 needs answered.
  Its leverage is limited by the MVP 2.1 withdrawal rule, not by the allocator.
- **Not activated.** Before any activation design, review should decide:
  - whether a withdrawal (rationing) decision should exist at all; that is a separate
    collective-choice mechanism and would make repeated access possible;
  - whether the effect should reach biology (stratified reserves and demography are later
    stages).

Physical-feedback gate: **NOT CLEARED** (pending scientific review).

---

## R. Stage 4D — store release / reserve management (2026-10-06)

**COUNTERFACTUAL / NOT ACTIVE.** The question is *how much* leaves storage when the
harvest falls short (`X`). Who receives it (`x_i`, §Q) is a separate question.
- The candidate is a unit-level, symmetric rule. It reads no claim, share or stratum id.
- No hierarchy, authority, coercion or conditional access is modeled.
- The authoritative rule stays MVP 2.1; the MVP 2.1 oracles are identical.

### R1. The current pipeline (from code)

```text
Farming      crop Y from fields worked by pooled labor (fields sized to need·(1 + surplus_target))
Foraging     effort targets need·(1 + surplus_target) − Y            surplus_target = 0.2 (human)
Trade        balance = H + K − Need; donors offer food_sharing_propensity·balance (0.3), taken
             from harvest first, then stores; recipients receive into harvest
Energetics   fed  (H ≥ Need): body reserves topped up (cap reserve_days_max·daily·people, 60 d),
                              then leftover stored if storage_retention > 0, else spoiled
             short (H < Need): X = min(Need − H, K), then body reserves, then energy deficit
             K' = (K − X + A)·r,  r = storage_retention: base 0.15, +0.35 storage_pits,
                                  +0.30 granaries (0 if mechanisms.storage is off)
Demography   fertility from food_ratio = H / Need (stores and reserves not counted);
             mortality from energy_deficit (after stores and reserves; exp, convex)
Migration    carry = 60,000 kcal per person; stores above it abandoned; utility cost of abandoning
Innovation   "surplus" term reads stores / Need; harvest_variability need reads harvest_history
```

- **What is not modeled:** storage capacity, seasons (the step is annual), seed requirements
  and decay of body reserves.

### R2. Intent of `X = min(D, K)`: an MVP simplification, not a documented hypothesis

- **When and how it was introduced:** in the first MVP 2 commit (`244289c`), extending the
  MVP 1 rule "intake plus reserves". The `pooled_energy_balance` rationale states an
  *order* ("shortfalls draw on food stores, then body reserves") with no purpose,
  `source_type = heuristic`.
- **No stated purpose:** its only listed limitation is equal sharing. Tests check the
  arithmetic, not a storage policy.
- **What the objective says:** storage, spoilage, portability and transferability are listed
  as mechanisms to develop (§7), and the ecology has no seasons (§3.3).
- **Conclusion:** the repository does not establish reserve management as intended; the rule
  is the minimal one. It is still not arbitrary under the current physics (R4).

### R3. Information available at the release decision

| Signal | What it is | Known when | Kind | New foresight if used? |
|---|---|---|---|---|
| `Need` (incl. energy debt) | this year's requirement | at energetics | causal | no; "next year ≈ this year" is a persistence assumption |
| `H` after trade, `K` after trade | this year's food | at energetics | causal | no |
| `storage_retention` r | the unit's storage technique | always | causal (capability) | no |
| body reserves | lossless, capped at 60 days of need | always | causal | no |
| `harvest_history` (10 y per capita) and its CV | recent production | always | causal state (innovation need) | no, but turning it into an expectation is a new behavioral hypothesis |
| `surplus_target` (0.2) | production target for foraging effort and field area | always | parameter | not a stock target (R5) |
| `planning_horizon_years` (10) | amortizes clearing over expected tenure | field planning | parameter | no production or need forecast exists |
| next year's field area | set by field planning, after energetics | after the decision | causal | a crop forecast would be new |
| beliefs, `food_log_prior` | spatial food beliefs for migration | always | causal | not temporal |

Nothing in the model forecasts next year's harvest, need or shortage.

### R4. The structural finding: under current physics the greedy release is optimal in kcal

- **Accounting:** in a shortage year with reserves `B ≥ D − X`, food left at the year's end
  is `r·(K − X) + B − (D − X)`. Its slope in `X` is `1 − r > 0`. With insufficient
  reserves, a smaller `X` adds current energy deficit one for one.
- **Result:** `X = min(D, K)` both maximizes the food left (stores plus reserves) and
  minimizes current starvation, for any `r < 1`.
- **Fed years don't help:** they refill body reserves *before* storing. A reserve drawn down
  by withholding is restored from surplus that would otherwise have been stored, so the
  loss `(1 − r)` recurs.
- **Body reserves:** fertility reads `H/Need` only, so drawing reserves has no demographic
  cost unless they run out. Holding stores while bodies draw down is therefore coherent
  physically, but strictly dominated.
- **What a reserve rule would need:** a motive the model lacks. Examples:
  - an expected *worse* future deficit, with convex mortality and a forecast;
  - a use of stores that reserves cannot serve (seed, a season's lean period, portability);
  - a cost of low body reserves.
- **Trade conflict:** trade counts every store above current need as giftable surplus. A
  protected reserve would conflict with it.

### R5. Candidates

| Candidate | Verdict |
|---|---|
| C0 `X = min(D, K)` | baseline (MVP 2.1) |
| C1 a target already in the model | **rejected**: no stock target or capacity exists. `surplus_target` is a production margin and already the mechanism that fills stores, so reusing it as a stock target reinterprets it and double-counts |
| C2 future-need buffer `X = min(D, max(K − R, 0))`, `R = b·Need` | the smallest rule expressible from decision-time information. Studied counterfactually with an experimental `b` (no canonical value; `b = 0` is C0). Not defensible as a default (R4) |
| C3 adaptive risk buffer from `harvest_history` | **rejected for now**: needs a new expectation hypothesis, and C2 already loses |
| optimize X over future realized states | **rejected**: omniscient |

Code: `population/store_release.py` (pure; unused by the simulator). Probe:
`scripts/probes/store_release_counterfactual.py`.

### R6. One-step counterfactual (neolithic 600 y and pressure + cultivation 400 y, seeds 0–3)

- **Method:** policy inputs are decision-time values only. Later authoritative years are read
  afterwards, for evaluation only.
- **Validation:** `min(D, K)` reproduces the recorded `X` to 8.6e-17 relative, and the
  observer leaves authoritative state identical.

| Prevalence | neolithic | pressure + cult |
|---|---|---|
| unit-years / shortage unit-years (D > 1e-9·Need) | 384,074 / 20,333 | 122,326 / 32,098 |
| stores cover D / stores exhausted short of D / no stores | 14,285 / 1,247 / 4,801 | 4,447 / 3,343 / 24,308 |
| D / Need p50 / p90 | 0.061 / 0.19 | 0.090 / 0.32 |
| K / Need (K > 0) p50 / p90 | 0.086 / 0.41 | 0.040 / 0.093 |
| retention at shortages with stores (r = 0.15 / 0.5 / 0.8) | 100 / 10,411 / 5,021 | 499 / 7,291 / 0 |
| body reserves at the cap / reserves ÷ D p50 | 78 % / 2.6 | 24 % / 0 |
| shortage chains (length 1 / 2 / 3 / ≥ 4) | 11,370 / 1,762 / 510 / 538 | 6,490 / 1,932 / 957 / 2,260 |
| gap to the next shortage p10 / p50 / p90 | 1 / 2 / 25 y | 1 / 1 / 6 y |
| next shortage within 10 y: retained food surviving to it, p50 / p90 | 41 % / 80 % | 25 % / 50 % |

**Sweep of `b`** (every binding unit-year is a hunger-with-retained-food event by
construction):

| b | binding unit-years | retained kcal (÷ withdrawn) | person-years | extra starvation kcal | events with energy deficit and retained stores |
|---|---|---|---|---|---|
| neolithic 0.05 | 9,880 | 6.0e9 (0.37) | 274,636 | 2.4e8 | 427 |
| neolithic 0.2 | 13,232 | 1.25e10 (0.77) | 374,387 | 4.1e8 | 493 |
| neolithic 1.0 | 15,520 | 1.62e10 (1.00) | 441,779 | 5.6e8 | 640 |
| pressure 0.05 | 6,875 | 3.3e9 (0.69) | 193,528 | 4.5e8 | 936 |
| pressure ≥ 0.2 | 7,785–7,790 | 4.8e9 (1.00) | 219,385 | 6.3e8 | 1,001 |

**Where each retained kcal goes** (ranges over b):

| | neolithic | pressure |
|---|---|---|
| paid now from body reserves | 0.96 | 0.86 |
| paid now as extra energy deficit | 0.033–0.041 | 0.13–0.14 |
| still stored one year later | 0.55–0.62 | 0.48–0.49 |
| surviving to the unit's next shortage | 0.14–0.22 | 0.21–0.22 |
| potential cover of that shortage's uncovered need (upper bound) | 0.027–0.047 | 0.17–0.19 |
| abandoned above the carry limit on a later move | ≤ 0.011 | ≤ 0.0013 |

- **Potential availability is not a benefit.** It ignores that the body reserves drawn now,
  being lossless, would themselves have been available, and that refilling them takes
  priority over storage.
- **Storage capacity:** no opportunity cost, because none is modeled. The carry limit is the
  only bound.
- **Controlled cases** (closed toy through the real `energy_balance`; valid only because
  nothing feeds back):
  - every reserve target that binds adds starvation or spoilage, in every case;
  - in the one-shortage case at r = 0.5, b = 0.1 leaves 285 kcal of stores plus reserves
    against 310 under the current rule;
  - a target binds with full stores only when `K − b·Need < D`.

### R7. One-step vs dynamic counterfactual

- **The one-step evaluation does not compound:** retained food never enters a later `K`.
- **A shadow replay of stores alone would be misleading.** Withholding changes body reserves
  and energy deficit, hence mortality, then population, Need, labor, fission and fusion.
  It also changes trade balances and offers, the migration stores cost, carry abandonment
  and the innovation surplus term (including storage technologies).
- **Only a true branched simulation** can evaluate dynamics. It is not warranted while R4
  gives no motive to retain.

### R8. Hunger with retained food, and the possible link to hierarchy (future hypotheses only)

- **No power is needed for it:** collective reserve preservation can produce hunger while
  food is stored, with nobody holding power. It is necessary, not sufficient, for power
  over storage.
- **A possible later sequence; every step after the first is an untested hypothesis:**
  collective reserve management → valuable control over intertemporal release →
  asymmetric influence over that decision → dependency during scarcity → possibly
  conditional access or obligations → possibly coercive capacity.
- **Design principle:** political power should be inferred from concrete asymmetric
  capacities over consequential decisions, not represented as a scalar. For storage, a
  future measure might be (ability to alter the release of a scarce resource) × (people
  dependent on it) × (cost imposed by refusal). Not implemented.

### R9. Recommendation: A, keep the current rule; no further store-release work now

The current rule is the minimal one, but under the current physics it is also the
kcal-optimal one (R4). A reserve-management hypothesis becomes meaningful only after a
mechanism gives retention a purpose, for example:
- seasonality or a lean period;
- seed requirements;
- a cost of low body reserves;
- expectation formation from `harvest_history` (C3).

Then it should be tested in a true branched simulation (C). Consequence for §Q: claim-sensitive
access stays one-shot per store cycle. The next MVP 3 review should look for differentiation
outside storage release.

---

## S. Stage 4E — control over new cultivated capacity (2026-10-07)

**`field_claim_continuity`: COUNTERFACTUAL / NOT ACTIVE.** Pure functions in
`population/field_control.py`. No simulator path calls them, no model rule is registered,
and there is no scenario setting. Probe: `scripts/probes/field_control_counterfactual.py`
(`controlled`, `runs [--stress]`). Tests: `tests/test_field_control.py`. The MVP 2.1 oracles
are identical.

### S1. Primitive and concrete semantics

- **Epoch-general primitive:** *effective control over durable productive capacity*. It is a
  physical stock at `[U]` plus a distribution of control at `[U,S]`. The intensive position
  is `control_i / share_i`: 1 is population-proportional, above 1 is above-proportional
  control per person.
- **Asset-specific mechanism:** how the stock is created, used, lost and produced from. For
  fields that means clearing labor, cultivation, crop yield, arable sharing, and abandonment
  at migration or below 0.05 ha.
- **Cultivated land is the first specialization:** `fields_ha` plus `field_claim`.
  `field_claim` is a stratum's share of effective control over the unit's cultivated
  productive capacity, meaning the modeled ability to benefit from existing fields or
  direct their use. It is **not** ownership, title, sale, inheritance, exclusion, rent,
  authority or coercion.
- **Epoch check:** the statements in S2–S5 hold unchanged for a herd, workshop, irrigation
  system, machine or firm. Each speaks only of a stock, its expansion `F0 → F1`, a
  partition of control, and the zero-stock rule.
  - What does not transfer is how the stock grows, how it shrinks (fields keep fractions
    under shrinkage; a herd that dies or is slaughtered might not), and what it produces.
  - So the boundary sits at the transition's inputs `(F0, F1)` and at the loss rule. No
    generic asset framework is built.
- **Contrast with stores (§Q, §R):**
  - Stored food is consumed, and control over it ends when the stock is exhausted.
  - Cultivated land is not used up by being used. Control ends only when the stock itself
    reaches zero.

### S2. The field-claim lifecycle as built (audited from code)

| Operation | Where | Rule |
|---|---|---|
| expansion `F1 > F0` | `FieldPlans.apply` → `FieldAccounts` → `account_strata` → `field_claims_after_change` | `a_i = c_i·F0 + s_i·(F1 − F0)`, `c_i' = a_i / Σa` (Σa = F1 mathematically; normalizing by Σa keeps one stratum exactly 1) |
| shrinkage `0 < F1 < F0` | same | `c` unchanged (proportional loss) |
| fields to 0 (planning below 0.05 ha, arable sharing) | same, then `settle_empty_claims` | `c = s` (`claim_zero_stock`), then exact compaction |
| migration | `Relocation.apply` sets `fields_ha = 0` | `c = s` at the next `settle_empty_claims` |
| fission | `lifecycle.split_unit` | fields split ∝ people moved; the daughter copies the strata, so positions are unchanged on both sides |
| fusion | `fuse_strata` | absolute control `c_i·F` of each predecessor, renormalized by the fused total; concatenated (the only source of heterogeneity) |
| compaction and coalescence | `normalize_strata` | exact compaction is lossless; capacity coalescence sums claims (`Σ|c − s|` can only fall) |
| shares | — | change only at fusion and coalescence (births and deaths do not, §C) |

Nothing else writes `fields_ha`: farming and soil do not, and the singular `FieldPlan`
class was dead code (removed in the refactoring pass, see `REFACTORING.md`).

### S3. Hypotheses for who controls new capacity `dF = F1 − F0`

Every hypothesis is a partition `n` of the new hectares. Then `a_i = c_i·F0 + n_i·dF` and
`c_i' = a_i/Σa` (`field_claims_after_expansion`).

- **H1, population allocation (`n = s`).** The current, neutral rule. It is not "communal
  property"; it is simply the rule when no other causal distinction is modeled.
- **H2, clearing-contribution allocation (`n = contribution/Σ`).** **It collapses exactly to
  H1 in the current model.**
  - Clearing hours are one unit-level flow: `ΔF·clearing_hours_per_ha(vegetation,
    clearing_efficiency)`, charged to next year's `labor_debt_hours`.
  - They are drawn from the single pool `labor_hours_columns`. That pool comes from the
    shared `[U, sex, age]` cohorts (§C), with unit-level technology (`clearing_efficiency`)
    and knowledge.
  - No code on that path reads strata (tested on the module source). So every stratum's
    contribution is `s_i·clearing_hours`, and `n = s`.
  - A difference would need a cause for stratum-differentiated labor (§N3). None is
    invented here.
- **H3, control continuity (`n = s + p·(c − s)`).** `p = field_claim_continuity ∈ [0, 1]`;
  a unit without fields (`F0 = 0`) has nothing to continue, so `n = s`.
  - `p = 0` is H1. `p = 1` gives new capacity to existing control.
  - `p` does not say *why* control continues (continuity of use, prior investment, plot
    extension, household management, custom, institutions or inheritance). It tests only
    the consequences.

### S4. Exact properties (proved, then tested)

- **`p = 0` reproduces the current rule bit for bit.** `n = s + 0·(c − s) = s` exactly,
  and the arithmetic is otherwise the authoritative one. This was tested on random 1-D
  blocks and padded table rows. In real runs the `p = 0` shadow strata sidecar equals the
  authoritative one (digest) in all 8 runs.
- **Deviation law.** Let `δ = c − s`. One step gives
  `δ' = λδ + (1 − λ)·pδ = ρ·δ`, where `λ = F0/F1` and **`ρ = p + (1 − p)·F0/F1 ∈ [F0/F1, 1]`**.
  - Every stratum's deviation, the whole position distribution around 1
    (`pos' − 1 = ρ·(pos − 1)`), `D = ½Σ|c − s|`, and the share-weighted Gini of positions
    all scale by the same `ρ`.
  - `p = 1` gives `ρ = 1`: claims are preserved, within rounding (5,000 random steps
    without drift).
- **No creation and no amplification.**
  - `c = s` stays `s` for every `p`.
  - `c'` lies between `c` and `s` component by component (convex envelope), stays
    normalized and stays nonnegative.
  - `D` never increases through the transition.
  - The absolute hectare gap `δ·F` grows with `F` at `p = 1`. That is preservation of a
    relative position, not concentration.
- **Persistence.**
  - With fixed shares, `D_T = D_0·Π ρ_t`.
  - For small steps, `D ∝ (F/F0)^−(1−p)`. So the area growth needed to halve `D` is
    `2^{1/(1−p)}`: 2, 2.52, 4 and 16 at `p` = 0, 0.25, 0.5 and 0.75, and never at `p = 1`.
  - One step of factor G retains `p + (1 − p)/G ≥ G^−(1−p)` (AM-GM), so annual steps retain
    at least this much.
- **Gross, not net, expansion dilutes.** Shrinkage keeps fractions and regrowth is
  allocated by `n`. A cycle of ×2, ×0.5, ×2 therefore takes `D` from 0.3 to 0.15, 0.15
  and 0.075 at `p = 0`, but leaves it at 0.3 throughout at `p = 1`. This asymmetry is part
  of the existing rule, not something the counterfactual adds.
- **Zero stock.**
  - Fields at zero reset claims to share (`claim_zero_stock`), and regrowth from zero
    follows share for every `p`.
  - Stale claims on an empty stock cannot be continued either (`F0 = 0 ⇒ n = s`).
  - Old control is never resurrected.

### S5. Shadow trajectories in real runs

- **Method:** the probe swaps `field_claims_after_change` for the H3 transition inside the
  passive accounting.
  - Because strata feed no physical mechanism, every authoritative quantity is identical
    across all `p` and both capacities, and equal to a plain run without the probe. This
    was checked by digest of events, RNG and unit physical state in every run.
  - Claims, compaction and coalescence then follow the counterfactual recursively, with
    fusion inheritance unchanged.
- **Runs:** neolithic 600 y and pressure + cultivation 400 y, seeds 0–3, `max_strata` 16
  and 32, `p ∈ {0, 0.25, 0.5, 0.75, 1}`, `w = 0`.

**Representation** (cells: neolithic / pressure, capacity 16):

| p | 0 | 0.25 | 0.5 | 0.75 | 1 |
|---|---|---|---|---|---|
| people-weighted D (all unit-years) | 0.0140 / 0.0307 | 0.0170 / 0.0371 | 0.0211 / 0.0465 | 0.0271 / 0.0622 | 0.0364 / 0.0935 |
| field position range p1–p99 (people in multi-strata units) | 0.66–1.37 / 0.56–1.47 | 0.60–1.49 / 0.48–1.57 | 0.43–1.60 / 0.36–1.72 | 0.22–1.79 / 0.19–2.02 | 0–2.11 / 0–2.82 |
| multi-strata unit-years | 148k / 69.4k | 149k / 69.4k | 150k / 69.7k | 151k / 69.9k | 152k / 69.9k |
| capacity coalescence field error Σ (16 / 32) | 0.034 / 0.006 · 0.065 / 0.012 | 0.057 / 0.010 · 0.11 / 0.021 | 0.093 / 0.018 · 0.18 / 0.037 | 0.17 / 0.032 · 0.35 / 0.079 | 0.33 / 0.065 · 0.79 / 0.18 |

- **Shared across all `p`:**
  - unit-years: 387,394 / 122,855;
  - unit-years with non-neutral field control: 105,884 / 65,898;
  - mean strata per unit-year: 2.7–2.8 / 6.1 (p90 9 / 16);
  - transitions from non-neutral control to zero fields: 2,228 / 1,420.
- **What changes with `p`:** continuity changes the *size* of differences, never *where*
  they exist.
- **Store deviation:** identical across `p` (0.0079 / 0.0135), because `w = 0` isolates
  stores.

**Persistence of fusion-created episodes:**
- *Definition of an episode:* a fusion leaves `D ≥ 0.01`. It is followed until the unit
  fuses again, disappears or the run ends (censored).
- 4,059–4,236 / 2,876–2,958 episodes. Kaplan–Meier survival, identical at 16 and 32.
- No episode ever grew: zero increases of `D` without a fusion, in every run.
- The analytical law `D_t = D_0·Πρ` holds per year to ≤ 1.6e-14 relative.

| p | not halved at 10 / 25 / 50 / 100 y | above 10 % at 50 / 100 y | halved by dilution: n, median years, median expansion factor | halved by zero-field reset |
|---|---|---|---|---|
| 0 | 0.75 / 0.38 / 0.09 / 0.01 · 0.72 / 0.29 / 0.03 / 0.01 | 0.34 / 0.07 · 0.25 / 0.07 | 1,055, 12 y, ×2.36 · 694, 11 y, ×2.33 | 590 · 351 |
| 0.25 | 0.82 / 0.50 / 0.14 / 0.03 · 0.82 / 0.40 / 0.07 / 0 | 0.42 / 0.13 · 0.32 / 0.06 | 678, 15 y, ×3.25 · 440, 17 y, ×3.33 | 692 · 417 |
| 0.5 | 0.88 / 0.64 / 0.27 / 0.03 · 0.87 / 0.60 / 0.16 / 0.03 | 0.43 / 0.18 · 0.37 / 0 | 261, 27 y, ×6.5 · 169, 27 y, ×6.7 | 817 · 499 |
| 0.75 | 0.89 / 0.70 / 0.43 / 0.14 · 0.87 / 0.68 / 0.35 / 0.11 | 0.43 / 0.18 · 0.36 / 0 | 11, 65 y, ×77 · 16, 57 y, ×84 | 885 · 546 |
| 1 | 0.89 / 0.70 / 0.43 / 0.18 · 0.87 / 0.68 / 0.37 / 0 | 0.43 / 0.18 · 0.37 / 0 | none | 902 · 554 |

- **At `p = 0`, dilution follows the law.** A difference halves after a median ×2.3–2.4 of
  cumulative gross expansion, about 11–12 years. The law's minimum is ×2; annual steps
  overshoot it.
- **At `p ≥ 0.75`, dilution practically stops.** Differences then end only when the fields
  reach zero (migration, abandonment). That is the dominant end at every `p ≥ 0.5`, and
  the only end at `p = 1`.
- **The cap on persistence is physical, not the transition.** At `p = 1`, 43 % / 37 % of
  episodes are still undiminished after 50 years, and the survival curve flattens.
  Survival stays bounded by fission, fusion and migration. Pressure units migrate or fuse
  too often for any difference to survive 100 years.
- **Deviation 25 or more years after a unit's last fusion** carries 8 % → 13 % (neolithic)
  and 4 % → 9 % (pressure) of the people-weighted deviation as `p` goes from 0 to 1.

**Resolution, 16 vs 32 (same `p`; signal = the `p = 0 → 1` change at 32):**
- `Σ|D16 − D32| / Σ|D(p=1) − D(p=0)|`:
  - neolithic 1.1e-4, 1.7e-4, 3.0e-4, 5.6e-4, 8.3e-4;
  - pressure 3.4e-4, 5.0e-4, 8.2e-4, 1.4e-3, 2.6e-3.

  Small at every `p`, but growing about 8× from `p = 0` to `p = 1`.
- **Per unit-year field-position distributions:** the share of signal-bearing unit-years
  where W1(16, 32) exceeds 10 % of W1(p0, p1) rises with `p`:
  - neolithic 1.9 %, 2.1 %, 3.0 %, 4.7 %, 7.8 %;
  - pressure 1.5 %, 1.7 %, 3.7 %, 8.0 %, 19 %.

  W1(16, 32) p99 is 0.0036 → 0.018 (neolithic) and 0.012 → 0.050 (pressure).
- **Episode statistics** (survival, dilution, resets) are the same at 16 and 32.

**Coalescence interaction:**
- Coalescence occurs only at a fusion, so a later difference carries coalescence error only
  through its origin.
- **Continuity preserves approximation error along with history.** Coalescence field
  error grows about 10–12× from `p = 0` to `p = 1` at both capacities: wider preserved
  differences make coalescence merge more distinct field positions, and `p = 1` then
  carries that error forward undiluted.
- **Where the 16 vs 32 differences sit:** all of the 16 vs 32 difference in the long-lived
  tail has a coalesced origin, but the tail holds only 2–6 % of the total difference.
- **Origins of long-lived differences:**
  - Neolithic: long-lived non-neutral unit-years have a coalesced origin about as often as
    all non-neutral ones (0.09–0.11 vs 0.10–0.11).
  - Pressure: they have one more often (0.34 vs 0.25). Pressure episodes start coalesced
    in 0.40–0.49 of cases.
- **Gate consequence:** before any mechanism reads persistent `field_claim`, the §M6
  mechanism-aware metric is needed. This applies especially under pressure.

### S6. `w = 1` propagation stress (socioeconomic only)

This is the same experiment at `w = field_output_claim_weight = 1`. Crop *attribution*
follows field control. Crop totals, food and all physical state are unchanged and
identical.

- **Field control is unaffected by `w`.** People-weighted D is the same as at `w = 0`
  (0.0139–0.0364 / 0.0306–0.0934), and the episode statistics match.
- **Persistent field control propagates into store control.** People-weighted store
  deviation for `p` = 0, 0.25, 0.5, 0.75, 1:
  - neolithic: 0.047, 0.055, 0.064, 0.074, 0.085 (×1.8);
  - pressure: 0.124, 0.139, 0.157, 0.177, 0.197 (×1.6).

  At `w = 0` it is 0.008 / 0.014 for every `p`, so `w = 1` alone multiplies store
  deviation by 6–9×, and continuity adds 1.6–1.8× on top.
- **Coalescence error grows further:** field error Σ at capacity 16 goes from 0.073 to
  0.48 (neolithic) and from 0.21 to 1.26 (pressure) as `p` goes from 0 to 1.
- **Resolution is weaker under `w = 1`:**
  - `Σ|D16 − D32|`/signal is 2.8e-4 → 1.4e-3 (neolithic) and 1.3e-3 → 3.6e-3 (pressure).
  - Unit-years where W1(16, 32) exceeds 10 % of the signal: 2.5 % → 9.5 % (neolithic) and
    2.8 % → 23.5 % (pressure).
- These stress findings are separate from the primary result. They show what *would*
  follow if persistent control were later allowed to steer attribution; nothing of the kind
  is active.

### S7. Recommendation

**Continuity deserves a later activation design, but not now and not as a bare `p`.**

- **What durability does.** Under the current rule (`p = 0`), fusion-created field-control
  differences halve after about ×2.3 of gross field expansion (about 11–12 years). That is
  already longer-lived than store differences (about 2 years, §M4), but dilution still
  erases them. Continuity (`p ≥ 0.75`) removes dilution as a sink. Differences then last
  until the physical asset is lost (migration, abandonment), and 37–43 % of them are
  undiminished after 50 years. This is the first candidate in MVP 3 that gives persistent
  within-unit differentiation without hardcoding property, inheritance or hierarchy.
- **What continuity does not do.** It preserves differences and never creates or amplifies
  them (S4, confirmed in every run). Continuity alone is preservation, not runaway
  inequality, and not hierarchy.
- **Why it is not ready:**
  1. **There is no causal reason for `p` today.** H2 collapses to H1 because clearing labor
     is a single unit-level pool. A defensible `p > 0` needs a named lower-level cause that
     makes existing controllers create or claim the new capacity: for example extension of
     an existing plot, household-differentiated clearing labor, or decision influence over
     clearing. Each of those is its own mechanism (§N3). `p` should then be derived from it,
     not set.
  2. **Continuity preserves numerical error along with history.** Coalescence field error
     grows about 10× from `p = 0` to `p = 1`, and the 16 vs 32 tail grows about 8×. Under
     pressure, 19 % (`w = 0`) to 24 % (`w = 1`) of signal-bearing unit-years have
     resolution uncertainty above 10 % of the effect. The §M6 mechanism-aware metric, which
     protects field positions, must precede any reader of persistent `field_claim`.
- **Next step:**
  - Keep `p = 0` (H1) and keep the gate closed.
  - Next review: choose whether to (a) design a cause for differentiated clearing or
    plot extension, which would make H2 differ from H1 and give `p` a basis, or (b) do the
    §M6 resolution metric first, since both continuity and any field-reading mechanism need
    it.
