# Social-Ecological Civilization Simulator

## Canonical Objective and Architectural Direction

**Project:** `madexplorer`  
**Document version:** 3.0  
**Canonicalized through:** MVP 2.1 freeze, 2026-10-01  
**Current scientific milestone:** MVP 2.1 frozen; MVP 3 next  
**Current implementation:** Python 3.13+  
**Document role:** durable project objective, scientific principles, and architectural constraints

This document defines what `madexplorer` is trying to become and the constraints that
future work should preserve. It is intentionally not an implementation diary, benchmark
log, or catalog of every model equation.

Historical decisions and lessons belong in `objective/status.md`. Exact frozen results,
checksums, scenarios, and validation records belong in the milestone manifests under
`baselines/`. Detailed equations and executable behavior belong in code, tests, scenario
configuration, and the model-rule registry.

### Document authority

When sources differ, interpret them by role rather than forcing one file to contain
everything:

- this document governs durable scientific intent and architectural constraints;
- milestone manifests and their frozen artifacts define the recorded scientific baseline;
- scenarios, source, and tests define the executable implementation of that baseline;
- `objective/status.md` records current lessons, caveats, and handoff state.

A future scientific change should update the executable model and its baseline deliberately;
if it changes a durable project principle or roadmap assumption, update this document too.

---

## 1. Objective

Build a reproducible, extensible simulation engine in which intelligent populations live
inside a spatially explicit ecology and develop social, economic, technological, and
political organization through local interaction.

The simulator should allow macro-scale patterns to emerge from mechanisms involving:

- geography, climate, resources, and ecology;
- demography and biological needs;
- movement, exploration, migration, and settlement;
- bounded perception, memory, and social information;
- subsistence, production, storage, exchange, and specialization;
- knowledge, learning, innovation, and technological diffusion;
- wealth, health, occupation, status, and other within-population differences;
- cooperation, competition, hierarchy, institutions, and political organization;
- ecological modification, shocks, disease, conflict, and collapse where modeled.

The simulator is **not** intended to replay a predetermined history. It should encode
mechanisms and behavioral hypotheses, then expose the consequences of those assumptions
across many stochastic runs.

The central research question is:

> Given a species, world, ecology, initial population, and explicit behavioral assumptions,
> what demographic, social, economic, technological, political, and ecological patterns
> repeatedly emerge, under what conditions, and through what causal pathways?

A secondary objective is species generality. The core engine should eventually support
humans, non-human intelligent species, fantasy species, and novel life histories without
hard-coding human historical outcomes into the simulation architecture.

---

## 2. Scientific Philosophy

### 2.1 Encode mechanisms, not outcomes

Do not encode rules whose purpose is to force a recognizable historical stage.

Avoid rules such as:

```text
large population -> state
surplus -> aristocracy
agriculture -> hierarchy
collapse -> healthier population
forest -> low development
```

Prefer mechanisms such as:

```text
food availability
labor productivity
resource appropriability
mobility and transport cost
storage and transferability
inheritance
status incentives
coordination costs
coercive capacity
public-good provision
autonomy preferences
coalition formation
disease exposure
nutrition and biological development
```

States, elites, markets, settlements, frontiers, revolts, collapses, and other social forms
should be interpretations of interacting mechanisms, not scripted milestones.

### 2.2 Make assumptions explicit and falsifiable

Substantive assumptions about behavior should be visible in configuration, model rules, or
well-defined mechanisms. Important hypotheses should be removable or replaceable so that
their effects can be tested through ablation and counterfactual runs.

A mechanism has little explanatory value if the outcome it is meant to explain has simply
been encoded into it.

### 2.3 Preserve causally important heterogeneity

Do not replace distributions with averages when the distribution affects behavior.

Age and sex already matter demographically. Future social modeling must preserve joint
structure in variables such as wealth, health, occupation, nutrition, preferences, status,
and migration propensity when those correlations change outcomes.

The goal is not maximal microscopic detail. The goal is the **minimum representation that
preserves the heterogeneity needed by the mechanism being modeled**.

### 2.4 Information is local and imperfect

Populations should act from information they could plausibly possess, not from global
simulation state.

