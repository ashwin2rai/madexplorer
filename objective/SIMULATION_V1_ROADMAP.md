# Simulation V1: Adopted Development Strategy and Roadmap

**Status:** ADOPTED STRATEGIC DIRECTION; DOCUMENTATION ONLY; NO V1 SOCIAL MECHANISMS IMPLEMENTED BY THIS DECISION

**Decision:** 6B-P5 strategic reassessment supersedes the old *development sequence*, not the scientific findings from Stages 5-6B.

**Authority:** This is the active near-term milestone plan. `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` remains authoritative for the long-term scientific objective and non-negotiable principles. `status.md` identifies implementation state. `SCIENTIFIC_DEBT_REGISTER.md` tracks accepted approximations and restrictions.

## 1. Decision and non-negotiable purpose

The objective is unchanged: investigate how ecological, demographic, economic, informational and behavioral mechanisms can generate different forms of social organization without scripting historical stages. A recognizable chiefdom, state, elite or collapse is never an acceptance target.

**Adopted strategy:** progressive scientific fidelity organized around a *complete causal loop*. Reach a small but functioning, reproducible, interpretable end-to-end **Simulation V1** first. Then improve scientific fidelity by replacing explicitly declared approximations in controlled, comparable experiments. This is a scientific research platform, not a claim to historical prediction or empirical validation.

**Two independent progress dimensions:**

- **Functional completeness:** is a capability absent, represented only, causally active, or integrated in a multiyear feedback loop? The V1 priority is to integrate the indispensable capabilities.
- **Scientific fidelity:** what are the rule's support, assumptions, invariants, behavioral alternatives, counterfactual tests, sensitivity, and scope of inference? The minimum fidelity gate applies to every addition; a working feature does not automatically become validated science.

Do not average these dimensions into a single percentage or use one as a proxy for the other. Scientific fidelity constrains functional progress without requiring a final theory before the next capability is built. Post-V1 work strengthens fidelity while protecting the working loop.

### 1.1 Specific scope choices adopted for V1

1. **Collective actors first.** Population units make social choices and enter arrangements with other units. They already have material, ecological, technological and demographic differences. V1 can examine differences *between* units; active socioeconomic inequality *within* units is deferred. Existing passive strata are preserved, not repurposed as an active social hierarchy.
2. **Minimal politics, not full state formation.** Include a bounded, consequential and reversible delegation or collective decision right over a shared activity. Authorization, exercise, withdrawal/revocation and loss of the right must have model semantics. Coercion, conquest, hereditary office and detailed legitimacy are out of V1 scope unless a specific later decision explicitly changes the contract.
3. **A small, assumed institutional repertoire.** Units may propose or select among a limited, declared set of resource-sharing or governance rules. Which arrangements are selected, sustained, revised or abandoned may emerge conditionally. The invention of contract-making, negotiation capacity, or the repertoire itself is *not* explained by V1.
4. **A single end-to-end pathway, not every original MVP feature.** Start with a plausible, persistent interunit provisioning / resource-allocation arrangement because working energy, stores and transfer accounting already exist. C1 (local need requests and donor rationing) is a potential component, not an independently mandated research stage or the final explanation of cooperation.
5. **Explicit claims.** V1 may examine conditional organization, dependence, unequal access, and bounded delegated control between units. It may not claim within-unit class formation, autonomous invention of institutions, coercive state formation, or historical forecasting.

The choices above are **accepted simplifications made to reach V1**, not conclusions that those absent processes are unimportant. Their scientific debt is recorded in `SCIENTIFIC_DEBT_REGISTER.md`.

## 2. Actual starting point

- **MVP 2.1** is the frozen repository default (`baselines/mvp2_1/`) and must remain available for comparison.
- **MVP 2.2 dietary-intake fertility** is scientifically accepted and opt-in via `scenarios/mvp2_2_*.yaml`; the existing manifest still says `CANDIDATE` as an administrative matter. Select the accepted 2.2 mechanism explicitly for V1 experiments, without silently changing the default or the frozen baseline.
- Ecology, demography, production, technology/knowledge, movement, stores, provisioning, and experimental reproducibility are implemented. Some economic choices are already actor-level; the engine is not devoid of decisions or social feedback.
- Trade transfers affect material outcomes, and existing ties matter for some knowledge processes. But trade allocation is prescribed rather than negotiated, and trade ties are not commitments governing future food allocation.
- Socioeconomic strata are **passive**; claims and identities do not yet cause physical outcomes. Existing strata tests and the resolution caution still apply to any future active stratum reader.
- No V1 arrangement lifecycle, revocable decision right, or within-unit distribution mechanism was implemented by adopting this roadmap. Historical C1/Stage 6C recommendations remain evidence and candidate designs, not authorized implementation.

