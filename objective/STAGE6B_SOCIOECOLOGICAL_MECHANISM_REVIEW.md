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

**Stage 6B-P4 decision (2026-10-29, for review; §18):** pathway C retained under a symmetric
comparison, by a narrower margin than in 6B (A and B also have causal foundations): local
contact, requests and donor rationing with φ fixed, assumptions unbundled, evaluated for
distinguishable and interpretable consequences against centralized controls on the same
contact graph and the P3 ceiling, with no expected direction. Fallback: choice among rival
resource-use opportunities (A1), pending P5. "Decision D" was 6B's option label, not a
pathway (§18.6).

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
  The cross-pathway judgement is reopened for 6B-P4.) *Superseded by §18.4: this table
  judged A at Levels 4–5 and C at Levels 1–2; P4 compares both at the same level.*

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

*Revised in §18.6 (6B-P4): assumptions unbundled; the falsification criterion "< 1 % from D0"
replaced by comparisons with centralized controls on the same contact graph, scheduling
noise and the P3 ceiling. Kept as the original record.*

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
  for over a century. Whether this is a model gap is for P4 (synthesis) and P5 (roadmap), not a P3 or
  migration-implementation task.
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
- *Execution environments.* An analysis set must share Python and numpy versions,
  dependency lock, belief backend, numeric platform, JIT and thread limits; otherwise it is
  refused, unless `--mixed-environments` requests an explicit comparison, printed as MIXED
  with each run's differing values. Timestamps, durations, start method (serial = parallel
  bit for bit) and `git_dirty` (the source hashes identify the code) are not compared.
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

## 17. Stage 6B-P3 — provisioning supply, demand and simultaneous feasibility (2026-10-28)

**Question.** When units are short while others nearby have surplus, how much unmet need
is physically unavoidable, and how much comes from donor offers, transport losses, the
recorded reach, competing demand, or the matching? No hypothesis is favoured. Everything
here is an analyst's counterfactual on recorded inputs: a feasible allocation is not one any
group knows of, can communicate, or would choose. P3 selects no mechanism (P4).

**Data.** Fresh provenance-verified recordings (§16 infrastructure), MVP 2.2 neolithic
600 y and pressure + cultivation 400 y, seeds 0–3, one execution environment:
- `donor_offer_audit` (schema 1): each unit's pre-trade need, harvest, stores and
  `social.food_sharing_propensity` (resolved per species, 0.3) as read in
  `TradeSubsystem.evaluate`, the reachable offering donors of every deficit unit with path
  costs (`ctx.movement.reachable`, same species), the authoritative transfers;
- `opportunity_audit` (schema 2) of the same runs, joined by `(year, unit id)`: same
  configuration, source and environment, the same units in every trade year, identical
  authoritative transfers (8 / 8 runs). Its data are byte-identical to the P2 recordings,
  so SciPy and the P3 code change nothing in the simulation.
- MVP 2.1 `provisioning_counterfactual` recordings are not used.
- Limitation: all neolithic runs share world 7 and all pressure runs world 3; seeds vary
  climate and demography, not topology.

**Accounting** (verified against the source; per trade year, after farming and foraging,
before energetics). `b = harvest + stores − annual need` (need includes carried energy
debt). Donors: `b > 0`, offer `O = phi·b`. Recipients: `b < 0` and need `> 0`, deficit
`D = −b`. An eligible edge is a same-species offering donor in a cell reachable from the
recipient's cell; `f = exp(−cost / transport_decay_km)` in (0, 1] (0 only by underflow).
Gross surplus `b`, offer `phi·b`, shipped `x`, delivered `f·x` and unmet `D − Σ f·x` are kept
apart; shipments are kcal leaving the donor, deliveries kcal arriving. The production
matching replayed from these inputs (`provisioning_counterfactual.match`) reproduces the
authoritative transfers in 2,400 / 2,400 · 1,600 / 1,600 trade years.

**Benchmark** (`economy/provisioning_feasibility.py`, NOT ACTIVE). Per trade year:
maximize `Σ f_ij x_ij` s.t. `Σ_j x_ij ≤ O_i`, `Σ_i f_ij x_ij ≤ D_j`, `x ≥ 0` on eligible edges;
a sparse LP solved by HiGHS (`scipy.optimize.linprog`). Each solution is checked outside the
solver: eligibility, `x ≥ 0`, budgets and deficits within 1e-9 of the problem scale, and
optimality by LP duality (dual feasibility and duality gap within 1e-7; observed ≤ 7e-15).
HiGHS feasibility tolerances are set to 1e-10; a failure raises, nothing heuristic is
substituted. Global lossless ceilings (every same-species pair, `f = 1`) are analytic,
`min(total budget, total deficit)`. Controlled cases with known optima are tested
(`tests/test_provisioning_feasibility.py`), including two donors of 50 and recipients R1
(reaches both) and R2 (reaches one): greedy 50, optimum 100, independent of ids.

**Results** (kcal summed over seeds and trade years, as % of the total pre-trade deficit;
neolithic 6.86e10 kcal, pressure 1.26e11 kcal):

| measurement | neolithic | pressure |
|---|---|---|
| positive surplus `Σ b` | 3,111 % | 382 % |
| offered `Σ phi·b` | 933 % | 115 % |
| A matching: shipped / delivered | 106 % / 62.6 % | 83.0 % / 44.0 % |
| B optimum: offers, recorded reach, transport | 65.0 % | 50.2 % |
| C optimum: offers, recorded reach, lossless | 79.9 % | 71.4 % |
| H ceiling: offers, all pairs, lossless | 100.0 % | 81.9 % |
| D optimum: full surplus, recorded reach, transport | 90.7 % | 87.3 % |
| G optimum: full surplus, recorded reach, lossless | 98.4 % | 95.6 % |
| E ceiling: full surplus, all pairs, lossless (not realizable) | 100.0 % | 99.9 % |
| matching at full surplus | 89.3 % | 82.0 % |
| unmet under the optimum given offers, reach and transport (deficit − B) | 35.0 % | 49.8 % |
| delivery feasible beyond the matching (B − A) | 2.4 % (3.9 % of A) | 6.2 % (14.2 % of A) |
| shipped / offered (matching); transport loss of shipments | 11.4 %; 41.2 % | 72.4 %; 47.0 % |
| recipient-years still short: matching / optimum | 33.5 % / 28.6 % | 71.5 % / 48.7 % |
| recipient-years receiving nothing: matching / optimum | 21.9 % / 8.2 % | 51.2 % / 21.7 % |