Knowledge of the world should arise through perception, residence, memory, exploration,
and social transmission. Information may be noisy, stale, incomplete, and confidence-
weighted.

Perfect map knowledge, lossless map-wide synchronization, or hidden access to future state
should not be introduced merely because it simplifies an algorithm.

### 2.5 Treat social organization as multidimensional

Do not reduce "civilization" or "development" to a single score.

The simulator should eventually be able to distinguish, among other things:

- population and density;
- production and consumption;
- wealth and its distribution;
- biological welfare and health;
- knowledge and technological capability;
- trade connectivity and specialization;
- political autonomy and state capacity;
- elite capture and coercive power;
- social cohesion and legitimacy;
- ecological impact and sustainability.

A society may score very differently across these dimensions. That is a feature, not a
problem to average away.

### 2.6 Adaptive resolution is a scientific representation problem

Population aggregation must not be treated as a free performance optimization.

If two groups or strata would make meaningfully different decisions, merging them into one
homogeneous actor changes the model. Adaptive resolution is valid only when the internal
heterogeneity and selective responses required by the science are preserved.

The current naive coarsening mechanism is therefore **not scientifically neutral** and is
disabled in canonical scientific scenarios.

### 2.7 Emergence and ontological restraint

> Hardcode lower-level causal mechanisms and genuine affordances. Simulate quantities,
> relationships, practices, stocks, and environmental state. Infer higher-level historical
> and sociological categories from the resulting data rather than using those categories
> as causal switches.

Emergence does not mean the simulator may contain no discrete variables. A genuinely
discrete discovery, technique, or physical threshold may be represented discretely when
that is scientifically justified. What must be avoided is promoting an *interpretive*
category into causal state.

Keep the following conceptually distinct, even when an early milestone represents several
of them with one coarse variable:

| Kind of state | Example |
|---|---|
| knowledge or competence | skill in agriculture as a domain |
| knowledge of a technique | knowing how a storage structure is built |
| practice / adoption | actually cultivating, actually storing |
| material stock or infrastructure | hectares of cleared fields, storage capacity actually built |
| biological / ecological state modified by practice | depleted soil, (future) domesticated crop traits |
| derived classification | "farming society", "sedentary", "chiefdom", "state" |

Knowing how to build a granary is not the same state as owning substantial storage. A
technique being known does not imply that it is practiced, and practice does not imply that
the infrastructure or biological change that practice can produce already exists.

The last row must remain *derived*. Avoid causal state such as `agriculture_stage`,
`chiefdom = true`, `state_society = true`, `elite = true`, or `collapse = true` whenever
the same concept can be inferred from underlying quantities and relationships. A future
"elite" should be identified from persistent differences in wealth, access, power, labor
obligations, reproductive outcomes, and similar quantities; a future "state" from durable
organizational capacities and relationships. Metrics and analyses may compute such labels;
mechanisms should not branch on them.

MVP 2 contains accepted coarse abstractions that bundle several rows of the table, most
notably the Boolean technologies (§8). They are modeling hypotheses at a stated resolution,
not the project's final ontology.

---

## 3. Canonical Project State

### 3.1 Current scientific base: MVP 2.1

MVP 1 and MVP 2 are complete. MVP 2.1 is the current scientific base for future work.

MVP 2.1 preserves the MVP 2 model while correcting the known B1 familiarity merge-year
semantic defect. Exact identity, validation results, and frozen artifacts are recorded in:

```text
baselines/mvp2_1/freeze_manifest.json
```

Performance Hardening is complete. Its chronology and measurements are historical evidence,
not the current project objective.

### 3.2 Capabilities present at the MVP 2.1 boundary

The frozen simulator already models:

- generated spatial worlds with land, water, climate, hydrology, vegetation, soil, and
  ecological food stocks;
- configurable species physiology, life history, movement, cognition, foraging, and social
  information parameters;
