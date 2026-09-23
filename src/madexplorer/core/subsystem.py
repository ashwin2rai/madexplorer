"""Staged evaluate/apply protocol (spec §28.4, §37).

A subsystem evaluates the current state and returns proposals without
mutating anything; the engine then applies the proposals. Every unit within a
subsystem therefore sees the same state regardless of iteration order.
"""

from collections.abc import Sequence
from typing import Protocol

from madexplorer.core.state import SimulationState, StepContext


class Proposal(Protocol):
    """A pending, self-contained state change."""

    def apply(self, state: SimulationState, ctx: StepContext) -> None:
        """Commit the change."""
        ...


class Subsystem(Protocol):
    """One stage of the simulation step."""

    name: str

    def evaluate(self, state: SimulationState, ctx: StepContext) -> Sequence[Proposal]:
        """Compute proposals from the current state without mutating it."""
        ...