Stage 6A reproduced (pressure): 71.5 % of recipient-years short after matching, 72.4 % of
offers shipped. Stage 6B reproduced: reachable delivered-equivalent *full surplus* / own
deficit p50 22.8 · 13.8 for recipients with a reachable offering donor (22.5 · 13.7 over all
recipient-years; corrected in 6B-P4, which found 22.8 paired with the all-recipient 13.7).

**Annual versus cumulative supply** (closure check). Each trade year is solved alone; no
food moves between years, and a counterfactual allocation does not feed back into later
recorded states (every year is evaluated on the actual history). Pooled over seeds and years
the pressure offers are 115 % of the deficit, but the offer-constrained ceiling is
`H = Σ_t min(offers_t, deficit_t)` = 81.9 %: offers in surplus years cannot cover other
years' deficits (nor another seed's, an independent run). Yearly offers fall short of yearly
deficits in 35.0 % of pressure years with a deficit (1.0 % neolithic), and those years hold
60.8 % of the pressure deficit (offers / deficit there p50 0.74). So the shortfall under
the optimum (49.8 %) splits, in this one order, into an annual aggregate offer gap
(deficit − H) of 18.1 % (neolithic 0.04 %), which no spatial or transport change can close
without larger offers, and reach plus transport given the offers (H − B) of 31.7 % (34.9 %).
In years whose offers do cover the deficit, 35.0 % · 34.9 % of it stays unmet under the
optimum: there the limit is spatial and transport, not aggregate offers.

**Conditional comparisons** (each changes one setting with the others fixed; they are not
additive shares and depend on the order of comparison):

| change | neolithic | pressure |
|---|---|---|
| matching → optimum (offers) / (full surplus) | +2.4 / +1.4 | +6.2 / +5.3 |
| transport → lossless (offers) / (full surplus) | +14.9 / +7.7 | +21.2 / +8.3 |
| recorded reach → all pairs, lossless (offers) / (full surplus) | +20.0 / +1.6 | +10.5 / +4.3 |
| offers → full surplus (transport) / (lossless reach) / (global) | +25.6 / +18.5 / +0.0 | +37.1 / +24.2 / +18.0 |

(percentage points of the total deficit)

**Competition and double counting.**
- Delivered-equivalent offers claimed by recipients (each counts every reachable donor)
  are 1.60 · 4.03 times the distinct offers of the claimed donors. Recipient-years sharing
  a donor with another recipient: 90.7 % · 99.0 %; with ≥ 2 reachable donors 98 % · 99 %.
- Connected donor-recipient networks with all deficits simultaneously satisfiable under the
  offers: 74.5 % · 15.2 % of network-years (multi-recipient 64.6 % · 9.2 %). The
  denominator is every connected component of the usable edges (offer > 0, deficit > 0,
  `f > 0`) in every trade year, pooled over seeds (3,365 · 1,869), each counted once
  whatever its size; recipients reaching no offering donor belong to no network. Networks
  are mostly small in the neolithic (recipients p50 1, max 204; pressure p50 9, max 100), so
  weighted shares are far lower: by recipients 25.4 % · 2.0 %, by deficit 15.6 % · 1.1 %. Networks in which every recipient
  is individually covered by the offers it reaches but not all jointly: 7.1 % · 13.7 % of
  those.
- Recipient-years with no reachable offering donor: 172 / 22,299 · 122 / 38,923.

**Distribution.** Population: recipient-years, i.e. units with `b < 0` and need `> 0` in a
trade year (zero-need and non-deficit units are not recipients, as in production), pooled
over seeds and years (22,299 · 38,923); unit-weighted, and population-weighted ("pop", by the
unit's people at trade). Intake is the authoritative `dietary_intake_ratio` after trade; for
a recipient it equals `(harvest + stores + received) / need` = `1 − unmet / need`, with need
including carried energy debt. Static: no feedback into later years. Three aggregate-optimal
allocations are compared, the solver's own and two labelled tie-breaks (most severe first,
least severe first, by `deficit / need`); none is a distribution rule, and they do not span
every optimal allocation:

| recipient-years | matching | optima (solver · severe · least severe) |
|---|---|---|
| full relief, neolithic | 66.5 % (pop 68.8) | 71.4 · 72.6 · 72.9 % (pop 75.0 · 76.1 · 74.2) |
| nothing, neolithic | 21.9 % (pop 16.5) | 8.2 · 16.5 · 13.2 % |
| intake p1, neolithic | 0.237 (pop 0.307) | 0.269 · 0.236 · 0.219 (pop 0.321 · 0.306 · 0.263) |
| full relief, pressure | 28.5 % (pop 28.8) | 51.3 · 50.5 · 53.7 % (pop 54.5 · 53.7 · 56.9) |
| nothing, pressure | 51.2 % (pop 49.3) | 21.7 · 25.0 · 21.7 % |
| intake p1, pressure | 0.444 (pop 0.479) | 0.386 · 0.385 · 0.366 (pop 0.409 · 0.406 · 0.389) |
| mean intake, pressure | 0.900 | 0.907 · 0.908 · 0.907 |

- Robust across the three optima: more full relief and fewer recipients with nothing, in
  both scenarios (pressure +22 to +25 points of full relief).
- Pressure intake p1 is lower under all three optima (0.37–0.39 vs 0.44), unit- and
  population-weighted. This is shown for these three allocations only; whether every
  aggregate-optimal allocation must lower the tail was not tested (no tail-protecting
  objective was run, by design). Neolithic p1 rises or falls with the tie-break
  (0.219–0.269 vs 0.237): optimizer-dependent, no conclusion.
