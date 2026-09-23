# Implementation Status

**Last updated:** 2026-09-23
**Last commit at time of writing:** `2198a13 bug: field expansion is unbounded`
**Current phase:** MVP 2 (agriculture and technology) implemented; population brake unresolved (see Issue 1).

This file records what exists, what was learned while building it, what is broken or
unfinished, and what to do next. The specification is `SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`;
section numbers below (§) refer to it.

---

## 1. Quick restart checklist

```bash
make install                                              # uv sync + pre-commit hooks
make check                                                # lint, format check, mypy, pytest (65 tests)
uv run madexplorer run scenarios/mvp1_sandbox.yaml --years 450 --quiet
#   regression: must print population=7282 units=286 occupied_cells=267
uv run madexplorer run scenarios/mvp2_neolithic.yaml      # ~8-20+ min, see Issue 1 and Issue 2
uv run madexplorer inspect runs/mvp2_neolithic/seed_0 --map
uv run madexplorer rules -v                               # every model rule with rationale
```

Then pick up at **Section 6, Recommended next steps**, item 1.

---

## 2. Decisions made (and why)

| Decision | Reason |
|---|---|
| Package is `madexplorer`, not the spec's working title `socioecology_sim`; CLI is `madexplorer` | Matches the repository name |
| Python 3.13 (spec says 3.12+) pinned in `.python-version`; uv manages it | Widest library support at the time |
| World is procedural with its own seed `world.topology.seed`, separate from `simulation.seed` | Ensembles over run seeds share one map; founders' cells stay valid |
| Species parameters have **no defaults in code**; they live in `species/*.yaml` | §5: humanity must be a profile, not hidden constants |
| Technology tree is data (`technologies/*.yaml`); the engine knows only 4 *capabilities* | Tech trees are hypotheses (§2.2); they can be swapped or ablated without code changes |
| MVP 1 scenario keeps all MVP 2 mechanisms switched off | Preserves an exact regression target |
| Annual timestep only (`timestep_years: 1`) | §19 allows annual for MVP; seasonal resolution deferred |
| Units hold exact age×sex cohort vectors instead of distributions | Exact conservation and cheap vectorized demography for MVP 1-2; distributions arrive in MVP 3 |

---

## 3. What is implemented

### 3.1 Engine and infrastructure (spec §19-§24, §28-§30, §39)

- **Staged evaluate/apply loop** (`core/subsystem.py`, `core/simulation.py`). Each subsystem
  returns proposals computed from the current state, and the engine applies them. The order is
  documented in `build_pipeline()`:
  climate → ecology → perception → belief sharing → farming → foraging → trade → energetics
  → demography → extinction → field planning → learning → diffusion → innovation → fission
  → fusion → migration → coarsening.
- **Named RNG streams** (`core/rng.py`): world, initialization, environment, perception,
  demography, social, migration, knowledge, innovation, trade. Streams are seeded by a stable
  hash of their names, so adding a stream never perturbs the others.
- **Invariants checked every step** (`core/invariants.py`, on by default): population
  accounting (Δpop = births − deaths), nonnegative cohorts, reserves and stocks, and valid cells.
- **Governance registry** (`core/governance.py`): `@model_rule` records name, version,
  rationale, source type (empirical/theoretical/heuristic/placeholder), parameters, domain and
  limitations. 39 rules are registered.
- **Provenance**: the manifest stores git commit, dirty flag, config hash, both seeds, model
  version, uv.lock hash, Python/NumPy versions, timestamp and runtime.
- **Event log with causes**: splits and merges (with hazard components), migrations,
  inventions (with logit components), adoptions, losses, cultivation start/abandon, resolution
  merges (with knowledge distance as approximation error), and extinctions.
- **Trace mode**: `--trace u1` logs migration utility components and innovation hazards.
- **Ablation switches**: `mechanisms:` has 13 booleans.
- **CLI**: `validate`, `run` (`--seed`, `--seeds 1:10`, `--years`, `--out`, `--trace`),
  `inspect` (`--map` prints an ASCII density map) and `rules`.
- **Outputs** go to `runs/<scenario>/seed_<n>/` (gitignored): manifest.json, scenario.json,
  metrics.csv, events.jsonl, spatial.npz and world.npz.

### 3.2 MVP 1: ecological-demographic sandbox (complete)

