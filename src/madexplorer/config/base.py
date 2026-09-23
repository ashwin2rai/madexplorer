"""Base class for immutable, strictly validated configuration models."""

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Immutable configuration model; unknown keys are validation errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")
