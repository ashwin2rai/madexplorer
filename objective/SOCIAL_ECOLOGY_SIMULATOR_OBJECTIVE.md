# Social-Ecological Civilization Simulator

## Objective, Model Specification, and Software Engineering Guidelines

**Working title:** `socioecology-sim`
**Primary implementation language:** Python 3.12+
**Document status:** Initial objective/specification
**Primary goal:** Build a reproducible, extensible simulation engine in which populations, cultures, institutions, technologies, and political structures emerge from interactions among species biology, environment, resources, ecology, incentives, social behavior, and stochastic events.

---

## 1. Project Objective

The simulator should model intelligent populations placed into a spatially explicit world with topology, climate, natural resources, plant and animal ecologies, and initial population seeds. The simulation should advance through a user-specified time horizon and record how populations:

- move through geography;
- forage, hunt, farm, herd, trade, build, and extract resources;
- grow or shrink demographically;
- accumulate and transmit knowledge;
- invent and diffuse technologies;
- form families, factions, coalitions, hierarchies, institutions, settlements, and states;
- split, merge, migrate, revolt, conquer, collapse, or decentralize;
- generate and distribute wealth and surplus;
- experience health, mortality, disease, nutrition, and biological development;
- create cultural norms, status systems, and political preferences;
- alter the ecosystems they inhabit;
- respond to shocks such as droughts, epidemics, war, climate change, and resource depletion.

The simulation is not intended to reproduce a predetermined historical sequence. It should encode local mechanisms and testable behavioral hypotheses while allowing macro-scale outcomes to emerge.

The core research question is:

> Given a species, geography, ecology, initial population, and behavioral assumptions, what social, technological, demographic, political, and ecological patterns repeatedly emerge across stochastic simulation runs?

A secondary objective is to make the species model configurable enough to simulate non-human and fantasy intelligent species such as elves, fairies, dwarves, giants, or entirely novel species without rewriting the social simulation engine.

---

## 2. Fundamental Design Philosophy

### 2.1 Encode mechanisms, not historical outcomes

The engine should not contain rules such as:

- `population > 50_000 -> create state`;
- `surplus > threshold -> create aristocracy`;
- `rainforest -> low civilization`;
- `collapse -> population becomes healthier`;
- `elves -> forest civilization`.

Instead, it should encode mechanisms such as:

- food availability;
- labor productivity;
- resource appropriability;
- mobility cost;
- coordination cost;
- status competition;
- wealth accumulation;
- inheritance;
- coercive capacity;
- autonomy preferences;
- public-good production;
- disease transmission;
- childhood nutritional stress;
- institutional legitimacy;
- trade and knowledge diffusion.

States, aristocracies, nomadic frontiers, empires, decentralized societies, collapses, and ecological niches should be emergent interpretations of these mechanisms.

### 2.2 Separate assumptions from outcomes

Every substantive assumption about intelligent behavior should be an explicit configurable parameter or model component. Where possible, assumptions should be grouped into interchangeable hypothesis modules so that a user can run counterfactual simulations with a mechanism enabled, disabled, or altered.

Examples:

- status-seeking enabled vs. disabled;
- inheritable wealth enabled vs. disabled;
- strong autonomy preference vs. weak autonomy preference;
- high vs. low coalition-forming tendency;
- state public-goods efficiency high vs. low;
- strong vs. weak wealth-health relationship.

### 2.3 Preserve heterogeneity

Population units must represent distributions, not average persons. Aggregation should preserve important variation in wealth, health, age, political attitudes, occupations, skills, and other variables.

### 2.4 Use adaptive resolution

The simulation should dynamically alter agent resolution as population and complexity increase. Small populations may be represented person-by-person. Large populations should be represented by weighted statistical population units. Politically or historically consequential tails, such as ruling families or elite factions, may remain at higher resolution than the mass population.

### 2.5 Treat "civilization" as multidimensional

Do not use a single civilization score. Track at least:

- total production;
- per-capita consumption;
- wealth distribution;
- biological welfare;
- state capacity;
- elite capture;
- political autonomy;
- knowledge stock;
- technological capabilities;
- ecological sustainability;
- trade connectivity;
- social cohesion;
- institutional legitimacy.

A polity may be technologically sophisticated while biologically unhealthy, wealthy while unequal, centralized while weak, or decentralized while prosperous.

---

## 3. Simulation Inputs

A simulation run should be fully defined by versioned input configuration and a random seed.

### 3.1 Required inputs

1. **World topology**
   - grid dimensions or mesh;
   - cell coordinates;
   - elevation;
   - slope;
   - water bodies;
   - river graph;
   - coastline;
   - optional caves, islands, underground layers, or vertical habitats.

2. **Climate/environment**
   - temperature regime;
   - precipitation;
   - seasonality;
   - wind;
   - solar exposure;
   - soil properties;
   - vegetation density;
   - biome attributes;
   - stochastic climate variation.

3. **Ecology**
   - plant species;
   - animal species;
   - biomass;
   - edible biomass;
   - predation;
   - reproduction;
   - migration;
   - disease reservoirs;
   - domesticability traits.

4. **Intelligent species definitions**
   - human or fantasy species profiles;
   - physiological distributions;
   - life-history parameters;
   - movement capabilities;
   - cognition and learning parameters;
   - social-psychology distributions.

5. **Initial population seeds**
   - position;
   - population size;
   - species;
   - age/sex/reproduction structure if applicable;
   - starting technologies;
   - starting knowledge;
   - cultural parameters;
   - initial wealth/resources;
   - optional starting institutions.

6. **Time horizon**
   - start time;
   - end time or number of years;
   - base timestep;
   - seasonal resolution if needed.

7. **Simulation seed**
   - random seed;
   - deterministic PRNG configuration.

### 3.2 Optional inputs

- exogenous disasters;
- known climate series;
- pre-existing roads or ruins;
- external migration events;
- pre-seeded languages;
- religious or ideological traits;
- scenario-specific technology constraints;
- explicit magic systems for fantasy worlds;
- multiple intelligent species occupying the same world.

---