- The two tie-breaks differ for 18.6 % · 26.4 % of recipient-years, by up to the whole
  deficit. Versus the matching, 12–22 % · 39–46 % of recipient-years gain and 4–9 % · 13–15 %
  lose, depending on the optimum. Gains of single-donor recipients are < 0.1 % of all gains.

**Order and id sensitivity of the matching** (production unchanged; same physics).
"Reassigned" is `Σ |received_variant − received_actual| / 2` over recipient-years, as a share
of total actual delivery; changes in yearly totals account for at most 0.9 · 2.0 points of
it, so it is almost entirely redistribution at a near-equal total. Two kinds of change are
distinguished:
- *Policy changes* (the severity priority or nearest-donor rule replaced): random recipient
  order, i.e. no severity priority: total −1.3 % · +1.4 %, different total in 337 / 2,400 ·
  1,267 / 1,600 years, 15.4 % · 31.1 % reassigned; random donor order −0.2 % · −2.4 %
  (1.0 · 3.9 % reassigned); farthest donor first −0.6 % · −5.9 % (1.5 · 6.3 %).
- *Arbitrary ids and tie-breaks* (policy kept): every unit id relabelled at random: no
  effect in any year. Ids decide only exact ties: no two recipients have equal severity, and
  equal-cost donor ties (15,772 · 32,248 recipient-years) are donors in the same cell with
  the same reach, interchangeable for every recipient. The controlled tests show id effects
  where such ties exist; the recorded runs contain none that matter.

**Interpretation.**
- *Neolithic:* offers exceed deficits nine-fold, yet 35 % of the deficit stays unmet under
  the optimum: the binding constraints are geography and transport (lossless +15, all pairs
  +20 points), not supply or matching (+2.4).
- *Pressure:* every constraint matters. Offers exceed deficits in aggregate (115 %) but not
  in 35 % of years; the offer cap (+37 points), transport (+21), reach (+10) and the matching
  (+6, 14 % of what it delivers) all bind, and they interact (transport matters less at full
  surplus, the matching less at full surplus).
- Full positive surplus is almost never short within a year (E < deficit in 0.25 % of
  pressure years), but that ceiling removes the offer cap. Under the existing offers the
  annual aggregate gap is 18.1 % of the pressure deficit (35 % of years): pressure shortage is
  partly offer-limited in aggregate, partly spatial and transport. In the neolithic it is
  spatial and transport. "Unavoidable" here always means unmet under the stated offers,
  reach, transport and one-year horizon on the recorded history, not physically inevitable.
- The 6B "surplus in reach p50 13.7 × deficit" counted full surpluses, before the offer
  fraction and with each donor counted by every recipient in reach.
- Robust across seeds: (B − A)/A 13–16 % (pressure), 1–5 % (neolithic); one topology per
  scenario.

**For P4.** These are physical bounds under the model's offers, reach and transport. Which
actor-level protocol, if any, could approach them (information, contact, willingness,
commitments) is not addressed. The zero-arable and shared-resource findings of §15 stand
unchanged and are not part of P3.

**Reproduce:**

```bash
uv run pytest tests/test_provisioning_feasibility.py -q
uv run python scripts/probes/donor_offer_audit.py record --jobs 2 --out runs/stage6b_p3/donor
uv run python scripts/probes/opportunity_audit.py record --jobs 2 --out runs/stage6b_p3/opportunity
uv run python scripts/probes/provisioning_feasibility.py analyse --load runs/stage6b_p3/donor --opportunity runs/stage6b_p3/opportunity
```

SciPy (1.18.1, HiGHS) is a development dependency; no model code uses it. numba imports
it at import time to check its version whenever it is installed; the four exactness oracles
are unchanged.

## 18. Stage 6B-P4 — scientific synthesis and Stage 6C decision gate (2026-10-29)

**Status:** synthesis and recommendation for review. No simulator, scenario, test or
baseline file changed. Starting commit `efe2603`, clean tree. P5 (roadmap) and Stage 6C
are not started; this section is not permission to implement.

### 18.1 Question and scope

Which pathway, A (rival resource access), B (productive or distributive coordination) or C
(provisioning and risk pooling), gives the strongest *scientifically interpretable,
actor-level interaction* to investigate next, grounded in the existing ecology, without
presupposing an institution, inequality or a social form? The question is not which pathway
most readily produces hierarchy.

The 6B comparison (§9) was asymmetric. A was judged on economic defensibility and exclusion
(Levels 4–5 of §3), C only on whether a material opportunity exists (Levels 1–2). P4
compares all three at the same level first:

> Does the modeled ecology create a consequential interaction between units, and is there a
> small, explicit unit-level decision that responds to it and is not already represented?

### 18.2 Consolidated evidence

Evidence kinds, in decreasing weight: **O** observed in active simulations; **R** read-only
counterfactual on recorded states; **F** mathematical feasibility bound; **P** behavioural
premise built into the model; **H** hypothesized, not implemented; **S** sociological
interpretation not established by measurement. All figures: MVP 2.2, neolithic 600 y ·
pressure + cultivation 400 y, seeds 0–3, one world topology per scenario (worlds 7 · 3).
Unit-years within a run are not independent replicates; the four seeds are the replicates.

