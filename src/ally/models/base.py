"""Stable model-provider contracts.

Ally depends on these contracts, not on Ollama, MLX, llama.cpp, CUDA, or any
other inference implementation directly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: tuple[ChatMessage, ...]
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str
    model: str
    provider: str


@runtime_checkable
class ModelProvider(Protocol):
    """Interface every inference backend must implement."""

    @property
    def name(self) -> str:
        """Stable provider identifier."""

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Produce a chat response."""
