# Codespaces puts the uv cache on a different filesystem, so hardlinks fail.
export UV_LINK_MODE ?= copy

.DEFAULT_GOAL := help
.PHONY: help install sync lint format typecheck test test-stat test-stat-long golden cov check run sim pre-commit clean \
	bench-perf bench-quick bench-scale bench-scale-units bench-scale-density bench-smoke bench-dev bench-rc baseline

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv, install deps and git hooks
	uv sync
	uv run pre-commit install

sync: ## Sync deps with uv.lock
	uv sync

lint: ## Lint with ruff
	uv run ruff check

format: ## Auto-fix lint issues and format code
	uv run ruff check --fix
	uv run ruff format

typecheck: ## Type-check with mypy
	uv run mypy

test: ## Run regression and mechanism tests (fast)
	uv run pytest

test-stat: ## Compact statistical model tests (< 1 min; part of MVP freezes)
	uv run pytest -m "statistical and not slow"

test-stat-long: ## Extended / research validation suite: 8 seeds x 900 years (manual, tens of min)
	uv run pytest -m "statistical and slow"

golden: ## Re-record exact regression fixtures after an intended behavior change
	UPDATE_GOLDEN=1 uv run pytest tests/regression

cov: ## Run tests with coverage report
	uv run pytest --cov=madexplorer --cov-report=term-missing

check: lint typecheck test ## Run lint, typecheck and tests (what CI runs)
	uv run ruff format --check

run: ## Show CLI help
	uv run madexplorer --help

SCENARIO ?= scenarios/mvp1_sandbox.yaml
sim: ## Run a scenario (SCENARIO=path, default MVP 1 sandbox)
	uv run madexplorer run $(SCENARIO)

# Benchmark tiers (status.md Section 0). Timings are machine-specific: compare with a
# reference recorded on the same machine. BENCH_JOBS worker processes for ensembles.
MVP2 ?= scenarios/mvp2_neolithic.yaml
BENCH_JOBS ?= 2
BENCH_LABEL ?= latest
bench-perf: ## Synthetic per-unit benchmark (100-2000 units, 30 ticks) -> benchmarks/perf/
	uv run madexplorer bench synthetic $(MVP2) --out benchmarks/perf/$(BENCH_LABEL)_synthetic.json

bench-quick: ## Engineering loop: 1,000 synthetic units, 10 ticks (~15 s; not saved)
	uv run madexplorer bench synthetic $(MVP2) --units 1000 --ticks 10

# Two scaling families (status.md 9.1): fixed local density (~0.4 units per land cell; units
# grow with the world) versus fixed world (40x40; units per cell grow). Dense beliefs cap the
# fixed-density family at ~4k units on this 7 GB machine.
SCALE_TICKS ?= 5
bench-scale-units: ## Unit scaling at fixed density: 500/1k/2k/4k units on 40/57/80/113 grids
	@for pair in 40:500 57:1000 80:2000 113:4000; do w=$${pair%%:*}; n=$${pair##*:}; \
		uv run madexplorer bench synthetic $(MVP2) --units $$n --ticks $(SCALE_TICKS) \
		--set world.topology.width=$$w --set world.topology.height=$$w \
		--out benchmarks/perf/$(BENCH_LABEL)_density_fixed_$${n}u.json || exit 1; done

bench-scale-density: ## Density scaling on the fixed 40x40 world: 250/1k/4k units
	uv run madexplorer bench synthetic $(MVP2) --units 250,1000,4000 --ticks $(SCALE_TICKS) \
		--out benchmarks/perf/$(BENCH_LABEL)_density_varied.json

bench-scale: ## Scaling: 100/1k/10k units on 40x40, 1k units on 100x100 -> benchmarks/perf/
	uv run madexplorer bench synthetic $(MVP2) --units 100,1000,10000 --ticks 10 \
		--out benchmarks/perf/$(BENCH_LABEL)_scale_units.json
	uv run madexplorer bench synthetic $(MVP2) --units 1000 --ticks 10 \
		--set world.topology.width=100 --set world.topology.height=100 \
		--out benchmarks/perf/$(BENCH_LABEL)_scale_world.json

bench-smoke: ## Smoke ensemble: 2 seeds x 250 years
	uv run madexplorer ensemble $(MVP2) --seeds 0:1 --years 250 --jobs $(BENCH_JOBS) --out ensembles/bench_smoke

bench-dev: ## Development ensemble: 8 seeds x 600 years (model changes)
	uv run madexplorer ensemble $(MVP2) --seeds 0:7 --years 600 --jobs $(BENCH_JOBS) --out ensembles/bench_dev

bench-rc: ## Release-candidate ensemble: 16 seeds x 1,000 years
	uv run madexplorer ensemble $(MVP2) --seeds 0:15 --years 1000 --jobs $(BENCH_JOBS) --out ensembles/bench_rc

baseline: ## Optional large ensemble: 32 seeds x 1,000 years (not the freeze reference; see status.md P7)
	uv run madexplorer ensemble $(MVP2) --seeds 0:31 --years 1000 --jobs $(BENCH_JOBS) --out ensembles/baseline_32x1000

pre-commit: ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

clean: ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.venv/*' -exec rm -rf {} +
