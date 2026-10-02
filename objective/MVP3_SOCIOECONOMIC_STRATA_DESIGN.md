# MVP 3 — Socioeconomic Strata: Design

**Status:** Stage 0 design, 2026-10-02. Governs MVP 3 Stages 1–6 unless revised here.\
**Base:** MVP 2.1 frozen (`baselines/mvp2_1/`), post-consolidation architecture
(`PopulationStore`, `population/fields.py`).

A **stratum** is a component of an adaptive mixture approximation of a unit's
socioeconomic distribution: a population share with a small vector of socioeconomic
quantities and an opaque identity. It has no label. "Elite", "farmer", "class" and the like
are descriptions an analysis may derive from simulated data; they never enter causal state
(objective §2.7).

---

## 1. Decisions in one page

1. **Minimal `[U,S]` state (§A):** population share `p`, field-claim fraction `f`,
   store-claim fraction `c`. Nothing else until a stage needs it.
2. **Physical stock at `[U]`, claims at `[U,S]` as fractions of it.** Existing subsystems
   keep changing the unit's `fields_ha` and `stores_kcal`; proportional changes (spoilage,
   abandonment, trade from stores, shrinking fields) leave fractions unchanged
   automatically. Only explicit strata mechanisms move fractions.
3. **Demography stays `[U, sex, age]`.** A stratum's people are `p_s × N_u`, with the unit's
   age–sex composition (independence assumption, §C). No `[U,S,sex,age]`.
4. **Storage:** a `StrataTable` owned by `PopulationStore`, row-aligned with `UnitTable`
   slots, holding padded `[capacity, S_max]` columns plus a per-unit count (§D).
5. **Stages 1–4 are an accounting overlay:** strata state is read by no `[U]` mechanism, so
   MVP 2.1 raw and logical oracles stay identical even when strata differ (§E). The first
   intended semantic change comes when strata feed back (Stage 5 or 6) and gets a new,
   versioned baseline.
6. **Strata outputs go to a separate stream** (strata metrics table, strata event log). The
   frozen metrics row and event log are hashed in full by the oracle and golden fixtures.
7. **First causal mechanism (§F):** appropriable returns to durable field claims, with
   intra-unit pooling made explicit. The source of heterogeneity already exists in MVP 2.1:
   **fusion** of groups with different per-capita fields and stores. No noise is injected.
8. **Strata are point masses.** They carry no internal variance, so new strata come from
   mechanisms that treat part of a population differently (events), not from a
   multimodality test. Merging is criterion-driven (§G).

---

## A. Minimal stratum state vector

| Field | Meaning | Range | Constraint |
|---|---|---|---|
| `share` (`p`) | fraction of the unit's people in the stratum | (0, 1] | Σ_s p = 1 |
| `field_claim` (`f`) | fraction of the unit's cultivated hectares (`fields_ha`) the stratum controls | [0, 1] | Σ_s f = 1 |
| `store_claim` (`c`) | fraction of the unit's food stores (`stores_kcal`) the stratum holds | [0, 1] | Σ_s c = 1 |
| `stratum_id` | opaque identity for persistence and mobility metrics | int64 | never read causally |

Derived, not stored: people `p·N`, hectares `f·F`, stored kcal `c·K`, per-capita claims
`f/p` and `c/p` (1 means an average holding).

**Why each varies within a unit.** `p` defines the mixture. `f` and `c` are the only existing
MVP 2.1 stocks that are durable, appropriable and transferable: they persist across years,
can be inherited by a lineage, and arrive unequally when groups fuse. Body reserves, food
ratio, knowledge and technologies do not satisfy that today (§B).

**Readers and writers.**

| | Stage 1 | Stage 2 | Stage 3 (first mechanism) | Later |
|---|---|---|---|---|
| `p` | lifecycle only | lifecycle | ledger weights (labor, need) | transfers between strata (Stage 4) |
| `f` | — | lifecycle, field planning (new hectares) | crop attribution | influence over field decisions (Stage 5) |
| `c` | — | lifecycle | store ledger | food access (Stage 6A) |

**Conservation and bounds.** `p`, `f`, `c` are each a partition of unity per unit
(tolerance `1e-12` after renormalization, which only structural operations perform).
Physical totals stay `[U]`, so claims reconcile with physical stock by construction.

**Zero-stock convention.** If a unit's physical total is 0 (no fields, empty stores), its
fractions are meaningless. They are then defined to equal `p`, so the next stock to appear
is attributed in proportion to people (labor) unless a mechanism says otherwise.

**Split (unit fission).** The daughter copies the parent's strata (same `p`, `f`, `c`).
Extensive physical totals are already divided in proportion to people, so per-capita claims
are identical on both sides. Neutral.

