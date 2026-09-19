"""Models that refer to secrets without containing secret material."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SecretRef(BaseModel):
    """Opaque reference suitable for ordinary non-secret configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
