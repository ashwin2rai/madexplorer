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


def source_tree_hash() -> str:
    """SHA-256 over the package's Python sources (path and content, sorted by path).

    Identifies the code that produced a run even when the git working tree is dirty.
    """
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def numeric_platform() -> str:
    """numpy version, machine and the SIMD targets numpy dispatches to on this CPU."""
    try:
        from numpy._core._multiarray_umath import (  # type: ignore[import-not-found]
            __cpu_baseline__,
            __cpu_dispatch__,
            __cpu_features__,
        )

        active = [t for t in __cpu_dispatch__ if __cpu_features__.get(t)]
        simd = f"baseline={','.join(__cpu_baseline__)} dispatch={','.join(active)}"
    except ImportError:  # pragma: no cover - numpy internals moved
        simd = "simd=unknown"
    return f"numpy={np.__version__} machine={platform.machine()} {simd}"


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
        "source_tree_sha256": source_tree_hash(),
        "dependency_lock_hash": _lock_hash(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        **extra,
    }