**Merge (unit fusion or aggregation).** Concatenate the strata of both units, reweighted
by their physical totals: `p ← p·N_unit/N_total`, `f ← f·F_unit/F_total`,
`c ← c·K_unit/K_total` (zero totals use the zero-stock convention). Then apply the
resolution rule (§G). Strata are not mixed across units at merge, because the arriving
group *is* the heterogeneity.

**Initialization.** A founded unit has one stratum with `p = f = c = 1`.

Deliberately **not** in the minimal vector:

- **labor allocation:** every stratum supplies labor in proportion to `p` (shared age
  structure). Nothing in MVP 2.1 gives subgroups a reason to allocate labor differently.
- **decision influence:** reserved for Stage 5 and defined only relative to a named
  collective choice.
- **consumption / food access:** pooled today; this is the Stage 6A candidate.
- **wealth** as a separate scalar: holdings are `f` and `c`, and there is no other good.

## B. State that stays `[U]`

From `population/fields.py`:

- **Location, identity, lineage:** `cell`, `species_id`, `id`, `parent_id`, `founded_year`.
- **Information:** `beliefs`, `food_log_prior`, `food_log_signal_var`, `report_cells`,
  `recent_residence`, `familiarity`. These are shared perception and memory.
- **Culture and technique:** `knowledge`, `technologies`. These are shared affordances;
  specialist knowledge is not modeled.
- **Physical stocks:** `fields_ha`, `stores_kcal`. Claims on them are `[U,S]`.
- **Demography:** `females`, `males`. This is the shared age–sex structure (§C).
- **Pooled flows:** `harvest_kcal`, `farm_harvest_kcal`, `forage_harvest_kcal`,
  `farm_hours`, `forage_hours`, `clearing_hours`, `labor_debt_hours`, `stored_kcal`,
  `energy_debt_kcal`. Labor and food are pooled; Stage 3 *attributes* them, it does not
  stratify them.
- **Nutrition outcome:** `food_ratio`, `energy_deficit`, `reserve_kcal_per_capita`. These
  stay `[U]` while consumption is pooled. They are the first candidates to become `[U,S]`
  if Stage 6A makes food access depend on claims.
- **Decisions and network:** `move_hazard`, `residence_years`, `groups`, `harvest_history`,
  `trade_ties`. Migration stays a whole-unit decision until a selective-migration stage.

Rule: a field moves to `[U,S]` only when a mechanism needs different values for different
parts of a unit to produce different outcomes.

## C. Population accounting

- **Representation:** the joint distribution is `P(age, sex, stratum) = P(age, sex) · p_s`.
  Cohorts stay `[U, sex, age]` and integer, with exact binomial demography unchanged.
- **Stratum population** is `p_s · N_u`, a real number. Σ_s p_s · N_u = N_u exactly up to
  float rounding of `Σ p = 1`. Integer persons per stratum are not tracked.
- **Births and deaths do not change `p`.** Under shared composition and shared vital rates,
  every stratum grows at the unit's rate. Shares change only through explicit structural
  operations (fusion, Stage 4 transfers).
- **Inheritance is implicit:** a stratum behaves like a lineage, and its claims pass to its
  descendants because the stratum persists.
- **Known limitation:** there is no correlation between age and socioeconomic position, and
  no differential fertility or mortality. If a later stage gives strata different food
  access or workload, choose deliberately between:
  - (a) per-stratum vital-rate multipliers acting on `p` (cheap; keeps the shared age
    structure);
  - (b) `[U,S,sex,age]` cohorts (exact; about 1.5 kB × S per unit, §J).

  Do not decide this before a mechanism needs it.

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
  Row `r` is the unit in slot `r`, so there is no unit↔stratum map to maintain. `ensure`,
  `reset`, `copy_row` and `load`/`unload` mirror `UnitTable`, and `PopulationStore`
  allocates both together.
- **Active strata** of slot `r` are columns `0 … n_strata[r]−1`, kept compacted; padding is
  zero. Iteration is vectorized over `(slots, S_max)` with a mask.
- **`S_max`** is a *resolution limit* (configuration, default 8), not a claim about how many
  classes a society has. Exceeding it triggers the resolution merge (§G).
- **IDs:** a per-store `int64` counter in `StrataTable`. It never uses `IdAllocator`, so
  unit IDs (`u…`) are unchanged. IDs are only for persistence and mobility metrics.
- **Object (reference) engine:** `PopulationUnit` gains one field `strata` (a small
  `StrataBlock` of arrays) declared in `fields.py` with a new `Storage.STRATA`. While
  registered it is a view of the slot row; detached, it is a plain block. The field-schema
  completeness test then forces its merge/split rules to be written down.
