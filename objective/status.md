# Implementation Status — MVP 2.1 → MVP 3 Handoff

**Updated:** 2026-10-02  
**Current scientific base:** MVP 2.1 frozen; pre-MVP 3 consolidation complete  
**Next milestone:** MVP 3 — Distributional Society

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
- Next: **design the socioeconomic-strata schema and its lifecycle semantics before
  implementing any MVP 3 mechanism.**

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
  allocation. `SimulationState.units/table/belief_store` are read-only views. MVP 3's
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

1. **Sustained growth.** Why does the frozen model sustain ~0.9–1.1% annualized net growth
   over ~600 years in the reference seeds despite its ecological and demographic feedbacks?
   *Diagnostic audit (2026-10-02, `scripts/probes/demography_audit.py`, seeds 0–3 ×
   600 y; reproduces the manifest's reference runs exactly).* Observed growth is
   0.91–1.05%/yr; the life table alone (TFR 6, forager Siler mortality, full fertility,
   baseline hazards) gives a Lotka rate of **1.24%/yr**. The model runs close to that
   ceiling because the brakes rarely engage:
   - **Fertility stays at its maximum.** After year 100, births are 0.95–1.04× those
     expected at full fertility in every 50-year period: the fertility multiplier is 1
     whenever intake meets need, and the population-weighted food ratio stays at 1.12–1.19
     with a mean energy deficit ≤ 0.003 (harvest-to-need ≈ 1 + the 0.2 surplus target).
   - **Mortality stays near baseline.** After year 100, deaths are 0.93–1.11× those of
     baseline hazards alone (CDR 28–35‰ against CBR 39–47‰); crowding accounts for ~3% of
     deaths early, rising to 7–8% by year 600. Starvation mortality is negligible.
   - **Expansion prevents crowding.** Occupied cells grow almost in proportion to
     population (seed 0: 3 → 734 of ~1,200 land cells); people per occupied cell stay at
     ~20–28 for ~450 years and rise to 30–38 only in the last century, as the island fills.
     Wild plant stocks stay near capacity (≈0.85–1.0); game falls to ≈0.3 by year 600.
   - **Agriculture is not the cause** of sustained growth: pre-agricultural growth (years
     50–200) is already ~1.0–1.4%/yr. Cultivation (invented years 157–237; 25% of harvest by
     250–391; 42–50% at 600) raises density where land is filling and delays the brake.
     Late signs of intensification: farm hours per capita rise (~450 → ~620 h/yr) as the
     crop return per farm hour falls (~900 → ~650 kcal/h), and growth slows (seed 0:
     0.76%/yr in years 551–600).
   - **Interruptions** are only early small-population stochastic drawdowns (≤17% before
     year 50); no later crises.

   No invariant or accounting defect was found: births and deaths match the life table's
   expectations under the model's rules. The open scientific question is therefore the
   absence of a density-dependent brake while intake meets need: shortage is absorbed by
   more labor and by moving rather than by lower fertility or higher mortality, and labor
   effort, density-dependent disease (beyond the crowding placeholder) and birth spacing
   under workload carry no demographic cost. Candidate future diagnostics (not added): a
   cause-attributed expected-mortality breakdown and per-capita foraging hours in metrics.
2. **Agriculture representation.** Is the zero-crop-capability → `plant_cultivation`
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

> **MVP 2.1 is frozen and consolidated. Design the joint socioeconomic-strata
> representation — its schema in `population/fields.py`-style declarations and its home in
> `PopulationStore` — before implementing MVP 3 mechanisms.**
