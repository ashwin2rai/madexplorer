# Simulation V1 Scientific Debt Register

**Status:** INITIAL REGISTER ADOPTED FOR PLANNING; individual future mechanisms are NOT implemented or scientifically validated by this document.

**Purpose:** preserve the scope, causal assumptions, scientific limitations, biases and replacement paths of simplifications deliberately accepted to reach a functioning Simulation V1.

**Governing documents:** `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md` (durable scientific principles), `SIMULATION_V1_ROADMAP.md` (active development plan), `status.md` (what actually runs), `MVP3_SOCIOECONOMIC_STRATA_DESIGN.md` and `STAGE6B_SOCIOECOLOGICAL_MECHANISM_REVIEW.md` (evidence).

Scientific debt is **not** a defect exemption. Accounting violations, broken reproducibility, impossible knowledge, invalid population lifecycle, and an assumed rule that directly forces a claimed emergent outcome remain blockers. An approximation may be accepted only with an explicit scope, test and replacement trigger. No proposed debt item authorizes code changes without a reviewed mechanism specification.

## 1. Register conventions

- **Lifecycle:** `EXISTING` (already a model assumption), `ACCEPTED_FOR_V1` (policy permission to use a simplification; not proof of implementation), `CONDITIONAL` (allowed only after resolving a claim-specific adequacy issue), `DEFERRED`, `REPLACED`, `CLOSED`.
- **Priority:** `P0` (must be addressed before a particular V1 claim/release gate), `P1` (first post-V1 sensitivity/replacement candidates), `P2` (important later but nonblocking within scope). Priority is not scientific certainty.
- **Accountability for each record:** mechanism/parameter links when introduced, current code/test status, why acceptable, possible bias, claim scope, and a concrete trigger for replacing the rule.
- **Active use:** on implementing a V1 mechanism, update this register and the model-rule metadata in the **same reviewed stage**. A proposed approximation must never be silently described as active.

## 2. Accepted and conditional simplifications

### V1-D01. Collective population units as social actors

- **Lifecycle / priority:** `EXISTING` + `ACCEPTED_FOR_V1`; `P1`.
- **Simplification:** units act collectively when requesting, contributing, entering arrangements or delegating a decision right. Individual/household preferences and internal representation are not modeled.
- **Justification:** units already have consequential production, movement, resources and demographic state; collective interunit decisions complete a useful first causal loop with limited new state.
- **Scientific limitation / bias:** unit-level consent may falsely imply coordination; hides minorities, within-group conflict, elite capture and unequal participation. Shared agreement is an assumption, not evidence of internal consensus.
- **Permitted scope:** between-unit participation, access and organization; **not** within-unit class, consent, representation or household politics.
- **Replacement:** introduce a minimal internal decision distribution or representation rule linked to an active mechanism, before general occupational/wealth stratification.
- **Trigger / links:** a substantive result changes when internal costs or interests differ; `src/madexplorer/population/`, objective §5, V1-2/V1-3.

### V1-D02. Passive socioeconomic strata and pooled internal welfare

- **Lifecycle / priority:** `EXISTING` + `ACCEPTED_FOR_V1`; `P1`.
- **Simplification:** `share`, `field_claim`, and `store_claim` are descriptive state, not active allocation or demographic mechanisms. Intake, effective labor and vital rates remain unit-level unless separately versioned.
- **Justification:** the existing strata representation and resolution investigations do not establish a defensible general initiator of internal inequality; V1 interunit questions do not require one.
- **Scientific limitation / bias:** cannot infer class formation, differential nutrition, intragroup extraction, inheritance-based advantage, or population change due to within-unit inequality. Pooling may conceal distributional harm.
- **Permitted scope:** descriptive strata accounting and unit-level welfare, never claims of active within-unit redistribution.
- **Replacement:** activate one scientifically specified access/consumption or burden pathway; verify claim accounting and mechanism-aware coalescence **before** physical state reads strata, then add differentiated welfare/labor where required.
- **Trigger / links:** any claim about within-unit inequality or any active stratum reader; `MVP3_SOCIOECONOMIC_STRATA_DESIGN.md` §§N7, M6, Q-S.

### V1-D03. Simple, local contact and communication

- **Lifecycle / priority:** `ACCEPTED_FOR_V1` (not active yet); `P1`.
- **Simplification:** prospective partners can be identified through a bounded spatial/contact rule rather than a fully endogenous social network with communication, discovery and reputation.
- **Justification:** permits the first local participation decision without adding a separate theory of encounter formation.
- **Scientific limitation / bias:** network topology and reach may determine who can help, bargain or join an arrangement; repeated geographic proximity is not proof of a relationship.
- **Permitted scope:** conditional results for the stated contact process; no claim of evolved acquaintance or real-world communication behavior.
- **Replacement:** distinguish encounters, remembered partners, communicated requests, reliability and search costs.
- **Trigger / links:** institutional formation or access reverses across plausible contact rules; `STAGE6B_SOCIOECOLOGICAL_MECHANISM_REVIEW.md` §§17-18, V1-1.

### V1-D04. Exogenous donor availability and offer fractions

