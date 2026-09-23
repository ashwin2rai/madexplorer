"""Run versioning metadata (spec §23.3)."""

import hashlib
import platform
import subprocess
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np

from madexplorer.config.loader import Scenario


def model_version() -> str:
    """Installed package version."""
    try:
        return version("madexplorer")
    except PackageNotFoundError:  # pragma: no cover - running from an uninstalled tree
        return "unknown"


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def _lock_hash() -> str | None:
    for directory in [Path.cwd(), *Path.cwd().parents]:
        lock = directory / "uv.lock"
        if lock.is_file():
            return hashlib.sha256(lock.read_bytes()).hexdigest()
    return None


def run_manifest(scenario: Scenario, **extra: Any) -> dict[str, Any]:
    """Metadata sufficient to reproduce and audit a run."""
    status = _git("status", "--porcelain")
    return {
        "scenario_name": scenario.config.name,
        "seed": scenario.config.simulation.seed,
        "world_seed": scenario.config.world.topology.seed,
        "config_hash": scenario.config_hash(),
        "model_version": model_version(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "dependency_lock_hash": _lock_hash(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        **extra,
    }
