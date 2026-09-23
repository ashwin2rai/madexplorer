"""Stable identifiers independent of container ordering (spec §23.2)."""


class IdAllocator:
    """Allocates monotonically increasing identifiers per prefix, e.g. ``u1, u2, ...``."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}

    def next(self, prefix: str) -> str:
        """Return the next unused identifier for ``prefix``."""
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count}"
