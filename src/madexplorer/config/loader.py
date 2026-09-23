"""Load scenarios from YAML and resolve species profile files."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from madexplorer.config.schema import ScenarioConfig
from madexplorer.species.profile import SpeciesProfile


def deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overrides`` into a copy of ``base``."""
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open() as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


@dataclass(frozen=True)
class Scenario:
    """A validated scenario together with its resolved species profiles."""

    config: ScenarioConfig
    species: Mapping[str, SpeciesProfile]

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Scenario":
        """Load a scenario file; species profile paths are relative to it."""
        path = Path(path)
        return cls.from_dict(_read_yaml(path), base_dir=path.parent)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], base_dir: Path = Path()) -> "Scenario":
        """Build a scenario from an already-parsed mapping."""
        config = ScenarioConfig.model_validate(data)
        species: dict[str, SpeciesProfile] = {}
        for ref in config.species:
            raw = _read_yaml(base_dir / ref.profile)
            raw = deep_merge(raw, ref.overrides)
            raw["id"] = ref.id
            species[ref.id] = SpeciesProfile.model_validate(raw)
        return cls(config=config, species=species)

    def with_overrides(self, *, seed: int | None = None, n_years: int | None = None) -> "Scenario":
        """Return a copy with the run seed and/or horizon replaced."""
        updates: dict[str, int] = {}
        if seed is not None:
            updates["seed"] = seed
        if n_years is not None:
            updates["n_years"] = n_years
        simulation = self.config.simulation.model_copy(update=updates)
        config = self.config.model_copy(update={"simulation": simulation})
        return Scenario(
            config=ScenarioConfig.model_validate(config.model_dump()), species=self.species
        )

    def to_dict(self) -> dict[str, Any]:
        """Fully resolved scenario, with species profiles embedded."""
        return {
            "scenario": self.config.model_dump(mode="json"),
            "species_profiles": {
                sid: profile.model_dump(mode="json") for sid, profile in self.species.items()
            },
        }

    def config_hash(self) -> str:
        """SHA-256 of the canonical resolved configuration."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
