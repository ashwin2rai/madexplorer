# madexplorer

A reproducible, mechanism-based **social-ecological civilization simulator**. Populations are
placed into a spatially explicit world with terrain, climate, rivers, and wild food ecology;
settlement, migration, demographic, and (later) economic, political, and technological
patterns emerge from local mechanisms rather than hard-coded historical rules.

The full objective and specification is in
[`objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`](objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md).

## Status: MVP 2.1 frozen — consolidation before MVP 3

MVP 2.1 is the frozen scientific base (`baselines/mvp2_1/freeze_manifest.json`). The code is
being consolidated and simplified without changing its results before MVP 3 (distributional
society) begins. See `objective/status.md` for the current handoff, accepted limitations and
open questions.

| Implemented | Mechanism |
|---|---|
| World | procedural terrain, sea level, depression-filled D8 rivers, freshwater access |
| Climate | latitude/lapse-rate temperature, coastal rainfall, AR(1) + regional interannual anomalies |
| Ecology | Miami-model NPP → edible plant and game stocks with logistic regrowth and depletion |
| Species | `SpeciesProfile` from YAML (Siler mortality, fertility schedule, metabolism, movement, cognition) |
| Population | bands with exact age × sex cohorts; energy balance and reserves; nutrition-dependent births/deaths |
| Behavior | diminishing-returns foraging with crowding, local noisy knowledge + sharing, perceived-utility migration (argmax over beliefs, one move hazard), hazard-based fission/fusion |
| Engine | staged evaluate/apply subsystems, one RNG stream per mechanism, conservation checks, ablation switches, declared merge/split rules for all unit state |
| Health | additive settlement-crowding mortality from sedentism and settled contact population |
| Outputs | provenance manifest, yearly metrics, event log with causes, spatial snapshots, decision traces |
| **MVP 2** | |
| Knowledge | per-domain knowledge that grows with practice × log(practitioners) and decays with disuse |
| Technology | discrete techniques as data (`technologies/*.yaml`): prerequisites, directing need, capability effects — a coarse MVP 2 hypothesis, not the project's theory of cultural evolution |
| Innovation | hazard needing both pressure (need signal) and capacity (knowledge, size, contacts, surplus); candidates compete as independent risks |
| Diffusion | knowledge gradients and technology adoption through co-location, adjacency, and trade ties; loss when knowledge decays |
| Cultivation | possible once crop capability is non-zero (`plant_cultivation`); groups then plan fields each year: when new land (clearing labor amortized over years resident, capped by the planning horizon) beats marginal foraging, they close part of the gap to the area that meets need, limited by labor; unprofitable fields shrink; cells share limited arable land. Cultivated soil depletes and recovers in fallow; fields displace wild food; leaving fields costs the labor to re-clear them |
| Storage | spoiling stores that buffer shortfalls and can't all be carried when moving |
| Trade | surplus sharing with nearby deficits, transport loss, persistent ties |
| Aggregation | experimental coarsening of similar co-located groups; off by default and in every canonical scenario because it is not scientifically neutral |
| Experiments | parallel multi-seed ensembles with milestone summaries, `--set` parameter overrides, paired comparisons |

No rule says "invent farming" or "settle down"; `mechanisms:` switches make each mechanism
removable for ablation. In the MVP 2.1 reference (`mvp2_neolithic`, seeds 0–3, 600 years)
cultivation starts around years 160–240, farming supplies a quarter of the harvest by years
250–390 and 42–50% at year 600, and the population grows to roughly 14k–34k. These are
mechanism demonstrations, not historical calibration; why growth stays so sustained is an
open question (`objective/status.md`).

Next milestones (objective §15): MVP 3 distributional society (joint socioeconomic strata:
wealth, health, occupations), MVP 4 hierarchy, institutions and politics, MVP 5+ richer worlds
and species.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
make install                 # uv sync + install pre-commit git hooks
```

Run `make` to list all targets (`test`, `test-stat`, `test-stat-long`, `golden`, `lint`,
`format`, `typecheck`, `check`, `cov`, `clean`, ...). `make test` runs exact regressions and
mechanism tests. `make test-stat` runs the compact statistical tests (under a minute). `make
test-stat-long` runs the extended / research validation suite (8 seeds × 900 years, tens of
minutes); it is manual and not required for normal development, CI or MVP freezes.

## Running simulations

```bash
uv run madexplorer validate scenarios/mvp1_sandbox.yaml
uv run madexplorer run scenarios/mvp1_sandbox.yaml                # writes runs/mvp1_sandbox/seed_0
uv run madexplorer run scenarios/mvp2_neolithic.yaml              # knowledge, farming, storage, trade
uv run madexplorer run scenarios/mvp1_sandbox.yaml --seeds 1:10   # several seeds, full outputs each
uv run madexplorer ensemble scenarios/mvp2_neolithic.yaml --seeds 0:15 --jobs 2 --years 600
uv run madexplorer ensemble scenarios/mvp2_neolithic.yaml --seeds 0:15 --jobs 2 --years 600 \
    --set species.human.cognition.observation_noise_sigma=0.1 --out ensembles/noise01
uv run madexplorer compare ensembles/mvp2_neolithic ensembles/noise01  # paired by seed
uv run madexplorer run scenarios/mvp1_sandbox.yaml --trace u1     # log migration component scores
uv run madexplorer inspect runs/mvp1_sandbox/seed_0 --map         # summary + ASCII population map
uv run madexplorer rules -v                                       # every model rule and its rationale
```

Python API:

```python
from madexplorer import Scenario, Simulator

scenario = Scenario.from_yaml("scenarios/mvp1_sandbox.yaml").with_overrides(seed=42)
result = Simulator(scenario).run()
result.save("runs/experiment_001")
```

### Scenarios and species

- `scenarios/*.yaml` define the world, time horizon, seeds, founding populations, and ablation
  switches (`mechanisms:`). The world has its own `world.topology.seed`, so ensembles over
  `simulation.seed` share one map.
- `species/*.yaml` hold **all** species parameters; none have defaults in code. A scenario can
  override any of them per species (`species[].overrides`) for sweeps and counterfactuals.
- `technologies/*.yaml` define a knowledge system: domains, base capabilities, discrete
  technologies with their capability effects, and innovation/diffusion weights. Every entry
  is a modeling hypothesis; Boolean technologies with hard prerequisites are a coarse MVP 2
  representation (objective §8.1). A scenario opts in with `knowledge_system:`.

### Run outputs

| File | Contents |
|---|---|
| `manifest.json` | git commit, config hash, seeds, model version, lockfile hash, runtime |
| `scenario.json` | fully resolved scenario including species profiles |
| `metrics.csv` | one row per year: population, groups, vital rates, food ratio, stocks, climate |
| `events.jsonl` | founding, splits, merges, migrations, extinctions, traces — with causes |
| `spatial.npz` | population per cell at the snapshot interval |
| `world.npz` | static world layers |

## Code layout

```
src/madexplorer/
  config/      pydantic schemas + YAML loading          core/        engine, RNG, events, invariants, governance
  world/       grid, generation, hydrology, climate     ecology/     productivity and wild food stocks
  species/     profile + life tables                    population/  units, energetics, demography, groups
  economy/     foraging, agriculture, trade             mobility/    movement, perception, migration
  metrics/     recorder                                 persistence/ output files
  knowledge/   domains, learning, diffusion, innovation resolution/  coarsening
  cli/         command-line interface
```

Every model equation is registered with `@model_rule` (name, version, rationale, source type,
parameters, limitations) so `madexplorer rules` answers *why does this rule exist?*
