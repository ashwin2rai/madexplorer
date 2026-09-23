# madexplorer

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
make install                 # uv sync + install pre-commit git hooks
```

Run `make` to list all targets (`test`, `lint`, `format`, `typecheck`, `check`, `cov`, `clean`, ...).

## Underlying uv commands

```bash
uv run madexplorer           # run the CLI entry point
uv run pytest                # tests
uv run ruff check --fix      # lint
uv run ruff format           # format
uv run mypy                  # type-check
uv add <pkg>                 # add a runtime dependency
uv add --dev <pkg>           # add a dev dependency
```
