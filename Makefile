# Codespaces puts the uv cache on a different filesystem, so hardlinks fail.
export UV_LINK_MODE ?= copy

.DEFAULT_GOAL := help
.PHONY: help install sync lint format typecheck test test-stat golden cov check run sim pre-commit clean \
	bench-perf bench-smoke bench-dev bench-rc baseline

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

test-stat: ## Run statistical multi-seed model tests (slow)
	uv run pytest -m statistical

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

bench-smoke: ## Smoke ensemble: 2 seeds x 250 years
	uv run madexplorer ensemble $(MVP2) --seeds 0:1 --years 250 --jobs $(BENCH_JOBS) --out ensembles/bench_smoke

bench-dev: ## Development ensemble: 8 seeds x 600 years (model changes)
	uv run madexplorer ensemble $(MVP2) --seeds 0:7 --years 600 --jobs $(BENCH_JOBS) --out ensembles/bench_dev

bench-rc: ## Release-candidate ensemble: 16 seeds x 1,000 years
	uv run madexplorer ensemble $(MVP2) --seeds 0:15 --years 1000 --jobs $(BENCH_JOBS) --out ensembles/bench_rc

baseline: ## Frozen MVP 2 baseline: 32 seeds x 1,000 years -> baselines/mvp2 (freeze only)
	uv run madexplorer ensemble $(MVP2) --seeds 0:31 --years 1000 --jobs $(BENCH_JOBS) --out baselines/mvp2

pre-commit: ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

clean: ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.venv/*' -exec rm -rf {} +