- exact age/sex demographic cohorts inside population units;
- energetics, fertility, mortality, crowding, and extinction;
- bounded perception and confidence-aware beliefs about places;
- ecological familiarity that changes through use and time;
- foraging, storage, trade, cultivation, field investment, and harvest;
- domain knowledge, learning, diffusion, innovation, technologies, and capabilities;
- fission, fusion, exploration, and migration;
- deterministic named random streams, event provenance, metrics, and invariant checks.

The reference scenarios demonstrate that agriculture can emerge from the modeled incentives
and that cultivation can materially increase carrying capacity under pressure. These are
mechanism validations, not claims of historical calibration.

### 3.3 Important accepted limitations

MVP 2.1 deliberately remains simple in several areas:

- social and economic state is still mostly group-level;
- migration decisions are still made by whole population units;
- wealth inequality, occupations, within-group health distributions, elites, factions, and
  political preferences are not yet represented;
- ecology is intentionally simplified, including static vegetation structure, no seasonal
  cycle, and a simple soil model;
- trade remains simple;
- migration utility retains a known wild-food-stock versus crop-flow simplification;
- current coarsening changes social behavior and is not valid as a neutral approximation.

These limitations define future work; they are not reasons to rewrite the frozen MVP 2.1
model before MVP 3.

---

## 4. Current Computational Architecture

The architecture at the MVP 2.1 boundary is an important part of the project's accumulated
learning. Future work should evolve it rather than returning to an object-per-agent design.

### 4.1 Authoritative numeric population state

`UnitTable` is the authoritative store for hot numeric population state. It uses a
columnar/structure-of-arrays representation indexed by stable population-unit rows.

`PopulationUnit` remains useful as a domain-facing object and compatibility view, but it
should not become the primary substrate for large numerical computation again.

This separation is fundamental:

```text
human-readable/domain-facing model
        !=
hot computational representation
```

The two may expose the same scientific state without requiring the same storage model.

### 4.2 Static, compiled, and dynamic state are distinct

The current architecture separates:

- **scenario configuration**: human-readable typed inputs;
- **`StaticContext`**: expensive mostly immutable world/species structures that can be
  shared across runs;
- **`CompiledScenario`**: numeric/indexed views of configuration for hot kernels;
- **`SimulationState` / `UnitTable`**: mutable state that evolves during a run;
- **`StepContext`**: per-tick services, caches, provenance, and accounting.

Preserve this distinction. It supports performance, reproducibility, ensemble execution,
and future non-Python execution backends.

### 4.3 Sparse state should stay sparse

Beliefs are sparse in production and dense only as a reference/testing backend. This is a
model for future design: do not materialize a dense tensor merely because its indices can
be imagined mathematically.

Use dense arrays where state is genuinely dense and regular. Use sparse or compressed
structures where most possible relationships do not exist.

### 4.4 Scientific semantics are not the same thing as an optimized kernel

Several mechanisms have optimized numeric paths while retaining reference behavior for
comparison. Preserve independent semantic oracles where they provide real protection
against silent scientific drift.

Do not remove useful reference implementations merely to satisfy a superficial DRY rule.
Conversely, do not maintain duplicate implementations that provide no independent
validation value.

### 4.5 The simulation tick is ordered scientific semantics

At the MVP 2.1 boundary, one annual step follows this conceptual order, with optional
mechanisms omitted when disabled:

```text
Climate
-> Ecology
-> Perception
-> Knowledge sharing
-> Harvest
-> Foraging
-> Trade
-> Energetics
-> Demography
-> Extinction
-> Field planning
-> Learning
-> Knowledge diffusion
-> Innovation
-> Fission
-> Fusion
-> Migration
-> Experimental coarsening
```

Subsystem ordering can affect outcomes. It must not be changed as an incidental refactor.
Changes to ordering are scientific changes and require explicit justification and
validation.

### 4.6 Composition semantics are first-class

Fields that belong to a population unit must have explicit behavior under lifecycle events
such as fission and fusion. The current field-composition rules are a valuable architectural
pattern.

As MVP 3 introduces strata, every new state variable should make clear:

- whether it is group-level or stratum-level;
- how it is initialized;
- how it splits;
- how it merges;
- how it migrates;
- whether it is conserved, averaged, inherited, recomputed, or discarded.

Hidden or ad hoc lifecycle semantics are not acceptable.

