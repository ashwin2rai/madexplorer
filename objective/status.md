# Implementation Status — MVP 3 (staged)

**Updated:** 2026-10-03 (Stage 4B)\
**Current scientific base:** MVP 2.1 frozen; pre-MVP 3 consolidation complete\
**Current milestone:** MVP 3 — staged socioeconomic differentiation

## MVP 3 stage handoff

**Completed:** Stage 4B — strata resolution hardening (design §O).

**Scientific behavior:** unchanged. At capacity 8 the strata sidecar is bit-identical to
Stage 4A in six full runs (19,422 coalescences). The Stage 3B/3C fixtures are unchanged and
the MVP 2.1 oracles are identical.

**What changed:**
- **Configurable capacity:** `strata.max_strata` is configurable per run (1..127, default 8,
  in `config_hash`, not in `static_key`). It is owned by `PopulationStore` and its
  fixed-width `StrataTable`, and the module global `S_MAX` is gone.
- **Bounded duplicate validation:** chunked, over active counts. Peak temporary on 50k rows
  is 0.7 / 1.3 / 4.0 MB at 8 / 16 / 32 (was 21 MB at 8).
- **Vectorized capacity coalescence:** the same rule, bit-identical to the retained scalar
  reference (a differential oracle). Speed-up is 1.4× / 3.7× / 5.9× at 8 / 16 / 32.
- **Per-dimension error reporting:** `field_error`, `store_error` and `combined_error` on
  every coalescence record and sidecar event, aggregated by `scripts/probes/strata_capacity.py`.
- **Physical isolation re-verified:** across capacities and w, physical outputs are
  identical.

**Default:** still 8, pending review.

**Sensitivity** (4 seeds; neolithic / pressure; w = 0):

| `max_strata` | at capacity | field error Σ | field distance vs 32 (p99) | w moves field repr. (p50) | run time vs 8 |
|---|---|---|---|---|---|
| 8 | 9 % / 32 % | 0.19 / 0.35 | 0.018 / 0.032 | 0.0061 / 0.0091 | — |
| 16 | 5.7 % / 26 % | 0.034 / 0.065 | 0.006 / 0.013 | 0.0023 / 0.0038 | +3 % / +6 % |
| 32 | 3.7 % / 21 % | 0.006 / 0.012 | — | 0.0007 / 0.0014 | +9 % / +24 % |

Coalescences still rise with capacity (demand is open-ended). Error falls about 6× per
doubling, and pooling totals at 16 are within 1e-3 to 6e-3 of 32.

**Recommendation:** CHANGE TO 16 at review. That would need new versioned strata fixtures at
16; the 3B/3C fixtures stay at 8.

**Physical-feedback gate:** not cleared. Capacity reduces but does not remove the w coupling,
and no physical mechanism is proposed whose information needs can be tested.

**Next stage:** PAUSE FOR REVIEW. Stage 4C is not authorized.

**Do not forget:**
- no differentiated labor exists;
- no reason for labor to differ has yet been modeled;
- adaptive merging remains deferred;
- the capacity metric remains numerical and mechanism-agnostic (equal field/store weights);
- `field_output_claim_weight` default 0.

---

### Stage 4A — labor and resolution design (previous handoff)

**Completed:** Stage 4A — labor and resolution design (design §N; probe
`scripts/probes/strata_capacity.py`).

**Production behavior:** unchanged (design, audit and probe only).

**Labor findings:**
- **One labor pool per unit:**
  - capacity = cohorts × age-labor curve × `foraging_hours_per_day` × 365;
  - clearing (charged as next year's debt) takes it first, then cultivation (capped at
    0.9 of the remainder), then foraging;
  - storage, trade and migration use no labor;
  - work has no energetic or demographic cost.
- **No stratum-differentiated labor is justified by any modeled variable.** Capacity comes
  from the shared age structure, knowledge and technology are `[U]`, and consumption is
  pooled. Field- or store-linked labor rules would bring in household tenure without pooling,
  authority, or private access.
