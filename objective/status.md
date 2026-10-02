# Implementation Status — MVP 2.1 → MVP 3 Handoff

**Updated:** 2026-10-01  
**Current scientific base:** MVP 2.1 frozen  
**Next milestone:** MVP 3 — Distributional Society

This is the short operational handoff. It should contain only current state, durable lessons,
known caveats, and constraints that future work must remember.

Use other artifacts by role:

- `objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` — canonical scientific objective and architectural direction;
- `baselines/mvp2_1/freeze_manifest.json` — exact current baseline and validation record;
- source, scenarios, tests, and model rules — executable semantics;
- `benchmarks/perf/` — retained performance evidence.

The former Performance Hardening log is retired. Its useful conclusions are preserved below;
its chronology is not part of the forward-looking documentation.

---

## 1. Current state

- MVP 1 complete.
- MVP 2 complete and preserved as the historical freeze.
- Performance Hardening complete.
- MVP 2.1 complete and frozen; this is the base for future science.
- MVP 3 is next. **Design the socioeconomic-strata representation before implementing MVP 3 mechanisms.**

### MVP 2.1 identity

- Manifest: `baselines/mvp2_1/freeze_manifest.json`
- Source-tree SHA-256: `55a9ea94b81cf786f3948f43d648696acad20504a540fe8494e09ca44192845c`
- Golden fixtures: `tests/regression/golden/`
- Raw-byte oracle: `benchmarks/perf/oracle_mvp2_1.json`
- Logical/backend-independent oracle: `benchmarks/perf/oracle_mvp2_1_logical.json`
- Production belief backend: sparse; dense remains the reference/debug backend.
- Canonical scenarios: `scenarios/mvp2_neolithic.yaml`, `scenarios/mvp2_pressure.yaml`

The only intended semantic difference from MVP 2 is **B1**, the merge-familiarity
decay-year fix. Historical MVP 2 artifacts remain under `baselines/mvp2/`.

The MVP 2.1 manifest records `make check` green, compact statistical tests 3/3, and the
aggregation strict xfail retained.

---

## 2. Architecture to preserve

- `UnitTable` is authoritative for hot numeric population state. `PopulationUnit` is a domain/view compatibility layer, not the numerical authority.
- Sparse beliefs are the production representation. Keep the dense implementation as an independent exactness oracle.
- Preserve the separation among static context, compiled numeric scenario data, and dynamic state.
- Simulation-step ordering is scientific semantics. Do not reorder subsystems as an incidental refactor.
- Lifecycle state needs explicit split/merge behavior. Extend the `FIELD_RULES` pattern as MVP 3 adds state.
- Named RNG streams are scientific infrastructure. Draw count, order, independence, and interpretation must not change accidentally.
- Reference and optimized implementations may intentionally coexist when their independence provides useful differential validation.

---

## 3. Lessons from Performance Hardening

### Scaling result

On the campaign machine, the canonical seed-0 600-year run improved from about **41.9 s to
15.5 s CPU** (~2.7×) while preserving the required reference behavior.

At equal state age and fixed density, final measurements were about **95–112 µs per
unit-year** from ~2k to ~50k units (+18% across ~25× scale). The ~50k-unit, 400×400 case
peaked around **2.5 GB RSS**. These are historical same-machine measurements, not runtime
requirements.

### What actually worked

1. Improve representation and dataflow before compiling kernels.
2. Compile reusable scenario data once and share phase-local indexes/caches.
3. Keep hot numeric state columnar and sparse state sparse.
4. Batch regular work; compile only kernels that remain hot after representation cleanup.
5. Profile again after structural changes; old hotspot rankings expire quickly.

There is no single dominant MVP 2.1 kernel left. Another general optimization phase would
have diminishing returns; optimize future bottlenecks when measured.

### Exactness lessons

- A mathematically equivalent floating-point rewrite is not automatically bit-identical. Python reductions, NumPy reductions, compiled expressions, and transcendental implementations can differ.
- Keep raw-byte and logical oracles for different equivalence levels.
- Keep stochastic draws outside compiled kernels unless RNG semantics are deliberately redesigned. The successful pattern is: **named stream → pre-draw → kernel → state update**.
- Do not remove independent reference paths merely to reduce code duplication.

### Memory lesson

Sparse beliefs removed the former units × world-cells memory ceiling. For MVP 3, the main
foreseeable risk is not persistent group state but **large temporary arrays created by
stratified demography**.

---

## 4. Accepted limitations

These are known limitations, not blockers or hidden bugs.

### Aggregation/coarsening is not scientifically neutral

Current coarsening turns merged populations into one decision-maker and can alter migration,
innovation, dispersal, and population dynamics.