## 4. Spatial World Model

### 4.1 Cell representation

Each spatial cell `c` at time `t` should expose a state vector:

```text
CellState(c, t):
    elevation
    slope
    temperature
    rainfall
    seasonality
    wind
    water_access
    river_access
    soil_nutrients
    soil_depth
    erosion_risk
    vegetation_density
    canopy_density
    understory_density
    biomass
    edible_biomass
    pathogen_pressure
    carrying_resources
    infrastructure
    land_use
    ecosystem_state
```

The world can begin as a regular square/hex grid for the MVP. The architecture should not assume that only grids are possible; later versions may use graph or irregular mesh representations.

### 4.2 Environment is dynamic

Cells should change through:

- seasons;
- climate trends;
- storms;
- drought;
- floods;
- fires;
- soil degradation;
- erosion;
- succession;
- human clearing;
- irrigation;
- construction;
- domestication;
- pollution;
- overhunting.

### 4.3 Accessibility, not biome labels

Do not encode a generic jungle penalty. Dense forests should affect several separate mechanisms:

- movement friction;
- line-of-sight and information radius;
- clearing labor;
- road construction cost;
- agricultural preparation;
- military projection;
- bulk transport;
- hunting/search time;
- state legibility.

The impact should depend on species physiology and technology.

A conceptual movement cost is:

```text
movement_cost = distance
              * terrain_friction
              * vegetation_friction
              * weather_friction
              / mobility_technology
```

For a species capable of flight, some components may be greatly reduced while wind and energy costs become more important.

### 4.4 Accessible food productivity

Distinguish ecological productivity from human-accessible food:

```text
accessible_calories = total_edible_calories
                    * accessibility
                    * harvest_efficiency
                    * knowledge_efficiency
```

A highly productive ecosystem can still provide low food return per labor hour for a particular species or technological regime.

### 4.5 Agriculture

Agricultural return should account for clearing, preparation, planting, maintenance, harvest, transport, storage, pests, and soil dynamics.

```text
net_food_return = harvest_calories / total_labor_cost
```

Forest agriculture may be viable through shifting cultivation, agroforestry, or specialized crops even where fixed-field cereal agriculture is difficult.

### 4.6 Landscape legibility

Track a derived measure of how easily a political actor can observe, tax, patrol, and administer a landscape.

Possible contributors:

```text
legibility = f(
    visibility,
    road_connectivity,
    settlement_concentration,
    crop_concentration,
    harvest_seasonality,
    storability,
    mobility_barriers,
    recordkeeping_technology
)
```

Low-legibility environments should make centralized extraction more expensive, not make intelligent life impossible.

---

## 5. Species Model

Humanity should be represented as one `SpeciesProfile`, not as hidden constants in the simulation.

### 5.1 SpeciesProfile

```text
SpeciesProfile
    physiology
    life_history
    metabolism
    movement
    cognition
    social_psychology
    perception
    manipulation
    niche_construction
```

### 5.2 Physiology

Represent traits as distributions where appropriate:

- adult body mass;
- height;
- strength;
- agility;
- endurance;
- heat tolerance;
- cold tolerance;
- disease resistance;
- injury resistance;
- healing rate;
- sleep need;
- sensory acuity.

### 5.3 Life history

- expected lifespan;
- mortality curve;
- maturation age;
- fertility schedule;
- pregnancy/gestation duration;
- pregnancy cost;
- offspring per birth;
- parental investment;
- menopause or equivalent;
- aging rate.

Use survival distributions such as Gompertz, Weibull, or empirical tables rather than fixed death ages.

### 5.4 Metabolism

- calorie requirements;
- water requirements;
- thermoregulation costs;
- diet breadth;
- digestion efficiencies;
- starvation tolerance.

### 5.5 Movement

- walking speed;
- running speed;
- swimming;
- climbing;
- flight;
- burrowing;
- carrying capacity;
- terrain-specific movement costs;
- weather sensitivity.

### 5.6 Cognition

Avoid a single intelligence scalar. Prefer dimensions such as:

- working memory;
- long-term memory;
- abstraction;
- spatial reasoning;
- social inference;
- planning horizon;
- learning speed;
- imitation;
- invention probability;
- teaching efficiency;
- knowledge retention.

### 5.7 Social psychology

Possible traits, ideally as population distributions:

- sociability;
- kin bias;
- reciprocity;
- conformity;
- status-seeking;
- dominance-seeking;
- autonomy preference;
- aggression;
- risk tolerance;
- coalition tendency;
- punishment tendency;
- out-group caution;
- generosity;
- trust propensity.

These parameters should influence behavior but should not directly define institutions.

### 5.8 Fantasy-species examples

#### Long-lived elves

Possible parameters:

- very long lifespan;
- late maturation;
- low fertility;
- high disease resistance;
- high agility;
- long planning horizon;
- high long-term memory.

Possible emergent consequences include long elite tenures, slow demographic recovery from war, long-lived personal grievances, lower need for archival institutions, or unusually persistent wealth accumulation. These are outcomes to observe, not pre-coded rules.

#### Flying fairies

Possible parameters:

- very low body mass;
- flight capability;
- high movement energy cost;
- low carrying capacity;
- high weather sensitivity;
- reduced river/cliff movement barriers.

Possible emergent outcomes include high information connectivity and low bulk-transport capacity.

---

## 6. Adaptive Population Representation

### 6.1 PopulationUnit

The core simulation actor is a `PopulationUnit`. It may represent one person or many people.

```text
PopulationUnit
    id
    species_id
    population_weight
    location
    demographic_distribution
    wealth_distribution
    health_distribution
    preference_distributions
    occupation_distribution
    skills_distribution
    cultural_state
    political_state
    knowledge_state
    resource_state
    social_links
```

### 6.2 Adaptive resolution

Resolution should depend on:

```text
resolution = f(
    represented_population,
    heterogeneity,
    political_leverage,
    event_intensity,
    uncertainty,
    computational_budget
)
```

Examples:

- a nomadic band of 30 may use 30 individual agents;
- a stable farming population of 2 million may use hundreds of weighted population units;
- a handful of rulers, generals, inventors, or major faction leaders may remain individual even when the general population is highly aggregated.

### 6.3 Statistical super-agents

If a unit represents `N` persons, unit-level outcomes should be computed by integrating or sampling over internal distributions rather than assuming identical behavior.

For a behavioral variable `x`:

```text
N_action = N * integral(P(action | x) * p(x) dx)
```

Approximate using:

- analytic moments where possible;
- quadrature;
- representative quantiles;
- stratified Monte Carlo;
- moment-matching approximations.

### 6.4 Splitting

Split a population unit when an event produces meaningful conditional divergence.

Examples:

- migration selects for high autonomy or risk tolerance;
- famine disproportionately harms low-wealth households;
- epidemic mortality varies by age or health;
- conscription affects particular cohorts;
- religious conversion divides cultural identity;
- class formation separates the upper wealth tail;
- rebellion sorts populations by political loyalty.

Conceptually:

```text
if conditional_response_variance > split_threshold:
    split_unit()
```

Daughter units must inherit conditional distributions, not copies of the original population distribution.

### 6.5 Merging

Merge units when they:

- occupy the same spatial/political context;
- have sufficiently similar state distributions;
- have no important unique social links;
- are below a political-importance threshold.

Distribution similarity can use metrics such as:

- KL divergence where appropriate;
- Jensen-Shannon divergence;
- Wasserstein distance;
- moment-based heuristics.

### 6.6 Sampling noise

Small populations should experience stronger stochasticity. Large populations should become more statistically predictable.

For sample means:

```text
standard_error ~= sigma / sqrt(N)
```

Do not remove rare high-leverage individual events simply because a population is large; retain high-resolution actors where their structural position justifies it.

---

## 7. Distribution Model

### 7.1 Use distributions appropriate to each variable

Examples:

| Variable | Candidate representation |
|---|---|
| height | Normal or empirical mixture |
| body mass | Lognormal or empirical |
| lifespan | Weibull/Gompertz/empirical survival |
| fertility | Poisson/negative binomial/empirical age schedule |
| wealth | Lognormal body + Pareto tail, or empirical quantiles |
| land ownership | Heavy-tailed |
| health propensity | Beta/logit-normal |
| risk preference | Beta |
| political loyalty | Categorical / Dirichlet |
| occupation | Categorical distribution |
| social-network degree | Heavy-tailed / empirical |
| innovation waiting time | Exponential/Weibull/hazard model |

### 7.2 Wealth distribution

A useful starting model is a lognormal body with a Pareto upper tail:

```text
wealth ~ Lognormal(mu, sigma) below cutoff
wealth ~ Pareto(alpha, cutoff) above cutoff
```

The exact form should be configurable.

### 7.3 Preserve correlations

Do not independently sample wealth, health, fertility, political influence, and other correlated variables.

Use either:

- conditional models;
- copulas;
- joint mixture models;
- synthetic micro-samples retained within a population unit;
- quantile bins with cross-variable covariance.

Examples:

```text
P(health | wealth, age, disease, occupation)
P(power | wealth, status, kinship, coercive_resources)
P(migration | autonomy, wealth, risk_tolerance, mobility_cost)
P(fertility | health, wealth, culture, age)
```

### 7.4 Parameter uncertainty

Distinguish:

- population heterogeneity;
- model parameter uncertainty;
- stochastic environmental variation.

They should not be represented by the same random variable.

---

## 8. Demography and Health

### 8.1 Population dynamics

At minimum track:

- births;
- deaths;
- migration;
- age structure;
- sex/reproductive structure where relevant;
- household or kin structure at appropriate resolution.

Simple logistic growth may be useful as a diagnostic but should not be the primary demographic engine once resource and health systems are active.

### 8.2 Resource-mediated fertility and mortality

Fertility and mortality should respond to:

- nutritional state;
- disease;
- physical workload;
- wealth;
- cultural norms;
- reproductive technology;
- war;
- maternal health;
- environmental conditions.

### 8.3 Wealth and health

Do not directly implement:

```text
health = k * wealth
```

Instead:

```text
wealth_distribution
    -> access to food
    -> housing
    -> sanitation
    -> rest/workload
    -> medical access
    -> exposure risk
    -> health outcomes
```

Use diminishing returns for many material health benefits.

### 8.4 Biological standard of living

Track biological welfare independently from aggregate wealth.

Potential metrics:

- adult height distribution;
- childhood growth stress;
- mortality by age;
- disease burden;
- disability;
- life expectancy;
- nutritional adequacy;
- workload.

### 8.5 Height and development

Adult height should reflect developmental history, not current adult wealth.

Conceptual model:

```text
growth_penalty = sum_over_childhood(
    malnutrition
    + infection
    + physical_stress
)

adult_height = genetic_potential - growth_penalty + noise
```

This allows political-economic changes to affect biological outcomes with generational delay.

---

## 9. Subsistence and Economy

### 9.1 Production

Production depends on:

- environmental resources;
- labor;
- tools;
- technology;
- skills;
- organization;
- infrastructure;
- ecological sustainability.

### 9.2 Surplus

Define surplus as resources remaining after subsistence and required maintenance:

```text
surplus = production
        - subsistence_consumption
        - maintenance
        - replacement_costs
```

Surplus can be stored, invested, redistributed, consumed, appropriated, traded, or wasted.

### 9.3 Specialization

Higher reliable surplus can support occupational specialization:

- crafts;
- administration;
- warfare;
- engineering;
- scholarship;
- religion;
- trade.

Specialization should improve some forms of productivity and innovation while creating dependence on trade and coordination.

### 9.4 Storage and lootability

Resources should have attributes including:

- storability;
- concentration;
- transportability;
- visibility;
- divisibility;
- spoilage;
- harvest seasonality.

These affect the ease with which surplus can be accumulated or appropriated.

---

## 10. Migration, Exploration, and Settlement

### 10.1 Local knowledge

Agents should not know the entire map.

Each unit maintains a belief/knowledge model of:

- current cell;
- neighboring cells;
- previously visited cells;
- information received through social networks or trade.

### 10.2 Perceived utility

Migration decisions should use perceived, not omniscient, utility:

```text
perceived_utility(cell) =
    food_expectation
    + water_access
    + trade_opportunity
    + security
    + autonomy
    - movement_cost
    - disease_risk
    - conflict_risk
    - extraction_burden
    + perception_noise
```

### 10.3 Exploration

Exploration radius and quality depend on:

- terrain visibility;
- vegetation;
- navigation skills;
- species perception;
- mobility technology;
- existing trails or roads;
- social information.

### 10.4 Forests and difficult terrain

Dense forests should emerge as difficult or favorable depending on:

- species mobility;
- knowledge;
- technologies;
- available food species;
- soil;
- disease;
- climate;
- rivers;
- population density.

This enables open Near-Eastern-like agricultural cores to emerge under some configurations without hard-coding them as privileged regions.

---

## 11. Knowledge, Technology, and Innovation

### 11.1 Knowledge stock

Track knowledge by domain rather than a single number:

```text
knowledge:
    ecology
    agriculture
    medicine
    metallurgy
    construction
    navigation
    warfare
    administration
    mathematics
    writing
    energy
    transport
    information
```

### 11.2 Technology capability vector

Possible dimensions:

```text
technology:
    food
    transport
    energy
    materials
    military
    medicine
    information
    administration
    construction
    sanitation
```

### 11.3 Innovation probability

Innovation should require both pressure and capacity.

Conceptually:

```text
innovation_hazard = sigmoid(
    need
    + knowledge_stock
    + specialist_population
    + connectivity
    + surplus
    - instability
    - knowledge_loss
)
```

Extreme need without capacity should often cause failure rather than innovation.

### 11.4 Directed innovation

Problem context should influence innovation domain:

- food stress -> agriculture/storage/irrigation;
- long-distance trade -> navigation/transport;
- warfare -> weapons/logistics/fortification;
- administrative complexity -> writing/accounting;
- disease -> sanitation/medicine;
- communication limits -> information technologies.

### 11.5 Knowledge diffusion

Knowledge flows through social links:

```text
knowledge_gain_i += sum_j(
    contact_strength_ij
    * transmissibility
    * max(knowledge_j - knowledge_i, 0)
)
```

Isolation should reduce diffusion but may preserve local specialization.

### 11.6 Knowledge loss

Knowledge may be lost due to:

- population decline;
- death of specialists;
- institutional collapse;
- loss of written archives;
- isolation;
- lack of continued practice.

Long-lived species may store more knowledge in living individuals while becoming differently vulnerable to catastrophic mortality.

---

## 12. Social Behavior and Cultural Systems

### 12.1 Human behavioral assumptions

The default human profile may include distributions for:

- food/security motivation;
- kin preference;
- reciprocity;
- cooperation;
- status-seeking;
- dominance-seeking;
- autonomy preference;
- conformity;
- punishment;
- coalition formation;
- risk tolerance;
- out-group caution.

These are hypotheses and should be configurable.

### 12.2 Culture

Culture should define learned norms and reward structures, including:

- what generates prestige;
- property norms;
- inheritance rules;
- marriage norms;
- redistribution expectations;
- authority legitimacy;
- warfare norms;
- punishment norms;
- religious beliefs;
- openness to outsiders;
- educational practices.

### 12.3 Status reward vector

A culture may assign status weights to:

```text
status_weights:
    wealth
    warfare
    generosity
    knowledge
    religious_authority
    monuments
    office
    lineage
    craftsmanship
```

The underlying desire for status can be biologically/socially distributed, while the route to gaining status is culturally learned.

### 12.4 Cultural evolution

Cultural parameters can change through:

- imitation;
- prestige-biased transmission;
- success-biased transmission;
- intermarriage;
- conquest;
- migration;
- institutional enforcement;
- random drift.

---

## 13. Hierarchy, Wealth Concentration, and Elite Formation

### 13.1 Do not equate surplus with hierarchy

Surplus creates an opportunity for appropriation. Durable hierarchy should depend on mechanisms such as:

- resource storability;
- resource concentration;
- coercive capacity;
- inheritance;
- restricted exit;
- control over infrastructure;
- legitimacy;
- coalition dynamics;
- counter-dominance capacity.

### 13.2 Appropriability

A conceptual measure:

```text
appropriability = surplus
                * lootability
                * coercion_monopolizability
                * exit_difficulty
                * legibility
```

### 13.3 Elite feedback

A possible positive feedback loop:

```text
wealth
    -> retainers/coercion
    -> resource control
    -> preferential appropriation
    -> more wealth
```

This loop should be counteracted by:

- coalition resistance;
- migration;
- redistribution norms;
- rebellion;
- competing elites;
- legitimacy constraints;
- administrative failure.

### 13.4 Inheritance

Distinguish temporary inequality from persistent class hierarchy.

Model inheritance of:

- wealth;
- office;
- land;
- status;
- social links;
- coercive assets.

The degree of inheritance persistence is a crucial parameter.

### 13.5 De-aggregate important tails

The upper wealth/power tail should be represented at finer resolution than the mass population when it has disproportionate political leverage.

---

## 14. State Formation and Political Organization

### 14.1 Separate state capacity from elite capture

Track at least:

```text
state_capacity
elite_capture
```

State capacity includes abilities such as:

- taxation;
- recordkeeping;
- enforcement;
- infrastructure construction;
- military mobilization;
- dispute resolution;
- public-goods provision.

Elite capture measures how strongly public institutions serve concentrated elite interests.

### 14.2 Coordination costs

Larger populations and territories require more coordination.

Conceptually:

```text
coordination_cost =
    population^gamma
    * territory^eta
    * heterogeneity_factor
    / (transport_tech * information_tech * administrative_tech)
```

### 14.3 State reach

Political control should decay with distance and terrain unless technology offsets it.

```text
state_reach(distance) =
    administrative_capacity
    * transport_capacity
    * information_capacity
    * exp(-lambda * effective_distance)
```

### 14.4 State benefits and costs