**Why the old order changes:** original MVP 3 put detailed within-unit differentiation before MVP 4 institutions. Research found no strong substrate for many within-unit initiators but established consequential between-unit interactions. That does not invalidate the MVP 3 research; it removes its completion as a prerequisite for all institutional work. The original five-MVP sequence is retained as a long-term research inventory, not as the V1 critical path.

## 3. What counts as Simulation V1

**Definition:** A reproducible exploratory simulator in which material and demographic conditions affect social decisions; some decisions create, maintain, alter and dissolve persistent arrangements; those arrangements affect resource access, burdens or bounded decision rights; and those changes affect future material conditions and choices over multigenerational runs.

### Minimum functional capabilities

| Capability | State at adoption | Required V1 state | Evidence to demonstrate |
|---|---|---|---|
| Ecological production, stocks, and constraints | Integrated | Preserve and connect | Material resource limits and source/sink accounting remain valid |
| Demography, movement, population lifecycle | Integrated | Preserve and connect | Social effects propagate into a named population or movement channel |
| Production, stores, bounded knowledge | Integrated | Preserve; refine only if needed for inference | Existing counterfactuals remain available |
| Social participation and allocation | Prescribed transfers; limited actor choice | Actor choices govern some interunit interaction | Different eligible choices change transfers under controlled inputs |
| Persistent arrangements | No operational resource commitment | Formation, continuation, change and dissolution | Event histories and state transitions alter later behavior |
| Interunit material differentiation | Present from ecological/production conditions | Observable with arrangement-dependent effects | Access, contributions, benefits or burdens can diverge without imposed class labels |
| Minimal political decision rights | Absent | Bounded, consequential, revocable authorization | Delegation affects feasible decisions and can be lost or rejected |
| Coupled feedback | Partial | Complete loop over multiple years | Social changes affect material/demographic conditions, which affect later social choices |
| Research and explanatory outputs | Strong baseline tools | Extend to decisions and institutions | Reproducible ablations, provenance, causal traces and ensemble summaries |

V1 requires mechanisms that *permit* different outcomes, including no arrangement, unstable cooperation and decentralized organization. It does not require a particular historical institution to form, or positive results in a predetermined fraction of runs.

### Scientific claim boundary

For V1, describe apparent institution formation as **selection and persistence of an arrangement within an assumed set of available rules and behavioral capacities**. Describe inequality primarily as **between-unit** inequality or dependence. Describe authority as **bounded operational control over specified decisions**, not a state, elite or monopoly on violence. Inferences are conditional on the assumed contact, incentives, decision, participation, and exit rules.

## 4. Roadmap with independent gates

Every milestone has a functional gate, a minimum scientific-fidelity gate, an accepted simplification, a stopping rule and a replacement boundary. The following are design commitments, **not claims of completed implementation**. Milestones are reviewed separately before code changes are authorized.

### V1-0: Research contract, scenarios and baselines

- **Question and capability:** Which model-supported forms of social organization can V1 investigate? Turn the adopted choices into one precise experimental contract.
- **Minimum work:** Explicit 2.2 opt-in; exact V1 scope and output schema; experiment matrix; case-based acceptance tests; a first version of the capability/debt records; clear default-versus-opt-in behavior.
- **Functional gate:** Each required capability has a testable definition and a path through the causal loop; a distinct V1 model/scenario identity is planned.
- **Fidelity gate:** Assumed versus endogenous processes, excluded claims, current ecological/migration concerns and baseline reproducibility are written down.
- **Accepted simplification:** Small scenario and actor scope; no general theory of social contracts.
- **Stop / replace:** Stop specifying when the next implementation change can be falsified. Broader questions move to debt or post-V1 research, not to open-ended prerequisite work. Revisit scope only if a core V1 claim would otherwise be invalid.
- **Dependencies:** Existing frozen model and accepted roadmap. **Status: strategy adopted, implementation specification not yet executed.**

### V1-1: Consequential local social participation

- **Question and capability:** Can units make bounded, feasible choices about providing and requesting assistance, with material consequences?
- **Minimum mechanism:** Local information/contact and an explicit request/participation/allocation procedure, using existing transfer and energy execution. Select the smallest useful part of C1 or a simpler alternative after specifying what the next arrangement actually needs.
- **Functional gate:** A unit's social choice changes at least some feasible allocations in controlled cases, reaching stored food/intake or another named downstream channel; no global omniscience is silently introduced.
- **Fidelity gate:** Matched-contact comparisons as appropriate; correct accounting, transport and termination; no hidden donor overcommitment; identifiable effects of contact, priority and choice; historical oracles unchanged with the mechanism disabled.
- **Accepted simplification:** Configurable participation/offer heuristics; simple locality and annual decisions; the present fixed donor offer may be retained temporarily if its consequences are declared.
- **Stop / replace:** Stop when V1-2 can depend on a documented, tested actor choice. An aggregate-null result does not block a necessary interface, but cannot be presented as evidence of a new social phenomenon. Replace contact/choice policy behind the transfer-execution boundary later.
- **Dependencies:** V1-0 and existing provisioning. C1's former Stage 6C static-difference threshold is **not** a V1 release prerequisite; any implementation still needs its own causal and feasibility tests.

