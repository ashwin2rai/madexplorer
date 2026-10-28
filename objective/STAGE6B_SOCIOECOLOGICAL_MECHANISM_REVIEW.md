# Stage 6B — Socioecological Mechanism Review

**Status:** comparative review, read-only experiment and mechanism selection (2026-10-27).
Nothing implemented or activated. Starting commit `cabe833` (Stage 6A committed), clean tree.
Reference model: MVP 2.2, selected explicitly (`scenarios/mvp2_2_*.yaml`). The MVP 2.2
manifest still reads CANDIDATE. That is an administrative baseline state, distinct from the
scientific acceptance of dietary-intake fertility, and it is unchanged here.
Design summary: `MVP3_SOCIOECONOMIC_STRATA_DESIGN.md` §AE.

**Stage 6B-P1 correction (2026-10-28).** Several measurements below were wrong, mislabelled
or over-interpreted. They are corrected in place, and §15 records what was originally
reported, what changed, and why. The decision below is **provisional**: it is re-examined in
6B-P4 after P2 and P3. P1 issues no pathway decision.

**Decision (original, provisional since 6B-P1): D (pathway C).** The physical substrate for risk pooling between units is
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

- Probe: `scripts/probes/opportunity_audit.py` (one read-only recording pass; since 6B-P1
  it also copies each unit's desired fields from the field-planning kernel, see §15).
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

**Realized foraging** (corrected in 6B-P1, §15):
- Wild harvest meets the *remaining* (crop-net) foraging target in 74.0 % · 29.3 % of
  eligible unit-years (originally reported as 90 % · 77 %, which counted crops twice).
- In 21.5 % · 62.9 % of eligible unit-years the unit's whole group applied all its labor and
  still fell short of its summed target. In a further 5.8 % · 10.6 % the group met it, but
  the effort-proportional split left this unit below its own target.
- Basic need from own production (crop + wild ≥ need, before stores and trade) is met in
  93.0 % · 67.7 % of unit-years. That is a different quantity from target attainment.
- A unit's own harvest share of the cell's accessible stock is p50 0.20 · 0.21, and
  exceeds 0.5 in 2.5 % · 10.5 % (this was originally labelled "stock-limited").
  *Collective* utilization of the cell, meaning all removals over the accessible stock, is
  p50 0.23 · 0.42 per foraging cell-year and exceeds 0.5 in 4.0 % · 28.8 %.
- Groups that miss their summed target remove p50 0.40 · 0.48 of the accessible stock.
  The solver leaves a target unmet only at full labor, so these groups exhausted their
  labor. That is not a binding labor margin: the labor elasticity of harvest at full
  effort is p50 0.76 · 0.70 (§15.1), so more labor would help, less than proportionally,
  and labor and the stock limit jointly. No single binding cause is identified. The earlier claim "production is mostly labour- and target-limited, not
  stock-limited" is withdrawn; under pressure most foraging units do not reach their
  target.

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

**Arable land rarely limits, and only locally** (corrected in 6B-P1; originally "the cap
binds in 0.000", read as "land never limits"):
- Neolithic: 0 / 290,439 farming cell-years at the cap or rationed.
- Pressure, cells with arable land: desired fields exceed the cap, so every unit is scaled
  down, in **25 / 56,788 cell-years (0.044 %)**. All of them have ≥ 2 farming units, with
  desired/cap p50 1.05 (max 1.08). 97 units were planned below fields they wanted to keep
  (22 cell-years).
- Pressure, cells with **no** arable land: 1,928 cell-years (2,803 unit-years) in which units
  wanted fields (p50 5.9 ha) were all planned to zero. None held fields before. The
  original metric skipped these cells. They are a location limit, not contested land, and
  they persist: 221 distinct units, p50 6 and up to 136 years each (§15.1).
- An incumbent contracts while another unit expands in 677 cell-years (1.2 %), but only 24 of
  those are rationed cells. The rest are units' own contraction choices, not the cap.
- Land-limited production in the sense of source 6 (land as the binding factor of a
  population's production) is not observed in these runs. Rare, local rationing exists.
  It is not evidence of land scarcity or of property institutions. "Rare" holds for land
  *competition*; land *unavailability* reaches 3.3 % of pressure farming cell-years and
  falls wholly on a few units (§15.1).

**Better-stocked alternatives are reachable and believed in** (units in multi-unit cells;
current per-head stock; a reachable or believed cell is not a realized or costless move,
and travel, carrying and familiarity costs are not counted here):
- *Analyst:* a reachable cell with at least the home per-head stock exists for 84 % · 72 %
  (best / home p50 1.5 · 1.2, ≈ 45 km).
- *Actor:* units hold beliefs on p50 20 · 12 alternative cells, believe a better one exists
  in 90 % · 81 % of cases (believed best / home p50 1.9 · 1.5), and none has zero known
  alternatives.

**Verdict A:** resource concentration is measurable, but economic defensibility is **not
identifiable**:
- no defence cost;
- low contrast;
- better-stocked cells are usually reachable and believed in (not shown to be realizable
  exits);
- land rationing is rare and local (0.044 % of pressure farming cell-years with arable land).

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

- **Short before trade:** 5.8 % · 30.6 % of all unit-years. (The original figure was
  conditional on having a neighbour in reach; isolated unit-years are 1.2 % · 0.02 %.)
- **Shortages are spatially correlated:** neighbours are short 22 % vs 4.9 % when a unit is
  / is not short (ratio 4.4) in neolithic; 38 % vs 26 % (1.5) under pressure.
- **Hypothetical surplus is nearly always in reach** (pre-competition, whole surplus
  balances after the transport delivery fraction; not offers `φ·b`, not allocated):
  - short units with a neighbour but no surplus unit in reach: 0.11 % · 0.30 %. Counting
    isolated short units, 0.77 % · 0.31 % of all short units;
  - delivered-equivalent surplus in reach / own deficit p10 5.0 · 1.8, p50 23 · 14; ≥ 1 for
    98.9 % · 94.9 %;
  - the same surplus unit is counted by several short units: by ≥ 2 for 56 % · 88 % of the
    surplus units counted at all (p50 2 · 6). The coverage figures are therefore not
    jointly available (reconciled in 6B-P3).
- **Potential role reversal** (corrected labels, 6B-P1; no transfer is observed or
  required). Take a surplus unit with at least one short unit in reach. At its first own
  shortage within 10 years:
  - a *formerly short neighbour* now has surplus in its reach in 63 % · 69 % of origin
    years (26,888 · 29,849, median delay 4 · 3 y);
  - counted once per distinct later shortage (most recent origin; 6,087 · 7,073), 51 % · 61 %
    (median delay 1 y);
  - some unit has surplus in reach in ≈ 100 % · 99.9 %;
  - the earlier wording "a former recipient can help its former donor" is withdrawn.
    Whether the neighbour actually received anything was not recorded.
- **Combined with 6A:**
  - offers are a strong causal lever (delivered food ∝ φ under pressure);
  - giving costs ≈ `r` kcal of next year's stores per kcal given;
  - 40–60 % of a gift would spoil anyway;
  - partner-pair reversal *in actual transfers* is only 9 % (5H). This is not for lack of
    opportunity; the central nearest-first queue never routes back.
- **Not established:** willingness. φ = 0.3 stays exogenous, no participant anticipates any
  benefit, and the network benefit says nothing about individual incentive.

**Verdict C (as originally stated; re-examined in 6B-P3/P4):** the strongest physical substrate. The ecology produces recurrent,
complementary, mostly reachable hypothetical surplus, with frequent *potential* role
reversal, at a low material cost to donors. What fails is the actor level:
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
| actor and information | defence actor undefined; better cells believed in | none | recipient (own deficit), donor (own surplus): identifiable |
| variation | with crowding | little | with synchrony, storage and scarcity (neolithic vs pressure differ) |
| persistence and reversal | location persistent, but units can leave | — | potential role reversal (51–69 %, by weighting): persistence and reversal both possible |
| representation | unit-level, but needs defence and exclusion state not justified | unit-level | unit-level; no strata |
| empirical relevance | strong in literature (1, 2, 6), but its conditions are absent here | 7, 8 need a real dilemma | 9, 10, 11 (simulations), conditions present |
| testability | weak (defence cost unidentified) | — | sharp (§14 falsification) |
| simplicity | would need defence, monitoring, exclusion | — | one event, no new persistent state |

- **Hard requirements** (consequence, substrate, identifiable actor): only C meets them.
- **The comparative judgement** is clearest on substrate and testability. A's literature is
  the most compelling empirically, but its preconditions (clumped, dense resources;
  land-limited production; closed outside options) are measurably absent. Building
  exclusion now would manufacture the mechanism. (6B-P1: land rationing is rare and local
  rather than absent, and under pressure most foraging units miss their remaining target.
  The cross-pathway judgement is reopened for 6B-P4.)

**Cross-cutting:**
- Mobility undermines A (open, known exits) and supports C (large networks).
- Unit boundaries matter mostly for B: within-unit pooling already absorbs the coordination
  that a household-level model might show.

## 10. Falsification evidence recorded

- A would have been strong had arable caps bound, outside options been closed or unknown,
  or alone-vs-pooled gains been large. Caps bind only rarely and locally (0.044 % of pressure
  farming cell-years with arable land). Better cells are usually believed in. Alone-vs-pooled
  gains are moderate.
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

- **Ownership, exclusion or territorial defence:** no defence cost, better cells usually
  reachable and believed in, land rationing rare and local.
- **Commons governance:** no material dilemma.
- **Joint-production coordination:** no synergy in the production function.
- **Partner preference** (5H) and **donor self-insurance** (6A).
- **Land-scarcity inequality:** land rationing is rare and local (pressure 0.044 %; neolithic
  none). Revisit only if a scenario or a future ecology makes land limiting.

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
room. It would be *potential* room, since the statistic observes no transfers (6B-P1).

## 15. Stage 6B-P1 — measurement and diagnostic corrections (2026-10-28)

**Scope.** Corrections to read-only analysis only. The simulator, scenarios, RNG, goldens
and oracles are unchanged. No pathway decision is issued here; that belongs to 6B-P4.

**Data.** There was no earlier recording to reuse, so all eight runs were recorded afresh:
MVP 2.2 neolithic 600 y and pressure + cultivation 400 y, seeds 0–3. All eight are
observer-neutral.
- The recorder additionally copies the field-planning kernel's `desired` scratch array, read
  after the same call (no RNG).
- On every positive-arable farming cell-year (290,439 · 56,788) it reproduces the kernel's
  arable sharing.
- Running the *original* analysis (git `56a5122`) on these recordings reproduces every
  originally reported figure. So each difference below comes from the measurement, not the
  data.

**Kinds of error.**
- (N) numerical result wrong;
- (L) result correct but label or denominator misleading;
- (I) result correct but the conclusion went beyond the observation.

| measurement | original (neolithic · pressure) | corrected (neolithic · pressure) | kind | interpretation changed? |
|---|---|---|---|---|
| foraging-target attainment | `farm + forage ≥ target`: 90.2 % · 76.7 % | `forage ≥ remaining target` (rel. tol 1e-9, above the solver's 1e-12), eligible = remaining target > 0: **283,276/383,045 = 74.0 % · 36,798/125,508 = 29.3 %** | N (the recorded target is already net of crops: `max(need·1.2 − crop, 0)`) | yes: under pressure most foraging units miss their remaining target. "Labour- and target-limited, not stock-limited" withdrawn |
| why the target is missed | — | group applied all labor and missed the summed target: 21.5 % · 62.9 % of eligible; group met it but the effort-proportional split left the unit short: 5.8 % · 10.6 % | new | the limiting input (labor, stock, or their concave combination) is not identified |
| basic need from own production | not separated | crop + wild ≥ need: 93.0 % · 67.7 % of unit-years; + stores 94.2 % · 69.4 % | new | target attainment ≠ nutritional adequacy |
| individual harvest share | "harvest / accessible stock", "stock-limited (> 50 %)": 2.5 % · 10.5 % | `unit_harvest_share` p50 0.20 · 0.21; > 0.5 in 2.5 % · 10.5 % of eligible | L | it is a share, not a limitation test |
| collective stock utilization | not established | cell removals / accessible stock per foraging cell-year (339,771 · 75,764; one group per cell, single species asserted): p50 0.23 · 0.42; > 0.5 in 4.0 % · 28.8 % (multi-unit cells 11.9 % · 33.3 %). Eligible unit-years with own share ≤ 0.5 but cell > 0.5: 3.2 % · 19.3 %. Removal = Σ member harvests to 4e-16 | new | under pressure, shared stocks are used much more heavily than individual shares suggest; groups missing their target remove p50 0.40 · 0.48. No scarcity threshold is asserted |
| arable cap events | "binding 0.000" (rounded; zero-arable cells silently skipped) → "land never limits" | positive-arable cells: at cap 0/290,439 · **26/56,788 (0.046 %)**; rationed (desired > cap) 0 · **25 (0.044 %)**, all multi-unit, desired/cap ≤ 1.08. Zero-arable cells with desired fields 0 · **1,928/58,716 cell-years (3.3 %)**, 2,803 unit-years, all planned to zero, none previously farmed | L + I | land rationing is rare and local, not absent; zero-arable demand is a location limit, not contested land |
| incumbent field reductions | 0.04 % "in a binding cell" (pressure) | incumbent cut while another expands: 221 (0.08 %) · 677 (1.2 %) in any cell, of which in rationed cells 0 · 24; units cut *by rationing* (wanted ≥ current, planned below): 0 · 97 units in 22 cell-years | I | most contractions alongside expansion are own choices, not displacement |
| potential role reversal | "former recipient can help its former donor" 63 % · 69 %, delay 4 · 3 y | formerly short reachable neighbour has surplus in reach at the origin unit's first later shortage: per origin year 63.1 % · 68.8 % (26,888 · 29,849); per distinct later shortage 50.7 % · 60.8 % (6,087 · 7,073), delay p50 1 y | L (no transfer observed) + weighting (one shortage counted once per origin year) | establishes physical potential for reversal only, not reciprocity or realized assistance |
| reachable-surplus coverage | "only 0.1 % · 0.3 % of short units have no surplus neighbour" | conditional on a neighbour: 25/22,152 (0.11 %) · 115/38,916 (0.30 %); of all short units, isolated counted: 172/22,299 (0.77 %) · 122/38,923 (0.31 %). Surplus in reach ≥ deficit: 98.9 % · 94.9 %. Surplus units counted by ≥ 2 short units: 56 % · 88 % | L + I | hypothetical, pre-competition, multiply counted, geographic (not contact or knowledge of stores). Joint feasibility is deferred to 6B-P3 |
| short before trade | 5.8 % · 31 % "of unit-years" | all unit-years 5.82 % · 30.63 %; with a neighbour 5.85 % · 30.63 %; isolated 3.2 % (147/4,614) · 26 % (7/27) | L | unchanged in substance |
| outside options | "open and known" | values unchanged (analyst 84 % · 72 %, believed 90 % · 81 %) | I | a reachable or believed better cell is not a realized, costless move |

**Unchanged and still supported:**
- pooled foraging replay is exact (339,771 · 75,764 groups), and one-step regrowth is exact;
- rivalry in shared cells (alone − pooled p50 +2.5 % · +4.3 % of need) and its intertemporal
  cost (0.18 · 0.29 kcal per kcal removed);
- pooled vs independent ≈ 1.2 % (B);
- spatially correlated but complementary shortages (synchrony ratio 4.4 · 1.5);
- recurring potential role reversal.

**Not established by these recordings** (deferred):
- which units actually received or gave transfers. This would need trade instrumentation
  (6B-P2/P3);
- which input limits a group that applied all its labor (§15.1 measures the labor
  elasticity at full effort; it shows joint limitation, not a single cause);
- whether multiply counted nearby surplus can jointly cover simultaneous deficits (6B-P3).

### 15.1 P1 closure review (2026-10-28)

Answers to the focused closure review. Same recordings (`runs/stage6b_p1/record`), pressure
figures unless stated; neolithic has none of the arable categories (no occupied cell lacks
arable land, and no cell is rationed).

**Arable land: three categories, kept apart.** *Desired fields* are the kernel's per-unit
decision before arable sharing: this year's step toward the unit's target, capped by
labor and need, not the target itself. The decision rule does not consult arable land;
the per-cell sharing then scales every unit by `min(1, arable / Σ desired)` and rounds
fields below 0.05 ha to zero.

| category | numerator / denominator | value |
|---|---|---|
| farming cell-years (base) | occupied cell-years with desired or planned fields | 58,716 (of 75,764 occupied) |
| allocation constrained by the cap (either category below) | cell-years / farming cell-years | 1,953 / 58,716 (3.3 %); 3,028 / 108,361 unit-years with desired fields |
| (1) land unavailable: zero arable, desired > 0 | cell-years / farming cell-years | 1,928 / 58,716 (3.3 %); 2,803 / 108,361 unit-years; 221 distinct units; 6 / 26 / 136 years per unit (p50/p90/max); desired p50 5.9 ha; previously farmed 0 |
| (2) competition: positive arable, desired > cap | cell-years / positive-arable farming cell-years | 25 / 56,788 (0.044 %); all with ≥ 2 cultivators; one cultivator exceeding the land 0; desired / cap ≤ 1.08; 225 unit-years; 565 of 11,700 desired ha unallocated (of 3.78 M desired overall) |
| units cut by rationing (wanted ≥ current, planned below) | units | 97 in 22 cell-years |
| deliberate exclusion | — | no rule excludes a cultivator (pro rata over all units); zeroed by the 0.05 ha rounding after scaling: 0 |

- *Zero-arable desired fields are an intermediate quantity, not accumulated demand.* With
  no fields the unit's desired step is recomputed from zero every year, so it never grows
  toward the target. It is nevertheless a real, recurring intention of the decision rule:
  farming beats foraging there by the rule's own comparison. It has no consequence: no
  cost, no state, and migration does not value arable land, so 221 units stay blocked, some
  for over a century. Whether this is a model gap belongs to P3 (demand) and P4.
- *Qualification of "land constraints are rare".* It holds for competition among
  cultivators (0.044 %). It does not hold for land unavailability (3.3 % of farming
  cell-years, concentrated on few units). No observation concerns exclusion.

**The desired-field diagnostic is a copy, not a duplicate.**
- `plan_with_desired` (probe) wraps the production kernel `plan_fields` for one call and
  copies its `desired` scratch argument afterwards. The kernel never rewrites that array
  while sharing land. No existing interface exposes desired fields: `FieldPlans` carries
  only the changed rows after sharing, and `_evaluate_reference` keeps its list local.
- `test_desired_capture_agrees_with_production_planning` (controlled state: a zero-arable
  cell, a scarce cell with ≥ 3 cultivators including an incumbent, an ample cell with a unit
  contracting by its own choice):
  - plans are identical with and without the capture, and equal to `_evaluate_reference`;
  - with unlimited land the authoritative Python path plants exactly the captured desired
    fields;
  - desired fields do not depend on arable land;
  - the captured fields reproduce the sharing in every cell;
  - the physical digest (events, RNG states, units) is unchanged.
- On the recordings the capture reproduces the kernel's sharing in 290,439 · 56,788 of
  290,439 · 56,788 positive-arable farming cell-years, and all 8 runs are observer-neutral.

**Foraging limitation.**
- *Denominator of "63 %":* eligible pressure unit-years, i.e. unit-years with a remaining
  (crop-net) foraging target > 0, pooled over seeds 0–3: **78,938 / 125,508 (62.9 %)**
  (neolithic 82,239 / 383,045, 21.5 %). At cell level: 48,498 / 75,764 foraging cell-years
  (64.0 %) · 62,689 / 339,771 (18.5 %).
- *Exhausted labor is established exactly.* `cell_harvest` lowers effort only when full
  labor would exceed the target, so a missed target implies full labor. Replaying harvest
  at full labor reproduces the recorded removal in 100 % of these groups.
- *Binding labor margin is not established.* Labor elasticity of harvest at full effort
  (`labor_elasticity`, `E·H'(E)/H(E)`): p10/p50/p90 0.65/0.76/0.89 · 0.57/0.70/0.85;
  ≥ 0.9 in 6.7 % · 3.3 %; < 0.5 in 1.0 % · 5.0 %. More labor would raise harvest, less than
  proportionally: labor and stock depletion limit jointly. This is a property of the
  model's harvest function at the recorded state, not a test of which constraint binds
  behaviourally.
- *Utilization consistency.* Stock is read in the same foraging call, before this year's
  harvest is applied, as stock × access; removal is the same proposal's plant + game
  removal, in kcal; removal equals the sum of member harvests to 3.6e-16. There is one
  foraging group per occupied cell-year (single species asserted), so foraging cell-years
  equal occupied cell-years (339,771 · 75,764), and none has zero accessible stock (no
  undefined ratios). No scarcity is inferred from the 0.5 threshold, which is descriptive.

**Reproduce:**

```bash
uv run pytest tests/test_opportunity_audit.py -q
uv run python scripts/probes/opportunity_audit.py record --jobs 2 --out runs/stage6b_p1/record
uv run python scripts/probes/opportunity_audit.py analyse --load runs/stage6b_p1/record --jobs 1
```

Recordings made before 6B-P1 lack desired fields and cannot be analysed by the current
probe. The 6B-P1 recordings (`runs/stage6b_p1/record`) carry no provenance; since 6B-P2 they
load only with `--legacy-unverified` (§16), and the 6B-P2 recordings reproduce their data
exactly.

## 16. Stage 6B-P2 — recording provenance and audit integrity (2026-10-28)

**Scope.** Engineering and scientific integrity of recording, validation and analysis. No
file under `src/` changed; the model, scenarios, RNG, goldens and oracles are unchanged.
No scientific decision is issued; transfers are recorded, not interpreted (P3, P4).

**Weaknesses found** (probes `opportunity_audit`, `donor_offer_audit`,
`provisioning_counterfactual`):
- an existing `NAME_SEED.pkl` was skipped because of its name, and analysis read every
  `*.pkl` in the directory: a wrong, partial, duplicated or stale file was used silently;
- recordings had no provenance (configuration, source, schema, environment), and a killed
  writer could leave a truncated file under the final name;
- neutrality was `physical_digest`: events, RNG states and a few unit fields. It misses
  ecological stocks, trade ties, beliefs, familiarity, the id allocator and other state
  (a test shows it unchanged after editing stocks and ties);
- hooks replaced class methods and a module function for the whole run; jobs reusing a pool
  worker relied on every `remove()` running;
- 6B observed potential assistance only. `provisioning_counterfactual` records
  authoritative transfers, but of MVP 2.1 runs (`_common.REFERENCE`), so they cannot be
  joined to the MVP 2.2 6B recordings.

**Corrections** (`scripts/probes/_integrity.py`, shared by the three probes):
- *Container and provenance.* One pickle per run, `{format, provenance, data_sha256, data}`
  with the data as pickled bytes, written to a temporary file, fsynced and renamed. The
  provenance is `core.provenance.run_manifest` (config hash, source-tree hash, git commit and
  dirty flag, package, lock, Python and numpy versions, belief backend, timestamp) plus the
  identity of the run (probe, `recording_schema_version`, run key, scenario path, settings,
  seed, world seed, requested horizon, `probe_sha256` over the probe script and its helper
  modules), execution settings (numeric platform, JIT, start method, thread limits), years
  completed and the neutrality record. Schemas: opportunity 2 (1 = the P1 layout), the others 1.
- *Reuse.* `record` keeps a recording only if it is intact and every identity key, including
  source and probe hash, matches; anything else stops the command and lists why
  (`--replace` overwrites deliberately).
- *Analysis.* Exactly one recording per requested run; duplicates, unexpected runs, missing
  runs, schema or configuration mismatches, failed neutrality and mixed sources are errors.
  A source differing from the checked-out code is allowed but flagged per run. `--seeds`
  analyses an explicit subset; the analysed set is printed with its provenance.
- *Legacy policy.* Recordings without provenance load only with `--legacy-unverified`, are
  printed as PROVENANCE UNVERIFIED, are never reused by `record`, and cannot be mixed with
  verified ones. Nothing is migrated or rewritten.
- *State fingerprint* (audit-only, one hash per component). Control (year, id allocator, RNG
  stream states read without creating streams, events), world, climate, ecology, strata ids
  and sidecars, storage slots, unit order, and every unit field declared in
  `population.fields.UNIT_FIELDS` read through its authoritative storage (table, belief
  store, strata table): cohorts, cell, stores, reserves, harvests, fields, knowledge,
  technologies, trade ties, familiarity, residence, beliefs (logical: current entries by
  cell, backend-independent), strata and the rest. *Excluded*, because no later year reads
  them: caches (capability maps, reachability, step-context transients), belief-store
  capacity and expired rows (raw rows are the raw oracle's), unit-object caches, timings,
  metrics recorders (probes record no metrics).
- *Neutrality.* An uninstrumented twin is stepped in lockstep; fingerprints are compared
  every 25 years and at the last year, and `physical_digest` at the end.
- *Hooks.* On the simulator's own subsystem instances (`hook`); the class and every other
  simulator are untouched. `plan_fields` and `gather_candidates` are swapped only during the
  instrumented call (`swapped`, restored on any exit). Captured values are copies or
  immutable. Pool workers are separate processes (`fork`); within one, hooks cannot leak.
- *Transfers.* The opportunity probe records each year's authoritative `Transfer`s
  (donor, recipient, shipped, delivered, recipient need; an empty list in a year without
  any) and the step's trade ledger. They join the observations by `(year, unit id)`: ids are
  allocated monotonically and never reused, fission creates new ids, fusion and extinction
  retire them.

**Reference demonstration** (MVP 2.2 neolithic 600 y and pressure + cultivation 400 y,
seeds 0–3; 2 CPUs; sparse beliefs; JIT on):

| check | result |
|---|---|
| record, `--jobs 2` (set A) | 8 / 8 runs, 183 s, all neutral (fingerprint at every 25-year checkpoint and the end; `physical_digest` equal) |
| record again into A | 8 / 8 valid recordings kept, nothing re-recorded |
| record, `--jobs 1` (set B) | 239 s; data bytes identical to A in 8 / 8 runs; provenance differs only in `timestamp_utc` |
| A versus the P1 recordings | `years`, `static`, `known` equal in 8 / 8 runs (NaN-aware deep comparison); A adds `transfers`, `trade_ledger` |
| analyse A twice (`--jobs 2`, `--jobs 1`) | identical output except elapsed time |
| analyse A versus P1 recordings (legacy mode) | identical figures; only the transfer section differs |
| legacy P1 recordings without the flag | refused, listing each file |
| `--seeds 0` subset | 2 runs analysed, 6 listed as ignored |
| transfer integrity (neolithic · pressure) | 59,588 · 76,603 transfers in 2,400 · 1,600 trade years (1,098 · 10 without any); ids recorded, delivery = shipped × exp(−cost/decay), need, and recipient short / donor in surplus: all exact; shipped and loss = ledger in every year; no id reappears |

Every P1 figure (§15, §15.1) is therefore reproduced from fully verified recordings.

**Limitations.**
- Pickle is trusted input: open only recordings you made.
- Source identity covers the `madexplorer` package and the probe scripts; scenario and
  species files enter through `config_hash`, the dependency lock through its hash. Compiled
  JIT caches and the numeric platform are recorded, not verified.
- Analysis accepts a consistent recording set made with other source code (flagged); the
  recording schema version, not the source hash, guards structural compatibility.
- Neutrality is checked at checkpoints (every 25 y and the end), not every year; the
  fingerprint covers state, not transient step-context values within a year.
- Other research probes keep the older `_common.physical_digest` and class-level hooks; they
  are outside P2's scope and their results are unchanged.
