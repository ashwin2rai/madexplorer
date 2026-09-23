"""Model-rule metadata registry (spec §39).

Every model equation is decorated with :func:`model_rule`, so the codebase can
answer "why does this rule exist?" via ``madexplorer rules``.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

SourceType = Literal["empirical", "theoretical", "heuristic", "placeholder"]

F = TypeVar("F", bound=Callable[..., object])


@dataclass(frozen=True)
class ModelRule:
    """Metadata describing one model equation or behavioral rule."""

    name: str
    version: str
    rationale: str
    source_type: SourceType
    parameters: tuple[str, ...]
    expected_domain: str
    known_limitations: str
    qualname: str


# Import-time metadata only; never mutated during a simulation run.
RULES: dict[str, ModelRule] = {}


def model_rule(
    *,
    name: str,
    version: str,
    rationale: str,
    source_type: SourceType,
    parameters: tuple[str, ...] = (),
    expected_domain: str = "",
    known_limitations: str = "",
) -> Callable[[F], F]:
    """Register the decorated function as a documented model rule."""

    def decorator(func: F) -> F:
        if name in RULES:
            raise ValueError(f"duplicate model rule name: {name}")
        RULES[name] = ModelRule(
            name=name,
            version=version,
            rationale=rationale,
            source_type=source_type,
            parameters=parameters,
            expected_domain=expected_domain,
            known_limitations=known_limitations,
            qualname=f"{func.__module__}.{func.__qualname__}",
        )
        return func

    return decorator
