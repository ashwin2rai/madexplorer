"""Event log with provenance for important state changes (spec §24.3)."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A recorded state change together with the inputs that caused it."""

    year: int
    kind: str
    data: Mapping[str, Any]

    def to_record(self) -> dict[str, Any]:
        """Flatten into a JSON-ready mapping."""
        return {"year": self.year, "event": self.kind, **self.data}


class EventLog:
    """Append-only, in-memory event store for one run."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def emit(self, year: int, kind: str, **data: Any) -> None:
        """Record an event of ``kind`` with provenance fields ``data``."""
        self._events.append(Event(year, kind, data))

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)