- **Candidate first quantity:** per-activity hours contributions (cultivation, clearing) as
  a transient flow, not `StrataTable` state. ∝ share today, and it cannot create strata;
  that is acceptable.

**Resolution findings** (`S_MAX` 4 / 8 / 16 / 32, 4 seeds, two scenarios):
- coalescences *rise* with capacity, because demand is open-ended (each fusion concatenates
  positions);
- representation error falls about 6× per doubling, and w's redirection of the field
  distribution about 2.6×;
- aggregate observables are flat;
- persistent memory is 32·S + 1 B/row (51 MB at 50k units for 32, about 2 % of RSS);
- runtime is +8–33 % at 16 and up to 3× at 32 (pure-Python coalescence).

**Locked decisions:**
- homogeneous populations may stay homogeneous; no invented differentiation;
- labor is quantitative and per activity (hours); no occupations or rank;
- labor contribution is a flow, not persistent state;
- gate: no physical mechanism reads strata until the resolution policy is shown stable for
  the information it uses;
- the generalized attribution `(1 − w)·cultivation_labor_share + w·field_claim` (identical
  today);
- `field_output_claim_weight` default 0;
- adaptive merging stays deferred; exact compaction only, no epsilon merge.

**Next stage (at 4A):** Stage 4B — Resolution hardening (done):
- capacity as a run parameter (`strata.max_strata`, default 8);
- vectorized capacity coalescence;
- chunked duplicate check;
- per-dimension coalescence error in the sidecar;
- re-run the capacity sensitivity to choose a default (16 the candidate).

Strata stay passive; oracles identical.

**Gate before physical socioeconomic feedback:**
- the resolution policy is shown stable for the dimensions the mechanism reads, and the
  coalescence metric protects them (§M6 C);
- an approved causal reason for stratum-differentiated labor or access (Stage 4D design
  review);
- 4C labor accounting is bit-identical first.

**Deferred:** hierarchy; unequal consumption; stratified demography; approximate adaptive
merging; work-related energetic or demographic costs.

---

### Stage 3D — scientific and representation review (previous handoff)

**Completed:** Stage 3D — scientific and representation review (design §M; probe
`scripts/probes/strata_review.py`).

**Production behavior:** unchanged (probe and documentation only; one test docstring
caveat).

**Findings:**
- **Representation load is real:** in the frozen reference runs (4 seeds), 9–10 %
  (neolithic) and 32–33 % (pressure with cultivation) of unit-years sit at `S_MAX`; capacity
  coalescence is routine (≈ 9k per 4 runs) and 82–93 % of merges join distinct field
  positions. Strata per unit-year: mean 2.2 / 3.8, median 1 / 2. Memory is fixed (padded);
  the hook is 8–13 % of run time.
- **Most extra strata are small modeled differences,** not dust: about 20 % have a dust twin
  (≤ 1e-12); most sit 1e-3 to 0.1 from their nearest neighbor.
- **The pooling nonlinearity in w is intended:** short years are linear; fed years add one
  hinge per stratum whose pre-pool leftover crosses 0 at `w* = (L/gY)·s/(s − f)`. The curve
  from the w = 0 records reproduces runs within 4e-16. It is continuous, nothing structural
  changes, and it is concentrated in a few unit-years.
- **Fusion is the only source of differentiation.** Without fusion, units never differentiate
  (checked at w = 1). Store differences fade in about 2 y; field differences fade with field
  expansion (median halving 11 y) or at once on migration. w only maps field memory onto
  stores.
- **Capacity coalescence lets w leak into field representation** (corrects §L15). Where w
  redirects a merge (12 % / 42 % of multi-strata unit-years), the field distribution moves by
  a median of 11 % of the unit's field dispersion (p99 42 %). Aggregate field dispersion is
  unchanged; no invariant is violated.