Populations experience both:

```text
state_benefits =
    security
    + infrastructure
    + trade_access
    + dispute_resolution
    + famine_relief
    + public_goods

state_costs =
    taxes
    + forced_labor
    + conscription
    + elite_extraction
    + restrictions
    + disease_from_density
    + autonomy_loss
```

Individuals and population units may tolerate, support, evade, resist, or exit states depending on their preferences and circumstances.

### 14.5 Autonomous/frontier populations

Do not create a `barbarian` agent type. Groups outside states may emerge because:

- mobility is valuable;
- state extraction is costly;
- terrain makes control expensive;
- pastoralism, hunting, trade, or raiding outperform incorporation;
- cultural autonomy is strongly valued.

A state may label such groups culturally, but the simulator should store objective characteristics rather than a civilizational category.

---

## 15. Factions, Coalitions, and Political Competition

### 15.1 Multi-level representation

The simulation may use:

```text
world
    -> polities / cultural groups
        -> factions / lineages / elite coalitions
            -> population units / individuals
```

### 15.2 Faction state

```text
Faction
    wealth
    status
    coercive_resources
    followers
    legitimacy
    kinship_network
    offices
    territorial_base
    goals/preferences
```

### 15.3 Status competition

Status is relative. Factions may spend resources on:

- warfare;
- monuments;
- public works;
- patronage;
- ritual;
- private consumption;
- scholarship;
- administration.

Different cultural prestige systems can therefore channel elite competition toward state-building, public goods, destructive positional spending, or other outcomes.

---

## 16. Social Fission, Merger, Rebellion, and Collapse

### 16.1 Group fission

Use probability/hazard rather than hard thresholds.

Possible inputs:

```text
fission_hazard = sigmoid(
    instability
    + food_stress
    + factionalism
    + coordination_cost
    + inequality
    - cohesion
    - institutional_capacity
)
```

### 16.2 Merger and federation

Groups may merge when benefits of:

- defense;
- trade;
- infrastructure;
- marriage alliances;
- shared institutions

outweigh autonomy and coordination costs.

### 16.3 Collapse is not a state transition keyword

Avoid a global `collapse()` rule.

Instead, political systems should degrade through failure of components:

- tax collection;
- logistics;
- legitimacy;
- food security;
- military cohesion;
- trade;
- infrastructure maintenance;
- elite cooperation;
- demographic stability.

Observers may later classify a period as a collapse from recorded metrics.

### 16.4 Resilience

Track resilience as an analytical measure derived from:

- food buffers;
- trade diversity;
- institutional capacity;
- ecological health;
- legitimacy;
- social trust;
- inequality;
- military pressure;
- redundancy.

External shocks interact with internal fragility.

---

## 17. Disease and Epidemiology

Disease should be a modular subsystem.

Each pathogen may have:

- transmissibility;
- virulence;
- incubation;
- immunity duration;
- species reservoirs;
- transmission mode;
- environmental sensitivity.

Transmission depends on:

- density;
- mobility;
- trade;
- sanitation;
- species resistance;
- urbanization;
- climate.

Disease should affect:

- mortality;
- fertility;
- labor productivity;
- migration;
- political legitimacy;
- military outcomes;
- knowledge retention.

---

## 18. Ecology and Niche Construction

Intelligent populations modify the environment through:

- fire;
- forest clearing;
- agriculture;
- irrigation;
- domestication;
- selective hunting;
- construction;
- mining;
- pollution;
- transport infrastructure.

The environment should therefore be partly endogenous.

Species may have different niche-construction capabilities.

---

## 19. Core Simulation Tick

The MVP can use a discrete timestep, likely seasonal or annual. The architecture should later support substeps or event-driven subsystems.

Conceptual order:

```text
for each timestep:

    1. update climate and weather
    2. update hydrology and environmental shocks
    3. update plant and animal ecology
    4. update pathogens

    5. update local resource availability

    6. for each population unit:
        perceive / update local knowledge
        forage / hunt / farm / herd / work
        produce resources
        consume resources
        update wealth and storage
        update nutrition and health
        update births and deaths
        update learning and knowledge
        evaluate movement / migration
        evaluate trade and social interactions

    7. update trade and knowledge networks
    8. update factions and elite competition
    9. update political institutions and state capacity
   10. update conflict / coercion / rebellion
   11. update infrastructure and niche construction
   12. attempt innovations
   13. diffuse technology and culture
   14. execute migrations, splits, mergers, and political changes
   15. adaptive-resolution split/merge pass
   16. calculate observables and diagnostics
   17. persist checkpoints/events/metrics
```

Order-dependent effects should be minimized. Where order matters, document it explicitly and use staged state updates rather than in-place mutation.

---

## 20. Events and Time Modeling

### 20.1 Hybrid time engine

Recommended long-term architecture:

- fixed timestep for environment, demography, and production;
- event queues for rare political, technological, or disaster events.

### 20.2 Event examples

- birth/death at individual resolution;
- leadership succession;
- invention;
- rebellion;
- war declaration;
- settlement founding;
- migration wave;
- epidemic introduction;
- drought onset;
- flood;
- volcanic event;
- institution creation.

### 20.3 Deterministic replay

Given:

- identical configuration;
- identical code version;
- identical random seed;

simulation outcomes should be replayable within documented numerical tolerances.

---

## 21. Software Architecture

Use a modular architecture with domain boundaries. Avoid a single monolithic `Simulation` class containing all behavior.

Suggested package structure:

```text
socioecology_sim/
    __init__.py

    config/
        schema.py
        loader.py
        defaults.py

    core/
        simulation.py
        clock.py
        rng.py
        events.py
        scheduler.py
        ids.py

    world/
        grid.py
        topology.py
        climate.py
        hydrology.py
        soil.py
        environment.py

    ecology/
        plants.py
        animals.py
        biomass.py
        foodweb.py

    species/
        profile.py
        physiology.py
        life_history.py
        cognition.py
        movement.py

    population/
        unit.py
        distributions.py
        demography.py
        health.py
        split_merge.py

    economy/
        production.py
        subsistence.py
        storage.py
        wealth.py
        trade.py

    society/
        culture.py
        status.py
        factions.py
        institutions.py
        state.py
        politics.py

    knowledge/
        domains.py
        innovation.py
        diffusion.py

    mobility/
        movement.py
        migration.py
        exploration.py
        pathfinding.py

    disease/
        pathogen.py
        transmission.py
        immunity.py

    conflict/
        warfare.py
        coercion.py
        rebellion.py

    resolution/
        refinement.py
        coarsening.py
        similarity.py

    metrics/
        observables.py
        recorder.py
        aggregations.py

    persistence/
        checkpoints.py
        event_log.py
        formats.py

    experiments/
        runner.py
        sweeps.py
        ensembles.py

    cli/
        main.py

    tests/
        ...
```

The exact structure may evolve, but subsystem boundaries should remain explicit.

---

## 22. Data Model and Configuration

### 22.1 Configuration format

Use YAML or TOML for scenario configuration. Validate with typed Python models.

Example:

```yaml
simulation:
  start_year: 0
  end_year: 5000
  timestep_years: 1
  seed: 182736

world:
  topology_file: data/world.nc
  climate_file: data/climate.nc

species:
  - id: human
    profile: species/human.yaml

initial_populations:
  - species: human
    cell: [120, 84]
    population: 32
    culture: proto_a
```

### 22.2 Typed schemas

Recommended tools:

- `dataclasses` for immutable domain data where appropriate;
- Pydantic for external configuration validation;
- NumPy arrays for dense numeric fields;
- xarray for labeled gridded environmental data;
- pandas or Polars only for analytics/output pipelines, not necessarily core inner loops.

### 22.3 Units

Use explicit units and document them.

Strongly consider a units library at configuration boundaries, but avoid excessive runtime unit overhead in performance-critical loops. Normalize internal units, for example:

- years;
- kilometers;
- kilograms;
- kilocalories;
- hectares;
- Celsius or Kelvin;
- persons.

Never mix implicit units.

---

## 23. Randomness and Reproducibility

### 23.1 Central RNG service

Do not call global `random` or `numpy.random` throughout the code.

Use a central RNG manager that creates deterministic named streams:

```text
rng.environment
rng.demography
rng.innovation
rng.migration
rng.politics
rng.disease
```

This makes debugging and partial reproducibility easier.

### 23.2 Stable identifiers

Agents, factions, settlements, and events should have stable IDs independent of list ordering.

### 23.3 Version every run

Persist:

- git commit hash;
- configuration hash;
- model version;
- random seed;
- dependency lock hash;
- timestamp;
- scenario metadata.

---

## 24. Persistence and Outputs

### 24.1 Avoid full-state snapshots every tick

For large simulations, full serialization at every timestep will be too expensive.

Use:

- periodic checkpoints;
- event logs;
- sampled metrics;
- spatial summaries.

### 24.2 Recommended outputs

- population by cell/species/culture;
- migration flows;
- settlements;
- wealth quantiles;
- health metrics;
- adult height distributions;
- state borders and reach;
- state capacity;
- elite capture;
- inequality measures;
- technologies;
- knowledge domains;
- trade networks;
- conflict events;
- ecological condition;
- land use;
- disease prevalence;
- autonomy/extraction measures;
- major institutional changes.

### 24.3 Event provenance

Important state changes should record causes/inputs sufficient for debugging.

Example:

```json
{
  "event": "population_split",
  "unit_id": "u1839",
  "year": 821,
  "reason": "migration_selection",
  "moved_population": 8421,
  "source_population": 50321,
  "destination_cell": [42, 91]
}
```

---

## 25. Experimentation Framework

The simulator should support ensemble experiments as a first-class feature.

### 25.1 Replicate runs

A scenario should be runnable across many seeds:

```bash
socio-sim run scenario.yaml --seeds 1:1000
```

### 25.2 Parameter sweeps

Support sweeping:

- species traits;
- climate variables;
- status-seeking;
- inheritance;
- disease resistance;
- mobility;
- elite capture mechanisms;
- autonomy preferences;
- agricultural productivity.

### 25.3 Ablation studies

Allow mechanisms to be disabled to test causal importance.

Examples:

```text
A: ecology + demography
B: + surplus
C: + appropriation
D: + status competition
E: + inheritance
F: + counter-dominance
G: + shocks
```

### 25.4 Outcome distributions

Never rely only on one visually interesting run. Report distributions across runs.

---

## 26. Calibration and Validation

This is an exploratory generative model, not a direct historical reconstruction. Validation should occur at several levels.

### 26.1 Unit-level validation

Check whether submodels reproduce expected behavior:

- disease model has correct qualitative epidemic curves;
- demographic model produces plausible age structures;
- movement costs respond monotonically to terrain;
- wealth distribution preserves target moments/tails;
- split/merge preserves population and total wealth.

### 26.2 Stylized facts

Test whether the model can reproduce broad qualitative patterns without directly encoding them.

Examples:

- higher storage/lootability can increase extractive hierarchy under some conditions;
- roads increase state reach;
- denser trade networks increase knowledge diffusion;
- crowding increases disease transmission;
- wealth inequality can create biological welfare gradients;
- severe extraction can induce migration when exit is feasible.

### 26.3 Historical calibration

Historical data may later be used to calibrate selected submodels, but avoid fitting the entire simulation to a single civilization.

### 26.4 Falsifiability

A mechanism should be removable. If the model only generates an expected result because that result is directly encoded, it has low explanatory value.

---

## 27. Performance Strategy

### 27.1 Correctness before optimization

Build a transparent reference implementation first.

### 27.2 Profile before optimizing

Use profiling to find actual hotspots.

Likely hotspots:

- pathfinding;
- environmental updates;
- distribution transforms;
- contact networks;
- split/merge logic;
- large-scale trade flows.

### 27.3 Vectorization

Use NumPy for large homogeneous numeric operations.

### 27.4 Compiled acceleration

Only after profiling, consider:

- Numba;
- Cython;
- Rust extensions;
- JAX;
- GPU acceleration.