---

## 5. Representation of Populations

### 5.1 Population units are statistical social actors

A `PopulationUnit` is not intended to represent a single person. It represents a weighted
population that can share location, information, culture, and other group-level state while
retaining internal demographic or socioeconomic distributions.

The representation should become richer only where that richness changes behavior.

### 5.2 Shared state and distributional state must remain separate

MVP 3 should preserve a clean distinction between group-shared state and state that varies
within the group.

Conceptually:

```text
Group-shared state [U]
    location
    species
    beliefs and environmental information
    familiarity / residence context
    much of culture and knowledge
    technologies
    social-network relationships
    group-level candidate generation

Distributional state [U, S]
    wealth
    health
    nutrition
    occupation
    status / leverage
    relevant preferences
    migration propensity

Demographic distribution [U, S, sex, age]
    cohort counts
```

Only mechanisms that are meaningfully distribution-sensitive should pay the cost of the
stratum dimension.

### 5.3 Preserve joint distributions where correlations matter

MVP 3 strata should be **joint weighted socioeconomic strata**, not independent marginal
histograms for wealth, health, occupation, and preference.

For example, if wealth affects nutrition, occupation affects exposure, and both affect
migration, those attributes need enough joint structure for the mechanism to see their
correlation.

The number of strata should be driven by scientific need and resolution policy, not by an
attempt to enumerate every possible person type.

### 5.4 Selective behavior is the reason strata exist

Strata are useful because different fractions of the same population may:

- experience different mortality and fertility;
- consume differently;
- specialize in different work;
- accumulate or lose wealth differently;
- adopt technologies at different rates;
- prefer exit, migration, rebellion, or cooperation differently;
- receive different benefits or burdens from institutions.

If a mechanism cannot produce a different response by stratum, it should normally stay at
the group level.

---

## 6. World, Ecology, and Species

### 6.1 World representation

The world should remain spatially explicit and computationally regular where practical.
Cells or equivalent spatial elements may contain:

- elevation and terrain;
- water and hydrology;
- temperature and precipitation;
- vegetation and habitat attributes;
- soil and arable potential;
- renewable and exhaustible resources;
- settlement, infrastructure, or human-modified state as later milestones require.

Behavior should depend on relevant physical properties and accessibility rather than on
hard-coded biome narratives.

### 6.2 Ecology should become dynamic only as required by questions being asked

The ecological model should grow by adding mechanisms with explanatory value: seasonality,
succession, depletion, disease reservoirs, domestication, niche construction, or climate
variation where justified.

Do not add ecological detail merely for realism if it does not affect the social mechanisms
under study.

### 6.3 Species are configuration, not branches in the social engine

Species definitions should eventually cover enough physiology and life history to alter:

- energy requirements;
- fertility and mortality schedules;
- maturation and longevity;
- mobility and carrying capacity;
- environmental tolerances;
- perception, memory, and learning;
- social tendencies where explicitly modeled.

The social engine should not contain special-case branches such as `if species == "elf"`.
Species differences should enter through data and general mechanisms.

---

## 7. Economy and Material Life

The economic model should explain how populations acquire, transform, store, exchange, and
control resources.

Over successive milestones it should support mechanisms including:

- foraging, hunting, cultivation, herding, extraction, and craft production;
- labor allocation and opportunity cost;
- storage, spoilage, portability, and transferability;
- specialization and occupation;
- exchange and trade networks;
- capital or productive investment where useful;
- ownership, wealth accumulation, inheritance, debt, or redistribution where justified;
- differential access to resources and the biological consequences of that distribution.

Surplus alone must not imply hierarchy. Hierarchy requires mechanisms that make surplus
appropriable, controllable, defendable, inheritable, or politically useful.

---

## 8. Knowledge, Culture, and Technology

Knowledge and technology should remain distinct concepts.

- **Knowledge** represents learned competence or understanding in domains.
- **Technologies** represent discrete techniques, practices, or artifacts with prerequisites
  and capability effects.
- **Culture** should represent socially transmitted norms, preferences, identities, and
  practices when those become behaviorally relevant.

