"""Registration and lookup for model providers."""

from __future__ import annotations

from ally.models.base import ModelProvider


class ModelRegistry:
    """Runtime registry that keeps Ally decoupled from inference backends."""

    def __init__(self) -> None:
        self._providers: dict[str, ModelProvider] = {}

    def register(self, provider: ModelProvider) -> None:
        name = provider.name.strip()
        if not name:
            raise ValueError("Provider name cannot be empty.")
        if name in self._providers:
            raise ValueError(f"Provider already registered: {name}")
        self._providers[name] = provider

    def get(self, name: str) -> ModelProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown model provider: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