### V1-2: Persistent arrangements and distributional consequences

- **Question and capability:** When do units form, retain, renegotiate or exit continuing arrangements, and who benefits or bears costs?
- **Minimum mechanism:** One arrangement family concerning contributions and allocation, with participants, operative rules, limited experience/memory, decisions to continue or revise, and termination. Track obligations explicitly; do not invent a generic institution framework.
- **Functional gate:** Arrangement membership and rules alter future participation/allocation. Formation, revision, withdrawal, dissolution and material feedback work in controlled cases and multiyear runs.
- **Fidelity gate:** Resource and obligation conservation; no double commitments, no duplicated stocks, no impossible information. Define fission, fusion, migration and extinction semantics, including who inherits or extinguishes obligations.
- **Accepted simplification:** Rule candidates are assumed; limited memory and simple adaptive evaluation. This is not an explanation of how contractual cognition or original institutions evolved.
- **Stop / replace:** Stop after complete lifecycle and repeated material consequences, not after solving cooperation generally. Later refine rule generation, bargaining, memory, commitment and allocation through narrow policy/state boundaries.
- **Dependencies:** V1-1 plus the existing population lifecycle.

### V1-3: Minimal, reversible political decision rights

- **Question and capability:** Under which conditions do units authorize a coordinator or delegate control, maintain decentralization, or withdraw that authority?
- **Minimum mechanism:** A bounded, explicit right to make consequential decisions about an arrangement, an authorization/selection process, exercise of the right, and a feasible refusal/revocation/exit process. Delegation is not automatically hierarchy.
- **Functional gate:** The right changes real allocation or participation outcomes; decentralized alternatives, no selection, turnover and revocation remain possible.
- **Fidelity gate:** Authority never follows automatically from wealth, population or a coordinator label. Information, enforcement, costs and outside options are explicit; no covert coercion or guaranteed compliance.
- **Accepted simplification:** Collective unit preferences; voluntary, bounded and revocable decision rights. Coercion, inherited office, conquest and full legitimacy processes are not modeled.
- **Stop / replace:** Stop when operational authority, its exercise and its loss are testable. Later add internal representation, costly exit, enforcement, coercion or coalition politics only against concrete questions and with new baselines.
- **Dependencies:** V1-2, because delegated rights require a consequential shared activity.

### V1-4: End-to-end multigenerational feedback and robustness

- **Question and capability:** How do changing environments, population conditions, arrangements and decision rights affect each other over time?
- **Minimum work:** Integrated V1 scenario(s), targeted instrumentation, paired ablations and contrasts across multiple seeds **and multiple world topologies**, limiting cases, and relevant assumption sensitivity.
- **Functional gate:** Demonstrate the complete feedback loop, including cases without institutional formation, persistent arrangements, altered arrangements and failure/dissolution. These are capability demonstrations, not predetermined frequency targets.
- **Fidelity gate:** Results trace to decisions and conserved flows, not artifacts of scheduling, identity, resolution, or experimental configuration. Check the zero-arable/migration adequacy issue **before** making claims about agricultural outside options, immobility, bargaining or dependence.
- **Accepted simplification:** A bounded scenario/parameter family. Not every climate, form of production, society or historical case is validated.
- **Stop / replace:** Stop when key V1 questions yield reproducible conditional answers with uncertainty and limitations. Surprises that change conclusions through documented but plausible assumptions become research findings, not automatic blockers.
- **Dependencies:** V1-1 through V1-3. In-scope material defects must be addressed as model changes, not hidden in tuning.

### V1-5: Simulation V1 research release

- **Question and capability:** Can another researcher run, compare, inspect and qualify the V1 model without reconstructing development history?
- **Minimum work:** Versioned opt-in V1 scenarios/baseline, recorded provenance, command-line workflows, explanatory summaries, mechanism rules, event and decision traces, capability matrix, debt register, limitations and reproducible tests.
- **Functional gate:** All V1 minimum capabilities above have end-to-end demonstrations; experiments are re-runnable and conclusions distinguish assumptions from generated results.
- **Fidelity gate:** Appropriate local, lifecycle, independent-reference, ablation, ensemble and regression checks pass. Historical MVP 2.1 and 2.2 expectations are preserved or explicitly versioned; existing oracles are never rewritten to conceal unexplained changes.
- **Accepted simplification:** A research-grade CLI release; browser UI, extensive history matching and advanced institutional detail are not release requirements.
- **Stop / replace:** Release once both gates pass. Remaining plausible extensions become versioned scientific debt, not reasons to withhold V1 indefinitely.
- **Dependencies:** V1-4 and documentation/verification checks.