- **Lifecycle / priority:** `EXISTING`; provisionally `ACCEPTED_FOR_V1` where retained; `P1`.
- **Simplification:** current provisioning uses a fixed offer fraction (phi = 0.3) and prescribed matching; a V1 participation protocol may temporarily retain that cap while changing the choice/commitment rule explicitly.
- **Justification:** isolates new social decisions from an ungrounded willingness and donation-quantity model, and reuses tested kcal/transport execution.
- **Scientific limitation / bias:** offer capacity can strongly limit delivery and dependence; results cannot establish endogenous altruism, reciprocal insurance, or willingness. The centralized matcher is **not** a social institution.
- **Permitted scope:** outcomes conditional on the configured cap and allocation policy; no general interpretation of generosity or reciprocity.
- **Replacement:** compare actor-specific willingness, quantities, perceived insurance benefit and donor risk while preserving feasible transfer execution.
- **Trigger / links:** changes in phi dominate the V1 conclusion, or willingness becomes the research question; Stage 6A/6B findings, review §§17-18, V1-1/V1-2.

### V1-D05. Minimal adaptive participation decisions

- **Lifecycle / priority:** `ACCEPTED_FOR_V1` (not active yet); `P1`.
- **Simplification:** units may use a declared short-memory, threshold, or similarly bounded decision heuristic for participation or continuation; no full social preference theory is claimed.
- **Justification:** makes participation and exit consequential and replaceable without waiting for empirical calibration of all motives.
- **Scientific limitation / bias:** thresholds, memory and outside-option weights may artificially stabilize or destabilize organizations. An outcome caused by a fixed heuristic is conditional on it.
- **Permitted scope:** comparisons across specified alternative heuristics; no claim to explain the evolutionary origin of cooperation or social preferences.
- **Replacement:** evidence-informed belief formation, bargaining, learned expectations or heterogeneous motives.
- **Trigger / links:** institutional duration/formation is highly sensitive to heuristic design; V1-1/V1-2 and new rule metadata when implemented.

### V1-D06. Assumed repertoire of institutional rules

- **Lifecycle / priority:** `ACCEPTED_FOR_V1` (not active yet); `P1`.
- **Simplification:** a limited set of permissible contribution/allocation/governance rules exists exogenously; units can adopt, revise or abandon these rules.
- **Justification:** tests how arrangements persist and affect material outcomes before modeling the invention of negotiation, norms and institutional design.
- **Scientific limitation / bias:** what arrangements are possible is built into the menu. Formation from this menu is not the spontaneous origin of institutions or their cognitive prerequisites.
- **Permitted scope:** conditional selection, persistence, modification and dissolution **within the supplied rule repertoire**.
- **Replacement:** endogenize rule proposal, innovation, diffusion, negotiation and recombination; compare against the fixed menu.
- **Trigger / links:** a conclusion depends on the menu or excludes plausible alternative rules; V1-2/V1-3.

### V1-D07. Simple commitment, obligation and memory state

- **Lifecycle / priority:** `ACCEPTED_FOR_V1` (not active yet); `P1`.
- **Simplification:** arrangements use a compact membership record, operative rule and limited experience history instead of a fully specified kinship, credit, trust or legal system.
- **Justification:** these are the smallest persistent state variables needed to make agreements affect later decisions.
- **Scientific limitation / bias:** simplified memory and low renegotiation costs may overstate fluidity; guaranteed commitments would overstate stability.
- **Permitted scope:** explicitly defined obligations with tested formation, fulfillment, revision, default and exit; no implication of law, insurance or enforceable debt beyond what is coded.
- **Replacement:** partner-level credit/reputation, costs, monitoring, enforcement and richer histories.
- **Trigger / links:** conclusions are driven by turnover, default or assumed enforcement; V1-2. **Any double counting or undefined lifecycle behavior is a blocker, not accepted debt.**

### V1-D08. Bounded, voluntary and revocable delegation

- **Lifecycle / priority:** `ACCEPTED_FOR_V1` (not active yet); `P1`.
- **Simplification:** a coordinator can receive an explicit, limited decision right; members can refuse or revoke according to declared rules. Coercive power and inherited office are not represented.
- **Justification:** permits a minimal operational political mechanism without equating surplus, status, network centrality or labels with power.
- **Scientific limitation / bias:** inexpensive exit may suppress domination; guaranteed compliance may inflate coordination. Cannot explain taxation under threat, conquest, hereditary elites, or state formation.
- **Permitted scope:** delegated control of named decisions and its maintenance/loss, among collective units under specified exit and compliance rules.
- **Replacement:** unequal enforcement, costly exit, political bargaining, coalition formation, within-unit representation and coercion, each in separate tests.
- **Trigger / links:** political questions require constrained refusal or durable coercive control; V1-3.

### V1-D09. Annual time step and coarse behavioral memory

