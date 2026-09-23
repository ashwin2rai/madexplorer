# madexplorer

A reproducible, mechanism-based **social-ecological civilization simulator**. Populations are
placed into a spatially explicit world with terrain, climate, rivers, and wild food ecology;
settlement, migration, demographic, and (later) economic, political, and technological
patterns emerge from local mechanisms rather than hard-coded historical rules.

The full objective and specification is in
[`objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md`](objective/SOCIAL_ECOLOGY_SIMULATOR_OBJECTIVE.md).

## Status: MVP 1 — ecological-demographic sandbox

| Implemented | Mechanism |
|---|---|
| World | procedural terrain, sea level, depression-filled D8 rivers, freshwater access |
| Climate | latitude/lapse-rate temperature, coastal rainfall, AR(1) + regional interannual anomalies |
| Ecology | Miami-model NPP → edible plant and game stocks with logistic regrowth and depletion |
| Species | `SpeciesProfile` from YAML (Siler mortality, fertility schedule, metabolism, movement, cognition) |
| Population | bands with exact age × sex cohorts; energy balance and reserves; nutrition-dependent births/deaths |
| Behavior | diminishing-returns foraging with crowding, local noisy knowledge + sharing, perceived-utility migration, hazard-based fission/fusion |
| Engine | staged evaluate/apply subsystems, named RNG streams, conservation checks, ablation switches |
| Outputs | provenance manifest, yearly metrics, event log with causes, spatial snapshots, decision traces |

Next milestones (spec §33): MVP 2 agriculture/storage/technology, MVP 3 distributional units and
adaptive resolution, MVP 4 politics, MVP 5 fantasy and multi-species worlds.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
make install                 # uv sync + install pre-commit git hooks
```

Run `make` to list all targets (`test`, `lint`, `format`, `typecheck`, `check`, `cov`, `clean`, ...).

## Running simulations

```bash
uv run madexplorer validate scenarios/mvp1_sandbox.yaml
uv run madexplorer run scenarios/mvp1_sandbox.yaml                # writes runs/mvp1_sandbox/seed_0
uv run madexplorer run scenarios/mvp1_sandbox.yaml --seeds 1:10   # replicate ensemble
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
  economy/     foraging                                 mobility/    movement, perception, migration
  metrics/     recorder                                 persistence/ output files
  cli/         command-line interface
```

Every model equation is registered with `@model_rule` (name, version, rationale, source type,
parameters, limitations) so `madexplorer rules` answers *why does this rule exist?*