- **Lifecycle:** `lifecycle.split_unit` copies the parent's strata row into the daughter's;
  `merge_units` concatenates; `discard`/`reset` zero the row (no stale strata). Deepcopy
  follows the existing `UnitRegistry.__deepcopy__` path.
- **Memory and portability:** small contiguous `[U, S_max]` arrays, SIMD- and GPU-friendly,
  with no Python object per stratum. Rejected alternatives:
  - a flat stratum pool with a CSR index: needs re-indexing after every structural event;
  - per-stratum objects: hot-loop cost;
  - `[U,S,S]` relationships: no mechanism needs them yet.

## E. Neutral representation and the MVP 3 exactness contract

- **Homogeneous** means every unit has exactly one stratum with `p = f = c = 1`. Stage 1 is
  only this.
- **Neutrality test (foundational):** with strata enabled, the MVP 2.1 raw and logical
  oracles and the golden fixtures are identical. This holds as long as:
  - (i) no `[U]` mechanism reads strata;
  - (ii) strata consume no random numbers;
  - (iii) strata do not use the unit `IdAllocator`;
  - (iv) strata outputs stay out of `SimulationResult.metrics` and `events`.
- **Stronger property through Stage 4:** because of (i), the oracles stay identical even
  when strata are heterogeneous (fusion concatenation, Stage 3 ledger). Only the strata
  outputs change.
- **First semantic change:** the first stage whose strata state feeds back into `[U]`
  dynamics (Stage 5 or 6A) records a new versioned baseline (`baselines/mvp3_x/`, new
  oracles). The MVP 2.1 artifacts stay as historical evidence.
- **Reordering and ID neutrality** hold exactly in real arithmetic. In floats, sums over
  strata depend on storage order. Contract: permuting or renumbering strata changes
  results at most at float-rounding level (tested with tolerance). The canonical storage
  order (creation order, compacted) is deterministic, so runs replay exactly.

## F. First causal mechanism (recommended for Stage 3)

**Appropriable returns to durable field claims, with intra-unit pooling made explicit.**

MVP 2.1 already pools within a unit: everyone works, eats and stores together. Stage 3 does
not change any `[U]` flow. It *attributes* the unit's realized store change to strata each
year, after energetics:

```text
ΔK_s = p_s · ΔK  +  α · Y_farm · (f_s − p_s)          (Σ_s of the α term = 0)
c'_s ∝ max(c_s · K_before + ΔK_s, 0)                    claims floored at zero
pooling transfer = Σ_s max(−(c_s·K_before + ΔK_s), 0)   covered pro rata by the others
```

- `Y_farm` is this year's crop. `α ∈ [0, 1]` (proposed name `field_claim_return_share`) is
  the share of crop output that accrues to claim holders rather than to labor, which is
  supplied in proportion to `p`.
- **Neutral limits:** `α = 0`, or `f = p` (homogeneous), gives `c → p`, the MVP 2.1
  accounting.
- **Heterogeneity source:** fusion concatenation. A resident group with established fields
  absorbing a group without them gives `f_s ≠ p_s` (a first-comer advantage). No random
  differentiation.
- **New hectares** from field planning are attributed in proportion to `p` (labor clears
  land), so expansion dilutes concentration. Abandonment by migration empties `fields_ha`
  (zero-stock convention); spoilage, trade and carrying losses act proportionally.

*Why this mechanism:* it uses the only durable, appropriable stocks MVP 2.1 already
simulates (objective §7: surplus alone must not imply hierarchy; appropriability must be
explicit). It has conserved flows, one parameter with a neutral limit, and leaves `[U]`
dynamics exactly unchanged.

Rejected for now:

- **unequal labor allocation:** no reason for it exists without specialization returns;
- **redistribution/extraction:** presupposes power, which is Stage 5;
- **influence:** Stage 5.

*Expected behavior, to test rather than assume:*

- Differentiation is persistent but bounded: claims spoil, deficits are pooled and new land
  is attributed by labor.
- It compounds only once claims feed back into decisions or access (Stage 5/6).
- If differentiation does not appear, diagnose the mechanism; do not add noise.

## G. Stratum dynamics (designed now, implemented in later stages)

| Event | Rule |
|---|---|
| Creation | Only by mechanisms that treat part of a population differently: fusion arrival (concatenation), and later explicit transfers (e.g. inheritance partition). Never by schedule or quota. |
| Divergence | Only through explicit flows (§F). Strata have no internal variance, so there is no multimodality test. |
| Population transfer between strata | Stage 4, only via a named mechanism that says what claims move with people. |
| Merge (resolution) | Merge two strata when their per-capita claim vectors `(f/p, c/p)` differ by less than a tolerance; shares and fractions add (exactly conservative). The approximation error is recorded, as `knowledge_distance` is for coarsening. When `n > S_max`, merge the closest pair; break ties by state values, never by ID or position. |
| Extinction | A stratum whose share reaches 0 is removed and the row compacted. Unit extinction removes the row. |
| Unit fission | The daughter copies the parent's strata (§A). Fission along strata lines (who leaves) is a later selective-fission mechanism. |
| Unit fusion / aggregation | Concatenate and reweight (§A), then apply the resolution rule. |
| Migration | Whole unit. Field claims empty with the fields; store claims are unchanged by proportional abandonment. |

