# Social-Ecological Civilization Simulator

## Canonical Objective and Architectural Direction

**Project:** `madexplorer`\
**Document version:** 3.1 (2026-10-07)\
**Current scientific milestone:** MVP 2.1 frozen; MVP 3 in progress (strata passive)\
**Current implementation:** Python 3.13+\
**Document role:** durable project objective, scientific principles, and architectural constraints

This document defines what `madexplorer` is trying to become and the constraints that
future work should preserve. It is intentionally not an implementation diary, benchmark
log, or catalog of every model equation.

### Document authority

When sources differ, interpret them by role:

- this document: durable scientific intent and architectural constraints;
- `baselines/` manifests and frozen artifacts: the recorded scientific baseline;
- scenarios, source, tests and the model-rule registry: the executable model;
- `objective/MVP3_SOCIOECONOMIC_STRATA_DESIGN.md`: the MVP 3 contract and stage findings;
- `objective/status.md`: current handoff, accepted limitations and working discipline.

Documents keep current conclusions, not appended logs; git keeps the history. A scientific
change updates the executable model and its baseline deliberately, and this document when
it changes a durable principle.

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

### 3.1 Scientific base: MVP 2.1

MVP 1, MVP 2 and Performance Hardening are complete. MVP 2.1 (MVP 2 plus the B1
merge-familiarity fix) is the frozen base, recorded in `baselines/mvp2_1/freeze_manifest.json`.
Later refactors are validated against its golden fixtures and raw/logical exactness
oracles, not against the manifest's original source hash.

The frozen simulator models generated worlds (terrain, water, climate, hydrology,
vegetation, soil, food stocks); configurable species physiology, life history, movement,
cognition and social information; exact age/sex cohorts; energetics, fertility, mortality,
crowding and extinction; bounded, confidence-aware beliefs; familiarity; foraging, storage,
trade, cultivation and harvest; knowledge, diffusion, innovation and technologies; fission,
fusion, exploration and migration; named RNG streams, event provenance, metrics and
invariants. The reference scenarios show agriculture emerging from modeled incentives and
raising carrying capacity under pressure: mechanism validations, not historical calibration.

### 3.2 Accepted limitations

Social state and migration are group-level (MVP 3 strata are still passive); ecology is
simple (static vegetation structure, no seasons, simple soil); trade is simple; migration
utility mixes wild-food stock and crop flow; naive coarsening changes behavior and is not a
neutral approximation. These define future work; `objective/status.md` lists them with
their evidence.

## 4. Current Computational Architecture

The architecture at the MVP 2.1 boundary is an important part of the project's accumulated
learning. Future work should evolve it rather than returning to an object-per-agent design.

### 4.1 Authoritative numeric population state

`UnitTable` is the authoritative store for hot numeric population state. It uses a
columnar/structure-of-arrays representation indexed by stable population-unit rows.

`PopulationUnit` remains useful as a domain-facing object and compatibility view, but it
should not become the primary substrate for large numerical computation again.

`PopulationStore` is the single owner of the coupled population representations;
`SimulationState` exposes them only as read-only views:

```text
PopulationStore
    unit registry     # identities, processing order
    UnitTable         # group-shared hot state      [U]
    BeliefStore       # sparse spatial beliefs
    StrataTable       # distributional state only  [U, S]   (MVP 3)
```

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

Within a subsystem, `evaluate` observes the current state, consumes its named random
streams and makes every stochastic decision, returning explicit proposals; `apply` commits
them deterministically and draws no random numbers.

### 4.6 Composition semantics are first-class

Fields that belong to a population unit must have explicit behavior under lifecycle events
such as fission and fusion. Every unit field is declared once (`population/fields.py`) with
its storage and its merge/split rule; table columns, row views, the documented rules and
the shared extensive/intensive compositions derive from that declaration, and a test fails
if the dataclass and the declarations disagree.

Every strata variable likewise makes clear:

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

Keeping the codebase lean is part of the same rule:

- delete code once its replacement is validated (batched rewrites left one-unit
  predecessors behind; phase aliases outlived their phases);
- independent reference implementations are validation, not duplication: share plumbing
  between a reference/fast pair, never the arithmetic it cross-checks;
- anything hashed into an oracle or `config_hash` is provenance: removing it is a
  provenance change, not a refactor;
- experiment probes share one helper module and are retired, with git as the archive, once
  their findings are recorded.

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

`madexplorer` should eventually be an interactive web application for configuring
scenarios, running simulations, inspecting emergent histories and comparing ensembles, with
substantial work executable on the client's machine (WebAssembly for CPU orchestration,
WebGPU where appropriate). These are deployment possibilities, not current commitments.

**Requirement today:** scientific semantics must remain separable from the execution
backend, so the same model can run through validated CPU, server and client-side
implementations without being redefined. In practice:

- authoritative numeric state in explicit arrays with stable shapes, dtypes and indices;
- human-readable configuration compiled into numeric runtime views;
- batched kernels with explicit inputs, outputs and pre-drawn random inputs; no Python
  object graphs inside hot scientific computation;
- deterministic iteration and stable identifiers where ordering matters;
- sparse representations for genuinely sparse relationships;
- reference implementations and backend differential tests (exact, logical, numerical or
  statistical oracles as the mechanism allows), so accelerated kernels never become a second,
  drifting scientific implementation;
- clear boundaries between simulation state, orchestration, visualization and persistence.

Do not contort irregular state (sparse, graph-like, event-driven) into GPU-shaped tensors;
a browser backend may be hybrid. Numba and NumPy's RNG are current implementation choices,
not part of the model: before exact cross-backend replay is required, decide deliberately
between byte-identical random streams and statistically equivalent streams with
backend-specific fixtures. Browser deployment is never a reason to weaken the model
(reduced stochastic independence, removed heterogeneity, game-like shortcuts).

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

### MVP 3 — Distributional Society — IN PROGRESS

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

MVP 3 began with the strata representation and lifecycle contract, then tested candidate
mechanisms counterfactually before any is activated; see the MVP 3 design document.

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
