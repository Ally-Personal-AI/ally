"""Provider-neutral grounding context contracts."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ContextBlock(BaseModel):
    """A unit of reference data supplied to a model request."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ContextProvider(Protocol):
    """Retrieve reference context relevant to a user query."""

    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        ...
