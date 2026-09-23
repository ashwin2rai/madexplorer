"""Central deterministic random-number service (spec §23.1).

No module may call the global ``random`` or ``numpy.random`` state. Subsystems
receive a named :class:`numpy.random.Generator` from :class:`RngManager`.
"""

import hashlib

import numpy as np


class Streams:
    """Canonical stream names. Each subsystem draws only from its own stream."""

    WORLD = "world"
    INITIALIZATION = "initialization"
    ENVIRONMENT = "environment"
    PERCEPTION = "perception"
    DEMOGRAPHY = "demography"
    SOCIAL = "social"
    MIGRATION = "migration"


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