Do not tie domain logic to one accelerator prematurely.

### 27.5 Spatial indexing

Use spatial indexes or neighborhood caches rather than global scans.

### 27.6 Parallel ensembles first

The easiest parallelism is independent simulation runs. Prioritize ensemble-level parallel execution before adding complex within-run concurrency.

---

## 28. Python Engineering Best Practices

### 28.1 Coding standards

- Python 3.12+;
- type hints on public APIs;
- `ruff` for linting and formatting;
- `mypy` or `pyright` for static checking;
- `pytest` for tests;
- docstrings for public modules/classes/functions;
- avoid hidden global mutable state;
- prefer composition over deep inheritance;
- keep functions small and domain-focused;
- use descriptive scientific names rather than game-like abbreviations.

### 28.2 Immutability

Prefer immutable configuration and value objects. Mutability should live in explicit simulation state containers.

### 28.3 Pure functions where possible

Submodels such as movement cost, production yield, health hazard, and innovation hazard should often be pure functions of state and parameters. This improves testing and reproducibility.

### 28.4 Separate state transition from decision calculation

Prefer:

```text
proposals = subsystem.evaluate(current_state)
next_state = resolver.apply(current_state, proposals)
```

rather than subsystems mutating shared objects unpredictably.

### 28.5 Avoid circular dependencies

Subsystems should communicate through narrow interfaces, events, or typed state views.

### 28.6 Dependency injection

Inject:

- RNG streams;
- configuration;
- clocks;
- policy/behavior modules;

rather than importing global singletons.

### 28.7 Numerical stability

- clamp probabilities to `[0, 1]`;
- use log-space for very small likelihoods;
- validate distributions before sampling;
- guard against negative population/resources;
- specify tolerances for conservation checks.

### 28.8 Conservation invariants

Continuously check:

- population conservation across split/merge/migration, except births/deaths;
- wealth/resource conservation except production, consumption, loss, or explicit transfer;
- probability normalization;
- nonnegative counts.

Assertions should be enabled in debug/testing configurations.

### 28.9 Logging

Use structured logging. Avoid excessive per-agent text logs in large runs.

Levels:

- `DEBUG`: detailed subsystem traces;
- `INFO`: major scenario milestones;
- `WARNING`: model instability or invalid corrections;
- `ERROR`: run-threatening failures.

### 28.10 Configuration over hard-coded constants

Model constants must live in versioned parameter sets, not scattered source literals.

---

## 29. Testing Strategy

### 29.1 Unit tests

Test each mathematical relationship independently.

Examples:

- forest density increases movement cost for baseline humans;
- flight reduces slope and river crossing penalties;
- higher wealth increases expected food access under the selected policy;
- split operations preserve weighted moments within tolerance;
- mergers preserve total population and wealth;
- innovation hazard rises with need at moderate conditions but can fall under extreme instability if configured.

### 29.2 Property-based testing

Use Hypothesis for invariants:

- populations never become negative;
- migration cannot move more people than exist;
- split + merge approximately reconstructs original moments;
- normalized distributions sum to one;
- state reach never becomes negative.

### 29.3 Regression tests

Maintain small deterministic worlds with fixed seeds and expected output summaries.

### 29.4 Statistical tests

Stochastic models should be tested over many samples for distributional behavior, not exact single draws.

### 29.5 Performance tests

Maintain benchmark scenarios at increasing scales.

---

## 30. Observability and Debugging

A complex emergent simulation is difficult to debug without explainability.

Every high-level decision should optionally expose component scores.

Example migration explanation:

```text
PopulationUnit u812 migration score:
    expected_food      +0.43
    trade_opportunity  +0.18
    autonomy_gain      +0.27
    movement_cost      -0.31
    disease_risk       -0.08
    uncertainty        -0.11
    final_hazard        0.38
```

The engine should support a trace mode for selected agents, cells, or factions.

---

## 31. Scenario Analysis Metrics

Recommended global metrics:

### Demographic

- total population;
- population density;
- urbanization;
- migration rate;
- age structure;
- life expectancy.

### Economic

- total production;
- per-capita consumption;
- stored surplus;
- trade volume;
- wealth Gini;
- top 1% wealth share.

### Biological welfare

- health index;
- childhood nutrition;
- adult stature distribution;
- disease burden;
- mortality.

### Political

- state capacity;
- elite capture;
- autonomy;
- extraction rate;
- institutional legitimacy;
- territory;
- state reach.

### Knowledge

- technology vector;
- knowledge diversity;
- diffusion speed;
- innovation rate.

### Ecological

- biomass;
- soil health;
- forest cover;
- biodiversity;
- human appropriation of productivity.

### Social

- inequality;
- faction count;
- cohesion;
- conflict rate;
- status concentration;
- cultural diversity.

---

## 32. Example Emergent Hypotheses the Simulator Should Permit

The engine should make it possible, but not inevitable, to observe hypotheses such as:

1. storable, concentrated agricultural surplus can support durable extraction and hierarchy;
2. difficult terrain and low state legibility can preserve political autonomy;
3. populations may choose lower-productivity regions to escape extraction;
4. state-building can improve aggregate production while reducing the biological welfare of lower economic strata;
5. political collapse can sometimes improve commoner nutrition through reduced extraction, but can also worsen welfare through conflict and infrastructure loss;
6. status competition can either build state capacity or waste surplus depending on culturally rewarded status pathways;
7. longer-lived species may have lower political turnover and stronger intergenerational memory;
8. highly mobile/flying species may be difficult to territorially control;
9. very small species may have excellent personal mobility but weak heavy-logistics capacity;
10. resource ecology can influence political organization through taxability and transport costs without explicitly determining government type.

These are experiment targets, not truths hard-coded into the engine.

---

## 33. MVP Scope

The first implementation should be deliberately smaller than the full vision.

### MVP 1: Ecological-demographic sandbox

Implement:

- grid world;
- topology;
- climate fields;
- basic plants/food resources;
- one human species profile;
- individual/small-group population units;
- movement;
- foraging;
- energy balance;
- birth/death;
- local knowledge;
- simple migration;
- reproducible run/output.