- Canonical scientific scenarios keep aggregation **off**.
- The aggregation statistical check remains a strict xfail.
- Do not use naive coarsening as a performance shortcut.
- MVP 3 adaptive resolution must preserve behaviorally important heterogeneity.
- Existing comments/defaults implying equivalence to aggregation-off need cleanup.

### Migration utility contains a stock-versus-flow approximation

Migration/stay utility still mixes quantities with imperfectly matched economic meaning,
including wild-food stock and crop flow. Field-replacement cost removed the worst double
counting; the remaining approximation is accepted and deferred.

### Ecology remains intentionally simple

No seasons, limited dynamic vegetation/succession, simple soil state, and simple exchange.
These are future scientific extensions, not missing engineering work.

### Social state and migration remain group-level

MVP 2.1 does not represent within-group wealth, health/nutrition, occupations, status,
political preferences, elites/factions, or selective subpopulation migration. A
`PopulationUnit` still relocates as one social actor. These are core MVP 3 concerns.

### Correctness audit

B1 was fixed and versioned in MVP 2.1. No other category-A correctness defect was identified
in the freeze audit. A newly discovered scientific bug must be classified, tested, versioned,
and re-baselined deliberately rather than hidden inside a refactor.

---

## 5. Resolved issues not to recreate accidentally

MVP 2 stabilization already addressed:

- candidate-count/Gumbel migration bias;
- map-wide lossless social belief synchronization;
- uncertainty handling for direct observations;
- hard saturation of migration food utility;
- permanent inherited ecological familiarity;
- the agriculture field-growth bootstrap trap;
- double counting of field/crop value in migration;
- innovation ordering bias;
- RNG-stream coupling across unrelated mechanisms;
- treating a population plateau as a required validation outcome;
- treating naive aggregation as scientifically neutral.

These may be revisited for a concrete scientific reason, but future changes should first
understand why the present mechanism exists.

---

## 6. MVP 3 constraints learned from MVP 2.1

MVP 3 should use **joint socioeconomic strata**, not unrelated marginal distributions.

```text
shared group state                 [U]
distributional state               [U, S]
demographic cohorts                [U, S, sex, age]
```

Keep genuinely shared state at `[U]`: location/species, beliefs/familiarity, much of
culture/knowledge, technologies, inter-group network state, perception, and group-level
movement candidate generation unless a mechanism specifically requires stratification.

Only distribution-sensitive mechanisms should pay for `S`. Strata exist to permit different
fractions of a population to experience or choose different outcomes.

### Demography must use bounded workspace

Hardening measured roughly 9.4 kB of demographic temporaries per unit per tick. Multiplying
the current pipeline naively by 8–16 strata would create multi-GB temporary working sets at
large unit counts.

Design stratified demography around:

```text
pre-drawn RNG
    -> fused/chunked unit × stratum processing
    -> bounded workspace
    -> direct authoritative cohort writes
```

Use `int32` for persistent cohort bins once bounds are explicit; use `int64` for totals and
accumulators where needed.

### Preserve future backend portability

The long-term target includes browser/client execution and potentially GPU acceleration.
MVP 3 does **not** need WebGPU, but it must not make Python objects or Numba behavior part of
the scientific semantics. Continue favoring explicit numeric state, explicit random inputs,
and bounded kernels that can eventually have validated alternate backends.

---

## 7. Change and validation rules

For substantial changes:

1. classify the change as **exact optimization**, **numerical reformulation**, **bug fix**, or **scientific model change**;
2. use the smallest targeted test that can falsify the claim;
3. keep `make check` green;
4. use golden fixtures/oracles and differential reference paths for semantics-preserving work;
5. run compact statistical validation when model behavior may change;
6. profile only when performance-relevant code or representation changes;
7. version and re-baseline intentional semantic changes instead of tuning back toward an old trajectory.

Always preserve named RNG streams and independent stochastic decisions. Do not change RNG
semantics or model coefficients merely to recover an old benchmark trajectory.

---

## 8. Immediate consolidation before MVP 3

- Align `README.md` with MVP 2.1 and current agriculture behavior.
- Remove stale aggregation comments/docstrings and reconsider the misleading aggregation default.
- Perform the planned codebase refactor review, favoring deletion and simplification over new abstraction.
- Design the MVP 3 stratum schema and lifecycle/composition semantics before implementing its mechanisms.

Do not mix this consolidation with unversioned changes to frozen MVP 2.1 scientific behavior.

---

## 9. Handoff

> **MVP 2.1 is frozen. Performance Hardening is complete. Consolidate and simplify without changing semantics, then design the joint socioeconomic-strata representation that anchors MVP 3.**
