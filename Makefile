# Codespaces puts the uv cache on a different filesystem, so hardlinks fail.
export UV_LINK_MODE ?= copy

.DEFAULT_GOAL := help
.PHONY: help install sync lint format typecheck test cov check run sim pre-commit clean

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

test: ## Run tests
	uv run pytest

cov: ## Run tests with coverage report
	uv run pytest --cov=madexplorer --cov-report=term-missing

check: lint typecheck test ## Run lint, typecheck and tests (what CI runs)
	uv run ruff format --check

run: ## Show CLI help
	uv run madexplorer --help

SCENARIO ?= scenarios/mvp1_sandbox.yaml
sim: ## Run a scenario (SCENARIO=path, default MVP 1 sandbox)
	uv run madexplorer run $(SCENARIO)

pre-commit: ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

clean: ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
	find . -type d -name '*.egg-info' -not -path './.venv/*' -exec rm -rf {} +
