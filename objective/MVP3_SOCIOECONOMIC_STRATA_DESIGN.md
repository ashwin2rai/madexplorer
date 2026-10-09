# MVP 3 — Socioeconomic Strata: Design

**Status:** current contract plus findings register (rewritten 2026-10-07; the full
stage-by-stage text, including the Stage 0 plan §A–§K, is in git at `aae0974`). Latest
stage: 5A (§T). Strata are a passive accounting overlay; the physical-feedback gate (§N7)
is closed.\
**Base:** MVP 2.1 frozen (`baselines/mvp2_1/`), post-consolidation architecture
(`PopulationStore`, `population/fields.py`).

A **stratum** is one component of an adaptive mixture approximation of a unit's
socioeconomic distribution. It has a population weight, a small vector of socioeconomic
quantities (control shares over the unit's durable physical stocks) and an opaque identity,
and no label. "Elite", "farmer", "class" and similar words are descriptions an analysis may
derive from simulated data; they never enter causal state (objective §2.7).

---

## 1. Current contract (as built)

### 1.1 State vector

| `[U,S]` field | Definition | Range | Constraint |
|---|---|---|---|
| `share` | represented population mass of the stratum / unit population | (0, 1] | Σ_s share = 1; never 0 |
| `field_claim` | share of effective control over the unit's cultivated land (`fields_ha`) | [0, 1] | Σ_s = 1 |
| `store_claim` | share of continuing effective control over the unit's stored food (`stores_kcal`) | [0, 1] | Σ_s = 1 |
| `stratum_id` | opaque identity for sidecar persistence and mobility tracking | int64 | never read causally |

- **`share` is a mixture weight,** not a socioeconomic characteristic.
- **Claims are relative control shares over stocks that stay `[U]`.** They do not
  duplicate the stock: hectares controlled are `field_claim × fields_ha`. A claim is not
  ownership, title, sale, inheritance, exclusion, rent, authority or coercion.
- **Positions are intensive:** `field_claim / share` and `store_claim / share`. 1 is a
  population-proportional position. Positions, not raw fractions, are the basis of
  similarity and coalescence distance.
- **Neutral allocation:** `field_claim = store_claim = share`. Homogeneous means one stratum
  with `share = field_claim = store_claim = 1`.
- **Why only these two claims:** fields and stores are the only MVP 2.1 stocks that are
  durable, appropriable and transferable. Labor allocation, decision influence, consumption
  and a separate wealth scalar are deliberately absent.

**Stays `[U]`** (`population/fields.py`): location, identity and lineage; information
(`beliefs`, `food_log_*`, `report_cells`, `recent_residence`, `familiarity`); culture and
technique (`knowledge`, `technologies`); the physical stocks `fields_ha`, `stores_kcal`;
demography (`females`, `males`); pooled flows (harvests, hours, `labor_debt_hours`,
`stored_kcal`, `energy_debt_kcal`), which strata *attribute* but do not stratify; nutrition
(`food_ratio`, `energy_deficit`, `reserve_kcal_per_capita`); decisions and network
(migration is whole-unit). Rule: a field becomes `[U,S]` only when a mechanism needs
different values for different parts of a unit to produce different outcomes.

### 1.2 Storage

```text
PopulationStore
    units       UnitRegistry       identities, processing order
    table       UnitTable          [U] hot state            (slot rows)
    strata      StrataTable        [U,S] state              (same slot rows)
    beliefs     BeliefStore
```

- **`StrataTable`** (`population/strata.py`), owned by `PopulationStore`: padded
  `[rows, max_strata]` float64 `share`, `field_claim`, `store_claim`, int64 `stratum_id`,
  plus int8 `n_strata` per row: **32·S + 1 B/row** (129 / 257 / 513 / 1025 B at
  S = 4 / 8 / 16 / 32). Row `r` belongs to the unit in slot `r`; active strata are
  columns `0 … n_strata−1`, compacted, zero-padded. The object engine uses a detached
  `StrataBlock` (a view of the row while registered).
- **Capacity:** `strata.max_strata` in `StrataConfig` (`config/schema.py`), **default 16**
  (`DEFAULT_MAX_STRATA`), validated 1..127. It is a numerical resolution limit, not a
  number of classes. It is in `config_hash` (provenance) but not in `static_key`, so runs
  differing only in capacity share one `StaticContext`. 8 is historical / explicit
  lower resolution; 32 is a sensitivity comparison, not ground truth.
- **Schema boundary:** stratum columns have their own declared schema in the strata module;
  they are not `UnitField`s. **IDs** come from a per-store counter, never the unit
  `IdAllocator`.
- **Memory:** 25.7 MB at 50k units and width 16 (≈ 1 % of a ≈ 2.5 GB run). Hot paths
  slice to the largest active count; the exact-duplicate check runs in chunks of 1024
  rows (`[1024, k, k]` temporaries). Python-object-per-stratum loops are ruled out.
- **Rejected:** a flat stratum pool with a CSR index, per-stratum objects, `[U,S,S]`
  relations, `[U,S,sex,age]` cohorts (≈ 11.6 kB/unit, ≈ 580 MB at 50k).

### 1.3 Population accounting

- **Canonical:** `P(age, sex, stratum) = P(age, sex) · share`. Cohorts stay
  `[U, sex, age]`, integer, with exact binomial demography. There is no `[U,S,sex,age]`;
  the model does not invent correlations between position and age.
- Stratum population `share × N_u` is real-valued. **Births and deaths do not change
  shares;** shares change only at fusion and capacity coalescence. Inheritance is implicit:
  a stratum persists like a lineage.
- **Labor:** one unit-level pool from the shared age structure, so each stratum's
  contribution to every activity is exactly its share. This is documented, not represented
  (§N, §P).

### 1.4 Lifecycle

| Event | Rule (code) |
|---|---|
| Initialization | one stratum, `share = field_claim = store_claim = 1` |
| Unit fission | daughter copies the parent's strata as new components (fresh ids); stocks split ∝ people, so positions are unchanged on both sides (`lifecycle.split_unit`) |
| Unit fusion / aggregation | `fuse_strata`: each predecessor's absolute holdings `claim × stock` are kept and renormalized by the fused total, `share' = share × N_unit / N_total`; strata are concatenated, not averaged. **The only source of heterogeneity.** Then normalization |
| Migration | whole unit; `Relocation.apply` sets `fields_ha = 0`, so field claims reset to share; store abandonment above the carry limit is proportional (store claims unchanged) |
| Zero-stock reset | stock = 0 ⇒ `claim = share` (`claim_zero_stock`), applied after every subsystem's apply (`PopulationStore.settle_empty_claims`). No NaNs; the representation never invents inequality |
| Exact compaction | components at bit-identical positions (every claim/share) are one stratum: summed share and claims, fresh id; lossless, no tolerance; runs before coalescence and repeats until no exact duplicate remains (`normalize_strata`) |
| Capacity coalescence | if `n_strata > max_strata`, greedily merge the pair minimizing `s_i s_j/(s_i+s_j)·((Δp_field)² + (Δp_store)²)` (equal Euclidean weighting, positions `claim/share`); shares and claims add (exactly conservative); components ordered canonically by state, ties keep the first pair, never by id or storage position. Numerical resolution management, not a sociological event; per-merge `field_error`, `store_error`, combined error go to the sidecar. `coalesce_to_capacity_reference` is the scalar differential oracle |
| Stratum extinction | a stratum whose share would reach 0 is removed; unit extinction resets the row |

**Creation is mechanism-driven.** A new stratum appears only when a causal mechanism treats
part of a represented population differently enough that a distinct state must be
represented. No statistical split test, no random differentiation, inequality targets,
hidden traits or class thresholds. A population homogeneous in every modeled causal
variable may stay homogeneous indefinitely.

### 1.5 Accounting equations (Stage 3B/3C, `population/strata_accounting.py`)

Physical code only records: `FieldAccounts` (`F0`, `F1`) from `FieldPlans.apply` and
`FoodAccounts` (`K0` opening after trade, `A` stored, `X` withdrawn, `K1` closing) from
`EnergyUpdates.apply`, held transiently on `StepContext`. `account_strata` runs after every
subsystem: accounting, then exact compaction, then `settle_empty_claims`. Nothing else reads
the accounts.

**Field claims** (`field_claim_accretion`), per unit with `ΔF = F1 − F0`:

```text
F1 == 0:   field_claim = share                              (claim_zero_stock)
F1 <  F0:  field_claim unchanged                            (proportional loss)
F1 >  F0:  a_i = field_claim_i·F0 + share_i·ΔF;  field_claim_i = a_i / Σa   (new land ∝ share)
```

New land ∝ share (labor clears land, labor ∝ share) is the least assumptive rule, not a
claim that tenure was egalitarian. Normalizing by Σa keeps a single stratum at exactly 1.

**Crop-output attribution** (`crop_output_attribution`, w = `strata.field_output_claim_weight`,
default 0.0, `0 ≤ w ≤ 1`, read only by `account_strata`, in `config_hash` not `static_key`):

```text
crop_output_share_i = (1 − w)·share_i + w·field_claim_i
```

w is the fraction of crop-output *attribution* (before pooling) that follows field control
rather than the labor baseline. It is not an extraction rate; consumption stays pooled.

**Pre-pool attribution and pooling transfers** (`food_pooling_transfer`,
`pooled_leftover_shares`); forage, trade received, reserves and store withdrawals use share
or store_claim, never field claims:

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
pool_transfer_i = store_transfer_i + harvest_transfer_i              Σ_i = 0
```

Positive means the stratum receives more from pooling than it contributes; it is not
labeled tax, rent or tribute. Negative pre-pool leftovers are covered pro rata by the
others (`pooled_leftover_shares`, a heuristic convention). Post-pool allocation stays MVP 2.1
(need and reserve top-up ∝ share).

**Store claims** (`store_claim_accretion`): existing stores lose `S_out`, `X`, spoilage and
abandonment proportionally; new stores appear only in fed years:

```text
A_i = A · share_i + (A / L) · (harvest_transfer_i + d_i)      (= A · allocated_i / L)
store_claim_i' = (store_claim_i · K0 + max(A_i, 0)) / Σ;      K1 = 0 → share
```

At w = 0 new stores ∝ share, so fusion-born store differences decay as stores turn over, and
the only nonzero pooling term is `X·(share − store_claim)`. Discarded leftover adds no
transfer. When `d ≡ 0` (w = 0, Y = 0 or `field_claim = share`) the Stage 3B values are
reproduced bit for bit.

**Numerical requirements:** every update is a convex combination or a ratio normalized by
its own sum (a single stratum stays exactly 1; column totals within 1e-12); deviations in
difference form (`claim − share`); no thresholds or branches on positions (`max(·, 0)`
acts at kcal scale); updates Lipschitz in positions; sums over strata sequential (`cumsum`)
so padding cannot change rounding; single-stratum units skipped. Zero-sum contract:
`|Σ_i pool_transfer_i| ≤ 2e-12 · X`.

### 1.6 Neutrality and exactness

- **Oracles:** with strata enabled, the MVP 2.1 raw and logical oracles and golden fixtures
  are identical, for heterogeneous strata too, as long as (i) no `[U]` mechanism reads
  strata state, (ii) strata consume no random numbers, (iii) strata do not use the unit
  `IdAllocator`, (iv) strata outputs go only to the sidecar.
- **Transformations:** renumbering `stratum_id`s is **bit-exact** (ids never enter
  equations, RNG, tie-breaking or processing order); reordering strata within a unit is
  neutral within strict floating-point tolerance; conserved totals (Σ shares, Σ claims,
  physical totals) use the tightest practical invariant. Future stochastic mechanisms must
  not make outcomes depend on ids or storage order.
- **Baselines:** targeted, versioned sidecar fixtures, not scientific baselines:
  `stage3b_seed11_30u_40y.json` (authoritative at w = 0) and
  `stage3c_w0.5_seed11_30u_40y.json` (w = 0.5 sensitivity), both pinned to
  `max_strata = 8`. Default-16 coverage is ordinary tests. A new versioned baseline
  (`baselines/mvp3_x/`) is recorded only when socioeconomic state intentionally affects unit
  outcomes; MVP 2.1 artifacts remain historical evidence.

### 1.7 Sidecar stream

Written only to outputs, never read by the simulation; the frozen metrics rows and event
log are unchanged.

- `strata_rows` (per `year, unit_id, stratum_id`): stratum state.
- `strata_events.jsonl`: structural operations (fusion creation, fission copies, exact
  compactions, `capacity_coalescence` with `field_error`, `store_error`, `combined_error`,
  `cost`, removals).
- `strata_flows.csv`: one row per stratum for unit-years with a nonzero pooling transfer:
  `share`, `store_claim` as used, `withdrawn_kcal`, `pool_transfer_kcal`,
  `pool_transfer_volume_kcal` (= Σ|transfer|/2), then `crop_kcal`, `field_claim`,
  `crop_attribution_correction_kcal` (d_i), `harvest_pool_transfer_kcal`,
  `store_pool_transfer_kcal`.

Derived measures (analysis only): people-weighted Gini / Theil of positions (within- and
between-unit), concentration, `n_strata` distribution and coalescence error, pooling
volume, year-to-year persistence by `stratum_id`.

### 1.8 Model rules

Verified against `grep -rn 'name="' src/madexplorer/population/strata*.py`.

| Rule | Module | Class / explicit assumption |
|---|---|---|
| `stratum_composition` | `strata.py` | all strata share the unit's age–sex structure; shares unchanged by births and deaths |
| `strata_fusion_inheritance` | `strata.py` | fused groups keep prior absolute positions as distinct components |
| `claim_zero_stock` | `strata.py` | claims on an empty stock equal population shares |
| `strata_exact_compaction` | `strata.py` | exact duplicate positions are one component (lossless) |
| `strata_capacity_coalescence` | `strata.py` | above `max_strata`, closest components coalesce (numerical approximation, recorded error) |
| `field_claim_accretion` | `strata_accounting.py` | neutral convention: new land ∝ share; loss proportional |
| `store_claim_accretion` (1.1) | `strata_accounting.py` | neutral convention: proportional depletion; new stores follow allocated leftover |
| `food_pooling_transfer` (1.1) | `strata_accounting.py` | accounting identity; harvest and store components |
| `crop_output_attribution` (1.0) | `strata_accounting.py` | heuristic modeling hypothesis (w); neutral at 0; no empirical value |
| `pooled_leftover_shares` (1.0) | `strata_accounting.py` | heuristic accounting convention (pro rata deficit coverage) |

Each rule is heuristic unless a source is cited, and ablatable through its neutral value.
The counterfactual modules `population/strata_access.py` (§Q), `population/store_release.py`
(§R) and `population/field_control.py` (§S) are **NOT ACTIVE**: no simulator path calls
them, no rule is registered, no scenario setting exists.

### 1.9 Locked decisions

- **No canonical nonzero w.** w = 0 is the neutral legacy limit, not a claim about
  historical societies; nonzero values are sensitivity hypotheses, never tuned. w is an
  abstraction standing in for missing labor and property mechanisms (§M).
- No random differentiation; creation only by mechanisms; fusion is currently the only
  source of heterogeneity (§M).
- Capacity coalescence is numerical resolution, not adaptive merging; adaptive merging is
  deferred (§M2).
- Capacity is not a substitute for a resolution policy (§N).
- **Resolution gate (§N7):** no physical mechanism may read stratum socioeconomic state
  until the resolution policy has been shown stable enough for the information that
  mechanism uses. Accounting-only flows may proceed. **Status: closed.** No mechanism is
  approved; any reader of persistent `field_claim` first needs the §M6 mechanism-aware
  metric (§Q, §S).

---

## 2. Findings register

Probes: current ones live in `scripts/probes/` (shared helpers `_common.py`). Retired
probes are cited as "git `aae0974`: scripts/probes/<name>.py". Reference scenarios
throughout: neolithic 600 y and pressure + cultivation 400 y, seeds 0–3, unless stated.

### §L. Stage 3A/3B/3C — economic accounting

- **Audit (3A).** Food flows audited from code: foraging adjusts to the crop
  (`need·(1 + surplus) − Y`); trade donors give from harvest, then stores; fed units eat
  from harvest and store only the leftover (`K1 = (K0 + A)·r`); short units eat all
  harvest, then stores `X = min(need − H, K0)`, then body reserves (`K1 = (K0 − X)·r`;
  never both A > 0 and X > 0). `fields_ha` changes only in `FieldPlans.apply`, migration,
  fission and fusion; new land is cleared in year t and first harvested in t + 1. Every
  audit check passed (neolithic seed 0 × 400 y, pressure seed 1 × 300 y). Evidence: git
  `aae0974`: scripts/probes/food_flow_audit.py.
- **Decided.** Stage 3B built the neutral accounting (land and store accretion, gross-flow
  instrumentation, pooling transfers) with w present but 0; Stage 3C activated w only as
  sensitivity cases (0, 0.25, 0.5, 1). The name `field_output_claim_weight` replaced the
  Stage 0 `field_entitlement_weight`, which suggested an institution the model does not
  contain. Stage 3B changed one Stage 2 passive convention: positive store growth no longer
  carries fractions forward (new stores ∝ allocated leftover), which changes strata state
  even at w = 0 but no unit state. Evidence for the w sensitivity: git `aae0974`:
  scripts/probes/crop_attribution_sensitivity.py.

#### L15. Stage 3C as-built notes

- w lives in `StrataConfig`, not `agriculture` (which feeds `static_key`): w changes no
  world, ecology or agronomy.
- In the current energetics A is either L (storage capability) or 0; partial storage is
  handled by the same formula and tested directly.
- **Grouping of strata.** Field claims are identical across w *as accounting rules*, but
  compaction and coalescence act on joint `(field, store)` positions, so stratum counts
  differ (neolithic seed 0, 400 y: 286 compactions at w = 0 vs 253–260 at w > 0;
  coalescences 12 vs 14–16). The claim "field claims identical across w" holds for
  coalescence-free runs only; §M6 corrects it for the represented distribution.

### §M. Stage 3D — scientific and representation review

Evidence: git `aae0974`: scripts/probes/strata_review.py (modes `representation`,
`nonlinear`, `persistence`, `sources`, `capacity`, `fieldgap`), at capacity 8,
w ∈ {0, 0.25, 0.5, 1}.

- **Load.** Coalescence is routine in farming runs: 9.1–9.9 % (neolithic) and 32–33 %
  (pressure + cultivation) of unit-years at capacity 8; 82–93 % of merges join field
  positions > 1e-9 apart. Most extra strata are small modeled differences (1e-3 to 0.1),
  not floating-point dust.
- **Nonlinear pooling response to w** is the intended mathematics: short years are linear
  in w; fed years have hinges at `w*_i = (L / gY) · s_i / (s_i − f_i)` (seed 0 median
  w* = 0.76). The closed form reproduces sidecar volumes within 4e-16; continuity holds at
  crossings.
- **Persistence (M4).** Field deviation is multiplied by F0/F1 each year (median halving
  11 y in real runs); store deviation at w = 0 by K0/(K0 + A) (median halving 2 y; 4 y at
  w = 1). At w > 0 stores track fields. Time-mean people-weighted |field position − 1|:
  0.011 (neolithic), 0.044 (pressure), the same at every w.
- **Sources (M5).** Fusion is the only operation that raises a unit's stratum count. With
  fusion disabled at w = 1 no unit ever has more than one stratum. Strata mostly hold
  memory of predecessor groups; w adds no source.

#### M2. Adaptive merging: DEFERRED

Greedy coalescence already merges dust pairs first, so pre-merging below capacity would not
reduce information loss, and padding gives no memory benefit. The binding constraint is
resolution policy, not adaptive merging. Revisit only when a mechanism defines which
differences matter behaviorally.

#### M6. Capacity coalescence and w; recommendation C

- With equal Euclidean weighting, store dispersion (which w inflates) decides which field
  differences are kept: where w redirects a coalescence (12 % of multi-strata unit-years
  neolithic, 42 % pressure) the field distribution moves by a median 1-D Wasserstein
  distance of 0.006 (11 % of the unit's own field deviation, 42 % at p99). Coalescence
  field error Σ (neolithic, w = 0 → 1): 0.19 → 0.42; store 0.03 → 1.19. No invariant is
  violated.
- **Recommendation C:** replace the metric with a mechanism-aware, error-aware resolution
  policy once downstream mechanisms define which information matters. No dimension weights
  now. Before any physical mechanism reads `field_claim` or `store_claim`, re-evaluate the
  metric and test capacity sensitivity.
- **w classification (M7):** a sensitivity parameter with no causal content under
  homogeneous labor; default stays 0.0.

### §N. Stage 4A — stratum labor and resolution design

- **Labor as built:** capacity C from `[U, sex, age]` cohorts; one pool drawn in a fixed
  order (clearing debt, cultivation capped at 0.9·(C − D), foraging the remainder); no
  energetic cost of work; no sexual division of labor or skill. Contribution and burden
  per stratum are implicitly ∝ share.
- **No causal reason for labor to differ by stratum (N3).** Field control, store control,
  fusion origin and age/sex all fail: any differentiated rule would bring in an unmodeled
  institution (household tenure without pooling, authority, private access). A scientific
  finding, not a gap to fill with an assumption.
- **If labor is needed later (N4–N6):** per-activity hour contributions as a transient flow,
  no occupations or rank; crop attribution generalizes to
  `(1 − w)·cultivation_labor_share + w·field_claim`; new-land control could follow clearing
  contribution, but if clearing labor followed control, dilution would stop and fusion
  memory would freeze (persistence by assumption). Adopt only with a cause.
- **Capacity sensitivity (N8, capacity 4/8/16/32):** coalescences *increase* with capacity
  because demand is open-ended; field error falls about 6× per doubling; aggregate
  observables are flat. Capacity cannot replace a resolution policy. Short-lived
  differentiation is not itself a defect (N10); persistence should come only with the
  mechanisms that cause it.
- Evidence: git `aae0974`: scripts/probes/strata_capacity.py.

#### N7. Resolution gate (locked invariant)

**No physical mechanism may read stratum socioeconomic state until the resolution policy
has been shown stable enough for the information that mechanism uses.** Accounting-only
flows (sidecar, attribution) may proceed under the current policy; production, food access,
migration and demography may not. Status: closed (§1.9).

### §O. Stage 4B — resolution hardening

- Built: `strata.max_strata` as a run setting owned by `PopulationStore`; chunked exact
  duplicate check (peak temporary for `check` on 50k rows: 21 MB → 0.7 MB at width 8);
  vectorized capacity coalescence, bit-identical to the scalar reference (squares through
  `pow`, reference summation order; 0.45 / 1.16 / 5.8 ms per 2S → S fusion at
  S = 8 / 16 / 32 vs 0.61 / 4.3 / 34 ms); per-dimension coalescence errors in sidecar
  events. At the then-default 8 the sidecar was bit-identical to Stage 4A (six full runs,
  19,422 coalescences).
- **Sensitivity (w = 0 / 1):** physical outputs identical across capacity and w. Neolithic
  field error Σ 0.19 / 0.42 at 8, 0.034 / 0.073 at 16, 0.006 / 0.012 at 32; pressure
  0.35 / 0.89, 0.065 / 0.21, 0.012 / 0.045. Pooling totals at 16 within 1e-3 (w = 0) and
  1e-3 / 6e-3 (w = 1, neolithic / pressure) of 32. The w coupling falls about 2.5× per
  doubling but is not removed. Run time at 16 / 32: +3 % / +9 % neolithic, +6 % / +24 %
  pressure.
- Evidence: git `aae0974`: scripts/probes/strata_capacity.py.

### §P. Stage 4B.1 — default resolution

- **Decided:** default `max_strata = 16` (was 8): field error about 6× lower, w coupling
  about 2.5× lower, +0.5 % memory at 50k units, +3–6 % run time. An engineering compromise,
  not a scientific claim; 32 did not justify +9–24 % run time. Physical outputs and oracles
  unchanged; the default strata sidecar differs from the old default-8 representation
  (intended). Fixtures pin 8.
- **Labor accounting deferred (P3):** with every labor determinant shared, each stratum's
  contribution equals its share; runtime state would add no information. The next stage was
  set as design only: identify the smallest lower-level mechanism giving people within one
  population a causal reason to experience different actions, access, obligations,
  opportunities or outcomes; state which subset differs and why if it creates strata; name
  the dimensions it reads (gate); prefer flows and existing state.

### §Q. Stage 4C — counterfactual stored-food access (NOT ACTIVE)

Question: if existing control over stored food influenced access during scarcity, how much
would allocation differ from pooling, and is that robust to resolution?

- **Semantics.** `store_claim` is continuing effective control over the surviving aggregate
  stock, not an exhaustible account; receiving food debits nothing and changes no claim.
  Scope: only the internal allocation of the physical withdrawal `X` covering an existing
  shortage. Timing (locked): pre-withdrawal claims, deficits
  `D_i = max(Need − H, 0)·s_i` (factored form; body reserves excluded), the MVP 2.1 `X`,
  counterfactual allocation, then the zero-stock reset if stores close at zero.
- **Allocator** (`population/strata_access.py`, pure):

  ```text
  q_i = s_i + a·(c_i − s_i)                         a = store_access_claim_weight ∈ [0, 1]
  X ≥ ΣD − allowance:  x_i = D_i                    stores cover everyone: claims cannot matter
  else water-filling:  offer_i = R·q_i / Σ q (hungry), capped at D_i − x_i; repeat
                       if Σ q (hungry) = 0: weights = remaining unmet need   (fallback)
  ```

  Neutral limits are bit-exact (`a = 0` or `c = s` gives `q = s`). Contract
  (`REL_TOL = 1e-12`): `0 ≤ x_i ≤ D_i`, `|Σx − X| ≤ REL_TOL·X + slack`, and at `a = 0` the
  transfer `x_i − X·c_i` equals the Stage 3B transfer. Redistribution from pooling
  `R = ½ Σ|x_i − X·s_i|`.
- **Structural finding: one-shot per store cycle.** Because `X = min(Need − H, K0)`, a
  withdrawal either covers every deficit (claims irrelevant) or empties the stores, after
  which the zero-stock rule erases control. Repeated preferential access needs a rationing
  rule (withdrawing less than the deficit while stores remain), which is out of scope. In
  real runs every mechanism-active unit-year was a depletion year (0 failures in
  2,602–2,905 multi-strata depletion events per run set).
- **Signal** (capacity 32): active unit-years 242 / 890 (neolithic / pressure) at w = 0 and
  443 / 2,018 at w = 1, out of 384,074 / 122,326. R total / X total at a = 1: 0.059 / 0.073
  (w = 0), 0.15 / 0.22 (w = 1). Typical active years move people by about 1–4 % of need
  (at most 12 %); most people lose slightly while a small high-control minority gains.
- **Resolution 16 vs 32:** agree to rounding at w = 0 (Σ|R16 − R32| / Σ R32 = 2e-16 /
  4e-9); under w = 1, small in aggregate (2e-4 / 4e-3) but 5 % of pressure active
  unit-years have uncertainty above 10 % of their signal (p99 21 %), associated with
  inherited coalescence (§M6).
- **Decided: D (with A for resolution at w = 0).** Resolution adequate for this mechanism
  at w = 0; the effect is small (about 2–7 % of withdrawn kcal at w = 0), concentrated and
  one-shot, limited by the MVP 2.1 withdrawal rule, not the allocator. Not activated.
- Evidence: `scripts/probes/store_access_counterfactual.py`.

### §R. Stage 4D — store release / reserve management (NOT ACTIVE)

Question: *how much* leaves storage when the harvest falls short (`X`), separate from who
receives it (§Q). Candidates are unit-level and symmetric; they read no claim, share or id.

- **Intent of `X = min(D, K)`:** an MVP simplification (first MVP 2 commit `244289c`,
  `pooled_energy_balance`, heuristic), not a documented reserve hypothesis. Nothing in the
  model forecasts next year's harvest, need or shortage; seasons, seed requirements,
  storage capacity and a cost of low body reserves are not modeled.
- **Structural finding: the greedy release is kcal-optimal under current physics.** In a
  shortage year with reserves `B ≥ D − X`, food left at year end is
  `r·(K − X) + B − (D − X)`, slope `1 − r > 0` in X; with insufficient reserves a smaller X
  adds energy deficit one for one. Fed years refill body reserves before storing, so the
  `(1 − r)` loss recurs. Fertility reads `H/Need` only. A reserve rule needs a motive the
  model lacks; it would also conflict with trade, which treats stores above current need as
  giftable.
- **Candidates:** C0 `X = min(D, K)` (baseline); C1 reuse `surplus_target` as a stock target
  — rejected (a production margin; double-counts); C2 buffer `X = min(D, max(K − b·Need, 0))`
  — studied with experimental b, not defensible as default; C3 adaptive buffer from
  `harvest_history` — rejected for now (new expectation hypothesis); omniscient
  optimization — rejected. Code: `population/store_release.py` (pure, unused).
- **One-step counterfactual:** `min(D, K)` reproduces recorded X to 8.6e-17. Each retained
  kcal is paid now mostly from body reserves (0.96 neolithic, 0.86 pressure) and partly as
  extra energy deficit (0.033–0.041 / 0.13–0.14); only 0.14–0.22 survives to the unit's
  next shortage. At b = 0.2: 13,232 (neolithic) and ≈ 7,790 (pressure) binding unit-years,
  extra starvation 4.1e8 / 6.3e8 kcal. In controlled cases every binding target adds
  starvation or spoilage. A shadow replay of stores alone would be misleading (mortality,
  trade, migration and innovation all respond); only a branched simulation can evaluate
  dynamics, not warranted without a motive.
- **Hunger with retained food (R8, future hypotheses only):** collective reserve
  preservation can produce hunger with nobody holding power; it is necessary, not
  sufficient, for power over storage. Political power should be inferred from concrete
  asymmetric capacities over consequential decisions, not represented as a scalar.
- **Decided: A, keep the current rule.** Consequence for §Q: claim-sensitive access stays
  one-shot per store cycle; look for differentiation outside storage release.
- Evidence: `scripts/probes/store_release_counterfactual.py`.

### §S. Stage 4E — control over new cultivated capacity (NOT ACTIVE)

**`field_claim_continuity`: COUNTERFACTUAL.** Pure functions in `population/field_control.py`.
Probe: `scripts/probes/field_control_counterfactual.py` (`controlled`, `runs [--stress]`).
Tests: `tests/test_field_control.py`. MVP 2.1 oracles identical.

**Primitive.** *Effective control over durable productive capacity*: a physical stock at
`[U]` plus a distribution of control at `[U,S]`, position `control_i / share_i`. Cultivated
land (`fields_ha` + `field_claim`) is the first specialization; `field_claim` is the modeled
ability to benefit from existing fields or direct their use, not ownership, title, sale,
inheritance, exclusion, rent, authority or coercion. The statements below speak only of a
stock, its expansion `F0 → F1`, a partition of control and the zero-stock rule, so they hold
for a herd, workshop, irrigation system, machine or firm; what does not transfer is how the
stock grows, shrinks and produces. Unlike stores (consumed; control ends at exhaustion),
land is not used up by use; control ends only when the stock reaches zero. The field-claim
lifecycle as built is §1.4–1.5 (nothing else writes `fields_ha`).

**Hypotheses for who controls new capacity `dF = F1 − F0`.** Each is a partition `n` of the
new hectares: `a_i = c_i·F0 + n_i·dF`, `c_i' = a_i/Σa` (`field_claims_after_expansion`).

- **H1, population allocation (`n = s`):** the current neutral rule; not "communal
  property", simply the rule when no other causal distinction is modeled.
- **H2, clearing-contribution allocation (`n = contribution/Σ`):** **collapses exactly to H1
  in the current model.** Clearing hours are one unit-level flow
  (`ΔF·clearing_hours_per_ha(vegetation, clearing_efficiency)`, charged to next year's
  `labor_debt_hours`) drawn from the single pool `labor_hours_columns`, built from shared
  cohorts with unit-level technology and knowledge. No code on that path reads strata
  (tested on the module source). A difference needs a cause for stratum-differentiated
  labor (§N); none is invented.
- **H3, control continuity (`n = s + p·(c − s)`), `p = field_claim_continuity ∈ [0, 1]`:**
  `F0 = 0 ⇒ n = s`. `p = 0` is H1; `p = 1` gives new capacity to existing control. `p` does
  not say *why* control continues (use, prior investment, plot extension, household
  management, custom, institutions, inheritance); it tests only consequences.

**Exact properties (proved, then tested):**

- **`p = 0` reproduces the current rule bit for bit** (random 1-D blocks, padded rows, and
  the shadow sidecar digest equals the authoritative one in all 8 runs).
- **Deviation law.** With `δ = c − s`: `δ' = ρ·δ`, **`ρ = p + (1 − p)·F0/F1 ∈ [F0/F1, 1]`**.
  Every deviation, `pos − 1`, `D = ½Σ|c − s|` and the share-weighted Gini scale by the same
  ρ. `p = 1` preserves claims within rounding (5,000 random steps without drift).
- **No creation and no amplification.** `c = s` stays `s` for every p; `c'` lies between
  `c` and `s` component by component, normalized and nonnegative; D never increases. The
  absolute hectare gap grows with F at p = 1: preservation of a relative position, not
  concentration.
- **Persistence.** With fixed shares `D_T = D_0·Π ρ_t`; for small steps
  `D ∝ (F/F0)^−(1−p)`, so halving D needs area growth `2^{1/(1−p)}`: 2, 2.52, 4, 16 at
  p = 0, 0.25, 0.5, 0.75, never at p = 1. Annual steps retain at least `G^−(1−p)`.
- **Gross, not net, expansion dilutes** (a ×2, ×0.5, ×2 cycle takes D from 0.3 to 0.075 at
  p = 0, keeps 0.3 at p = 1); this asymmetry is in the existing rule.
- **Zero stock.** Fields at zero reset claims; regrowth from zero follows share for every p;
  old control is never resurrected.

**Shadow trajectories** (probe swaps the transition inside passive accounting; every
authoritative quantity identical across p and capacity, checked by digest; capacity 16 and
32, `p ∈ {0, 0.25, 0.5, 0.75, 1}`, w = 0). Cells neolithic / pressure, capacity 16:

| p | 0 | 0.5 | 1 |
|---|---|---|---|
| people-weighted D | 0.0140 / 0.0307 | 0.0211 / 0.0465 | 0.0364 / 0.0935 |
| field position p1–p99 | 0.66–1.37 / 0.56–1.47 | 0.43–1.60 / 0.36–1.72 | 0–2.11 / 0–2.82 |
| episodes not halved at 50 y | 0.09 / 0.03 | 0.27 / 0.16 | 0.43 / 0.37 |
| halved by dilution: n, median years, expansion | 1,055, 12 y, ×2.36 / 694, 11 y, ×2.33 | 261, 27 y, ×6.5 / 169, 27 y, ×6.7 | none |
| halved by zero-field reset | 590 / 351 | 817 / 499 | 902 / 554 |
| coalescence field error Σ (cap 16) | 0.034 / 0.065 | 0.093 / 0.18 | 0.33 / 0.79 |

- Where differences exist is shared across p (105,884 / 65,898 non-neutral unit-years);
  continuity changes their *size*. Store deviation is identical across p (w = 0 isolates
  stores). Episodes (fusion leaving D ≥ 0.01): no episode ever grew without a fusion; the
  law holds per year to ≤ 1.6e-14 relative; survival identical at 16 and 32.
- At p = 0 dilution follows the law (halving after ×2.3–2.4, about 11–12 years). At
  p ≥ 0.75 dilution practically stops (11 / 16 dilution halvings at p = 0.75); differences
  end mainly when fields reach zero (dominant end at every p ≥ 0.5, only end at p = 1). The
  cap on persistence is physical (fission, fusion, migration), not the transition.
- **Resolution 16 vs 32:** `Σ|D16 − D32|` / signal grows about 8× from p = 0 to 1
  (1.1e-4 → 8.3e-4 neolithic, 3.4e-4 → 2.6e-3 pressure). Unit-years with W1(16, 32) above
  10 % of signal: 1.9 % → 7.8 % (neolithic), 1.5 % → 19 % (pressure).
- **Continuity preserves approximation error along with history:** coalescence field error
  grows about 10–12× from p = 0 to 1; pressure episodes start coalesced in 0.40–0.49 of
  cases.
- **`w = 1` stress (socioeconomic only):** field control unaffected by w; persistent field
  control propagates into store control (store deviation neolithic 0.047 → 0.085, pressure
  0.124 → 0.197 from p = 0 to 1, vs 0.008 / 0.014 at w = 0); resolution weaker (W1 tail
  2.5 % → 9.5 % neolithic, 2.8 % → 23.5 % pressure). Shows what *would* follow; nothing is
  active.

**Decided: keep p = 0 (H1) and the gate closed.** Continuity is the first candidate in MVP 3
that gives persistent within-unit differentiation without hardcoding property, inheritance
or hierarchy, and it only preserves, never creates or amplifies. It is not ready: there is
no causal reason for p today (H2 collapses to H1; p should be derived from a named cause,
not set), and it preserves numerical error, so the §M6 metric must precede any reader of
persistent `field_claim`.


### §T. Stage 5A — endogenous differentiation audit (design only, 2026-10-07)

Starting point `f5e44e0` (Stage 4E plus the refactor-only cleanup; both MVP 2.1 oracles
re-verified identical). No mechanism was added and production behavior is unchanged.
Evidence: the code audit below and the read-only probe
`scripts/probes/practice_participation.py` (`controlled`; `runs`, observer neutral by
digest).

**Problem.** Through Stage 4E, heterogeneity enters only through fusion. A homogeneous unit
stays homogeneous; store control is too transient to persist (§Q, §R). Field control can
persist, but its continuity has no cause (§S). The missing piece is a modeled process that
treats part of an initially homogeneous population differently, so that a persistent
causal distinction follows.

**Epoch-general principle.** Candidates are judged as general primitives (differentiated
practice, skill, contribution, investment, access, participation, control or network
position), with an era-specific concrete implementation.

**Audit of existing substrate:**

| Area | What exists (code) | Partial / subset treatment today |
|---|---|---|
| Technology | `technologies: frozenset` per unit, plus a bitmask. Capabilities are additive and apply to the whole unit as soon as the technology is held (`knowledge/system.py`, `capability_column`). Discovery, availability, practice and proficiency are one Boolean (system.py docstring) | none. Practice *intensity* of cultivation is already separate (`fields_ha`, `farm_hours` are an economic decision) |
| Knowledge and learning | Domain levels `K_d` `[U]`, intensive (merge: population mean; split: copy). Practice `s_d = Σ_a w_{d,a}·hours_a/labor`. Learning `K ← K + lr·s·log1p(N·s/n) − (decay/retention)·K` (`learning.py`, rule note: "all members practice in proportion to labor"). Agriculture efficiency `K/(K + 2)` multiplies crop yield; ecology efficiency `K/(K + 0.05)` is saturated | none, but the rule is hours-driven: gain is linear in `s`, with proportional decay |
| Familiarity | per-cell foraging skill; +rate per year foraged, not scaled by hours; decays when idle | none; foraging is near saturation |
| Labor | capacity = cohorts × age curve × 5 h/d × 365. Order: clearing debt, then cultivation (cap 0.9), then foraging. Foraging solves for an effort fraction < 1 when full effort overshoots its target. No idle-hours variable | unit-wide, population-proportional; age enters only as unit totals |
| Durable assets | `fields_ha` (created by clearing labor), `stores_kcal`. Storage is a retention *rate*, not a capacity stock; soil is per cell; there is no infrastructure | none (H2 = H1, §S) |
| Trade | unit-to-unit food kcal, whole-unit balance; `trade_ties` unit-level (daughters start with none) | none; no goods, money or per-person access |
| Migration, fission | Migration moves the whole unit. Fission draws departing cohorts binomially at one rate per cohort; the daughter copies knowledge, technology, familiarity and strata | none beyond fusion; fission is representative |
| Other resources | per-cell plant, game, soil and arable land; arable shared pro rata with no incumbency | none |

**Measured activity demand** (labor capacity at the start of the year; neolithic 600 y /
pressure + cultivation 400 y; seeds 0–3):

| | neolithic | pressure |
|---|---|---|
| farming unit-years | 318,012 of 379,499 | 94,681 of 119,321 |
| cultivation hours ÷ capacity, p50 / p90 | 0.35 / 0.61 | 0.57 / 0.78 |
| farming unit-years with cultivation below 0.5 / 0.25 of capacity | 0.75 / 0.28 | 0.36 / 0.11 |
| labor-capped (≥ 0.9) | 0.00 | 0.02 |
| unused capacity, p50 / p90 | 0.16 / 0.39 | 0.00 / 0.25 |
| cultivation spell per unit id, p50 / p90 | 14 / 52 y | 8 / 46 y |
| farming unit-years with clearing; clearing ÷ capacity p90 | 0.16; 0.06 | 0.18; 0.09 |

Hours can exceed the start-of-year capacity (max about 1.6) where demography or fusion
changes the unit during the year.

- **Finite activity demand is the rule, not the exception.** Cultivation needs only part of
  a unit's labor. If those hours were performed by the people who farm, the practicing
  share would be `f = s / s_max`, strictly between 0 and 1. This is deterministic and
  follows from the field area, the hours per hectare and the time budget; no random
  fraction is involved.

**The existing learning rule rewards concentration**
(`practice_participation.py controlled`, neolithic parameters, the authoritative `learn`):
- The same total cultivation hours are performed either by everyone (share `s`) or by
  `f = s/0.9` of the people at share 0.9.
- In the concentrated case, practitioners reach agricultural efficiency far sooner and
  hold it higher. For example, at N = 40:
  - s = 0.25: 0.58 vs 0.34 after 5 years, 0.83 vs 0.64 after 20 years, 0.92 vs 0.82 at
    equilibrium;
  - s = 0.1: 0.88 vs 0.65 at 100 years.
- Non-practitioners stay at 0.07–0.42 (they still learn a little through the foraging
  weight 0.15).
- Ecology competence is saturated either way (0.99+), so the economically consequential
  difference is in agriculture.
- The reason is the rule's form. Gain is linear in practice share, and
  `N·s = (fN)·(s/f)` keeps the practitioner term unchanged, so the equilibrium level
  scales as `1/f`.

**Candidates ranked** (by audit evidence):

| Candidate | Existing causal substrate | Can split a homogeneous unit | Persistence | Epoch-general | New state | New physical feedback (when active) | Risk of smuggling institutions | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Practice concentration under finite activity demand, sustained by learning-by-doing** | yes: finite demand (above), hours-driven learning, knowledge → crop yield | yes; the share `f` is deterministic | while practiced; decays with disuse (agriculture decay 0.02/y, half-life ≈ 35 y) | yes (practice → competence) | per-stratum domain competence; practice share as a flow | yes (yield of practitioners) — gated | low: no rank or ownership; needs one initiation hypothesis (below) | **recommended** |
| Differentiated contribution to durable assets (clearing) | clearing is finite demand (16–18 % of farming unit-years, small FTE) | only with the same concentration hypothesis | as fields (§S) | yes (investment → control) | per-stratum contribution (flow) | no (claims are passive) | moderate: contribution ⇒ control is a further hypothesis | downstream of the recommended mechanism; gives §S its cause |
| Uneven technology adoption | none: technology is a unit-wide Boolean with instant whole-unit effect | no, without separating discovery from practice | — | yes | a practice/adoption ontology | yes | moderate | subsumed: for cultivation, practice is already hours, not the Boolean |
| Familiarity differentiation | per-cell skill, not hours-scaled | no | decays | partly | per-stratum familiarity maps (heavy: sparse per cell) | small (foraging near saturation) | low | rejected: inert and expensive |
| Exchange participation | unit balance only; food only; unit ties | no | — | yes | per-stratum ties or goods | yes | high (merchant category) | rejected for now: no substrate |
| Migration and settlement history | whole-unit migration; representative fission | no (only fusion) | — | yes | selective fission or migration | yes | low | rejected: no within-unit path |
| Resource access (stores, fields) | claims exist (§Q–§S) | no | stores transient; fields need a cause | yes | — | yes | moderate | not a first splitter (§Q, §R, §S) |
| Age-structured participation | labor and need curves by age | no (age is shared by design, §1.3) | people age through it | — | — | — | low | rejected: not socioeconomic |

**Recommended first differentiator: practice concentration under finite activity demand.**
*Different practice histories lead to different accumulated competence.*
- **Epoch-general primitive:** persistent practice differentiation leading to competence.
- **First concrete domain:** cultivation, against foraging. The same idea later fits
  crafts, trade, administration and machinery.

**Smallest causal event.**
- In a unit-year where cultivation demand `H` is below the practice capacity of the whole
  unit, subset A (share `f = s/s_max`, with `s = H/C`) performs the year's cultivation
  hours and subset B does not; B forages.
- "A farmed this year, B did not" is a stated cause. "Specialists vs others" is a
  category and is not used.
- No individual identities are represented: A and B are mixture components, so no random
  partition picks people. `f` comes from demand and the time budget.

**Initiation needs one explicit hypothesis** (the only new behavioral assumption;
undecided):
- (i) **A per-participant cost** (setup, travel or coordination per practitioner-year).
  Concentration then lowers hours immediately and dominates. Epoch-general, but it is a
  physical labor cost.
- (ii) **Experience-based assignment** (work goes to the most competent). This is
  deterministic and self-reinforcing once competence differs. It ties at perfect
  homogeneity, so on its own it amplifies only fusion-born differences.
- (iii) **Allocation that anticipates learning.** This is a foresight hypothesis.

Stage 5B should not choose by fiat. It should treat concentration as a counterfactual
degree `c ∈ [0, 1]` (0 = spread, the current assumption), like `p` in §S, and measure the
consequences. The candidate causes go to review.

**Randomness policy.** Concentration needs none: `f` is determined. A stochastic version
would represent real uncertainty about who is available (illness, absence), not a
partition chosen to manufacture strata; it is not recommended.

**Future split criterion (not implemented).** A stratum may be split when a modeled
allocation gives a subset of it a materially different practice flow (practice share
differing by more than a set fraction of the activity's demand) in a year. The split
creates two components with identical claims and inherited competence. They differ from
that year's learning step onward, so exact compaction does not re-merge them; positions
must then include competence.
- **Bounded growth.** With experience-based allocation (water-filling from the most
  competent stratum), each activity splits at most one marginal stratum per unit-year.
  Other strata are wholly in or wholly out.
  - When demand rises, part of B joins A. When it falls, part of A leaves; that part keeps
    competence without practice and decays toward B.
  - Decay is exponential, so the leavers never merge with B exactly. Capacity coalescence
    must absorb them, and its metric must include competence.
- **Combinatorics.** One activity gives at most two practice states per stratum
  lineage. Several activities would multiply profiles. Hence: one activity first, then
  differentiate more only with evidence.

**Candidate state semantics (design; nothing added):**

| State | Kind | Creation | Reinforcement | Decay or destruction | Fusion | Fission | Coalescence |
|---|---|---|---|---|---|---|---|
| per-stratum domain competence `K_{s,d}` (first: agriculture) | intensive (per capita) | split: both parts inherit `K` | the existing learning rule on the stratum's own practice `s_{s,d}` and population | the existing proportional decay; no reset on loss of fields (skill outlasts the asset and decays with disuse) | strata concatenate, each keeping its `K`; the unit's knowledge is derived as `Σ share·K` (matches today's population-mean merge) | copy (representative); selective fission by practice is a later possibility | population-weighted mean |
| per-stratum activity practice `s_{s,a}` | intensive flow (per tick, not stored) | allocation each year | — | — | — | — | — |
| per-stratum clearing contribution (for §S) | extensive flow (hours) | allocation each year | — | — | — | — | — |

**Consequences and links:**
- **Technology ontology.** Discovery, availability, practice, proficiency and
  infrastructure are conflated in the Boolean technologies. The recommended mechanism does
  *not* require separating them: `plant_cultivation` stays a unit-level affordance,
  practice is hours, and proficiency is the existing agriculture domain made `[U,S]`.
  Partial technology adoption would need the separation later.
- **Labor (revisits §N).** Differentiated labor becomes meaningful only after this split:
  A's hours go to cultivation and B's to foraging. The order is preserved: differentiation
  first, labor dimensions second.
- **§S continuity.** If the same practitioners also clear (construction practice comes
  from clearing), clearing contribution concentrates. H2 then differs from H1, and new
  land follows contribution. This gives continuity a cause: `p` would emerge from the
  overlap between practitioners and existing controllers instead of being set. This is a
  further hypothesis, not forced.
- **Later hierarchy (future research only).** Persistent practice differentiation could
  lead to different productive positions, then different dependencies or bargaining
  positions, then asymmetric control over consequential decisions, and possibly
  institutions. Only the first step belongs to Stage 5. No power, status or rank scalar is
  introduced.
- **Resolution.** A future mechanism-aware merge metric must preserve, per stratum:
  - agriculture competence, weighted by its consequence: the efficiency derivative
    `K_half/(K + K_half)²`, so differences matter most at low competence;
  - current practice status;
  - `field_claim` position.

  Equal-weight Euclidean distance in claim positions (§M6) would not protect competence.
- **Physical feedback (when ever active).** Crop yield would use practitioners' competence,
  and competence would change hours and yield. Gated (§N7). Stage 5B stays counterfactual.

**Deferred:**
- the initiation hypothesis;
- any activation, and the yield and labor feedback;
- selective fission;
- multi-activity profiles;
- competence in the coalescence metric;
- per-stratum familiarity, exchange and access;
- hierarchy, property, inheritance and authority.


### §U. Stage 5B — participation overhead and practice concentration (2026-10-08)

**COUNTERFACTUAL / NOT ACTIVE.**
- Pure functions in `population/practice_concentration.py`. No simulator path calls them,
  no model rule is registered, and there is no scenario setting.
- Probe: `scripts/probes/practice_concentration_counterfactual.py` (`controlled`,
  `runs`). Tests: `tests/test_practice_concentration.py`.
- Starting point `2671a1f` (Stage 5A). Authoritative labor, crop output, knowledge and
  strata are unchanged.

**Question.** Why would a finite amount of cultivation be concentrated on part of an
otherwise identical population, rather than spread across everyone? Candidate tested: a
per-participant overhead (setup, access, coordination or travel), with the epoch-general
primitive *participation costs labor beyond productive time*.

**Labor as built** (audited in `economy/agriculture.py` and `economy/foraging.py`):
- capacity `C` = age-weighted adults × `foraging_hours_per_day` (5) × 365;
- clearing debt `D` = last year's clearing hours;
- cultivation hours `P = min(fields × 600, m·max(C − D, 0))`, with
  `m = max_farm_labor_share` = 0.9 — the cap is 0.9 of *post-debt* labor;
- foraging gets `max(C − D − P, 0)`, and its effort fraction falls below 1 when full
  effort would overshoot the target;
- productive hours contain no implicit overhead.

Learning, per unit:
`K ← max(K + speed·lr·s·log1p(N·s/n) − (decay/retention)·K, 0)`, with
`s = 1.0·P/C + 0.15·plant_forage/C`, agriculture `lr` 0.35, `n` 2 and decay 0.02.
Crop yield = potential × crop capability × `K/(K + 2)`, so
`dE/dK = K_half/(K + K_half)²` exactly (tested numerically).

**Overhead hypothesis.**
- Each participating labor-equivalent person (`L = C/(5·365)` of them) costs `o` hours a
  year, inside the same budget.
- Total cultivation labor is `P + o·f·L`, where `f` is the participating share. Strata
  share the age structure, so a population share is also a labor share.
- Feasibility: `m·f·(C − D) ≥ P + o·f·L`, so
  **`f_min = P / (m(C − D) − o·L)`**, which is `P/(m(C − D))` at `o = 0`. It is 1 when
  that budget does not exceed `P`, and 0 without cultivation.

**Optimization result: a corner solution.**
- The cost `P + o·f·L` is linear in `f` with slope `o·L`.
- At `o = 0` every feasible `f ∈ [f_min, 1]` costs the same: indifference, so there is no
  reason to concentrate.
- For **every** `o > 0`, however small, the optimum jumps to the minimum feasible share
  `f_min` (tested for `o` down to 1e-9).
- So the overhead does not give graded concentration. It is a switch from "undetermined"
  to "maximal concentration", and the size of `o` barely moves the result. At
  `P/(C − D) = 0.35` and 40 labor-equivalents, `f*` is 0.389 / 0.391 / 0.401 / 0.443 at
  `o` = 1 / 10 / 50 / 200 h per participant-year.
- The labor saved by concentrating is small unless `o` is large: 0.03 % / 0.3 % / 1.6 % /
  6 % of capacity at those `o`. The incentive's scale is unidentified, and no existing
  quantity calibrates `o`.

**Countervailing forces in the existing model:**
- The cap `m` (0.9 of post-debt labor per participant) is the **only** force that
  bounds concentration, and it sets `f_min` itself.
- None of the following exist:
  - a cost of work, fatigue or load (§N: work has no energetic or demographic cost);
  - diminishing productivity per participant (yield is per hectare, and hours are
    linear);
  - risk diversification;
  - temporal availability;
  - spatial or task-simultaneity limits.
- Age enters only as unit totals.
- The learning rule itself *rewards* concentration (§T), so it adds no balance.

**Who participates is a separate question.** Overhead per participant-year fixes how many
participate, not who.
- If participants were reassigned every year in proportion across the unit ("rotation"),
  everyone's practice history would average out and no persistent competence difference
  would form. The shadow runs confirm it (below).
- Persistent differences need **continuity of participation** (the same components
  keep practicing). That is a further hypothesis. An *entry* overhead (a cost paid when
  someone starts practicing) would imply continuity; an annual overhead does not.
- The primary experiment uses continuity: changes in the participating share are taken
  from or returned to the other components in proportion, so competence is never used.
  Competence-based assignment is a separate, secondary test.

**Diagnostic concentration** `f(c) = 1 − c·(1 − f_min)` is a sensitivity coordinate, not
a mechanism. `c = 0` is today's spread.

**Component learning.**
- Each shadow component learns with the authoritative arithmetic on its own practice
  `s_i`.
- The social-learning term counts the *unit's* practitioners `N·s_unit`, which does not
  depend on how the same hours are distributed.
- Participants farm `P/(f·C)`; the rest of the labor forages in proportion to what each
  component has left.
- Hours are conserved (`Σ share·s_i = s_unit`), and learning is linear in `s` and `K`. So
  **the share-weighted mean competence equals the authoritative unit level at every
  `c`**: concentration redistributes competence without changing the unit's mean.
- At `c = 0` (equal practice) the update is the unit update bit for bit (tested).
- Diffusion and innovation change `K` after learning. The shadow carries those unit-level
  increments to every component alike, a stated neutral convention.

**Controlled two-component trajectories** (40 people; agricultural efficiency,
practitioners / others):

| case | c = 0 (5 / 25 / 100 y) | c = 1 (5 / 25 / 100 y) |
|---|---|---|
| low demand, s = 0.1 | 0.17 / 0.46 / 0.65 | 0.53 / 0.08 · 0.82 / 0.28 · 0.91 / 0.46 |
| moderate, s = 0.35 | 0.42 / 0.75 / 0.87 | 0.63 / 0.12 · 0.87 / 0.36 · 0.94 / 0.56 |
| near-full, s = 0.85 (f_min = 0.94) | 0.68 / 0.90 / 0.95 | 0.69 / 0.15 · 0.90 / 0.43 · 0.95 / 0.62 |
| capped, s = 0.95 | identical (no concentration possible) | identical |
| no cultivation | identical; no split | identical |
| stop after 30 y (s = 0.35) | 0.75 at 25 y, 0.57 at 100 y | 0.87 / 0.36 at 25 y → 0.70 / 0.38 at 100 y |
| demand falls 0.6 → 0.2 at y 30 | 0.85 at 25 y, 0.83 at 100 y | 0.89 / 0.40 at 25 y → 0.93 / 0.70 at 100 y |

- **Differentiation is bounded.** Both components learn under the same rule. The gap is
  largest early and at low demand, and the non-participants still learn a little through
  the 0.15 foraging weight. Nothing runs away.
- **Disuse.** Without practice both components decay by 2 % a year, so the competence
  gap halves in 34.3 years.
- **Starting after a homogeneous history.** Both components inherit equal competence and
  diverge only from the first differing year.

**Clearing and field control (§S).**
- The labor sequence gives **no causal reason** that cultivation participants are also
  the people who clear. Clearing is a unit-level flow charged as debt against the next
  year's *total* capacity, and it is not attributed to anyone.
- **Differentiated clearing contribution therefore still lacks a mechanism**, and H2 still
  equals H1.
- The shadow only quantifies the hypothetical case where participants clear (below). It
  is not evidence for the link.

**Real runs** (neolithic 600 y and pressure + cultivation 400 y, seeds 0–3; probe at
`c88d489`; every run reached its horizon; observer neutral by physical digest in all 8).
The shadow mean competence equals the authoritative unit level to ≤ 9.1e-16 in every
shadow. Neolithic first, pressure second in each cell; E is agricultural efficiency
`K/(K + 2)`.

*Opportunity.* Concentration is possible in most farming unit-years:

| | neolithic | pressure |
|---|---|---|
| farming unit-years | 325,766 | 102,200 |
| `f_min` p50 / p90 | 0.41 / 0.71 | 0.68 / 0.93 |
| `f_min` < 0.75 / < 0.5 / < 0.25 | 0.93 / 0.66 / 0.25 | 0.64 / 0.26 / 0.08 |
| everyone needed (`f_min` = 1) | 0.006 | 0.047 |
| consecutive years with `f_min` < 0.75, p50 / p90 / max | 6 / 34 / 258 | 3 / 12 / 133 |

*Concentration sweep* (continuity assignment, capacity 16; gap = participants minus
others, share-weighted, over unit-years with both):

| | c = 0.25 | c = 0.5 | c = 0.75 | c = 1 |
|---|---|---|---|---|
| E-gap p50 / p90 | 0.014 / 0.040 · 0.005 / 0.022 | 0.015 / 0.043 · 0.005 / 0.024 | 0.017 / 0.049 · 0.006 / 0.027 | 0.021 / 0.058 · 0.006 / 0.034 |
| unit-years with E-gap > 0.05 | 0.046 · 0.019 | 0.059 · 0.023 | 0.078 · 0.029 | 0.117 · 0.044 |
| E-gap max | 0.18 · 0.14 | 0.19 · 0.14 | 0.20 · 0.15 | 0.23 · 0.20 |
| practitioner E ÷ unit E − 1, p50 / p90 | 0.002 / 0.006 · 0.000 / 0.003 | 0.004 / 0.014 · 0.001 / 0.007 | 0.008 / 0.025 · 0.001 / 0.012 | 0.012 / 0.044 · 0.002 / 0.022 |

- **The differentiation is real but small.** At maximal concentration the median gap is
  0.021 (neolithic) and 0.006 (pressure); a gap above 0.1 occurs in 1.9 % and 0.9 % of
  unit-years. The seed-0 smoke runs (0.04–0.07) overstated it.
- **It grows monotonically and modestly with `c`.** No `c` produces a qualitative change,
  consistent with the corner result: the degree of concentration is not where the
  consequence lies.
- **Potential physical consequence** (if crop yield used practitioners' competence instead
  of the unit mean): a median 1.2 % / 0.2 % yield difference at `c = 1`, p90 4.4 % / 2.2 %.
  This bounds what activation could do through this channel. Pressure is smaller because
  demand is higher (`f_min` near 1).

*Who participates* (c = 1, capacity 16):

| assignment | E-gap p50 / p90 | > 0.05 / > 0.1 | K-gap p50 | splits / unit-year | component lifetime p50 / p90 |
|---|---|---|---|---|---|
| continuity | 0.021 / 0.058 · 0.006 / 0.034 | 0.117 / 0.019 · 0.044 / 0.009 | 4.2 · 2.9 | 6.8 · 6.7 | 0 / 3 y |
| rotation | 0.002 / 0.006 · 0.001 / 0.004 | 0.000 / 0.000 · 0.000 / 0.000 | 0.5 · 0.6 | 13.4 · 12.1 | 0 / 1 y |
| competence-based | 0.091 / 0.179 · 0.058 / 0.113 | 0.748 / 0.364 · 0.473 / 0.113 | 16.7 · 19.6 | 0.8 · 0.8 | 2–3 / 21–24 y |
| continuity, minimum duration 3 y | 0.022 / 0.060 · 0.007 / 0.036 | 0.125 / 0.019 · 0.041 / 0.007 | 4.3 · 3.1 | 3.3 · 2.9 | 0 / 6–7 y |

- **Rotation erases differentiation** (confirmed): no unit-year exceeds a 0.05 gap.
- **Assignment matters more than concentration.** Competence-based assignment raises the
  median gap 4× / 10× over continuity (0.09 / 0.06) and makes it self-reinforcing: the same
  components keep practicing, so splits fall 8× and p90 component lifetime rises 8×. It is the
  secondary hypothesis (ii) of §T; it is not tested here as a cause, only as a consequence.
- A minimum participation duration halves the churn at no cost to the gap.

*Representation.*
- **Immediate splitting saturates any capacity.** For every `c > 0`, units sit at the
  capacity in 88–92 % of unit-years, at 16 and at 32 alike (mean 14.9 / 29.5 components).
  Doubling capacity doubles splits and coalescences.
- **Capacity does not change the measured differentiation.** The participant/other gaps
  are identical at 16 and 32, and within-unit dispersion differs by < 3 %. The extra
  components hold near-duplicates (redundant pairs per unit-year 0.29 → 0.92 at `c = 1`
  neolithic, 0.8 → 4.9 pressure).
- **An accumulated-divergence merge is enough.** At τ = 0.05 (efficiency), units hold 3.5 /
  2.4 components on average (p99 8 / 6), never reach the capacity, and need no forced
  coalescence. Median within-unit dispersion falls (0.021 → 0.009 / 0.006 → 0.0015); p90
  is largely kept in neolithic (0.049 → 0.045), less under pressure (0.025 → 0.016). τ = 0.01 still reaches the capacity in 39 % /
  12 % of unit-years.
- **The coalescence metric should be slope-weighted** (§T Resolution). Choosing the pair by
  K-distance loses 2–9× more efficiency variance than choosing by efficiency, and picks a
  different pair in 24–54 % of forced coalescences (`c > 0`). The slope-weighted K-distance
  `K_half/(K + K_half)²·|ΔK|` ranks pairs exactly as the efficiency loss does (median
  Spearman 1.00 in every shadow); plain K-distance does not (0.85–0.99).
- **Cost.** The 13 shadows take about 100× the plain run (neolithic 2,058 s against 20 s for
  4 seeds), dominated by split and coalescence churn. A single active representation with a
  τ merge would be far cheaper; this is not measured here.

*Persistence after cultivation stops* (units with a within-unit E spread ≥ 0.05 at the
stop; Kaplan–Meier share not yet halved at 10 / 25 / 50 y, resumption censored):

| | c = 0 (fusion only) | c = 1 continuity | c = 1, τ = 0.05 | c = 1 competence |
|---|---|---|---|---|
| neolithic | 1.00 / 0.63 / 0.17 (57) | 1.00 / 0.86 / 0.46 (8,724) | 0.85 / 0.62 / 0.30 (6,756) | 0.99 / 0.86 / 0.45 (9,264) |
| pressure | 1.00 / 0.18 / 0.00 (58) | 1.00 / 0.38 / 0.00 (1,085) | 0.52 / 0.11 / 0.04 (953) | 1.00 / 0.29 / 0.00 (2,440) |

- **Differences outlast practice by decades in neolithic** (about half not halved at 50 y,
  near the 34-year decay half-life) and **for 10–50 years under pressure** (all halved by
  50 y), where fusion mixes units faster. Stop episodes number in the thousands only because
  concentration creates the spread; under fusion alone there are 57–58.
- The τ = 0.05 merge shortens persistence because it fuses decaying leavers back early.

*Clearing link* (hypothetical H2: participants clear; field-claim deviation from share
per expansion, p50 / p90): 0.022 / 0.067 · 0.009 / 0.059 at c = 0.25, rising linearly to
0.089 / 0.267 · 0.036 / 0.235 at c = 1 (36,950 · 15,385 expansions). The linearity is
mechanical: the deviation is `(1 − f)` scaled by the expansion. It quantifies the size of
§S's H2 *if* the link existed; it is not evidence for the link.

**Recommendation: B, confirmed.** The real runs measure consequences and do not change it.
- Participation overhead is physically plausible but degenerates to maximal
  concentration; a countervailing mechanism or a graded cost is needed before activation.
- Persistence needs continuity of participation, a separate hypothesis; rotation erases
  the effect.
- Even at maximal concentration with continuity, the consequence is small (median E-gap
  0.02 / 0.006; median yield effect ≤ 1.2 %). Who participates (assignment) matters 4–10×
  more than how many.
- **If a version is ever activated,** it needs: continuity (or an entry cost) stated as a
  hypothesis; an accumulated-divergence merge (τ ≈ 0.05) rather than immediate splitting;
  and the slope-weighted coalescence metric.
- Reviewed and accepted (2026-10-09).


### §V. Stage 5C — entry costs and participation continuity (2026-10-09)

**COUNTERFACTUAL / NOT ACTIVE.**
- Pure functions in `population/entry_cost.py`. No simulator path calls them, no model rule
  is registered, and there is no scenario setting.
- Probe: `scripts/probes/entry_cost_counterfactual.py` (`controlled`, `runs`, `report`).
  Tests: `tests/test_entry_cost.py`.
- Starting point `eeb431f` (Stage 5B). Authoritative labor, crop output, knowledge and
  strata are unchanged.

**Question.** Can a cost of *starting* an activity, which continuing practitioners do not
pay again, make participation histories persistent? Two problems are kept apart:
- **initiation:** why only part of a homogeneous unit would begin;
- **continuity:** why the same part would continue rather than be replaced.

**Epoch-general primitive.** Entering or re-entering an activity costs effort that
continuing practitioners do not repeat: familiarization, tool preparation, access to a
work place, learning procedures, coordination, switching. Cultivation is the first domain.

**Labor audit (unchanged from §U, re-verified).**
- `FarmingSubsystem.evaluate`: `P = min(fields × 600, m·max(C − D, 0))`, `m = 0.9`.
- `D` is the clearing planned in the previous year (`FieldPlans.apply` adds it to
  `labor_debt_hours`); foraging gets `max(C − D − P, 0)` and resets `D` to 0.
- Agriculture practice is `1.0·farming + 0.15·plant_foraging`; clearing feeds the
  construction domain only.
- No existing quantity is a setup or entry cost, so nothing is double-counted. Entry hours
  live in a counterfactual ledger only.

**Entry cost versus §U overhead.**

| | recurring overhead (§U) | entry cost (§V) |
|---|---|---|
| who pays | every participant | entrants only |
| when | every year | the year of entry or re-entry |
| labor | `P + o·f·L` | `P + e·L·Σ φ_i x_i` |
| depends on history | no | yes, through `φ` |

**Model.** `B = m(C − D)` is the whole unit's cultivation budget, `L = C/(5·365)` its
labor-equivalents, `e` the entry cost in hours per entering labor-equivalent. Component `i`
has share `s_i` and entry factor `φ_i ∈ [0, 1]` (0 = continuing participant, 1 = full
entrant). This year's participants are `x_i ∈ [0, s_i]`.

```latex
\text{feasible: } \sum_i x_i\,(B - e L \varphi_i) \ge P, \qquad
\text{entry labor: } e L \sum_i \varphi_i x_i
```

- Productive hours are never reduced. If even full participation cannot carry `P` plus
  entry labor, the allocation is reported **infeasible** with its shortfall (labor that a
  physical version would have to displace). No free hours are invented.
- **Optimum.** Entry labor is linear, and a cheaper component also adds more net capacity
  (`B − eLφ` falls with `φ`). Filling components in ascending `φ` is therefore optimal (an
  exchange argument), and it stops at the smallest feasible share.
- **Ties.** Components with equal `φ` cost the same. They are taken in proportion to their
  shares, so the allocation never depends on component order or identity (tested by
  permutation).

**Result 1: initiation is the §U corner again.** With no history (`φ = 1` everywhere):

```latex
f^* = \frac{P}{B - eL} \quad (e > 0), \qquad f \in [P/B,\,1] \text{ indifferent at } e = 0
```

- This is exactly §U's `f_min` with `o = e`. For **every** `e > 0` the first entry is
  maximal concentration. At `e = 0` the cost is flat.
- The cost decides **how many** enter, never **which**. Equal components tie and are taken
  in proportion: an anonymous exposure split with no identities.
- That a strict subset enters at all rests on a behavioral assumption: the unit
  coordinates this year's entry to minimize this year's entry labor (myopic, unit-level).
  Physics does not imply it.
- Infeasible when `P > B − eL`: first entry at `e = 1,500 h` and `s = 0.85` leaves a
  shortfall of 0.77 C.

**Result 2: continuity is real but not unique.** Incumbents `h` (`φ = 0`), others `φ = 1`:

| case | optimum | determined? |
|---|---|---|
| `P ≤ hB` (incumbents suffice) | any `f ∈ [P/B, h]` drawn from incumbents; entry labor 0 | **no**: how many, and which incumbents, are both indifferent |
| `P > hB` (incumbents insufficient) | all incumbents + `n = (P − hB)/(B − eL)` entrants | amount yes; which entrants: tie |

- Entry cost explains why incumbents are used **before** newcomers. That is the
  continuity-versus-rotation contrast.
- It does not say whether to keep all incumbents (`retain`, status quo) or shed down to
  `P/B` (`min`) when demand falls. Both ends of the interval are tested.
- **Rotation's cost.** Rotation redraws participants in proportion, so with last year's
  share `h` and need `f` it pays `eL·f(1 − h)`. In steady state that is `eL·f(1 − f)` a
  year (0.0067 C at `f = 0.4`, `e = 50`), while continuity pays 0.

**Result 3: universal participation is also a continuity equilibrium.**
- If everyone participates (M0), everyone is an incumbent after the first year. Entry
  labor is `eL` once, then 0 for as long as cultivation continues.
- M2 pays `eL·f*` once, then 0 while demand does not rise. The one-time difference is
  `eL(1 − f*)` per cultivation start.
- Under fluctuating demand, M2 pays again at every rise above its incumbents; M0 never
  does. Over a spell, a far-sighted unit could prefer universal familiarity.
- **Entry cost locks in whatever the first allocation was.** Concentration comes from
  the myopic first-entry choice, not from the continuing cost.

**Participation memory (hypotheses, not model state).** `since` = years since a
component last participated (1 = last year, ∞ = never). The competence state cannot
stand in for it: non-participants also gain `K` (the 0.15 foraging weight, diffusion), and
`K` is an intensive mean, not a recency. Using `K` for both would double-count one
familiarity. Variants:
- `W1`: immediate expiry (only last year's participants are incumbents);
- `W10`: finite window of 10 years;
- `H10`: gradual decay `φ = 1 − 2^{−(since − 1)/10}`.

**Assignment models.**
- **M0 proportional:** everyone participates.
- **M1 rotation:** the smallest feasible share, redrawn in proportion every year.
- **M2 entry-cost continuity:** minimum entry labor; `min` or `retain` at the indifference
  interval.
- **M3 competence:** the same amount as M2, drawn by descending `K` (secondary).

At equal `K`, M3 ties and is proportional (tested): competence alone cannot select a
subset from a homogeneous unit.

**Coordination assumption.**
- *Continuity* can be read as individual inertia: an incumbent loses nothing by
  continuing, and a newcomer must pay to start.
- *Initiation* and *shrinking* need a unit-level coordination that the model does not
  represent: agreeing that only some start, and who stops when demand falls. No chief,
  enforcement or ownership is implied, but the coordination is an assumption.

**Controlled results** (40 people, `e = 50 h`; full tables in the probe's `controlled`
output).

*First entry and the ledger* (`s = P/B`):

| s | e = 1 / 10 / 50 / 200: `f*` | entry hours / C at e = 50 | incumbents h = 0.2: entrants n at e = 50 |
|---|---|---|---|
| 0.1 | 0.100 / 0.101 / 0.103 / 0.114 | 0.003 | 0 |
| 0.35 | 0.350 / 0.352 / 0.361 / 0.399 | 0.010 | 0.155 |
| 0.6 | 0.600 / 0.604 / 0.619 / 0.683 | 0.017 | 0.413 |
| 0.9 | 0.901 / 0.906 / 0.928 / infeasible | 0.025 | 0.722 |

*Cases* (efficiency of incumbents / others at 25 and 100 years):

| # | case | result |
|---|---|---|
| 1 | homogeneous, no cultivation | nothing happens in any model |
| 2 | first encounter, s = 0.35 | M1–M3 enter at the corner `f = 0.40`; M2 then pays nothing (0.87/0.36 → 0.94/0.56), M1 pays 0.24 a year and equalizes (0.76/0.74 → 0.87/0.87), M0 pays once |
| 3 | incumbents h = 0.4, stable | M2 keeps them at zero cost; M1 pays 0.24 a year; M0 pays 0.6 once |
| 4–5 | demand rises gradually / suddenly 0.2 → 0.6 | M2 adds entrants only as demand rises (gradual: ≈0.01 a year; sudden: 0.46 in one year) |
| 6 | demand falls gradually 0.6 → 0.2 | `min` sheds to 0.22 (0.93/0.61); `retain` keeps 0.69 (0.85/0.52) |
| 7 | cultivation stops | W1 histories lapse in a year; W10 incumbents keep their status 10 years |
| 8 | returns after 1 idle year | W1: history already lapsed, so re-entry is proportional and mixes (0.89/0.61 at 50 y); W10: former participants re-enter free and the same people resume (0.91/0.48) |
| 9 | returns after 30 idle years | every memory has lapsed: M2 draws entrants in proportion, M3 picks the formerly competent; gaps re-form through practice (M2 0.92/0.60 at 100 y) |
| 10 | incumbents exceed demand (h = 0.8, s = 0.2) | indifference interval [0.22, 0.80]: `min` 0.93/0.52, `retain` 0.81/0.52 at 100 y |
| 11 | incumbents insufficient (h = 0.2, s = 0.6) | all incumbents + 0.48 entrants in year 1 |
| 12 | fusion competence difference, no history | M2 ties (proportional); M3 selects the competent (0.64/0.38 in year 1) |
| 13 | equal competence, different histories | M2 selects incumbents (0 entry); M3 ties and pays 0.24 |
| 14 | e = 1,500 h, s = 0.85 | infeasible; shortfall 0.77 C |
| 15 | e = 0 | indifferent; `min` concentrating at `e = 0` is a tie rule, not a cost |

*Hysteresis* (demand 0.2 → 0.6 → 0.2 → 0.6, 20 years each; entrants at the second rise):

| model | f at the second low | entrants at the second rise | cause |
|---|---|---|---|
| M0 | 1.00 | 0 | everyone stays familiar |
| M1 | 0.23 | 0.53 | history ignored |
| M2 min W1 | 0.22 | 0.46 | leavers lapse after one year: no allocation memory |
| M2 retain W1 | 0.68 | 0 | status quo ratchets `f` to the past maximum |
| M2 min W10 | 0.22 | 0.01 | proportional shrinking among equal-cost incumbents rotates the whole former pool, keeping it incumbent |
| M2 min H10 | 0.22 | 0.34 | the most recent are strictly cheapest, so the same people continue; leavers partly decay |

- **Hysteresis comes from the memory form combined with the tie convention, not from the
  entry cost alone.** With W1 the allocation has no memory beyond a year. `retain` and W10
  give strong but convention-made hysteresis. H10 gives graded hysteresis from cost
  differences alone.

**Population turnover.** A stratum is a mixture, not a set of immortal people.
- Each year a share `τ` of a unit's labor is new to work: children ramping into labor
  between ages 6 and 15. Measured from the actual age structure, `τ` is about 3 %/y
  (pressure smoke run: p50 0.031, p90 0.049).
- Without turnover, a participating component's new workers (its children; strata share
  the age structure) silently inherit its incumbency. Persistence then becomes
  **hereditary by representation**.
- The share of original participants after `T` years is `e^{−τT}`: half after about
  22 years.
- Sensitivity `turnover`: each year a share `τ` of every component with a history becomes
  history-free (same `K`, a stated approximation) and must pay to enter.

**Real runs** (neolithic 600 y and pressure + cultivation 400 y, seeds 0–3, at `15e06f0`;
13 shadows, trajectories at `e = 50 h`).
- Every run reached its horizon and was observer-neutral by physical digest.
- Shadow mean competence equals the authoritative unit level to ≤ 1.1e-15 in every shadow.
- **Cross-checks:** M2 min W1 reproduces §U's `c = 1` continuity (E-gap 0.0211 / 0.0576 vs
  0.0214 / 0.0579), and M3 reproduces §U's competence assignment (0.091 / 0.179). This is
  as the mathematics predicts: with one-year memory, minimal entry is §U's continuity.
- Cells below show neolithic · pressure.

*Authoritative context.*

| | neolithic | pressure |
|---|---|---|
| farming unit-years | 325,766 | 102,200 |
| cultivation spells per unit id, p50 / p90 / p99 | 11 / 50 / 113 y | 8 / 44 / 122 y |
| turnover `τ` (labor new to work per year), p50 / p90 | 0.032 / 0.056 | 0.031 / 0.053 |
| fissions / fusions | 9,857 / 6,464 | 4,311 / 3,713 |

*The entry ledger* (mean entry hours as a share of capacity per farming unit-year, and
the share of farming unit-years infeasible, at `e = 50`):

| model | entry hours / C | infeasible | entrants / year |
|---|---|---|---|
| M0 proportional | 0.00081 · 0.00072 | 0.0001 · 0.0024 | 0.029 · 0.026 |
| M1 rotation | 0.00557 · 0.00528 | 0.0078 · 0.0621 | 0.204 · 0.193 |
| M2 min W1 | 0.00085 · 0.00151 | 0.0078 · 0.0621 | 0.031 · 0.055 |
| M2 retain W1 | 0.00047 · 0.00061 | 0.0029 · 0.0165 | 0.017 · 0.022 |
| M2 min W10 | 0.00009 · 0.00012 | 0.0025 · 0.0098 | 0.003 · 0.005 |
| M2 min H10 | 0.00034 · 0.00048 | 0.0074 · 0.0597 | 0.012 · 0.018 |

- **Continuity saves 70–85 % of rotation's entry labor**, but the amounts are small: about
  0.5 % of capacity for rotation at `e = 50`, and about 2.4 % at `e = 200`.
- **Universal participation is as cheap or cheaper over real histories.** M0 pays entry
  once per cultivation start. It costs the same as minimal continuity in neolithic
  (0.00081 vs 0.00085) and half as much under pressure (0.00072 vs 0.00151), where demand
  rises often. Measured over the spell, the entry cost does not favor concentration. Only
  the myopic first-entry choice does (Result 3).
- **Concentration meets infeasibility.** When demand rises near the cap, a concentrated
  unit cannot absorb its entrants' entry labor. That happens in 6.2 % of pressure farming
  unit-years under minimal continuity, against 0.24 % for M0. A physical version would have
  to displace production or broaden participation.
- **Sensitivity.** Entry labor scales almost linearly with `e` (ledger `e` = 1 / 10 / 50 /
  200 for M2 min W1: 0.00002 / 0.00016 / 0.00085 / 0.00376 of C, neolithic). The ranking of
  models is the same at every `e > 0`, and at `e = 0` everything is zero (indifference).
- **Indifference is common.** Under minimal continuity, 2–4 % of the unit could join at
  zero cost on an average farming year, and 28–30 % under W10. The `min` / `retain` choice
  is real, not a corner case.

*Competence* (participants minus others; same metrics as §U):

| model | E-gap p50 / p90 | E-gap > 0.05 / > 0.1 | yield effect p50 / p90 | splits / unit-year | lifetime p50 / p90 |
|---|---|---|---|---|---|
| M1 rotation | 0.002 / 0.006 · 0.001 / 0.004 | 0 / 0 · 0 / 0 | 0.2 % / 0.4 % · 0.04 % / 0.3 % | 13.4 · 12.1 | 0 / 1 y |
| M2 min W1 | 0.021 / 0.058 · 0.006 / 0.033 | 0.115 / 0.019 · 0.043 / 0.008 | 1.2 % / 4.4 % · 0.2 % / 2.1 % | 6.8 · 6.7 | 0 / 2–3 y |
| M2 retain W1 | 0.040 / 0.112 · 0.033 / 0.112 | 0.319 / 0.105 · 0.164 / 0.059 | 1.1 % / 3.3 % · 0.2 % / 1.9 % | 1.1 · 0.5 | 1 / 22 y · 4 / 32 y |
| M2 min W10 | 0.024 / 0.076 · 0.002 / 0.028 | 0.187 / 0.039 · 0.033 / 0.005 | 1.4 % / 4.4 % · 0.07 % / 1.4 % | 10.7 · 11.0 | 0 / 1 y |
| M2 min H10 | 0.053 / 0.124 · 0.013 / 0.064 | 0.444 / 0.148 · 0.113 / 0.026 | 2.9 % / 6.8 % · 0.4 % / 3.2 % | 5.1 · 5.6 | 0 / 3 y |
| M2 min W1 turnover | 0.019 / 0.050 · 0.005 / 0.029 | 0.083 / 0.013 · 0.037 / 0.007 | 1.1 % / 3.9 % · 0.2 % / 2.0 % | 13.1 + 13.8 · 11.8 + 13.7 | 0 / 1 y |
| M2 min W1, e = 200 | 0.020 / 0.056 · 0.006 / 0.032 | 0.110 / 0.018 · 0.042 / 0.008 | 1.2 % / 4.3 % · 0.2 % / 2.1 % | 6.8 · 6.7 | 0 / 2 y |
| M3 competence | 0.091 / 0.179 · 0.058 / 0.112 | 0.747 / 0.362 · 0.469 / 0.111 | 4.1 % / 8.1 % · 1.1 % / 4.6 % | 0.8 · 0.8 | 2–3 / 21–24 y |

- **Entry-cost continuity does not change §U's result.** With one-year memory, the gap,
  yield effect and churn are §U's continuity. The size of `e` is irrelevant to competence
  (e = 200 ≈ e = 50): the cost changes the ledger, not who practices.
- **Memory form is what matters.** Decaying memory (H10) orders entrants strictly by
  recency, so the same people continue. It roughly doubles to triples the gap (median
  yield effect 2.9 %), approaching competence assignment from history alone.
  - The 10-year window rotates the whole former pool through the proportional tie: it
    narrows the gap under pressure (0.002) and creates no lasting core.
  - `retain` keeps a fixed core (p90 lifetime 22–32 y) with a larger tail (E-gap > 0.1 in
    10.5 % / 5.9 % of unit-years). Its median yield effect is no larger, because more people
    participate.
- **Who participates still matters more than entry costs.** M3's median gap is 1.7–4.5× H10's
  and 4–10× W1's.

*Persistence after cultivation stops* (KM share not halved at 25 / 50 years): neolithic
0.81–0.87 / 0.41–0.46 for every M2 variant and M3 (§U: 0.86 / 0.46); pressure 0.21–0.36 /
0.00. τ = 0.05 shortens it (0.60 / 0.27; 0.08 / 0). **Entry costs do not prolong
persistence:** once cultivation stops, competence decays the same way whatever the
allocation rule was.

*Population turnover.*
- Turnover reduces the gap by about 12 % (0.0211 → 0.0186 neolithic) and doubles the
  churn (13.8 extra history splits per unit-year). It does not change the conclusions
  above.
- It does change the interpretation of long continuity. With `τ ≈ 0.032`, only half of a
  participating component's labor is the same people after about 22 years.
- In the runs without turnover, a lineage that keeps participating for decades (p90
  cultivation spell 44–50 y; `retain` cores to 32 y) is mostly its members' successors.
  Strata share the age structure, so those successors are implicitly the participants'
  own children. Without turnover, **long incumbency in anonymous strata is hereditary by
  representation, not by mechanism**. This limitation does not invalidate continuity over
  years to about a decade, and it does invalidate any reading of multi-generation
  occupational persistence.

*Representation.*

| model | components after merges (cap 16), mean | splits / unit-year | τ merges or coalescences |
|---|---|---|---|
| M0 | 8.1 · 12.4 (fusion only) | 0 | coalescences 41 k · 44 k |
| M1 rotation | 14.9 · 14.5 | 13.4 · 12.1 | 5.2 M · 1.6 M |
| M2 min W1 | 14.9 · 14.5 | 6.8 · 6.7 | 2.7 M · 0.9 M |
| M2 retain W1 | 14.7 · 14.2 | 1.1 · 0.5 | 0.49 M · 0.11 M |
| M3 | 14.8 · 14.4 | 0.8 · 0.8 | 0.39 M · 0.14 M |
| M2 min W1, τ = 0.01 | ≤ 13.6 · ≤ 10.7 | 5.5 · 3.8 | 2.0 M τ / 0.21 M · 0.49 M τ / 0.01 M |
| M2 min W1, τ = 0.05 | 5.0 · 3.4 (p90 9 · 6) | 1.5 · 1.0 | 0.61 M τ / 1 · 0.14 M τ / 0 |

(Counts after the year's merges are `min(pre-merge count, capacity)` from the saved
pre-merge counts; exact without a τ merge, an upper bound with one. The probe now records
them after merging.)

- **Entry-cost continuity halves rotation's churn, and `retain` cuts it 12×. Every rule
  except a divergence merge still fills the capacity.** Reduced churn under `retain` and
  M3 means stable cores, which is exactly the lock-in §24 warns about, not better science.
- **τ = 0.05 remains enough**: 5.0 / 3.4 components with no forced coalescence, keeping the
  p90 dispersion (0.0446 vs 0.0489 neolithic).

*16 vs 32.*
- Gaps, yield effects and persistence are identical at 16 and 32 (M2 min and M2 retain).
  Within-unit dispersion differs by under 3 %.
- Doubling the capacity doubles splits and coalescences, and the redundant pairs grow
  3–4×. As in §U, resolution does not drive the scientific distributions.

*Coalescence metric.*
- The slope-weighted K-distance ranks pairs exactly as efficiency loss does (median
  Spearman 1.00 in every shadow). Merging by plain K-distance loses 1.3–9× more efficiency
  variance. §U's conclusion holds under entry-cost continuity.
- **History matters for equivalence when memory is longer than a year.**
  - Under W10, 0.23 · 0.18 pairs per unit-year have near-equal competence (|ΔE| < 1e-3) but
    a different entry-cost class. A competence-only metric would merge components whose
    future entry costs differ.
  - Under W1 there are none, because one-year history coincides with current status.
- The shadow merged only within the same class: no forced coalescence had to cross
  classes. Merges of different `since` within a class (e.g. W10 incumbents 2 and 7 years
  idle) are frequent and approximate the history by a share-weighted mean.

*Clearing.* Nothing in 5C attributes clearing; H2 equals H1, and `field_claim_continuity`
stays off.

**Recommendation: B** (entry costs explain continuity, not initiation), with a D caveat on
magnitude.
- **Initiation** is §U's corner: maximal concentration for every `e > 0`, indifference at
  0. A strict subset enters only under a myopic unit-level coordination assumption. Over
  real histories, universal participation costs the same entry labor (neolithic) or half
  (pressure), with far fewer infeasible years.
- **Continuity** is explained relative to rotation: entry costs put incumbents before
  newcomers and save 70–85 % of rotation's entry labor. They leave how many incumbents to
  keep undetermined, and the outcome then depends on memory form and tie convention.
  Allocation hysteresis is convention-made except under decaying memory.
- **Consequence:** with one-year memory, entry-cost continuity reproduces §U's small gap
  (median yield effect 1.2 % / 0.2 %). Decaying memory raises it to 2.9 % / 0.4 %. The size
  of `e` does not matter.
- **Not E**, provided turnover is stated. Over about a decade, persistence is causal (entry
  cost plus learning). Beyond about one generation, anonymous strata make it hereditary by
  representation.
- **What remains unexplained:**
  - why a unit would start with a subset rather than everyone (the coordination
    assumption);
  - how many incumbents to keep when demand falls;
  - which memory form, if any, is real;
  - the physical cost of infeasible entry (displacement), which is not modeled.
- **If anything is carried forward:** a decaying-memory entry cost as the continuity
  hypothesis, a turnover term, a τ divergence merge, and a slope-weighted coalescence
  metric that also respects entry-cost class.
- Reviewed and accepted (2026-10-09).


### §W. Stage 5D — causal opportunity differentiation audit (2026-10-09)

**DESIGN AND AUDIT ONLY.** No production code, no shadow mechanism. One read-only probe
(`scripts/probes/exposure_audit.py`) reads the event stream of plain runs. Starting point
`4eb4d55` (Stage 5C).

**Question.** What concrete event or process can make initially equivalent people within a
unit meet different opportunities, gain different experience, and eventually differ
persistently? This stage is about the *origin* of differentiation, not its persistence.

**Answer.** Nothing in the current simulator gives different subsets of one unit
different opportunities. Location, access, knowledge, technology, contact and activity
decisions are all aggregated to the unit. The strongest candidate is a technique reaching
some people before others. It has a real modeled event, but the timing evidence suggests
the exposure would usually be gone before practice begins. **Recommendation: D.**

#### Audit of within-unit opportunity representation

| Domain | What the code represents | Within-unit subset? | Evidence |
|---|---|---|---|
| Location | one cell per unit; migration moves the whole unit | no | `unit.py:266`; `migration.py:172` ("Whole-group moves only; selective emigration arrives with distributional units") |
| Foraging access | the unit's current cell only; per-cell access fractions | no | `foraging.py:296`, `:383-393` |
| Fields | `fields_ha`, one scalar per unit; arable shared pro rata per cell | no | `unit.py:290`; `agriculture_kernel.py:140` |
| Familiarity | one value per unit and cell | no | `familiarity.py:66`, `:84-93` |
| Labor and activities | aggregate hours; cap on hours (`m = 0.9`), none on headcount | no | `agriculture.py:323-337`; `foraging.py:314-320` |
| Technology | Boolean set per unit; invention adds it to the whole unit at once | no | `innovation.py:75` ("No specialists yet; innovation is a property of the whole group"), `:146-163`; `system.py:11-16` |
| Knowledge | one vector per unit; learning from unit activity shares | no | `learning.py:366` ("all members practice in proportion to labor") |
| Diffusion and adoption | unit-unit contact weights (same cell, adjacent, trade ties); every contact counts every year | no | `diffusion.py:30-47`, `:204-214` |
| Information | unit-unit encounters pass 8 reports about cells | no | `exploration.py:709-781` |
| Trade | unit-unit food balance; partners by proximity | no | `trade.py:106-151` |
| Demography | age × sex cohort counts; binomial deaths and births | counts only; nothing records who | `demography.py:90-116` |
| Fission | departing members drawn binomially per age/sex cohort; the daughter copies knowledge, technology, beliefs and strata shares | **yes, the only subset draw**, representative in everything but age/sex | `groups.py:93-102`; `lifecycle.py:71-136` |
| Fusion | sums cohorts; population-weighted means; strata concatenate | between-unit only | `lifecycle.py:156-235`; `strata.py:212-230` |
| Strata | `share`, `field_claim`, `store_claim`; age structure shared; nothing authoritative reads them | passive | `strata.py:9`, `:200-205` |
| Turnover memory | knowledge, technology and familiarity are unit properties; no per-age skill | — | `life_history.py:141` ("Skill is not modeled separately from labor") |

- **Subset events that exist:** deaths, births and fission. Only fission separates people,
  and it is representative: who leaves differs from who stays only by age and sex.
- **Existing quantities that count people:**
  - the practitioner term `N·s` in learning (a scalar);
  - crowding contact population;
  - the reproductive-pair check for fusion.

  None selects a subset.

#### Timing evidence (read-only probe; neolithic 600 y, pressure 400 y, seeds 0–3)

| | neolithic | pressure |
|---|---|---|
| `plant_cultivation` gained by invention / adoption / fission copy / fusion union | 38 / 205 / 9,305 / 4 | 38 / 101 / 3,959 / 10 |
| population at invention, p50 / p90 (one discoverer ≈ 1/N) | 28 / 41 (0.036) | 28 / 40 (0.036) |
| years from invention or adoption to first cultivation, p50 / p90 / max | 16 / 60 / 114 | 8 / 34 / 58 |
| cultivation in the year of acquisition | 0 % | 0 % |
| acquired but never cultivated | 34 of 243 | 20 of 139 |

- About 97 % of holders get the technique by fission copy. Only a few dozen units per run
  discover it or adopt it from a contact.
- **Knowing comes years to decades before practice.** What starts cultivation is the
  return comparison (`fields_toward_target`), not access to the technique.

#### Candidate symmetry-breaking families

**A. Localized opportunity or exposure.**
- No substrate. A unit is in one cell, fields are a unit scalar, and foraging uses only
  the current cell.
- Partial exposure would need subsets placed in space (plots, trips, positions): new
  spatial granularity inside the unit.

**B. Finite participation opportunities.**
- No headcount limit exists anywhere; only hours and land are limited.
- Stages 5B and 5C showed that a limited amount of work does not choose its participants.
  A capacity alone needs a selection rule, which is the problem itself.

**C. Uneven knowledge transmission.**
- The events exist: invention is a discrete stochastic event with a modeled hazard, and
  adoption is a discrete draw per contact. A discovery is plausibly made by a few people.
- But the representation applies them to the whole unit instantly. Supporting a subset
  needs the ontology split that `system.py:11-16` already names: *availability* (the unit
  holds the technique) versus *who knows it*.
- Timing evidence: the exposure would most plausibly be gone within a few years, while
  practice starts a median 8–16 years later. It binds only if within-unit spread is slow
  or happens only through practice. Both are new assumptions; the second reduces back to
  who practices (5B/5C).

**D. Contact and interaction history.**
- Contacts are unit-level weights with no headcount and no subset travel.
- A subset meeting outsiders would need subset contacts, which is effectively a social
  network or expeditions. Too early.

**E. Movement and recombination.**
- Fission is the only real subset draw, but it is representative and creates differences
  *between* units, not within.
- Selective fission (who leaves depends on experience) is a hypothesis.
- Fusion is already the known source of differences, and it is excluded as an answer to
  within-unit origin.

#### Stochastic encounters and statistical symmetry

- **Legitimate:** a modeled event (an invention, a contact) involves `k` of `N` people,
  every member equally likely. Statistical symmetry holds before the event, and realized
  symmetry breaks after it.
- In the mixture representation the exposed share `k/N` is taken *in proportion from
  every component*. That is the expected value, so no component is picked at random and
  no identity is created.
  - Randomness stays where the model already has it: whether the event happens (the
    hazard).
  - Randomness about `k` would be a stated hypothesis (e.g. a small number of
    discoverers).
- **Artificial:** dividing a homogeneous unit into classes by a random draw with no event
  behind it. Rejected, as in every earlier stage.

#### Ranked comparison

| Criterion | C uneven transmission | E fission / recombination | B finite opportunities | A localized exposure | D contact history |
|---|---|---|---|---|---|
| Causal grounding | invention and adoption are modeled events; a finite number of discoverers is plausible | binomial cohort draw exists | none: hours, not positions | none in code | none in code |
| Breaks within-unit symmetry | yes (realized, statistically symmetric) | no (between units) | no (needs a selection rule) | yes, if positions existed | yes, if subset contacts existed |
| Existing substrate | events exist; no knower share | high | hours caps only | none | none |
| Persistence | weak: knowledge precedes practice by 8–16 y (p50) | via separate units | — | — | — |
| Epoch generality | high (literacy, metallurgy, machinery) | high | high | high | high |
| Minimal new state | one knower share per unit per technique | none (selectivity is a hypothesis) | positions | within-unit positions | subset contact records |
| Representation risk | low: acquisition events are rare (≈ 35–60 per run); no split needed until consequences differ | none | high (5B/5C churn) | high | high |
| Demographic coherence | good if new workers start as non-knowers and learn | n/a | — | — | — |
| Assumptions | number exposed; within-unit transmission rate; whether knowing gates practice | what makes leavers differ | the selection rule | spatial structure inside a unit | network structure |

Ranking: **C > E > B > A ≈ D**. None is ready for implementation. C is the only one
grounded in an existing event that could break symmetry within a unit.

#### The smallest causal event (candidate C), specified

1. **What happens:** a unit invents a technique, or adopts it through a contact. A small
   number of its people know it first.
2. **Why:** the invention hazard and the adoption draw already exist; a discovery is made
   by someone.
3. **Why only part:** an invention or a contact involves a finite number of people, not
   the whole unit.
4. **Affected fraction:** `k/N` with `k` the number of discoverers or contact
   participants. This is a hypothesis: the model has no headcount for these events.
   Taken in proportion from every component.
5. **What differs immediately:** who knows the technique. Competence, claims and
   everything else are unchanged.
6. **Why it could persist:** only if knowing gates practice and practice builds
   competence (5B), and if entry costs keep the same people practicing (5C).
7. **Convergence:** within-unit transmission (a new rate), and turnover (new workers start
   as non-knowers).
8. **Turnover:** knowledge is not inherited by birth. New workers (≈ 3.2 % of labor a
   year, §V) start unexposed and learn from the unit at large, so no successor silently
   inherits a predecessor's experience. Teaching that favors knowers' own children would
   be a further hypothesis.

**Why this is not a stratum generator.** The event exists before any split. It is driven
by the existing invention or adoption hazard, and it fixes an observable quantity (a
knower share). A component would split only when that share changes what someone does,
for example when cultivation needs more people than know the technique.

**Meaningful consequences:**

| Consequence | Status |
|---|---|
| Practice history | only if knowing gates practice (hypothesis) |
| Competence | through practice (existing rule, 5B) |
| Resource access, contribution, asset control | none modeled (H2 = H1; claims passive) |
| Future opportunity | through 5C entry costs (hypothesis) |

**Minimal state:** one knower share `q ∈ [0, 1]` per unit for the technique, not a
stratum split. It follows fission (binomial knowers, proportional in expectation) and
fusion (population-weighted). A stratum split happens only when `q` limits participation.

#### Representation and turnover

- **Split rule:** split a component only when an event gives part of it a different
  *action* (practice), not merely a different exposure. Both parts inherit identical
  competence and claims.
- **Store state or consequences?** Store the exposure as a unit scalar `q` and represent
  its consequences through components only when they occur. This avoids 5B/5C's splitting
  every time practice changed.
- **Merge rule:** components with the same knowledge status and near-equal competence (the
  slope-weighted metric, §U/§V) may merge. Different status may not.
- **Fission and fusion:** `q` is copied in expectation and population-weighted on fusion.
  The knower status of components is carried with them.
- **Turnover:** each year a share `τ` of labor enters unexposed and learns at the
  within-unit transmission rate. Without such a rate the current model implicitly
  transmits instantly and perfectly. That is today's whole-unit assumption, and it is what
  makes acquisition unit-wide.

#### Epoch-general interpretation

Someone encounters a technique before others: a farming method, a craft, writing, a
machine. The same event (partial exposure at discovery or contact, then transmission
inside the group) is the general primitive. Cultivation is the first case.

**Recommendation: D. No convincing initiation mechanism yet.**
- The simulator has no within-unit opportunity differentiation (audit). Inventing one
  (positions, places, networks) would be manufacturing.
- The best-grounded candidate (C) is plausible and epoch-general. Its effect on who
  cultivates depends on two unmodeled quantities: how many people an invention or contact
  exposes, and how fast a technique spreads inside a group. The timing evidence (practice
  8–16 years after acquisition) suggests the exposure is usually gone before it matters.
- **Recommended Stage 5E (narrow):** a falsification test of C before any design.
  - A read-only shadow keeps `q` per unit for `plant_cultivation`:
    - start at `k/N` at invention (`k` = 1 and a small sweep);
    - copy it on fission (expectation) and weight it on fusion;
    - new workers enter unexposed at the measured `τ`;
    - within-unit transmission is swept over half-times from 1 to 20 years (sensitivity,
      not calibration).
  - Measure how often `q < f_min` in farming unit-years, i.e. whether knowledge would
    ever bind who cultivates.
  - If it rarely binds at plausible half-times, reject C for cultivation and record that
    initiation needs a different domain or a representation change (spatial or contact
    subsets).
- No splitting, no activation, no new canonical parameter. The physical-feedback gate
  stays closed.
- Pending scientific review.

---

## 3. Open questions

- **First endogenous differentiator (§T).** Practice concentration under finite demand
  needs an initiation hypothesis (per-participant cost, experience-based assignment, or
  anticipatory allocation) before any design is activated. Stage 5B (§U): overhead alone
  gives a corner solution; assignment (continuity or competence) matters more than the
  degree of concentration; the consequence is small under continuity. Stage 5C (§V): entry
  costs explain continuity relative to rotation but not initiation (same corner); how many
  incumbents to keep, the memory form, and the coordination assumption remain open. Stage 5D
  (§W): the simulator has no within-unit opportunity differentiation; the best-grounded
  origin is partial exposure at technique acquisition, which timing suggests is transient;
  a falsification test is proposed.

- **Cause of differentiated clearing or plot extension.** Whether new land follows labor
  (H1/H2) or control (H3) needs a named lower-level cause (plot extension,
  household-differentiated clearing labor, decision influence over clearing); p would be
  derived from it (§S, §N).
- **Mechanism-aware coalescence metric (§M6 C).** Needed before any reader of persistent
  `field_claim` or `store_claim`; candidate next step alongside the cause above (§S).
- **Private return to effort / labor differentiation (§N).** Whether some non-pooled access
  should exist so labor contribution can differ; otherwise labor stays ∝ share.
- **Pooled-deficit coverage.** Pro rata coverage of negative pre-pool shares
  (`pooled_leftover_shares`) is a convention; any other allocation is an institution.
- **Rationing / withdrawal decision.** Whether a collective decision to withdraw less than
  the deficit should exist; it would make claim-sensitive access repeatable (§Q).
- **Purpose for retention.** Seasons or a lean period, seed requirements, a cost of low body
  reserves, or expectation formation from `harvest_history`; only then is a reserve rule
  meaningful, tested in a branched simulation (§R).
- **Heterogeneous body reserves.** Reserves stay ∝ share, exact while access is pooled;
  revisit if food access differs by stratum.
- **Stratified demography trigger.** Reconsider only when an implemented mechanism produces
  meaningful stratum differences in fertility conditions, mortality exposure, food access
  relevant to either, or workload with demographic consequences; options are per-stratum
  vital-rate effects on `share`, or `[U,S,sex,age]` cohorts (§1.3).
- **Adaptive merging (§M2)** and a canonical nonzero w: only with a mechanism or an MVP 3
  scientific baseline and its provenance.