| finding | source | kind | supports | does not support | confidence, limits | pathway |
|---|---|---|---|---|---|---|
| Co-located units share one finite wild stock: 20 % · 62 % of foraging unit-years in multi-unit cells | 6B §6, `opportunity_audit` | O | rival use is common, especially under pressure | contested ownership, exclusion | high; exact replay of pooled harvest (339,771 · 75,764 groups) | A |
| Being alone would raise harvest by p50 2.5 % · 4.3 % of need; > 10 % in ≈ 20 % · 23 % | 6B §6 (P1), `alone_harvest` | R (static, one year) | rivalry is consequential, moderately at the median and strongly in the tail | that units would act on it; dynamic cost | per seed p50 1.6–3.0 % · 3.8–4.9 %, > 10 % in 14–22 % · 20–25 % (P4 reanalysis); no feedback | A |
| Collective utilization > 0.5 in 4.0 % · 28.8 % of foraging cell-years; crop-net target met 74.0 % · 29.3 %; full labor applied and target missed 21.5 % · 62.9 % of eligible unit-years; labor elasticity at full effort p50 0.76 · 0.70 | P1 §15, §15.1 | O / R | under pressure shared stocks are heavily used and most foragers miss their target | a single binding input; stock "limitation" (0.5 is descriptive) | high for the measures; labor and stock limit jointly | A (and B: effort margins are absent where labor is exhausted) |
| Intertemporal cost: 0.18 · 0.29 kcal of next year's stock per kcal removed, ≈ 5.3 % · 3.7 % of co-users' need | 6B §6 | R | a weak intertemporal commons | a commons dilemma | one-step regrowth exact | A, B |
| Zero arable land with positive desired fields: 1,928 / 58,716 pressure farming cell-years, 2,803 unit-years, 221 units, p50 6 and up to 136 years each; neolithic none | P1 §15.1 | O | a recurrent mismatch between a decision rule (field planning) and the location it is made in; migration does not value arable land | that better information would cause migration; land scarcity | high; one topology | A (location), P5 |
| Competition for positive arable land: 25 / 56,788 cell-years (0.044 %); no exclusion rule | P1 §15.1 | O | land competition is rare and local | land-limited production (Kohler et al. 2025) | high; one topology, current parameters | A |
| Better-stocked cells reachable for 84 % · 72 % of units in shared cells; believed in by 90 % · 81 % | 6B §6 | O (beliefs) / R | outside options are usually known | that moving is costless or would be chosen | travel, carrying and familiarity costs not counted | A |
| Pooled vs independent satisficing in multi-unit cells: total harvest 1.012 · 1.012; members differing by > 10 % of need 8.5 % · 7.0 % | 6B §7 | R | the cooperative-stopping convention changes little | that coordination in general is unimportant | per seed 1.011–1.013 · 1.010–1.017 (P4); harvest depends only on total effort (no synergy, no task needing several units, annual step: no timing) | B, A |
| Shortages before trade 5.8 % · 30.6 % of unit-years; spatially correlated (neighbour-short ratio 4.4 · 1.5); hypothetical surplus in reach | 6B §8, P1 | O | complementary shortage and surplus recur | that anyone knows of the surplus; joint availability | high | C |
| Donor offer `φ·b`, φ = 0.3 for every unit with surplus; central matching, most severe first, nearest donor first; global visibility | 6A §AD, `trade.py` | **P** | — | an endogenous sharing decision | a premise, not a finding | C |
| Production matching reconstructed exactly (2,400 · 1,600 trade years); delivered 62.6 % · 44.0 % of the pre-trade deficit; 71.5 % of pressure recipient-years still short | P3 §17 | O | the realized transfers are understood quantitatively | that transfers are negotiated assistance | exact | C |
| Optimum, same offers, reach, transport: 65.0 % · 50.2 %; lossless 79.9 % · 71.4 %; full surplus 90.7 % · 87.3 %; global lossless full surplus 100 % · 99.9 % | P3 §17 | F | allocation adds little under fixed offers (+2.4 · +6.2 points); offers (+25.6 · +37.1 with transport) and transport (+14.9 · +21.2) are the large levers; not additive | that any actor could realize them; causal shares | duality-certified; conditional comparisons | C |
| Annual aggregate offer gap (deficit − H) 0.04 % · 18.1 % of the deficit; yearly offers short in 1.0 % · 35.0 % of years | P3 closure §17 | F | under pressure part of the shortfall is aggregate offers within a year | that it is physically unavoidable (it is conditional on φ) | one-year horizon, no feedback | C |
| Apparent nearby offers counted 1.6 · 4.0 × the distinct offers; networks jointly satisfiable 74.5 % · 15.2 % by count, 15.6 % · 1.1 % by deficit | P3 §17 | F | "surplus in reach" greatly overstates jointly available help, especially under pressure | — | — | C |
| Three aggregate-optimal allocations: full relief 28.5 → 50.5–53.7 % (pressure); intake p1 0.444 → 0.366–0.386 | P3 closure | F | a large redistribution is possible at a small aggregate change | that the tail loss is inevitable, or that any allocation is "right" | three optima only | C |
| Removing the severity priority (random order) reassigns 15.4 % · 31.1 % of delivered food at ±1.4 % total; id relabelling: no effect | P3 §17 | R | allocation policy decides *who* is served much more than *how much* | id artifacts in the recorded runs | — | C |
| Self-insurance cap on offers: no non-arbitrary magnitude, ≈ 1–2 % of withheld kcal would reach a later shortage; rejected | 6A §AD | R | willingness has no motive in the current physics | that willingness is irrelevant | — | C |
| Potential role reversal 51–69 % (by weighting); realized pair reversal under central matching 9 % | P1 §15, 5H §AA | R / O | the physical room for two-way relations exists, but the central queue does not produce two-way dyads | reciprocity | potential only | C |
| Passive strata: representation without consequential difference; Stage 4–5 differentiators rejected or negligible (5B–5F) | MVP3 §L–§AC | O / R | internal distinctions are not yet behaviourally meaningful | that strata are unnecessary in principle | — | P5 |

**Number check (P4).** Every figure above matches the authoritative record (§6–8, §15–17,
§AD, §AE), re-derived where stated. One mixed-denominator citation is corrected: the 6B
measure "reachable delivered-equivalent full surplus / own deficit" is p50 22.5 · 13.7 over all
recipient-years and 22.8 · 13.8 for recipients with a reachable offering donor; §17 and
`status.md` paired 22.8 with 13.7. The task brief's figures agree with the record; its
phrase "18.1 % of cumulative deficit" is correct as the sum of yearly gaps (deficit − H), not a
gap in cumulative offers (which exceed the deficit, 115 %).

**Robust within these experiments:** direction and order of magnitude of every finding
above across all four seeds; replay exactness; the ordering of the P3 benchmarks. **Likely
dependent on topology or parameters:** the zero-arable counts (one pressure world), the
shared-cell frequency and outside options (map, density), the offer lever (φ, storage
retention `r`), transport (`transport_decay_km`, reach), and the correlation of shocks.

### 18.3 Literature