| Area | Implementation | Source type |
|---|---|---|
| Terrain | spectral-noise elevation, sea-level quantile, slope | — |
| Hydrology | priority-flood depression filling, D8 flow accumulation, rivers, freshwater access | theoretical |
| Climate | latitude and lapse-rate temperature, lognormal coastal rainfall, AR(1) global anomalies plus a regional rainfall field | empirical / heuristic |
| Ecology | Miami-model NPP → edible plant and game capacities; logistic regrowth with recolonization | empirical / placeholder |
| Life history | Siler mortality (Gurven & Kaplan forager averages), beta-shaped fertility normalized to TFR, need and labor by age | empirical / heuristic |
| Energetics | pooled sharing, body reserves (60-day cap), thermoregulation cost, travel energy | heuristic |
| Demography | binomial deaths/births per cohort; starvation multiplies hazard; fertility falls with food ratio; births need a fertile male in the cell | heuristic |
| Foraging | diminishing returns `A(1−e^{−rE/A})`, satisficing to need +20%, shared pools under crowding, familiarity learning | heuristic |
| Perception | vegetation-occluded radius, noisy observations, memory horizon, neighbor belief sharing | heuristic |
| Migration | perceived utility (log food per head, water, path cost, staleness, Gumbel noise), logistic hazard with inertia | heuristic |
| Group dynamics | fission hazard (size per group, food stress), fusion hazard (small size, lacking a mate) | heuristic |
| Movement | friction = slope × vegetation; walkers can't cross water; swimmers and fliers supported | heuristic |

**Result:** founders colonize by budding and moving. Groups stay around 25 people. Population
saturates at about 0.27 people/km² with birth rate ≈ death rate (≈38/1000), game is overhunted
to about 2% while plants hold at about 70%, and marginal land stays empty.

### 3.3 MVP 2: agriculture and technology (implemented, calibration open)

| Area | Implementation |
|---|---|
| Knowledge | Vector per domain (ecology, agriculture, storage, construction). Per year: `K += a·s·log1p(N·s/n0) − δK`, where `s` is practice from activity shares, so knowledge equilibrium rises with log group size and falls with disuse. |
| Technologies | 6 in `technologies/neolithic.yaml`: storage_pits, plant_cultivation, seed_selection, ground_stone_axes, fallow_rotation and granaries. Each has knowledge prerequisites, required technologies, a need signal and capability effects. |
| Capabilities | crop_yield, storage_retention, clearing_efficiency, soil_management (base values plus additive effects). |
| Innovation | hazard = sigmoid(baseline + need + log(K/K_min) + log1p(N/25) + connectivity + surplus − instability + species propensity). Need signals are food_stress, harvest_variability, clearing_burden and soil_depletion. At most one invention per group per year. |
| Diffusion | knowledge flows down gradients from contacts (same cell 1.0, adjacent 0.3, trade ties), capped at the largest gap. Groups adopt a technology when they have ≥50% of its prerequisites; they lose it below 25%, and losses cascade to dependent technologies. |
| Cultivation | Crop harvest runs before foraging. Clearing labor rises with vegetation and falls with axes, and is amortized over expected tenure (years resident, capped by planning horizon). Soil nutrients deplete under cultivation and recover in fallow. Fields displace wild plants and game. Fields expand when farming beats marginal foraging, capped at need +20% (satisficing). |
| Storage | Surplus fills body reserves, then stores; stores are drawn before body reserves and spoil by `1 − retention` each year. Moving abandons stores beyond carrying capacity and all fields, and migration utility counts both as costs. |
| Trade | Groups offer 30% of their surplus to nearby groups in deficit (within the relocation range), worst deficits first and nearest donors first. Transport loss is `exp(−cost/60 km)`; ties persist at 0.7 per year and carry knowledge. |
| Aggregation | With more than 3 same-species units in a cell, the most similar pair (identical technologies, knowledge distance ≤ 1) merges into a multi-group unit. Fission of a multi-group unit buds off exactly one group. |

**Emergent results (40×40 world, seed 0, before the field cap):** foragers saturate at about
25k people by year 700. Storage pits are invented around year 82 and cultivation around year
375; farming then takes over (63% of food farmed and 42% sedentary by year 1,000). The
forager-only baseline on the same world stops at about 22k.

**Experiment: perception noise controls transition order (32×32 world):**

| Perception noise | Sedentism appears | Farming appears | Year ~700 |
|---|---|---|---|
| 0.1 | ~yr 230, before saturation | ~yr 290 | 58k people, 85% farmed |
| 0.3 (default) | ~yr 580, after saturation | ~yr 520-580, under density stress | 22k people, 22% farmed |

The model can therefore produce both "sedentism before farming" (Natufian-like) and "farming
under population pressure", depending on one behavioral parameter. This is worth a proper
multi-seed sweep.