Innovation should depend on modeled opportunity, need, knowledge, capability, and chance;
it should not be an automatic clock toward a predetermined tech tree.

Diffusion should depend on contact and social structure. Knowledge may be lost where
practice, teachers, population, or institutional support disappear.

### 8.1 The MVP 2 technology table is a coarse hypothesis

MVP 2 represents technologies as Boolean possession with hard prerequisites and capability
effects (`technologies/*.yaml`). This is an accepted, frozen MVP 2 representation and a
modeling hypothesis at a stated resolution. It is **not** the universal architecture for
cultural evolution, and the project is not fundamentally a tech-tree simulator.

Hard prerequisites should be used only where a dependency is genuinely physical or
logical. Where A merely makes B easier or more probable, future models should prefer:

- knowledge dependence;
- ecological preconditions;
- continuous competence;
- probabilistic opportunity;
- material prerequisites;
- soft causal dependence;

rather than a mandatory historical chain. New broad societal concepts should not be added to
the technology table.

Several current technologies combine kinds of state that §2.7 keeps distinct. For example,
`granaries` bundles knowing a storage technique with possessing storage capacity (its
retention effect applies as soon as the technology is held), and its hard prerequisite on
`plant_cultivation` encodes a historical association rather than a physical necessity;
`plant_cultivation` acts as a coarse discrete affordance: before it, crop capability is zero;
after it, cultivation is possible and the economic decision about fields takes over. That is
an accepted MVP 2 abstraction, not necessarily the final representation of agriculture.

### 8.2 Future refinement of agriculture

A future agricultural milestone may need to distinguish:

- deliberate cultivation practice;
- local species domesticability (an ecological property of places and taxa);
- repeated selection pressure from cultivation;
- biological domestication state of crop populations;
- material agricultural infrastructure (cleared, improved, irrigated land);
- actual agricultural calorie dependence (an outcome, measured rather than declared).

Where scientifically appropriate these should evolve continuously from practice and
environment, rather than forming a scripted sequence of named stages such as
"proto-cultivation → domestication → agriculture". No domestication ladder should be added
to the Boolean technology table as a shortcut.

---

## 9. Social and Political Development

Political organization is a future scientific layer, not a label applied to population
size.

The simulator should eventually be able to represent mechanisms such as:

- wealth concentration and inheritance;
- status competition and prestige;
- coalitions, factions, patronage, and collective action;
- coercive capacity and organized violence;
- taxation, tribute, redistribution, and public goods;
- legitimacy, compliance, autonomy, and resistance;
- administrative reach and communication cost;
- elite capture versus broad state capacity;
- federation, secession, rebellion, conquest, and institutional collapse.

A state should emerge when organizations acquire durable capacities and relationships that
justify calling them a state. It should not be created by crossing a scalar threshold.

Collapse likewise should be the observed consequence of declining capacities,
fragmentation, demographic/ecological stress, conflict, or institutional failure—not a
single scripted state transition named `collapse`.

---

## 10. Randomness, Reproducibility, and Provenance

Stochasticity is part of the model and must be governable.

### 10.1 Named random streams

Random draws should come through deterministic named streams rather than global RNG state.
Independent mechanisms should not become coupled merely because an unrelated code path
consumes an extra random number.

### 10.2 Reproducibility has levels

Distinguish deliberately between:

1. **exact replay** — identical seeded output on the supported numerical platform;
2. **numerical equivalence** — results differ only within an approved numerical tolerance;
3. **stochastic equivalence** — implementations sample the same intended probability law
   but do not preserve exact draw order.

A change must not silently move from one category to another.

### 10.3 Runs must be attributable

A scientifically meaningful run should record enough provenance to identify:

- scenario/configuration;
- model/software version;
- seed and RNG contract;
- relevant backend;
- mechanism switches;
- important numerical/platform information when required by the reproducibility level.

---

## 11. Validation and Model Governance

The simulator is useful only if mechanisms can be challenged independently of attractive
emergent stories.

### 11.1 Test the mechanism at several levels

Use complementary validation layers:

- unit tests for equations and local invariants;
- lifecycle and conservation tests;
- exact golden regressions where exact replay is meaningful;
- reference-versus-optimized differential tests;
- statistical tests for stochastic mechanism properties;
- matched-seed ablations for causal comparisons;
- ensembles and parameter sweeps for outcome distributions;
- stylized-fact or historical comparison only where the comparison is scientifically
  defensible.

A single interesting seed is evidence that something can happen, not that the mechanism is
credible or typical.

### 11.2 Preserve causal tests, not historical coincidence

Canonical scenarios should test whether mechanisms produce expected causal responses under
controlled conditions. They should not be tuned to mimic a single historical civilization
or exact population curve unless historical calibration is explicitly the experiment.

### 11.3 Model rules require metadata

Substantive scientific rules should remain registered/documented with, where applicable:

- rationale;
- source or evidence type;
- parameters;
- domain of validity;
- limitations;
- version introduced or changed.

Heuristic assumptions are acceptable when clearly identified as heuristics. Hidden
heuristics are not.

### 11.4 Scientific changes require explicit versioning

A correction to scientific semantics is not an ordinary refactor. Record it as a model
change, explain the reason, update tests and baselines intentionally, and preserve prior
milestone artifacts when they remain useful for comparison.

---

## 12. Engineering Principles

### 12.1 Less is more

Prefer the smallest design that makes scientific semantics explicit and testable.

Do not introduce abstraction merely because a future feature might need it. Do not preserve
an abstraction whose only purpose was an implementation phase that has ended.

Favor:

- explicit state over magical state;
- narrow interfaces over framework-like indirection;
- composition over deep inheritance;
- typed data over loosely structured dictionaries in scientific cores;
- pure or side-effect-bounded kernels where practical;
- clear ownership of mutation;
- one authoritative representation of hot state;
- comments that explain scientific intent, not syntax.

### 12.2 Separate scientific semantics from execution strategy

A scientific mechanism should not be defined by whether it currently runs in Python,
NumPy, Numba, WebAssembly, WebGPU, or another backend.

Where practical, organize computation as:

```text
validated state + explicit parameters + explicit random inputs
                    ->
              bounded kernel
                    ->
          explicit state transition
```

This does not require every subsystem to be purely functional. It does require the model's
meaning to be separable from incidental runtime machinery.

### 12.3 Optimize measured bottlenecks without changing the model

Prefer, in order:

1. remove repeated work and allocation;
2. separate immutable from dynamic data;
3. improve data layout and locality;
4. batch regular operations;
5. reduce interpreter dispatch in hot paths;
6. compile stable numerical kernels where measurement justifies it;
7. parallelize independent simulations when ensemble throughput is the goal.

Do not simplify scientific behavior merely to obtain a faster benchmark.

### 12.4 Memory is a first-class scaling constraint

Avoid architectures that require a dense cross-product of every conceptual dimension.
Strata, world cells, technologies, social links, and histories should only multiply each
other where the model genuinely requires that joint state.

Large temporary tensors are as important to control as persistent state. Prefer bounded or
chunked workspaces when an operation can be expressed that way.

### 12.5 Conservation and invariants are executable documentation

Continuously protect invariants such as:

- population accounting across births, deaths, fission, fusion, and migration;
- nonnegative resources and counts;
- valid probability ranges;
- conservation of explicitly conserved quantities;
- valid split/merge semantics;
- stable identifiers and table ownership.

Assertions and tests around these rules are part of the scientific specification.

---

## 13. Long-Term Deployment Vision: Web and Client-Side Compute

The intended end state is not only a research codebase. `madexplorer` should eventually be
usable as an interactive web application in which users can configure scenarios, run
simulations, inspect emergent histories, compare ensembles, and explore causal mechanisms.

A major long-term goal is to make substantial simulation work executable on the **client's
machine**, including use of the client's GPU where it is scientifically and technically
appropriate. WebGPU is a plausible future execution target; WebAssembly or other browser
runtimes may provide CPU execution and orchestration. These are deployment possibilities,
not current implementation commitments.

### 13.1 Architectural requirement today

The durable requirement is:

> Scientific semantics must remain separable from the execution backend so that the same
> model can eventually run through validated CPU, server, and client-side accelerated
> implementations without redefining the science.

This requirement should influence architecture now even though a browser backend is not an
MVP 3 deliverable.

### 13.2 Decisions that support future client execution

Prefer designs that make future portable kernels possible:

- authoritative numeric state in explicit arrays or compact typed buffers;
- stable shapes, dtypes, masks, and indices for hot state where scientifically sensible;
- human-readable configuration compiled into numeric runtime views;
- batched kernels with explicit inputs and outputs;
- limited dependence on Python object graphs inside hot scientific computation;
- deterministic iteration and stable identifiers where ordering matters;
- sparse representations for genuinely sparse relationships;
- reference implementations and backend differential tests;
- clear boundaries between simulation state, orchestration, visualization, and persistence.

Do **not** contort irregular scientific state into GPU-shaped tensors merely to claim GPU
compatibility. Some mechanisms are naturally sparse, graph-like, event-driven, or branchy.
A future browser implementation may be hybrid, with regular numerical kernels accelerated
and orchestration/irregular state handled on the CPU.

### 13.3 RNG portability will eventually need an explicit contract

Named NumPy RNG streams are the correct current architecture, but NumPy's implementation
should not be assumed to be the permanent cross-runtime RNG specification.

Before exact cross-backend replay becomes a requirement, define whether the project needs:

- byte-for-byte identical random streams across Python/WASM/WebGPU; or
- statistically equivalent backend-specific streams with backend-specific golden fixtures.

Make that decision deliberately rather than discovering it during a port.

### 13.4 Current optimizations are implementation choices, not permanent dependencies

Numba is useful for the current Python engine. It is not part of the scientific model.
Likewise, future WebGPU kernels must not become a second scientific implementation that can
drift unnoticed.

The CPU/reference path should remain capable of validating accelerated paths through exact,
logical, numerical, or statistical oracles appropriate to the mechanism.

### 13.5 Browser deployment is not a reason to weaken the model

Client-side execution should be pursued by better representation, kernel design, workload
partitioning, streaming, and adaptive resolution—not by silently reducing stochastic
independence, removing heterogeneity, or replacing mechanisms with game-like shortcuts.

---

## 14. Outputs and Experimentation

The engine should support both interactive exploration and reproducible research.

Persist useful results rather than every byte of state at every tick. Depending on the
experiment, outputs may include:

- time-series metrics;
- periodic population/world snapshots;
- event logs with provenance;
- selected traced-unit histories;
- run manifests;
- ensemble summaries and distributions.

Important analyses should be expressible as repeatable experiments:

```text
scenario
+ parameter set
+ mechanism switches
+ seeds
+ recorded software/model version
-> reproducible ensemble
```

Outputs should be designed so that the future web application can stream and visualize
results without requiring the simulation core to know about UI concerns.

---

## 15. Roadmap

The roadmap is conceptual. Exact milestone contents may change as experiments reveal which
mechanisms matter.

### MVP 1 — Ecological-demographic sandbox — COMPLETE

Established the basic world, ecology, population, movement, energetics, demography,
reproducibility, and subsystem architecture.

### MVP 2 / 2.1 — Agriculture, knowledge, and population dynamics — COMPLETE / FROZEN

Established bounded environmental knowledge, foraging, agriculture, trade, knowledge,
technology, innovation, fission/fusion, migration, stronger validation, and the current
scientific base. MVP 2.1 corrected the B1 merge-familiarity defect.

### Performance Hardening — COMPLETE

Established authoritative columnar population state, compiled scenario views, selective
compiled kernels, sparse belief storage, exact/logical oracles, and large-scale performance
measurements while preserving frozen semantics.

The enduring result is architectural, not the historical benchmark numbers.

### MVP 3 — Distributional Society — NEXT

MVP 3 should introduce the minimum within-group socioeconomic structure required for
heterogeneous behavior.

Core goals:

- joint weighted socioeconomic strata;
- wealth and material access;
- health, nutrition, and biological welfare by stratum;
- occupations and specialization;
- relevant within-group preferences/status;
- selective demographic and migration responses;
- principled adaptive population resolution;
- efficient stratified demography with bounded working memory;
- explicit split/merge semantics for all new state.