Verified for P4 (Crossref DOI records; access stated honestly). It extends §2, whose
access labels and the corrections below stand.

| source | access | studied | demonstrated | not inferable | MadExplorer hypothesis |
|---|---|---|---|---|---|
| Dyson-Hudson & Smith 1978, *Am. Anthropol.* 80:21, doi:10.1525/aa.1978.80.1.02a00020 | abstract | 3 ethnographic cases | territoriality "seems to accord" with dense, predictable resources | a test; anything about non-exclusive shared use | exclusion pays only on dense, predictable cells once defence has a cost (no cost exists here) |
| Smith & Codding 2021, *PNAS* 118:e2016134118, doi:10.1073/pnas.2016134118 | abstract | 89 Pacific-coast forager societies | reliance on and *ownership* of clumped aquatic resources associates with institutionalized inequality; pressure and warfare do not | causation; ownership sits inside the predictor | needs a clumped resource class, absent here |
| Kohler et al. 2025, *PNAS* 122:e2400691122, doi:10.1073/pnas.2400691122 | full text | > 1,100 sites, house-size Ginis | enduring inequality lags cultivation > 1 millennium; associates with land-limited production, scale, settlement hierarchy (authors: exploratory, cross-sectional) | causal paths; actor interactions | relevant only if land becomes limiting |
| Moritz et al. 2018, "Emergent sustainability in open property regimes", *PNAS* 115:12859, doi:10.1073/pnas.1812028115 | full text | framework + 8 illustrative cases | open access can be sustained by mobile users tracking patches; low circumscription is one boundary condition; when conditions change, systems shift to exclusion or overuse | a test (cases illustrate) | rival use stays open while exits are cheap; rising density or movement cost should precede any advantage of exclusion |
| Moritz, Gardiner, Hubbe, Johnson et al. 2019, "Comparative study of pastoral property regimes in Africa offers no support for economic defensibility model", *Curr. Anthropol.* 60(5):609–636, doi:10.1086/705240 (a distinct publication) | metadata and title only (Crossref; no abstract in the record) | comparative African pastoral property regimes (per title) | per its title, no support for the economic-defensibility model in that sample | anything beyond the title; how defensibility was operationalized; generality beyond African pastoralism | weakens defensibility (Dyson-Hudson & Smith) as the default frame for A; it does not bear on non-exclusive rivalry |
| Schlager & Ostrom 1992, *Land Econ.* 68:249, doi:10.2307/3146375 | metadata | conceptual | operational (access, withdrawal) vs collective-choice rights (management, exclusion, alienation) | — | today every co-located unit has access and withdrawal only |
| Aktipis et al. 2016, *Hum. Ecol.* 44:353, doi:10.1007/s10745-016-9823-z | full text | pairs of agents, Maasai-inspired | need-based transfers outperform account-keeping in volatile settings, but neither beats no exchange unless "generosity", the probability that an agent honors a request it can afford, is ≥ ≈ 0.8, in that model's pairwise setting, shock regime and herd dynamics | emergence (rules imposed); multi-agent networks; any threshold on the *amount* given | the threshold is about the reliability of honoring affordable requests, not the share of surplus offered: it does not map onto φ = 0.3. It suggests that request-honoring reliability, if ever modelled, may matter non-linearly |
| Hao et al. 2015 (online 2014), *Evol. Hum. Behav.* 36:265, doi:10.1016/j.evolhumbehav.2014.12.003 | metadata | network ABM | (reported via Campennì) asking the wealthiest partner beats asking a random one | emergence; verified content | whom to ask matters, and depends on information about partners |
| Campennì, Cronk & Aktipis 2022 (online 2021), *Hum. Ecol.* 50:35, doi:10.1007/s10745-021-00273-6 | abstract + preprint full text | NetLogo ABM, 6–50 agents | need-based > debt-based for survival; advantage largest in small groups with weakly correlated shocks; asking rule uses full knowledge of partners' herds | emergence; spatial correlation (theirs is synchrony) | correlated shortfalls among a unit's contacts should limit any provisioning protocol |
| Jaeggi & Gurven 2013, *Proc. R. Soc. B* 280:20131615, doi:10.1098/rspb.2013.1615 | abstract | meta-analysis of 32 independent study populations, human (foragers and other small-scale societies) and non-human primate, pooled | overall weighted reciprocity effect r = 0.20 (most conservative measure) to 0.48 (least conservative); no human / primate difference; relative effects of reciprocity, kinship and tolerated scrounging similar (abstract; on which subset of populations the three were compared is not stated in the abstract, and the full text was not read) | motives; causation (correlational within populations); that reciprocity dominates; anything about need-based requests | contingency on past giving is empirically comparable in size to kinship and tolerated scrounging, so need-based giving should not be assumed to be the default motive |
| Claessens, Ayers, Cronk & Aktipis 2021, *Evol. Hum. Behav.* 42:104, doi:10.1016/j.evolhumbehav.2020.08.004 | preprint abstract | 3 economic-game experiments | when resources are hidden, people ask without need and refuse when able | field behaviour; dynamics | visibility is a variable: global visibility (current matcher) is a strong assumption |
| Gurven 2004, *Behav. Brain Sci.* 27:543, doi:10.1017/s0140525x04000123 | abstract | review | kin selection, reciprocity, tolerated scrounging and signalling each explain part of sharing; donor control is central | a single rule | donor control and demand pressure are separable assumptions |
| Grimm et al. 2020, *JASSS* 23(2):7, doi:10.18564/jasss.4259 | most of text | method | ODD second update ("purpose and patterns"; optional rationale) | — | specification standard for 6C |
| Winterhalder 1986, *J. Anthropol. Archaeol.* 5:369, doi:10.1016/0278-4165(86)90017-6 | metadata (DOI now verified) | simulation | — (not re-checked) | — | — |

**Corrections to §2.** Source 10: the need-based advantage is largest in *small* groups;
its "correlation" is synchrony across all agents, not spatial correlation; the asking rule
uses full information on partners' herds; access upgraded to abstract + preprint. Source 11
DOI verified. Source 2: "ownership" is part of the predictor. Source 6: the authors call the
analysis exploratory.

