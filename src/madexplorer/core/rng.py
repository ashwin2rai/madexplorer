"""Central deterministic random-number service (spec §23.1).

No module may call the global ``random`` or ``numpy.random`` state. Subsystems
receive a named :class:`numpy.random.Generator` from :class:`RngManager`.
"""

import hashlib

import numpy as np


class Streams:
    """Canonical stream names, one per stochastic mechanism.

    No two mechanisms share a stream, so changing how many numbers one mechanism draws
    (a parameter change, an ablation, a new rule) never shifts another's draws.
    """

    WORLD = "world"
    INITIALIZATION = "initialization"
    ENVIRONMENT = "environment"
    PERCEPTION = "perception"
    KNOWLEDGE_SHARING = "knowledge_sharing"
    DEMOGRAPHY = "demography"
    FISSION = "fission"
    FUSION = "fusion"
    MIGRATION = "migration"
    INNOVATION = "innovation"
    TECHNOLOGY_ADOPTION = "technology_adoption"
    TRADE = "trade"


def _stable_key(name: str) -> int:
    """Hash a stream name to an integer that is stable across processes and platforms."""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "little")


class RngManager:
    """Hands out independent, named, reproducible generators.

    Each stream is seeded from ``(seed, stable_hash(name))``, so drawing more
    numbers from one stream, or adding a new stream, never perturbs another.
    """

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams: dict[str, np.random.Generator] = {}

    def stream(self, name: str) -> np.random.Generator:
        """Return the generator for ``name``, creating it on first use."""
        generator = self._streams.get(name)
        if generator is None:
            sequence = np.random.SeedSequence([self.seed, _stable_key(name)])
            generator = np.random.default_rng(sequence)
            self._streams[name] = generator
        return generator

    def keyed(self, mechanism: str, *keys: int | str) -> np.random.Generator:
        """A fresh generator for one ``(mechanism, keys...)`` draw site, e.g. year and unit id.

        Unlike :meth:`stream`, its numbers do not depend on how many draws other units or
        years made, so splitting or merging units cannot perturb unrelated units. It is
        slower (one generator per call); subsystems adopt it when adaptive resolution in
        MVP 3 makes draw order unstable.
        """
        entropy = [self.seed, _stable_key(mechanism)] + [
            k if isinstance(k, int) else _stable_key(k) for k in keys
        ]
        return np.random.default_rng(np.random.SeedSequence(entropy))