## 5. Evidence floor and decision rules

### Minimum evidence gate for each V1 mechanism

1. Specify purpose, actors, information, timing, allowed actions, and the exact claim supported.
2. Declare assumptions and whether each key process is imposed, selected or generated.
3. Verify resource, population, stock, obligation and lifecycle invariants as applicable.
4. Demonstrate controlled positive, negative and limiting cases with independent checks when practical.
5. Compare against a disabled mechanism or an alternative central assumption; hold unrelated premises constant where possible.
6. Run a bounded dynamic and sensitivity check targeted at assumptions likely to reverse interpretation; record conditional results, including nulls.
7. Record rule metadata, model/scenario identity, provenance, code links, tests, and remaining debt.

This is a **minimum exploratory scientific standard**, not comprehensive empirical validation. The strength of the claim must be no greater than the evidence.

### Four dispositions for unresolved issues

| Disposition | When | Consequence |
|---|---|---|
| **Investigate now** | Invalid accounting, impossible information, broken lifecycle, unidentifiable causal claim, or an assumption that directly supplies the conclusion | Fix or constrain the claim before proceeding |
| **Approximate and proceed** | Coherent, falsifiable policy at an appropriate scope, satisfying the evidence floor | Accept and document scientific debt with an explicit scope/trigger |
| **Defer** | Improvement matters to a broader future question but not current integrity or interpretation | Keep named research question and trigger; do not add it to the critical path |
| **Remove** | A mechanism adds complexity without necessary function or interpretable contribution | Omit it and record the decision if it supersedes earlier work |

Reopen a completed mechanism immediately for violated conservation, systematic information leaks, lifecycle defects, or a hidden premise that forces the claimed result. Otherwise, a surprising or sensitive finding may be published/recorded conditionally and addressed later. A null finding does not imply failed engineering if the necessary capability is present and its limitations are honest.

## 6. Reporting functional completeness separately from fidelity

For each subsystem maintain a row with: capability, current state (`absent` / `represented` / `active` / `integrated`), links to controlled and end-to-end tests, empirical/theoretical support, known limitations, decision status, and debt references. The table in section 3 is the starting snapshot; update it at every milestone, without converting qualitative assessments into aggregate numerical percentages.

An integrated but highly idealized rule is functionally complete for its limited purpose yet low in externally validated fidelity. A rigorous, inactive counterfactual is scientifically valuable but does not fulfill V1 functionality. **Both must remain visible.**

## 7. Architecture and implementation workflow

Preserve the existing staged evaluate/apply scheduler, `PopulationStore` / `UnitTable`, explicit `StrataTable` boundary, named RNG streams, material accounting, model-rule registry, opt-in mechanism settings, independent reference paths and exact/logical oracles. Add only the narrow arrangement and decision-right state required by V1. A participant list must not be conflated with fusing units; a coordinator label must not confer authority by itself.

Each implementation substage should yield: a falsifiable mechanism specification; one coherent code change; lifecycle and invariant tests; a relevant counterfactual or ablation; updated rule metadata and scientific-debt record; a reproducibility report; and a clear accept/revise/defer/remove disposition. Keep changes uncommitted for the user's review; separate intentional model changes from exact refactors, and explicitly version or re-baseline semantic changes. Do not immediately issue an implementation prompt merely because the strategy is adopted.

## 8. After V1: targeted scientific fidelity improvements

Rank replacements by which assumptions most strongly condition V1 conclusions, not by which subsystem is most intellectually interesting. Likely themes include: improved social learning/contact/participation; empirical and theoretical bases for obligations and institutional rules; consequential within-unit access, nutrition and representation; costs of exit, enforcement and conflict; richer ecology/seasonality/transport; and broader calibration/validation. Every replacement should be compared with the V1 configuration through controlled cases and common experiment suites. A finer mechanism earns its complexity by changing evidential support, explanatory power or scope, not by realism alone.

## 9. Preserved history and supersession

The scientific findings, negative results and constraints in `MVP3_SOCIOECONOMIC_STRATA_DESIGN.md` and `STAGE6B_SOCIOECOLOGICAL_MECHANISM_REVIEW.md` remain in force **as findings**. Stage 6B-P4's selection of C1 was a provisional *next investigation* under the old sequencing logic; it is **superseded as a mandatory next development gate**. C1 remains a candidate component of V1-1 and a reference for contact-matched tests. Stage 6C is **not started, not automatically authorized**. Original MVP 3-5 research goals remain long-term work, with their dependency ordering relaxed for this V1 route. Neither scientific results nor past baselines are retroactively reclassified.