**Adaptive merge decision:** DEFER. Greedy coalescence already merges dust first, so it
would not reduce loss. There is no memory gain. The binding constraint is distinct positions
above `S_MAX`, which is a resolution-policy question.

**Current interpretation of socioeconomic strata:**
- memory of fused predecessor groups, not self-sustaining differentiation;
- positions decay toward 1 under the neutral conventions;
- w is a sensitivity parameter standing in for missing labor and property mechanisms.

**Next scientific stage (at 3D):** Stage 4 — Stratum labor contribution (design first; candidate B) — designed in Stage 4A.

**Reason:** labor ∝ share is the assumption behind both new land ∝ share and w; labor and
specialization is the lower-level process MVP 3 intends to represent; and resource access
(A) or influence (C) would act on transient fusion memory. The design must first name a
causal reason for labor to differ by stratum under pooled consumption, with no
rich-get-richer, rent or inheritance rule. Pause for review before implementing.

**Do not forget:**
- `field_output_claim_weight` default remains 0;
- no canonical nonzero w has been selected;
- differentiation comes only from fusion and decays (stores in years; fields with expansion
  or migration);
- capacity coalescence is frequent under farming pressure and its joint (field, store)
  metric lets w alter represented field claims. Revisit it (mechanism-aware and error-aware,
  plus `S_MAX` sensitivity) before any physical mechanism reads claims.

---

### Stage 3C — crop-output attribution sensitivity (previous handoff)

**Completed:** Stage 3C — crop-output attribution sensitivity (design §L4–§L6, §L15).
Earlier stages: 3B neutral accounting (below), 3A audit, 2.1 exact compaction, 2 passive
heterogeneous strata, 1 neutral representation.

**Scientific hypothesis introduced:** `field_output_claim_weight` (w,
`strata.field_output_claim_weight`, rule `crop_output_attribution`, heuristic). It is the
fraction of crop-output attribution that follows field control rather than the
population/labor baseline: `d_i = g·w·Y·(field_claim_i − share_i)`. It is not an
extraction rate, rent, tax or hierarchy coefficient.

**Default:** 0.0 (the neutral legacy limit; Stage 3B bit for bit).

**Physical feedback:** none. Across w, unit state, metrics, events, ecology, RNG states and
population are identical (tested); the MVP 2.1 oracles are IDENTICAL.

**What nonzero w changes:**
- crop-output attribution (`d_i`);
- pooling-transfer accounting: a harvest component (`−d_i` in short years; pro rata
  coverage of negative pre-pool leftovers in fed years) beside the store component;
- claims on newly stored food (new stores follow the allocated leftover).

**What it does NOT change:**
- field claims (identical across w as a distribution);
- actual consumption, food ratio, reserves;
- labor (still ∝ share — w is conditional on that simplification);
- demography;
- unit physical state.

**Sensitivity results** (neolithic seed 0, 400 y; `scripts/probes/crop_attribution_sensitivity.py`):

| | w = 0 | 0.25 | 0.5 | 1 |
|---|---|---|---|---|
| final field \|pos − 1\| (people-weighted) | 0.0254 | 0.0254 | 0.0254 | 0.0254 |
| final store \|pos − 1\| | 0.0146 | 0.0241 | 0.0339 | 0.0534 |
| final corr(field, store) | 0.11 | 0.20 | 0.27 | 0.33 |
| crop attribution moved / crop of differentiated units | 0 | 0.41% | 0.80% | 1.59% |
| harvest pooling volume (kcal) | 0 | 1.5e6 | 3.7e6 | 2.6e7 |
| store pooling volume (kcal) | 4.7e6 | 5.7e6 | 6.7e6 | 8.6e6 |
| exact compactions / capacity coalescences | 286 / 12 | 260 / 16 | 256 / 16 | 253 / 14 |

- The field-position series is identical across w (max difference ≤ 1.4e-17); dilution of
  fusion-born field inequality by new land (∝ share) is independent of w.