MVP 3 should begin with the **strata representation and lifecycle contract**, not with a
collection of disconnected social mechanisms.

### MVP 4 — Hierarchy, Institutions, and Politics

Candidate mechanisms include:

- appropriation and wealth concentration;
- inheritance;
- status competition;
- elites, factions, and coalitions;
- coercive capacity;
- taxation/tribute and public goods;
- state capacity versus elite capture;
- legitimacy, autonomy, resistance, and rebellion;
- political fission, federation, conquest, and collapse.

These should build on MVP 3 distributions rather than invent a parallel political actor
model disconnected from material society.

### MVP 5+ — Richer Worlds and Species

Candidate extensions include:

- richer ecology and seasonality;
- disease and epidemiology;
- domestication and broader production systems;
- infrastructure and transport networks;
- multi-species interaction;
- fantasy and non-human species;
- longer-run cultural or biological evolution where justified;
- interactive browser deployment and validated client-side acceleration.

---

## 16. Non-Goals

The project should resist several attractive but damaging directions.

It is not currently trying to:

- reproduce one real civilization exactly;
- predict the real political future;
- simulate every individual person;
- include every known social-science theory simultaneously;
- maximize realism independent of explanatory value;
- turn historical stage names into transition rules;
- treat one random seed as a scientific result;
- use naive aggregation as a performance shortcut;
- rewrite working mechanisms simply to adopt a fashionable technology;
- make every subsystem GPU-compatible before a browser backend exists.

---

## 17. Definition of Success

The project is succeeding when it can answer questions of the following form without the
answer being hard-coded:

- Under what ecological and informational conditions does cultivation become attractive?
- When does increased production improve biological welfare, and when is it captured or
  offset by population growth or inequality?
- How do mobility, storage, trade, and resource appropriability change the distribution of
  wealth and power?
- When do specialists, elites, factions, institutions, or states emerge?
- Under what conditions do populations remain decentralized despite high productivity?
- How do shocks propagate differently through unequal or differently organized societies?
- Which conclusions are robust across seeds, parameter uncertainty, and alternative
  behavioral hypotheses?
- Which macro outcomes depend on mechanisms that can be isolated and falsified?

Software success means the same scientific questions can be investigated without the engine
becoming an unmaintainable collection of special cases.

Long-term platform success means users can explore these questions interactively—including,
where practical, by running validated simulations on their own CPU/GPU through a web
application—without creating a separate, scientifically divergent simulator.

---

## 18. Canonical Rules for Future Work

When making a design decision, prefer the option that best preserves these rules:

1. **Mechanisms over narratives.** Never script the social outcome we are trying to explain.
   Hardcode mechanisms and affordances; infer historical categories from the data (§2.7).
2. **Explicit assumptions.** Important behavioral hypotheses must be inspectable and
   testable.
3. **Minimum sufficient heterogeneity.** Preserve distributions and correlations only where
   they change mechanisms, but do not average away causal structure.
4. **Local information.** Actors may use only information the model gives them a plausible
   way to possess.
5. **Scientific semantics before optimization.** Representation and execution may change;
   the model must not change accidentally with them.
6. **One authoritative hot state.** Avoid competing mutable representations of the same
   numeric state.
7. **Dense when dense, sparse when sparse.** Do not materialize conceptual cross-products
   without evidence they are required.
8. **Lifecycle semantics are explicit.** New state must define split, merge, migration, and
   conservation behavior.
9. **Randomness is governed.** Preserve named streams, provenance, and declared
   reproducibility guarantees.
10. **Validate causally.** Use mechanism tests, ablations, ensembles, and independent
    oracles; do not optimize for one attractive trajectory.
11. **Keep the architecture portable.** Scientific kernels should not depend unnecessarily
    on Python objects or any one execution backend.
12. **Less is more.** Add complexity only when it represents a necessary mechanism,
    protects correctness, or solves a measured engineering problem.

If future implementation work conflicts with these principles, the conflict should be made
explicit and resolved scientifically rather than hidden inside a refactor.