**Synthesis.**
- *C:* no source shows request or giving rules emerging; every provisioning model imposes
  them (Aktipis 2011, 2016; Hao 2015; Campennì 2022). Benefits depend on willingness (a
  threshold in Aktipis 2016), group size and synchrony. Empirically, reciprocity matters as
  much as kinship and tolerated scrounging (Jaeggi & Gurven), and hidden resources change
  asking and giving (Claessens). The literature therefore supports C's *questions*
  (whom to ask, what is visible, who decides), not any particular rule.
- *A:* territoriality and inequality sources concern exclusion and ownership, under
  conditions measurably absent here (clumped, dense resources; land-limited production).
  Moritz et al. 2018 is the only source here on non-exclusive shared use, and it makes
  mobility and circumscription, not defence, the first-order variables. Moritz et al. 2019
  (a separate comparative study, read at title level only) reports no support for the
  defensibility model among African pastoral regimes. Neither speaks against rivalry
  *without* exclusion as a substrate for allocation decisions; the A literature reviewed
  simply does not address that question.
- *B:* almost no direct support in this set (Gurven's coordination during acquisition;
  labor exchange in one Moritz 2018 case). **Recorded as an evidence gap of this review, not
  disconfirming evidence:** the coordination literature (e.g. on collective action in
  acquisition or timing) was not searched.
- *Method:* ODD and pattern-oriented modelling separate verification (the code does what is
  specified) from validation (the specification is adequate). The oracle infrastructure
  addresses the first only.

### 18.4 Symmetric comparison

*Revised at P4 closure (2026-10-29). The first P4 draft said A's decisions had "little
margin" and B "no representable" form. Both overstated the evidence and are corrected below.*

Same criteria, same level (a consequential interaction and the smallest new unit-level
decision). No numerical scores. "Not measured" is not "small".