---

## 4. Bugs found and fixed (all committed)

| Bug | Symptom | Fix |
|---|---|---|
| `Scenario.with_overrides` dropped the knowledge system | Every `madexplorer run` of MVP 2 silently ran without knowledge or technology | Pass `knowledge` through; regression test `test_overrides_preserve_species_and_knowledge_system` |
| Technology loss check passed an empty held set | Any technology with `requires` counted as lost every year (≈32k losses per run); dependent technologies stayed rare | `KnowledgeModel.unsupported()` checks knowledge, then cascades dependency losses; test added |
| Field expansion unbounded | Food ratio 3.0, 4.8M kcal stored per person, 794k people by year 1,000 | Fields capped at need × (1 + surplus_target) / yield |
| D8 flow terminated in noise pits | Only 2 river cells on a 64×64 map | Priority-flood fill before routing |
| Latitude gradient 0.6 °C/deg | Sea level at 50°N below freezing | Default 0.4 °C/deg |
| Premature cultivation by mobile bands | Early growth ~20% lower with cultivation on | Clearing amortized over expected tenure |
| Ecology knowledge efficiency 0.83 for expert founders | 17% lower foraging returns, stalled growth | `half_efficiency_level: 0.05`, so level-5 foragers are ~99% efficient |

---

## 5. Open issues and known problems

### Issue 1: no density brake on farming populations (highest priority)

After the field cap, a 32×32 run kept growing and accelerating: 30.5k (yr 600) → 43.5k (yr 650)
→ 64.7k (yr 700), about 0.8%/yr, with food ratio ~1.1, stores ~80-100k kcal per person, 74%
of food farmed, 74% sedentary, and 241 cells over 100 people. So the cap fixed overproduction
but not growth. Farmland
at full technology feeds thousands of people per cell (3,000 arable ha × ~1.7M kcal/ha), and
nothing makes dense settlement costly. Candidates, in recommended order:

1. **Density-dependent disease** (§17 is MVP-listed later, but a minimal crowding term is the
   standard brake). Mortality rises with cell density and sedentism, and falls with sanitation
   technology. This is also what gives the Neolithic its known health penalty (§8.4, §32
   hypothesis 4).
2. **Lower `crop_max_yield_kcal_per_ha`** (2.0e6 is optimistic for early cultivars after seed
   and processing losses) and/or a higher `cultivation_hours_per_ha`.
3. **Soil depletion that bites harder**: the farmed-soil mean only reached ~0.94. Fallowing
   may be too effective (+0.5 soil management), or depletion too slow.
4. Check whether reported "surplus" should suppress fertility less. There is currently no
   upper limit on fertility response beyond natural TFR 6.

### Issue 2: performance

| Run | Runtime |
|---|---|
| MVP 1, 64×64, 450 years (7k people) | ~10 s |
| MVP 2, 40×40, 1,000 years (51k people, before tech fix) | ~7.5 min |
| MVP 2, 40×40, 1,000 years (794k people, runaway) | ~22 min |
| MVP 2, 32×32, 1,000 years (after field cap) | >10 min (timed out) |

Hotspots from profiling: belief sharing (`mobility/exploration.py`, dictionary merges over
~230-cell belief maps when only ~18 reachable cells matter), perception, migration utility,
then foraging. Cost scales with the number of units, which aggregation bounds at 3 per cell.
The MVP 2 scenario was shrunk from 64×64/1,500 years to 40×40/1,000 years for this reason.

### Issue 3: calibration sensitivities

- **Early foragers live on a food knife-edge.** A 4% change in foraging productivity changed
  population at year 150 by ~40% (145 vs 83, median of 6 seeds). Results that hinge on early
  growth need multi-seed ensembles.
- **Perception noise sets transition order** (see the experiment above). It is a real model
  property but should be swept, not fixed silently.
- Most parameters are placeholders; `madexplorer rules` lists the source type of each.

### Issue 4: modelling simplifications to revisit

- Vegetation is static: clearing, fire and succession don't change the vegetation field, so
  movement friction and legibility don't respond to land use.
- There are no seasons. Harvest seasonality and storage timing are annual averages.
- Species sharing a cell forage and farm one after another in id order, not jointly.
- Food sharing within a group is equal: no intra-group inequality (MVP 3).
- Migration moves whole groups only; there is no selective emigration of risk-tolerant
  members (§6.4), which needs distributional units.
- Winner's-curse bias: picking the best of ~40 noisy candidates inflates the best
  alternative's utility, contributing to high forager mobility (about half of groups move
  each year at saturation).