Goal: demonstrate plausible settlement and movement patterns.

### MVP 2: Agriculture and technology

Add:

- cultivation;
- storage;
- technologies;
- innovation;
- knowledge diffusion;
- trade;
- population aggregation.

Goal: allow sedentary high-density populations to emerge.

### MVP 3: Distributional society

Add:

- wealth distributions;
- health distributions;
- occupations;
- adaptive split/merge;
- wealth-health relationship;
- biological welfare.

Goal: represent inequality without individualizing millions of people.

### MVP 4: Politics

Add:

- factions;
- status competition;
- appropriation;
- coercion;
- state capacity;
- elite capture;
- exit/rebellion;
- infrastructure/public goods.

Goal: allow decentralized societies, states, and hierarchical systems to emerge.

### MVP 5: Fantasy species and multi-species worlds

Add:

- arbitrary species profiles;
- flight;
- different lifespans;
- different metabolism;
- cross-species ecology;
- multi-species trade/conflict.

---

## 34. Non-Goals for Early Versions

Do not initially attempt:

- photorealistic geography;
- perfect historical reconstruction;
- individual neural-network agents;
- full natural-language culture;
- realistic tactical combat;
- millions of individually simulated people;
- unrestricted machine-learning decision systems;
- every known disease;
- every historical technology;
- real-time graphical rendering.

The priority is a scientifically interpretable, reproducible mechanism-based engine.

---

## 35. Recommended First Technical Stack

Suggested starting dependencies:

```text
Python 3.12+
numpy
scipy
pydantic
xarray
networkx
pyyaml or tomllib/tomli
pyarrow
pytest
hypothesis
ruff
mypy or pyright
```

Optional later:

```text
numba
polars
zarr
h5py
geopandas
rasterio
jax
ray / dask
```

Use dependencies only when they solve a demonstrated need.

---

## 36. Suggested Public API

A minimal user-facing Python API might be:

```python
from socioecology_sim import Scenario, Simulator

scenario = Scenario.from_yaml("scenario.yaml")

sim = Simulator(scenario)
result = sim.run()

result.save("runs/experiment_001")
```

For ensembles:

```python
from socioecology_sim.experiments import Ensemble

ensemble = Ensemble(
    scenario="scenario.yaml",
    seeds=range(1000),
)

summary = ensemble.run()
```

### CLI

```bash
socio-sim validate scenario.yaml
socio-sim run scenario.yaml
socio-sim run scenario.yaml --seed 42
socio-sim ensemble scenario.yaml --seeds 1:1000
socio-sim inspect runs/experiment_001
```

---

## 37. Example Internal Interfaces

```python
class Subsystem(Protocol):
    def evaluate(self, state: WorldState, ctx: StepContext) -> list[Proposal]:
        ...


class Proposal(Protocol):
    priority: int

    def apply(self, state: MutableWorldState) -> None:
        ...
```

The exact interfaces may differ, but the architecture should encourage staged evaluation and controlled mutation.

### Population distribution abstraction

```python
class Distribution(Protocol):
    def mean(self) -> float: ...
    def variance(self) -> float: ...
    def quantile(self, q: float) -> float: ...
    def sample(self, rng, n: int) -> np.ndarray: ...
    def condition(self, predicate) -> "Distribution": ...
    def merge(self, other: "Distribution", weight: float) -> "Distribution": ...
```

Where exact conditional distributions are impossible, use explicit approximation policies and record approximation error when feasible.

---

## 38. Conservation and Integrity Rules

The engine must continuously respect invariants.

### Population

```text
population_next = population_now
                + births
                - deaths
                + immigration
                - emigration
```

### Resources

All resource changes must be explainable by:

- production;
- transfer;
- consumption;
- spoilage;
- destruction;
- ecological regeneration.

### Wealth

Transfers do not create wealth. Production, destruction, consumption, or valuation changes must be explicit.

### Split/merge

Splits and merges must conserve weighted totals within numerical tolerance.

---

## 39. Model Governance

Every model equation or rule should have metadata:

```text
name
version
rationale
source_type: empirical | theoretical | heuristic | placeholder
parameters
expected_domain
known_limitations
```

This is important because many social-science mechanisms will initially be heuristic.

The codebase should make it easy to answer:

> Why does this rule exist?

and

> What happens if we remove or change it?

---

## 40. Guiding Principle

The simulator should be built around the following conceptual hierarchy:

```text
physics / geography
        ↓
ecology
        ↓
species biology
        ↓
individual and population behavior
        ↓
economy and subsistence
        ↓
culture and social networks
        ↓
institutions and politics
        ↓
knowledge and technology
        ↓
feedback into ecology and society
```

No upper layer should be completely predetermined by a lower layer. Lower layers create constraints and incentives; upper layers create feedback and path dependence.

The final ambition is a simulation in which:

- species traits alter ecological opportunities;
- ecological opportunities alter subsistence;
- subsistence alters surplus and mobility;
- surplus and mobility alter hierarchy and state formation;
- political organization alters distribution;
- distribution alters health and demography;
- institutions alter knowledge accumulation;
- technology alters the environment and carrying capacity;
- cultural values redirect universal or species-specific motivations;
- all of these processes recursively change the future.

The simulator should therefore be capable of producing histories that are plausible but not predetermined, and of comparing repeated histories across different assumptions.

---

## 41. Definition of Success

The project is successful when a user can provide:

1. a topology/environment;
2. ecological parameters;
3. one or more species profiles;
4. initial population seeds;
5. a time horizon;
6. a random seed;

and receive a reproducible simulation containing:

- evolving population distributions;
- migration and settlement histories;
- ecological changes;
- economic production and inequality;
- health and demographic outcomes;
- cultural differentiation;
- technological evolution;
- political organization;
- conflict and cooperation;
- adaptive population resolution;
- interpretable event logs and metrics.

Crucially, the engine should not require the user to specify in advance where civilizations, states, empires, frontiers, elites, or collapses will occur.

Those should be outputs.