| criterion | A rival access | B coordination | C provisioning |
|---|---|---|---|
| 1 material foundation | **yes:** rival use common (20 % · 62 %), median cost of co-use 1.6–4.9 % of need by seed, > 10 % for 14–25 % of shared-cell unit-years; zero-arable blockage (221 units) | **narrow form tested, small:** pooling of effort within a cell changes total harvest ≈ 1 % (no synergy in the production function). **Untested:** coordination of access (who uses which stock), of timing, of distribution | **yes:** transfers change intake; offers and transport are large levers (P3) |
| 2 smallest new decision | choose among rival resource-use opportunities: which reachable cell to forage or settle, informed by crowding and arable land (not exclusion) | agree on who uses which stock or when (access or timing coordination) | whom to contact; whether and what to request; how a donor rations among requests (offer fixed) |
| 3 margin for that decision | **plausible, not measured.** Exhausted labor (62.9 % of pressure eligible unit-years) removes the *effort* margin, not the *where* margin. Pooled vs independent tested only the stopping rule within one cell, not choice among cells. Better cells are believed for 81–90 % of crowded units (believed best / home p50 1.5–1.9); whether units under-respond is unknown. Migration counts believed co-users but ignores arable land | **not measured.** Access coordination over rival stocks is possible in principle; timing is not representable at an annual step; distributive coordination overlaps C | **measured and bounded:** priority alone reassigns 15–31 % of delivered food; aggregate gain ≤ +2.4 · +6.2 points under fixed offers |
| 4 motivation | own need (represented) | own need; any gain from agreement would need a joint objective (new) | recipient: own deficit (represented). Donor: none; φ is a premise (6A) |
| 5 information | own beliefs on cells and co-users (represented); arable land of other cells (not in migration's utility) | others' intentions (not represented) | own deficit (represented); contact set (to be grounded, §18.6); others' surplus not visible to actors |
| 6 consequences | location, depletion, cultivation, survival, dispersal | allocation of stocks among co-users | who is served, intake, unused offers, contact dependence |
| 7 falsifiability | static: believed and true options vs realized moves; dynamic: requires changing migration | requires a joint-decision model first | static and exact on recorded states, with a physical ceiling (P3) |
| 8 representation | unit level | unit level | unit level |
| 9 complexity and isolation | modifies an existing, central decision; every move changes later states, so consequences are dynamic by nature | needs a new decision structure among co-users | one event inside the trade step; static counterfactuals are exact |
| 10 explanatory value | high: open access under mobility and circumscription (Moritz 2018) is a central question for later access decisions | potentially high; currently unspecified | replaces a non-actor allocation (global matcher, global visibility) in an *already active* between-unit interaction; risk: only a different allocation algorithm |

**Reading of the matrix.**
- A, B and C all have a causal foundation at Level 2 (B through rivalry, which any access
  coordination would act on). Neither A nor B is deprioritized for lacking foundation, and
  neither is asked to justify exclusion, property, synergy or institutions.
- The tested pooling result is small for the stopping rule; it does not bound choice among
  rival cells (A) or untested coordination of access, timing or distribution (B).
- What still separates C at this level:
  1. *Identifiability.* C's first question can be answered by exact static counterfactuals
     on recorded states inside one step, against a certified physical ceiling. A1's
     consequences are intrinsically dynamic (moves change every later state); B lacks a
     specified decision.
  2. *Size of the actor-semantics gap.* The current between-unit food interaction is
     implemented without actors (central queue, global visibility). A's crowding response
     is already mediated by actor beliefs in migration; its gap is a missing information
     item (arable land) in an existing decision.
  These are properties of the mechanisms, not of the repository's infrastructure.
- The margin for C is *larger in evidence*, not necessarily larger in reality: A1's margin
  is unmeasured. C's preference is therefore narrower than the first draft stated.

### 18.5 Candidate actor-level mechanisms (comparable, not instructions)

| | A1: choice among rival resource-use opportunities | B1: coordination of access or timing | C1: local contact, requests and donor rationing (φ fixed) | C2: endogenous willingness |
|---|---|---|---|---|
| hypothesis | units choosing where to forage or settle with crowding and arable land in view change dispersal, depletion and cultivation outcomes beyond the current migration rule | co-users agreeing on access or timing changes outcomes beyond independent use | local contact, requests and donor rationing produce distinguishable, interpretable consequences relative to central matching on the same contact graph | a donor decision on how much to give changes delivery materially |
| decision | which reachable cell to use or move to | who uses which stock, when | whom to ask, what to request, how to ration | fraction of surplus to give |
| information | own beliefs (exist); arable land of believed cells (new to migration) | others' intentions (new) | own deficit; contact set; donor sees only requests received | own state; perhaps past interactions (absent) |
| existing support | `migration.py` (food per head counts believed others); opportunity recordings | none | P3 recordings, `match`, `provisioning_feasibility.solve` | `donor_offer`, 6A recordings |
| new assumptions | arable term (and possibly crowding) in location utility | a joint decision procedure | contact rule, request content, rationing rule, termination | a motive and a magnitude (none anchored, 6A) |
| null / rejection | static re-evaluation shows the current rule already follows the better believed options; or blocked units have no believed arable alternative | — (to be specified) | §18.6 items 5–6 | magnitude cannot be anchored without an arbitrary parameter |
| first step | read-only: do blocked or crowded units have believed better options and stay? | specify a decision | static comparisons (§18.6) | φ sensitivity only |
| scope | migration change (P5 decides whether this is a model correction) | new decision model | analysis first, then opt-in | blocked by motive |
| confounds | travel, familiarity, belief staleness | — | contact definition; φ; transport; no feedback | `r`; budget convention |

### 18.6 Decision

**Decision labels.** The letters used in stage decisions are *option labels of each stage's
brief*, not pathways. Stage 6B chose "Decision D", the option under which pathway C (risk
pooling) was selected and a C mechanism recommended; 6A's "Decision B" is unrelated. P4's own
options are A–D, where Option D is a prerequisite investigation. Below, "C" always means the
*pathway*.

1. **Recommendation: pathway C remains the next investigation, as C1** (local contact,
   requests and donor rationing, φ fixed), not P4 Option D. The preference over A is
   narrower than in the first draft and rests on identifiability and on the actor-semantics
   gap (§18.4), not on A lacking foundation.
2. **Why over A and B at the same level.** All three have a foundation. C1's question is
   answerable exactly and statically within one step against a physical ceiling, and it
   removes a non-actor implementation of an interaction that is already active. A1 is a
   strong candidate whose margin is unmeasured and whose consequences are dynamic; its first
   component (arable information in migration) may be a model-adequacy correction for P5
   rather than a social-pathway choice. B is unspecified beyond the tested pooling rule.
3. **Behavioural assumptions C1 introduces:** a contact rule; what a request communicates;
   a donor rationing rule; a termination rule. It *keeps* φ = 0.3 and transport. It adds no
   memory, preference, debt, kin or visibility of others' surplus.
4. **First falsifiable question (6C-2).** Holding offers, deficits, transport and the
   contact graph fixed, do request sequencing and donor rationing produce consequences
   (delivered food, recipients served, unmet need, lower-tail intake, contact dependence)
   that differ from a centralized control on the same graph by more than arbitrary
   scheduling does, and can each difference be traced to a named assumption? No direction
   is expected: lower delivery is as informative as higher.

**Protocol questions for 6C-1** (to be specified there, not decided here; each is a
behavioural assumption and is varied alone):

| question | options to examine | default for the first static test, and why |
|---|---|---|
| contact eligibility | same species within the current reach (geographic, as the matcher now); same or adjacent cell; units met in prior years | current reach, so contact is held equal to production and the protocol's other parts are isolated; flagged as a premise. If no contact rule can be grounded better than geography, the pathway stays **conditional** |
| requester information | own deficit and contact set only; plus contacts' surplus (visibility as a variable) | own deficit and contact set; others' surplus hidden (the matcher's global visibility is what is being removed) |
| request content | need only (a signal); a quantity | a quantity: remaining deficit grossed up for the edge's transport fraction, so donor shipments can be checked against it |
| donor knowledge | all requests of a round at once; requests one at a time | all requests of a round at once (avoids arrival-order artifacts) |
| rationing | proportional to requested amounts; equal split with redistribution of unused shares; donor's own severity order | proportional and equal both tested; severity order is the central rule's policy and serves as a control |
| donor budget | commitments `Σ_j x_ij ≤ O_i` over all rounds, offer remaining carried between rounds | as stated: the original offer is never exceeded |
| recipient cap | ask one donor per round, or split the request; shipments capped at remaining deficit / f before shipment | one donor per round in the first test (no over-commitment), split-request as a variant |
| termination | no transfer in a round; all requesters satisfied or out of contacts; a round limit K | the first two; K only as a safety bound, and results must be invariant to it. *To check in 6C-1:* "no transfer in a round" can end the protocol while some requesters still have untried contacts (e.g. every request in a round reached an exhausted donor); the rule must be verified against that case, or replaced by "no untried contact with remaining offer" |

**Comparisons (6C-2), all on the same recorded years and offers:**

| arm | contact graph | sequencing | rationing | isolates |
|---|---|---|---|---|
| S existing severity-priority matching | current reach | global, most severe first | donor nearest first | — (production; exact) |
| R centralized random priority | current reach | global, random | nearest first | priority policy on the current reach graph (S vs R) |
| G contact-restricted centralized control | the 6C-1 contact graph | global: severity (G_S) and random (G_R) | nearest first | contact constraint (G_S vs S, G_R vs R). If the contact graph equals current reach, G_S = S, G_R = R and the contact effect is zero by construction |
| L local requests | the same graph as G | requester-driven rounds | proportional / equal | sequencing and rationing (L vs G); rationing alone (L-proportional vs L-equal) |
| F physical ceiling | the same graph | — | — | P3 optimum restricted to the 6C contact graph: an upper bound for G, L and any allocation restricted to that graph. S and R use the current reach graph and need not fall below it unless the two graphs coincide (their own bound is the P3 optimum on current reach) |
| scheduling noise | as in each arm | random orders, ids, K | — | the yardstick for "distinguishable" |

**Contact matching.** Any comparison that isolates allocation policy (priority, sequencing,
rationing) from contact must hold the contact graph fixed: L is compared with G_S and G_R, not
with S or R, unless the 6C contact graph equals current reach.

**Metrics:** delivered food; recipients served (any, full, partial, none); unmet deficit and
its distribution; intake p1 and p10 (authoritative definition); unused offers; contact
dependence (share of a recipient's receipts from its main donor; replaceability when that
donor is removed); scheduling sensitivity. **Repeated dyads** are compared with a
contact-matched null (recurrence under G and R on the same graph, and under random donor
choice within the contact set), never read as relationships by themselves.

5. **Proceed to dynamic implementation (6C-3, 6C-4) only if:**
   - the 6C-1 contact rule is grounded well enough to state as a premise (otherwise C stays
     conditional);
   - the comparison of L with its contact-matched controls (G_S, G_R) gives scientifically
     meaningful, interpretable differences, assessed across the four seeds with seed-level
     uncertainty and heterogeneity reported (alongside the scheduling-noise range), rather
     than a fixed every-seed threshold;
   - each such difference is traced to a named assumption (contact, sequencing or rationing);
   - results are invariant to K and ids, and no graph-restricted arm (G, L) exceeds F;
   - the difference is not merely a reshuffle equivalent to a priority change (L vs the
     contact-matched random-priority control G_R).
   Improved delivery or nutrition is **not** a criterion.
6. **Do not implement C1 dynamically (stop at 6C-2)** if L is indistinguishable from its
   contact-matched controls given the cross-seed uncertainty; if its differences depend on
   K, ids or arbitrary order; if they reduce to a priority change (L vs G_R); or if the
   contact rule cannot be grounded. A redistribution alone is not evidence of a meaningful
   social mechanism. A well-measured null is a scientifically useful result, recorded as
   such: it shows that, under these premises, local contact and rationing add nothing beyond
   central allocation on the same graph.
7. **Fallback: A1** (choice among rival resource-use opportunities with crowding and arable
   land in view). Return to it if C1 is rejected, if contact cannot be grounded, or if P5
   judges the zero-arable / migration mismatch to be a model-adequacy defect that should be
   corrected first. Its first step is read-only (§18.5).
8. **Not assuming the outcome.** No memory, debt, reputation, kin or partner preference; no
   new persistent state; offers unchanged; outcomes may be cooperative, competitive,
   unequal or neutral.
9. **Not yet:** willingness rules, directional memory, reciprocity, credit, partner
   commitment, exclusion, territory, ownership, strata activation, authority, any change to
   migration, any production configuration switch.

**Changes to the 6B proposal (§14).** Assumptions unbundled; the "< 1 % from D0" criterion
replaced by the comparisons above; aggregate gains bounded by F; φ held fixed deliberately
(it is the largest lever, +25.6 · +37.1 points, but has no grounded motive, 6A, and changing it
together with contact would confound both).

**Status labels.** *Demonstrated physical substrate:* complementary shortage and surplus;
rival use of shared stocks; zero-arable blockage. *Proposed actor-level mechanism:* C1.
*Experimentally supported behavioural consequence:* none yet. *Hypothesized persistent
relationship:* none proposed (recurring dyads are first tested against a contact-matched
null). *Hypothesized institution:* none. Food-sharing opportunities are not insurance;
rivalry is not property; the production matcher is not negotiated coordination.

### 18.7 Proposed Stage 6C structure (conditional on approval after P5)

P5 may reorder MVP milestones or implementation priority; this sequence applies only if C1
is retained.

| step | content | exit gate |
|---|---|---|
| 6C-1 | specify contact, request, rationing and termination (table above), in ODD terms | every assumption named and separately variable; contact rule grounded, or the pathway stays conditional |
| 6C-2 | static comparisons S, R, G, L, F with scheduling noise (no simulator change) | §18.6 items 5–6 |
| 6C-3 | minimal opt-in rule, versioned, default off; oracles identical when off | exact equivalence when off; static results reproduced in-run |
| 6C-4 | branched dynamic runs: intake, survival, migration, fission, contact dependence, dyads against the contact-matched null | promote, revise or reject |

### 18.8 Limitations

- One topology per scenario; four seeds; one parameterization (φ, `r`, transport decay,
  reach). C's preference over A rests on identifiability and the actor-semantics gap
  (§18.4); A1's margin is unmeasured, and a measured A1 margin, a scenario making land
  limiting or exits costly, or a P5 adequacy judgement on migration could reverse it.
- All counterfactuals are static: no feedback into demography, migration or stores.
- The literature supports C's questions, not its rules; no source shows provisioning rules
  emerging. B is under-covered by the literature reviewed.
- Several sources were accessed at abstract or metadata level only (§18.3).
- The analyst's information (P3 optimum) exceeds any actor's; the optimum is a bound, not a
  target.

### 18.9 Issues reserved for P5

P5 remains free to reorder the MVP milestones and the implementation priority, including
placing an A1-type correction or capability work before C1.

1. **Zero-arable cultivation** (221 units, up to 136 years): field planning and migration
   do not share information about arable land. A model-adequacy question, not a migration
   feature request.
2. **Shared-resource rivalry** remains a substrate for later resource-access decisions
   (Moritz: mobility and circumscription first), without ownership or territory.
3. **Passive strata:** representation is not mechanism. Strata become necessary only when a
   mechanism makes outcomes depend on within-unit position (e.g. who bears the cost of a
   transfer or of foraging effort).
4. **Provisioning premises:** φ = 0.3, central matching, global priority and geographic
   contact are assumptions whose effects must not be read as endogenous decisions.
5. **Validation vs verification:** exact reproducibility does not establish sociological
   adequacy.
6. **Sequence:** consequential between-unit interaction before internal differentiation;
   whether the MVP order (strata before interaction) should change.
7. **Model capabilities:** no within-year timing, no joint production, no clumped resource
   class, one topology per scenario: each limits a pathway (B, A) independently of evidence.

**Reproduce (P4 reanalysis):** the per-seed A and B figures use the probe's own
`analyse_run` on fresh verified `opportunity_audit` recordings (8 / 8 neutral, commit
`efe2603`); the 6B coverage medians use `donor_offer_audit.inputs` on the P3 recordings.
No repository code was added.