- While field inequality exists, store positions respond roughly linearly in w and
  correlate more with field positions. Controlled probe: a minority holding 2.5× its share
  of land reaches store position 1.36/1.71/2.42 after one year at w = 0.25/0.5/1, against
  1.0 at w = 0. Both fade as land expands (≈ 1.0 by year 40).
- Field heterogeneity appears only after ≈ year 200 (farming), so effects are late and
  small in the canonical run.
- With w > 0 store positions coincide less often: fewer exact compactions and slightly more
  strata (final mean 1.56 → 1.65 per unit).
- Cost: the accounting hook is ≈ 0.38 s of a ≈ 4 s 400-y run at every w (no marginal cost
  of nonzero w beyond noise). `bench-quick` 95.8 ms/tick (before: 99.7–107).

**Limitations found:**
- The strata grouping (compaction, coalescence) is joint in `(field, store)`, so w can
  change the number of components. Field claims are unchanged as a distribution. Capacity
  coalescence could, in principle, then merge different field positions differently (not
  observed).
- Energetics stores either all leftover or none, so partly discarded surplus never occurs
  physically. The formula handles it and is tested directly.
- In fed years with every pre-pool leftover ≥ 0 there is no transfer: each stratum keeps its
  attributed surplus.

**Validation:**
- `make check` 664 passed; `make test-stat` 3/3.
- Raw and logical MVP 2.1 oracles IDENTICAL; golden fixtures unchanged.
- Stage 3B fixture unchanged at w = 0 (flows digested on the Stage 3B columns, which keep
  their order).
- New: `tests/test_strata_attribution.py`, fixture `stage3c_w0.5_seed11_30u_40y.json`.
- `config_hash` changes (the new `strata` section); this is metadata, not state.

**Next (at 3C):** pause for scientific review — done in Stage 3D.

**Do not forget:**
- no canonical nonzero w has been selected;
- the Stage 3B w = 0 fixture remains authoritative;
- adaptive approximate merging remains unimplemented;
- actual resource-access inequality remains future work.

---

### Stage 3B — neutral socioeconomic accounting (previous handoff)

**What now exists (Stage 3B)**
- **Gross food accounting:** transient per-step `FoodAccounts` (`K0`, `A`, `X`, `K1`) and
  `FieldAccounts` (`F0`, `F1`), recorded by energetics and field planning and consumed by
  `account_strata` after each subsystem.
- **Neutral field-claim accretion** (`field_claim_accretion`): new land ∝ share; shrink keeps
  fractions; zero → share.
- **Neutral store-claim accretion** (`store_claim_accretion`): new stores ∝ share;
  proportional depletion (withdrawal, spoilage, trade out, abandonment) keeps fractions;
  zero → share.
- **Explicit pooling transfers** (`food_pooling_transfer`, observational):
  `X·(share − store_claim)` in deficit years; zero-sum within `2e-12·X`.
- **Sidecar:** `strata_flows` (`strata_flows.csv`).
- **Regression fixture:** `tests/regression/golden_strata/stage3b_seed11_30u_40y.json`
  (re-record only with `UPDATE_STRATA_FIXTURE=1`; not a scientific baseline).
- **Probe:** `scripts/probes/food_flow_audit.py --heterogeneous`.

**Scientific feedback into the unit simulation:** none. MVP 2.1 oracles identical.

**Important neutral conventions (not historical claims):**
- new cultivated land is allocated by population share; field shrinkage preserves claim
  fractions;
- new stored food is attributed by population share; store depletion is proportional;
- pooled access is proportional to share;
- body reserves remain unit-level. Revisit only if a later mechanism introduces genuinely
  unequal caloric access.

**Observed consequences** (neolithic seed 0, 400 y, and the probe):
- Neutral accretion dilutes fusion-born differences: new land and new stores go by share, so
  positions drift toward 1. At year 400 the people-weighted mean |position − 1| is 0.018
  (field) and 0.008 (store). In the probe, a field position of 2.5 falls to ≈ 1.1 within
  ≈ 25 years as fields expand.