Identical-split and identical-merge neutrality follow from adding fractions. They are
Stage 4 metamorphic tests, but the resolution merge is needed as soon as fusion
concatenates (Stage 2), so its mechanics land there and its criterion is tuned in Stage 4.

## H. Derived metrics (separate strata stream; analysis only)

- **Inequality:** people-weighted Gini and Theil T of per-capita field and store claims
  across all strata. Theil decomposes into within-unit and between-unit parts.
- **Concentration:** share of claims held by the smallest set of strata containing ≤ 10%
  of people (top-decile control); claim held per person in it.
- **Resolution:** distribution of `n_strata`; merges and their recorded approximation error.
- **Pooling:** annual intra-unit pooling transfer (kcal), the MVP 2.1 redistribution made
  visible; land-claim returns `α·Y_farm·Σ|f−p|/2`.
- **Persistence:** year-to-year rank correlation of per-capita claims by `stratum_id`.
- **Mobility** (Stage 4+): population flows between strata.
- **Later:** influence concentration and covariance of influence with claims (Stage 5);
  labor specialization entropy if labor allocation is ever stratified.

Labels such as "elite-like concentration" are computed from these in analysis tooling,
never fed back.

## I. Model provenance (new `ModelRule`s)

| Rule | Stage | Explicit assumption |
|---|---|---|
| `stratum_composition` | 1 | Age–sex structure is shared by all strata (independence); `p` is unchanged by births and deaths. |
| `strata_merge_on_fusion` | 2 | An arriving group remains a distinct component; claims are concatenated, not averaged. |
| `claim_zero_stock` | 2 | Claims on an empty stock default to population shares. |
| `new_field_claims` | 2–3 | New cleared land belongs to strata in proportion to the labor supplied (∝ `p`). |
| `field_claim_returns` | 3 | A share `α` of crop output accrues to field-claim holders (appropriability). |
| `intra_unit_pooling` | 3 | Consumption is pooled; deficits beyond a stratum's own store claim are covered pro rata by others (a recorded transfer). |
| `strata_resolution_merge` | 2/4 | Merging near-identical strata is a numerical approximation with recorded error. |

Each of these is heuristic, needs an empirical or theoretical source if one exists, and
must be ablatable through a switch or a neutral parameter value.

## J. Performance

Per unit, persistent:

| Representation | Bytes per unit (S_max = 8) | 50k units |
|---|---|---|
| `StrataTable` (3 × f64 + i64, padded) + `n_strata` | ≈ 260 B | ≈ 13 MB |
| Existing cohorts alone (`2 × 91 × i64`) | ≈ 1.5 kB | ≈ 73 MB |
| **Rejected:** `[U,S,sex,age]` cohorts | ≈ 11.6 kB | ≈ 580 MB, plus demography temporaries ≈ 75 kB/unit/tick (≈ 3.8 GB) |
| **Rejected (scientifically, not by memory):** dense `[U,S,S]` relations | ≈ 0.5 kB | ≈ 26 MB |

The Stage 3 ledger is O(U·S_max) vectorized work per tick, small next to demography or
migration. Python-object-per-stratum loops are ruled out for hot paths.

## K. Open questions for review (affect architecture)

1. **α and its canonical default.** With `α = 0` the canonical runs show only fusion-born
   store differences that decay and field claims that persist but are inert. With `α > 0`
   claim holders accrue part of crop output produced by pooled labor, which is implicit
   extraction. This needs your decision, and α needs a provenance note.
2. **Strata outputs in a separate stream.** This is required for frozen exactness (§E iv).
   Confirm that a separate strata metrics table and event log is acceptable.
3. **Event-driven creation.** Point-mass strata cannot detect internal multimodality.
   Confirm that creation comes from mechanisms rather than a statistical split test.
   The alternative, tracking within-stratum variance, would add state per stratum.
4. **Resolution merge in Stage 2,** not only Stage 4, because fusion concatenates from
   Stage 2 on. Stage 4 keeps the criterion and the metamorphic tests.
5. **Float-level reordering neutrality** (§E) as the contract, rather than bit-exactness
   under permutation.
6. **Independence of age and position** (§C) as the MVP 3 representation, until a stage
   demonstrates a need for differential demography.