- Trade is reciprocal provisioning of a single good (kcal); there are no markets, prices or
  distinct goods yet.
- Knowledge is group-level. There are no specialists, archives or writing (§11.6 archive loss).
- Merging units takes the union of their technologies and population-weighted knowledge.
  That's an approximation; the merge event records its error.
- `technology_adopted` / `invention` events are verbose: ~2,700 adoptions per run is fine,
  but the log may need sampling at larger scales.

### Issue 5: small nits

- `EcologyState.soil_nutrients` is one cell average, not tied to individual fields.
- `cells_within()` uses a Chebyshev square; perception is square, not circular.
- `mean_soil_nutrients_farmed` reports 1.0 when nothing is farmed (by design, but easy to misread).
- `README.md` describes MVP 2 as the status; update it when Issue 1 is resolved.

---

## 6. Recommended next steps (in order)

1. **Resolve Issue 1.** Add a minimal `disease/` subsystem: a crowding mortality term,
   `h *= 1 + k·f(density, sedentism) / sanitation`, registered as a model rule with a
   `mechanisms.disease` switch. Then re-run `mvp2_neolithic` and confirm the population
   plateaus, with lower biological welfare in dense farming cells than for foragers.
2. **Performance pass** before MVP 3 multiplies state size:
   - restrict belief sharing to cells reachable from the receiver, or prune belief maps to a
     spatial-memory radius (new cognition parameter);
   - cache per-tick arrays (need, labor, capabilities) in `StepContext`;
   - add parallel ensembles (`--seeds 1:20 --jobs N` with `ProcessPoolExecutor`), since §27.6
     says parallel ensembles come first.
3. **Ensemble tooling** (§25): an `ensemble` subcommand that runs seeds in parallel and writes
   distribution summaries of key metrics (time to cultivation, peak population, farm share at
   year N). Use it to rerun the perception-noise experiment properly.
4. **Regression fixtures** (§29.3): store a small MVP 2 summary with fixed seeds and compare in
   CI, like the MVP 1 7282/286/267 target.
5. **MVP 3: distributional society** (§33):
   - wealth and health distributions inside units (lognormal body + Pareto tail, §7.2) with
     preserved correlations (§7.3);
   - occupations enabled by surplus (§9.3);
   - health as a pathway from wealth, not a direct function of it (§8.3);
   - adult height from childhood stress (§8.5);
   - adaptive split/merge driven by conditional divergence (§6.4-6.5), replacing the current
     knowledge-distance coarsening;
   - selective emigration by risk tolerance.
6. Afterwards, MVP 4 (factions, appropriation, state capacity) and MVP 5 (fantasy and
   multi-species worlds; flight is already supported in movement).

---

## 7. Map of the code

```
src/madexplorer/
  config/        schema.py (scenario models), loader.py (Scenario, overrides, hashing)
  core/          simulation.py (Simulator, pipeline), state.py (state, StepContext, ledger),
                 subsystem.py, rng.py, ids.py, events.py, invariants.py, governance.py, provenance.py
  world/         grid.py, generation.py, hydrology.py, climate.py, subsystems.py
  ecology/       resources.py (NPP, capacities, regrowth, displacement), subsystems.py
  species/       profile.py (SpeciesProfile), life_history.py (LifeTables)
  population/    unit.py, energetics.py, demography.py, groups.py, initialization.py
  economy/       foraging.py, agriculture.py, trade.py
  mobility/      movement.py, exploration.py (perception, belief sharing), migration.py
  knowledge/     system.py (schema + KnowledgeModel), learning.py, diffusion.py, innovation.py
  resolution/    coarsening.py
  metrics/       recorder.py
  persistence/   output.py
  cli/           main.py
scenarios/       mvp1_sandbox.yaml, mvp2_neolithic.yaml
species/         human.yaml
technologies/    neolithic.yaml
tests/           65 tests: unit, Hypothesis property tests, statistical, integration
```

### Conventions to keep

- A new mechanism gets a pure function decorated with `@model_rule`, a subsystem with
  `evaluate()` → proposals → `apply()`, a `mechanisms:` switch, and a metric.
- Units are in field names (`_km`, `_kcal`, `_years`, `_c`, `_mm`, `_ha`).
- Never mutate cohort arrays in place: `PopulationUnit.population` is cached and reset only
  when `females` or `males` is reassigned.
- Draw randomness only from a named stream, in deterministic iteration order (insertion order
  of `state.units`).
- After any change, the MVP 1 regression (7282/286/267 at 450 years) should still hold unless
  the change is intentionally behavioral; say so in the commit.