- Unequal store claims meet deficit years in 126 unit-years (pooling volume ≈ 4.7e6 kcal over
  the run).
- Resets on empty stocks make components coincide more often: 286 exact compactions; capacity
  coalescences fall from 36 to 12.
- Cost: `account_strata` ≈ 7% of a 400-y run (≈ 53 µs per call, 17 calls per step), mostly
  the generic zero-stock pass. Restricting that pass to stock-changing subsystems would halve
  it (not done). `bench-quick` 99.7–107 ms CPU/tick (noise); no new persistent memory.

**Next (at 3B; done in 3C):** Stage 3C — crop-output claim sensitivity. Stage 3C had to
decide and test:
- `field_output_claim_weight` (w, design §L4), introduced as an explicit scientific
  hypothesis;
- `w ∈ {0, 0.25, 0.5, 1}` as controlled sensitivity cases, with the general harvest term
  `g·w·Y·(field_claim − share)` in attribution, leftover allocation and pooling transfers;
- persistence or dilution of fusion-born field inequality under each w;
- still no actual consumption inequality.

**Deferred question:** should body reserves become heterogeneous once actual food access does?

**Stage 3A locked decisions** (§L; implemented at w = 0 in Stage 3B)
- Food flows are not a fungible pool:
  - fed units eat from harvest and store the leftover;
  - short units eat harvest, then stores, then reserves;
  - a unit never both adds to and withdraws from stores in one year;
  - trade donors and recipients are disjoint;
  - pre-trade `harvest = crop + forage` bitwise.

  Verified by `scripts/probes/food_flow_audit.py`.
- `fields_ha` changes only in field planning (F0 → F1), migration (→ 0), fission and fusion.
- Land: new land ∝ share; loss proportional; zero → share; normalize by Σ absolute.
- Parameter `field_output_claim_weight` (w, replaces `field_entitlement_weight`):
  `crop_output_share = (1−w)·share + w·field_claim`. It is an attribution basis before
  pooling, not an extraction rate. w = 0 is the neutral legacy limit; probes use
  0/0.25/0.5/1; no canonical nonzero value.
- Pre-pool attribution: forage, trade received and reserves ∝ share; crop per w; trade given
  ∝ the unit's pre-trade attribution (from harvest) or ∝ store_claim (from stores);
  withdrawals ∝ store_claim.
- Pooling stays the MVP 2.1 behavior (need and reserves ∝ share). The recorded
  `pool_transfer_i = post-pool − pre-pool` sums to 0 and carries no institutional label.
- Store claims: depletion proportional; new stores (fed years only) ∝ allocated pre-pool
  leftover `ℓ_i = L·share_i + g·w·Y·(field_claim_i − share_i)`, with negative ℓ covered pro
  rata; zero stores → share.
- Gross flows come from a read-only per-step `FoodAccounts`, filled by the trade and
  energetics apply, never from `K1 − K0`.
- Numerics: convex or self-normalized updates in difference form; no thresholds on
  positions; exact compaction after updates; no epsilon merge.
- Baseline: MVP 2.1 oracles stay frozen and identical through 3B/3C; add versioned sidecar
  fixtures only; the next full baseline comes when strata change unit outcomes.

**Still unresolved:**
- how pooled deficits are covered (pro rata for now);
- whether new land should ever follow control rather than labor;
- whether body reserves should stay ∝ share once access differs (Stage 6A).

**Stage 2.1 (exact compaction) in brief.** Within one unit, components at exactly the same position
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
- Crop-attribution weight `field_output_claim_weight` (Stage 3A, §L4): neutral 0 = the
  legacy equal-pooling limit. Nonzero values are hypotheses and sensitivity cases, never
  tuned. A reference value is set only with an MVP 3 baseline.
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
- `field_output_claim_weight` = 0 remains the legacy neutral limit.
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
