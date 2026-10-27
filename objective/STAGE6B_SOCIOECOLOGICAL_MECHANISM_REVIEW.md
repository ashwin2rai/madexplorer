# Stage 6B — Socioecological Mechanism Review

**Status:** comparative review, read-only experiment and mechanism selection (2026-10-27).
Nothing implemented or activated. Starting commit `cabe833` (Stage 6A committed), clean tree.
Reference model: MVP 2.2, selected explicitly (`scenarios/mvp2_2_*.yaml`). The MVP 2.2
manifest still reads CANDIDATE. That is an administrative baseline state, distinct from the
scientific acceptance of dietary-intake fertility, and it is unchanged here.
Design summary: `MVP3_SOCIOECONOMIC_STRATA_DESIGN.md` §AE.

**Decision: D (pathway C).** The physical substrate for risk pooling between units is
strong. What is missing is an actor-level interaction:
- provisioning is centrally sequenced, with global information;
- willingness is an exogenous parameter.

**Recommended Stage 6C:** one explicit, local *need request → response* event, with
proportional rationing by each donor (§14).

---

## 1. Question and scope

Which ecological opportunities and social interactions could generate persistent
differences in access, cooperation, dependence and collective organization? And which of
them can the current simulator credibly represent?

Three pathways compete on equal terms:
- **A**, resource access, defensibility and outside options;
- **B**, collective coordination of productive resources;
- **C**, risk pooling and intergroup dependence.

Mobility and unit boundaries are treated as a cross-cutting challenge to all three.
Producing inequality or hierarchy earns no credit.

## 2. Sources

Access level is stated per source. Metadata comes from Crossref DOI records. No full texts
were read.
- "Abstract" means the publisher or Crossref abstract.
- "Search summary" means only a search-engine summary of the abstract was reachable (the
  publisher blocked direct access).
- Nothing beyond these is claimed.