- **Lifecycle / priority:** `EXISTING` + `ACCEPTED_FOR_V1`; `P2`, conditional for within-year claims.
- **Simplification:** opportunities, choices and responses are resolved through the existing annual scheduler rather than detailed seasonal meetings, crises and contract windows.
- **Justification:** fits a stable, well-verified simulator and permits multigenerational feedback.
- **Scientific limitation / bias:** may hide timing-related shortages, simultaneous claims, rapid sanction and strategic sequencing. Annual scheduling may influence which options remain feasible.
- **Permitted scope:** annual or longer outcomes; no seasonal credit/response interpretation.
- **Replacement:** a validated within-year event or seasonal substep with preserved population/food accounting.
- **Trigger / links:** ordering or timing materially reverses V1 conclusions; `core/simulation.py`, V1-1/V1-2.

### V1-D10. Coarse ecology, agriculture and technology

- **Lifecycle / priority:** `EXISTING` + `ACCEPTED_FOR_V1`; `P2` except for claim-specific adequacy failures.
- **Simplification:** limited seasonality, simple soils/resource structure, Boolean technologies and an agricultural affordance rather than modeled domestication. Production and access conditions are those of the configured world.
- **Justification:** existing ecological and economic dynamics already create consequential opportunities for between-unit interaction.
- **Scientific limitation / bias:** resource predictability, territoriality, storage value and timing may differ from richer historical/ecological settings; cannot infer domestication or real-world prevalence.
- **Permitted scope:** conditional statements about the actual simulated ecological regimes.
- **Replacement:** add resource clumping, seasons, transport/infrastructure or a gradual domestication mechanism only when a named institutional comparison needs them.
- **Trigger / links:** a V1 inference depends on absent environmental variability; objective §§6-8, Stage 6B review §18.9.

### V1-D11. Limited external validation and initially stylized scenarios

- **Lifecycle / priority:** `EXISTING` + `ACCEPTED_FOR_V1`; `P1` after the required V1 experiments.
- **Simplification:** V1 is an exploratory mechanism model, not a calibrated reconstruction of ancient societies or a predictive tool.
- **Justification:** isolated mechanisms and end-to-end feedback can be assessed before broad empirical validation is available.
- **Scientific limitation / bias:** plausible simulated histories cannot establish real-world frequencies, parameter values or historical causes. Existing Stage 6B experiments used a small scenario/topology range.
- **Permitted scope:** scenario- and assumption-conditional mechanisms, with uncertainty. **V1-4 nevertheless requires multiple seeds and world topologies**, not a single-map anecdote.
- **Replacement:** targeted empirical calibration, out-of-sample comparisons, alternative model structures and sensitivity work.
- **Trigger / links:** a claim shifts from exploratory conditional explanation to real-world prevalence or prediction; V1-4/V1-5.

### V1-D12. Arable-opportunity and migration mismatch

- **Lifecycle / priority:** `CONDITIONAL`; `P0` **for claims involving agricultural outside options, mobility constraints, bargaining, immobility or dependence**; otherwise defer a wider migration redesign.
- **Simplification / observed issue:** current field planning can seek arable land in zero-arable cells, while movement does not directly evaluate arable opportunity. Stage 6B-P1 documented 1,928 affected farming cell-years and 221 distinct affected units in the pressure experiments.
- **Justification for conditional deferral:** a provisioning-only controlled test can remain interpretable without solving the entire agricultural migration problem.
- **Scientific limitation / bias:** apparent dependence or lack of exit may be an artifact of opportunity information rather than organization or authority.
- **Permitted scope:** do not interpret results about agricultural alternatives or dependence until V1-4 verifies adequacy or implements a bounded remedy. This is **not** blanket permission to ignore the mismatch.
- **Replacement:** a read-only opportunity audit, then a minimal comparable arable signal in feasible movement choices if needed; separate intentional model version.
- **Trigger / links:** the selected V1 test relies on feasible agricultural exit/opportunity; Stage 6B review §18.9, `scripts/probes/opportunity_audit.py`.

## 3. Non-debt blockers and release obligations

These cannot be excused by this register:

1. Resource, food, population, obligation or claim conservation violations; double spending or commitments that appear/disappear without specified semantics.
2. Hidden omniscience or use of unobserved future state in actor decisions.
3. Undefined split/fusion/migration/extinction behavior for persistent arrangements or authority.
4. A rule that forces an institutional outcome and then claims the outcome emerged.
5. Tests that only verify agreement with an implementation while scientific claims exceed the checked mechanism.
6. Unexplained changes to existing raw/logical oracles, seeds, baselines, config/provenance, or scientific semantics.
7. A V1 release without demonstrable multiyear feedback, institutional lifecycle, bounded decision-right dynamics and reproducible comparisons.

## 4. Register update procedure

At each implementation review: (a) identify newly active assumptions, (b) assign or update debt IDs and rule/code/test links, (c) state which inferences remain conditional, (d) document sensitivity/limiting results, (e) classify blockers versus acceptable debt, and (f) propose the highest-value subsequent replacement. No record is closed merely because a test passes; closure requires removing the assumption, replacing it with a better-grounded rule and assessing the impact, or explicitly showing that it no longer matters to the questions being asked.

**Current decision boundary:** the collective-actor, limited-politics and assumed-institution-repertoire choices are approved for *the V1 development strategy*. The specific new social rule equations, data structures, parameters and implementations are still to be reviewed; none has been added by this documentation change.