| # | Citation | Type | Access |
|---|---|---|---|
| 1 | Dyson-Hudson, R. & Smith, E.A. (1978). Human territoriality: an ecological reassessment. *American Anthropologist* 80(1): 21–41. doi:10.1525/aa.1978.80.1.02a00020 | theory + comparative ethnography (N. Ojibwa, Basin-Plateau, Karimojong) | abstract |
| 2 | Smith, E.A. & Codding, B.F. (2021). Ecological variation and institutionalized inequality in hunter-gatherer societies. *PNAS* 118(13): e2016134118. doi:10.1073/pnas.2016134118 | empirical comparative (Pacific-coast North American foragers; ≈ 89 societies per search summary) | Significance statement + search summary |
| 3 | Bowles, S. & Choi, J.-K. (2013). Coevolution of farming and private property during the early Holocene. *PNAS* 110(22): 8830–8835. doi:10.1073/pnas.1212149110 | theory + simulation | abstract |
| 4 | Schlager, E. & Ostrom, E. (1992). Property-rights regimes and natural resources: a conceptual analysis. *Land Economics* 68(3): 249–262. doi:10.2307/3146375 | conceptual | metadata only (bundle of rights used as the standard framework; content not verified from the text) |
| 5 | Bowles, S. & Fochesato, M. (2024). The origins of enduring economic inequality. *Journal of Economic Literature* 62(4): 1475–1537. doi:10.1257/jel.20241718 | review of archaeological evidence (Neolithic western Eurasia, 11.7–5.3 ka) | abstract |
| 6 | Kohler, T.A., Bogaard, A., Ortman, S.G., Crema, E.R., et al. (2025). Economic inequality is fueled by population scale, land-limited production, and settlement hierarchies across the archaeological record. *PNAS* 122(16): e2400691122. doi:10.1073/pnas.2400691122 | empirical comparative (> 1,100 sites, > 47,000 residential units, house-size Ginis) | abstract |
| 7 | Ostrom, E. (1990). *Governing the Commons: The Evolution of Institutions for Collective Action.* Cambridge University Press. ISBN 978-0-521-40599-7 | case studies + theory | catalogue record (content cited at the level of the book's thesis only) |
| 8 | Powers, S.T., van Schaik, C.P. & Lehmann, L. (2016). How institutions shaped the last major evolutionary transition to large-scale human societies. *Phil. Trans. R. Soc. B* 371(1687): 20150098. doi:10.1098/rstb.2015.0098 | theoretical review | abstract |
| 9 | Aktipis, C.A., Cronk, L. & de Aguiar, R. (2011). Risk-pooling and herd survival: an agent-based model of a Maasai gift-giving system. *Human Ecology* 39(2): 131–140. doi:10.1007/s10745-010-9364-9 | agent-based simulation | search summary |
| 10 | Campennì, M., Cronk, L. & Aktipis, A. (2022). Need-based transfers enhance resilience to shocks: an agent-based model of a Maasai risk-pooling system. *Human Ecology* 50(1): 35–48. doi:10.1007/s10745-021-00273-6 | agent-based simulation | search summary |
| 11 | Winterhalder, B. (1986). Diet choice, risk, and food sharing in a stochastic environment. *Journal of Anthropological Archaeology* 5(4): 369–392 (DOI not verified) | simulation | abstract |
| 12 | Grimm, V., Revilla, E., Berger, U., et al. (2005). Pattern-oriented modeling of agent-based complex systems: lessons from ecology. *Science* 310(5750): 987–991. doi:10.1126/science.1116681 | methodology | abstract |
| 13 | Grimm, V., Railsback, S.F., Vincenot, C.E., et al. (2020). The ODD protocol … second update. *JASSS* 23(2): 7. doi:10.18564/jasss.4259 | methodology | abstract + parts of text |

**Per-source notes.** Mechanism and claimed evidence come from the accessed material.
Conditions marked *(inferred)* are this review's reading of the source.

| # | Proposed mechanism | Evidence (as accessed) | Operates when / may fail when | Simulator needs | Applicability |
|---|---|---|---|---|---|
| 1 | Territoriality is expected when critical resources are dense and predictable, so that the benefits of exclusive use exceed the costs of defence | Three ethnographic cases "seem to accord"; qualitative | Dense, predictable resources / sparse or unpredictable ones *(inferred: the model's logic)* | Resource density and predictability, defence cost, exclusion | Density and predictability are measurable here; the cost side (defence, monitoring) is absent |
| 2 | Defensible, clumped, monopolizable resources (aquatic, especially salmon) are associated with institutionalized inequality; population pressure and warfare show no such association | Comparative association (Significance statement) | Initial emergence; an association, not a demonstrated causal path | Clumped resources, control, inheritance of position | No aquatic or clumped resource class exists; plant and game stocks are diffuse |
| 3 | Farming and private property coevolve because farm wealth is demarcable and defensible; farming was not initially more productive | Model and simulation only | A coordination equilibrium on property; explicitly not "unicausal" | Demarcable assets, recognized claims, enforcement | Fields exist and persist, but nothing excludes others from them; claims are attributional (§AE) |
| 4 | Property is a bundle of distinct rights: access, withdrawal, management, exclusion, alienation | Conceptual | — | Separate representation of each right | Today every co-located unit has access and withdrawal. No unit has management, exclusion or alienation |
| 5 | Wealth inequality was ephemeral and rare in the Neolithic and became enduring only ≥ 4,000 years after farming. Aggressive egalitarianism held it back; later technology raised the value of material wealth relative to labour | Archaeological synthesis (review authors' interpretation) | Persistence needs mechanisms beyond emergence; reversal is common | Persistence and reversal processes | Directly challenges agriculture → inequality: a simulator should be able to produce reversals |
| 6 | Persistent inequality lags cultivation by > 1 millennium. It goes with *land-limited* (not labour-limited) production, population scale and settlement hierarchy; governance mediates | Comparative house-size Ginis (observational) | Land is the binding factor / labour-limited production | Land scarcity, transmission, settlement ranking | Residential units ≠ PopulationUnits. Land never binds in our runs (§AE A) |
| 7 | Commons can be governed by self-organized institutions, not only by the state or by privatization | Case studies | A real commons dilemma with an identifiable user group | Shared stock, users' interdependence, rules | Requires a consequential commons. Ours is materially small (§AE B) |
| 8 | Negotiated, self-enforcing rules move groups from a "Hobbesian" game to cooperative equilibria (food-sharing rules, irrigation, property, reputation) | Theoretical review | A proposed evolutionary explanation, not a universal sequence | Rules, negotiation, enforcement | Level 5 only; premature without Levels 3–4 |
| 9 | Need-based asking and giving (osotua) pools risk and extends herd survival | ABM comparison: osotua vs no exchange vs probabilistic giving | Not verified for correlated shocks | Requests, need, giving rule | Close match to our provisioning substrate |
| 10 | Need-based transfers beat debt-based ones for survival. Benefits grow with network modularity and size and shrink with correlated shocks | ABM | Less correlated shocks | Need signal, network, transfer rule (need- vs debt-based) | Directly relevant: our shocks are spatially correlated, but surplus remains abundant (§AE C) |
| 11 | Sharing reduces shortfall risk more than diet switching does, and only a few participants are needed | Simulation | Shortfalls not perfectly correlated *(inferred)* | Stochastic shortfall, sharing group | Supports small local pools |
| 12–13 | Evaluate against several independent patterns; describe entities, schedule, decisions, information and outputs explicitly | Methodology | — | — | Used for the comparison and the §14 specification |

**What the evidence is.**
- *Empirical associations:* 2, 6, and in part 5.
- *Theory:* 1, 3, 4, 7, 8.
- *Simulation demonstrations:* 9, 10, 11.
- No source demonstrates that actors deliberately maximize an insurance benefit (9, 10 and
  11 show outcomes of assumed rules).
- Sources 5 and 6 contradict any simple progression from farming to inequality.

## 3. Five mechanism levels

| level | A access | B coordination | C risk pooling |
|---|---|---|---|
| 1 opportunity | yes: stable, moderately heterogeneous wild capacity | weak: harvest depends only on total effort (no joint-production synergy) | yes: staggered shortages with abundant nearby surplus |
| 2 consequential interaction | yes: co-users deplete one stock within and across years; fields displace wild capacity | barely: pooled vs independent use differs ≈ 1 % | yes: transfers change recipients' intake and survival (5H, 6A) |
| 3 behavioral decision | partial: migration counts others at a destination; no access decision | none (a fixed pooling convention) | **missing**: exogenous φ, central matching, global information |
| 4 persistent relational state | none (fields persist, but are not protected) | none | ties exist but are symmetric and unread by trade |
| 5 institution | none | none | none |

## 4. Simulator substrate (verified in code, MVP 2.2)

Annual order (`core/simulation.py` `build_pipeline`):

```text
climate → ecology → perception → knowledge sharing → farming → FORAGING → TRADE
→ energetics → demography → extinction → FIELD PLANNING → learning → diffusion
→ innovation → fission → fusion → MIGRATION
```

| finding | where |
|---|---|
| **Rival use of a finite stock.** One accessible plant and game stock per cell; within-year harvest concave in total effort, `H(E) = Σ a(1 − e^{−rEw/a})` | `economy/foraging.py` `_harvest`, `cell_harvest`:176; `foraging_kernel.py` `forage_groups`:87 |
| **Automatic pooling.** Co-located units of one species apply one common effort fraction until the *summed* target (`1.2·N − crop`) is met; harvest is split by effective labour | `foraging.py`:342 (target), `cell_harvest`; kernel :156 |
| **Intertemporal commons.** Stocks carry over with `logistic_regrowth` (plant 1.5/y, game 0.4/y) | `ecology/resources.py` `logistic_regrowth`:86; `ecology/subsystems.py` |
| **Land-use externality.** Fields displace wild plant (fully) and game (partly) capacity in the cell | `resources.py` `displacement_multipliers`:121 |
| **Arable sharing.** If desired fields exceed the cell's arable area, all units, incumbents included, are scaled pro rata (no protection of prior clearing) | `agriculture_kernel.py` `plan_fields`:140 |
| **Movement to alternatives.** Belief-based destination utility counts believed *others* (food per prospective head); only cells with an unexpired belief are candidates | `mobility/migration.py` `food_ratio`:46, `gather_candidates`:503 |
| **Central coordination of provisioning.** Global recipient order (most severe first); every same-species offer in range visible; offer `0.3·b` | `economy/trade.py` :127, :133 |
| **Intra-unit pooling.** Equal sharing of food within a unit | `population/energetics.py` `energy_balance`:119 |
| **Control recorded, not enforced.** `field_claim` and `store_claim` are passive; no decision reads them | `population/strata.py`; design §1 |
| **Fission and fusion.** Fusion: smallest unit in a cell joins the largest; fission: a representative split | `population/groups.py`:50, :281 |
| **Outputs independent of control.** Crop goes to the unit holding the fields; wild harvest goes to co-users by labour, not by any claim | as above |

**Scarcity types implemented:**
- *absolute* (local stocks or regional surplus below need);
- *local* (better cells exist at path cost ≤ 60 km, with travel and carry costs);
- *rival access* (the shared within-cell stock; a carried-over depletion; field displacement;
  pro rata arable sharing).

Exclusion, defence, monitoring and sanction are **not implemented** anywhere.

## 5. Methods (pre-registered measures)

- Probe: `scripts/probes/opportunity_audit.py` (one read-only recording pass).
- Helpers: `economy/opportunity_audit.py`.
- Tests: `tests/test_opportunity_audit.py`.
- Runs: MVP 2.2 neolithic 600 y and pressure + cultivation 400 y, seeds 0–3.
- Fidelity:
  - all 8 runs are observer-neutral (physical digest);
  - pooled foraging replays the authoritative harvest **bit for bit in 339,771 / 339,771
    and 75,764 / 75,764 groups**;
  - one-step regrowth replays next year's stock exactly (error 0, 60,345 cell-years).

| criterion | A | B | C |
|---|---|---|---|
| material consequence | harvest gain if co-users absent (static: same stock, labour, target; the unit alone) | pooled vs independent satisficing (each unit stops at its own target, scramble shares by effort): totals, members, shortfalls | from 6A: offers bind; here: whether surplus exists in reach when a unit is short |
| strong result requires | consequential rivalry **and** constrained outside options (analyst and actor) | materially different joint vs independent outcomes, with distinct interests | recurrent, feasible, staggered complementarity at a cost compatible with participation |
| negative control | unoccupied cells are never counted as contested; single-unit cells give alone = pooled = independent (tested) | proportional targets give pooled = independent (tested) | units with no neighbour in reach reported separately |
| what is held fixed | stock, returns, labour, efficiency, targets; no exclusion rule; no feedback | the same | balances before trade; no willingness inferred |
| kind | static counterfactual (one year) + observational | static counterfactual | observational |

## 6. Results — A: resource access (neolithic · pressure)

**Potential** (true accessible capacity, land cells):
- Gini 0.14 · 0.23; p90/p10 1.9 · 3.8.
- Interannual CV p50 0.10 · 0.05; year-to-year rank correlation 0.87 · 0.96.
- So capacity is **predictable but only modestly concentrated**: home capacity relative to
  occupied cells in reach is p10–p90 0.81–1.22 · 0.69–1.48.
- No clumped, dense resource class exists.

**Realized foraging:**
- Own production meets the target in 90 % · 77 % of unit-years.
- Harvest / accessible stock p50 0.20 · 0.21; stock-limited (> 50 % taken) only
  2.5 % · 10.5 %.
- Production is mostly labour- and target-limited, not stock-limited.

**Rivalry is real:**
- 20 % · 62 % of foraging unit-years are in multi-unit cells.
- Being alone would change harvest by p50 +2.5 % · +4.3 % of need. It exceeds +10 % in
  20 % · 23 %, and is negative in the lower tail: pooling gives some units more than their
  own target.
- The summed target exceeds what full effort can take in 39 % · 69 % of groups.
- *Across years:* each kcal removed costs 0.18 · 0.29 kcal of next year's stock. Another
  unit uses the cell next year after 83 % · 95 % of removals, but the loss is only
  5.3 % · 3.7 % of those co-users' need.
- *Fields:* displaced wild capacity per co-resident p50 1.1 % · 2.6 % of need (p90 3.7 % ·
  11 %); 96–97 % of the affected units farm themselves.

**Land never limits:**
- The arable cap binds in **0.000** of 290,391 · 56,770 farming cell-years.
- Incumbents are cut while others expand in 0.04 % (pressure).
- Production is labour-limited.
- So the land-limited condition associated with persistent inequality (source 6) is absent.

**Outside options are open and known** (units in multi-unit cells):
- *Analyst:* a reachable cell with at least the home per-head stock exists for 84 % · 72 %
  (best / home p50 1.5 · 1.2, ≈ 45 km).
- *Actor:* units hold beliefs on p50 20 · 12 alternative cells, believe a better one exists
  in 90 % · 81 % of cases (believed best / home p50 1.9 · 1.5), and none has zero known
  alternatives.

**Verdict A:** resource concentration is measurable, but economic defensibility is **not
identifiable**:
- no defence cost;
- low contrast;
- open, known outside options;
- non-binding land.

Rivalry exists (Level 2), but its decision layer (moving away from crowded cells) is
already represented by migration.

## 7. Results — B: coordination

- **Total harvest:** pooled / independent 1.012 · 1.012. Groups differing by more than
  1 % of target: 19 % · 15 %.
- **Members:** (pooled − independent) / need p10–p90 −0.05..+0.07 · −0.03..+0.06;
  differing by more than 10 %: 8.5 % · 7.0 %.
- **Shortfalls:** pooling-induced shortfalls (short under pooling only) are 0.5 % · 0.7 % of
  members; the reverse never occurs.
- **Crop-fed co-users** (zero target) are 0.2 % · 2.0 % of members and receive 0.03 % ·
  0.3 % of the wild harvest.
- **Heterogeneity** of target per effective hour (max/min) p50 1.2 · 1.35, so interests are
  similar.
- **No synergy:** harvest depends only on total effective effort. Joint work has no
  productivity bonus, and no task needs several units.

**Verdict B:** the shared-patch convention is a numerical sharing rule with small
consequences. It does not hide a coordination problem. Shared code execution is not
social coordination. **Rejected for 6C.** (The intertemporal externality of § 6, 4–5 % of
co-users' need, is too small for a commons dilemma, source 7.)

## 8. Results — C: risk pooling

- **Short before trade:** 5.8 % · 31 % of unit-years.
- **Shortages are spatially correlated:** neighbours are short 22 % vs 4.9 % when a unit is
  / is not short (ratio 4.4) in neolithic; 38 % vs 26 % (1.5) under pressure.
- **Surplus nonetheless abounds:**
  - only 0.1 % · 0.3 % of short units have no surplus neighbour;
  - delivered-equivalent neighbour surplus / own deficit p10 5.0 · 1.8, p50 23 · 14.
- **Staggered recurrence:** when a unit that had a short neighbour falls short itself
  within 10 years (26,888 · 29,849 cases, median delay 4 · 3 y):
  - a **former recipient now has surplus in reach in 63 % · 69 %** (bilateral
    feasibility);
  - **some** neighbour has surplus in 100 % · 99.9 % (network feasibility).
- **Combined with 6A:**
  - offers are a strong causal lever (delivered food ∝ φ under pressure);
  - giving costs ≈ `r` kcal of next year's stores per kcal given;
  - 40–60 % of a gift would spoil anyway;
  - partner-pair reversal *in actual transfers* is only 9 % (5H). This is not for lack of
    opportunity; the central nearest-first queue never routes back.
- **Not established:** willingness. φ = 0.3 stays exogenous, no participant anticipates any
  benefit, and the network benefit says nothing about individual incentive.

**Verdict C:** the strongest physical substrate. The ecology produces recurrent,
complementary, mostly reachable surplus, with role reversal within a few years, at a low
material cost to donors. What fails is the actor level:
- central global priority;
- every offer visible to every deficit unit;
- donors that never see a need;
- no directional memory.

## 9. Cross-pathway comparison

| criterion | A | B | C |
|---|---|---|---|
| material consequence | moderate (2–4 % of need, p90 15 %) | small (≈ 1 %) | large (6A: delivered ∝ φ; recipients' intake and survival) |
| causal specificity | high (stock, depletion) | high, but trivial | high (balance, reach, transport) |
| existing substrate | rivalry yes; land scarcity, density and defence no | no synergy | yes |
| actor and information | defence actor undefined; outside options known | none | recipient (own deficit), donor (own surplus): identifiable |
| variation | with crowding | little | with synchrony, storage and scarcity (neolithic vs pressure differ) |
| persistence and reversal | location persistent, but units can leave | — | role reversal within 3–4 y: persistence and reversal both possible |
| representation | unit-level, but needs defence and exclusion state not justified | unit-level | unit-level; no strata |
| empirical relevance | strong in literature (1, 2, 6), but its conditions are absent here | 7, 8 need a real dilemma | 9, 10, 11 (simulations), conditions present |
| testability | weak (defence cost unidentified) | — | sharp (§14 falsification) |
| simplicity | would need defence, monitoring, exclusion | — | one event, no new persistent state |

- **Hard requirements** (consequence, substrate, identifiable actor): only C meets them.
- **The comparative judgement** is clearest on substrate and testability. A's literature is
  the most compelling empirically, but its preconditions (clumped, dense resources;
  land-limited production; closed outside options) are measurably absent. Building
  exclusion now would manufacture the mechanism.

**Cross-cutting:**
- Mobility undermines A (open, known exits) and supports C (large networks).
- Unit boundaries matter mostly for B: within-unit pooling already absorbs the coordination
  that a household-level model might show.

## 10. Falsification evidence recorded

- A would have been strong had arable caps bound, outside options been closed or unknown,
  or alone-vs-pooled gains been large. None holds.
- B would have been strong had pooled and independent outcomes differed materially. They
  differ ≈ 1 %.
- C would have been weak with synchronized shortages and no surplus in reach. Shortages are
  correlated (neolithic ratio 4.4), yet surplus is in reach for 99.7–99.9 %.

## 11. Measurement scale

PopulationUnits are not households, kin groups, archaeological residential units (source 6)
or polities.

**Observable today:**
- unit-level production, stocks, transfers and their direction;
- spatial occupancy;
- co-use of cells;
- persistence of location.

**Not observable:**
- household wealth distributions (no unit Gini maps to a house-size Gini);
- rank;
- property;
- political subordination.

Persistent location advantage is not hereditary rank. Material reliance is not authority.
The pooled foraging rule is not an institution.

## 12. Rejected alternatives

- **Ownership, exclusion or territorial defence:** no defence cost, open and known exits,
  non-binding land.
- **Commons governance:** no material dilemma.
- **Joint-production coordination:** no synergy in the production function.
- **Partner preference** (5H) and **donor self-insurance** (6A).
- **Land-scarcity inequality:** land never binds. Revisit only if a scenario or a future
  ecology makes land limiting.

## 13. Open questions

- Would a clumped, predictable resource class (aquatic, nut groves) or binding arable land
  change A? This is an ecology question, not a social one.
- Can the willingness premise ever become endogenous? Candidates: directional memory
  (need-based vs debt-based, source 10) or kin (fission genealogy, 6A §7).
- Spatially correlated shocks (neolithic 4.4) may limit pooling benefit in drought years
  (source 10). The recorded synchrony is year-level only.

## 14. Recommended Stage 6C interaction: local need requests with proportional donor rationing

Stated in ODD terms (source 13):

| element | specification |
|---|---|
| **actors** | a *requester*: a unit with `b = H + S − N < 0` before trade. A *donor*: a unit with `b > 0` that receives a request |
| **trigger** | the requester's own pre-trade shortfall (observable to it: own harvest, stores, need) |
| **resource** | the donor's provisionable offer, `o = φ·b` (φ = 0.3 retained as an explicit need-based giving premise, osotua-like), shipped with the existing transport loss |
| **information** | the requester knows its own deficit and which same-species units are within one relocation range (current reach assumption, documented); it does **not** know their surplus. The donor knows its own `b` and only the requests addressed to it. No global queue, no global severity ranking |
| **feasible actions** | the requester asks reachable units nearest first, each for its remaining deficit grossed up for transport. The donor gives each request `x = min(o_left·q/Σq, q)` (proportional to requested amounts `q`, no priority). Unmet requesters re-ask further units in later rounds; rounds end when no transfer occurs or after `K` rounds |
| **behavioral premises (remaining)** | willingness φ (exogenous); need-based (not debt-based) giving; requesters ask nearest first; proportional rationing |
| **constraints** | `Σx ≤ o ≤ b`; reach; transport; the donor pays from harvest then stores (unchanged) |
| **consequences** | recipients' harvest and donors' harvest/stores (as now); ties updated as now. Who is served under contested supply changes, not how much is offered |
| **persistence** | none new (Level 2–3). A directional record is deliberately left to a later stage |
| **representation** | unit-level state suffices (two configurations of a unit with equal `H, S, N, cell` behave identically). No strata |
| **alternative outcomes** | cooperative: abundant surplus, ≈ D0. Competitive: contested donors ration among several requesters; winners change. Unequal: repeatedly nearest requesters capture supply. Neutral: identical to D0 |
| **falsification** | (1) if delivered food, unmet deficit, recipients' intake and the set of served recipients differ from D0 by < 1 % in both scenarios over 4 seeds (static, then branched), centralization was not consequential: stop and return to the willingness question. (2) if results depend materially on `K` or on id tie-breaks, the rule is an artifact. (3) aggregate changes must be separated from redistribution (6A method) |
| **informative without inequality** | whether local information and decentralized rationing change *who* is buffered in scarcity; whether the network buffers correlated shocks; how often requesters must go beyond their nearest donors |
| **minimal implementation (6C)** | `economy/trade.py`: a versioned alternative to the matching in `TradeSubsystem.evaluate` (new rule `local_need_requests`, v1.0); `config/schema.py`: `mechanisms.local_provisioning_requests = False`; static comparison helpers reusing `economy/donor_offer.py`; tests; an opt-in branch. Matching, offers and ties are unchanged when off; MVP 2.1 and 2.2 oracles are identical |

A later stage, not 6C, could test a *directional* exchange memory (need-based vs debt-based,
source 10). This review's reversal feasibility (63–69 %) shows it would have behavioural
room.
