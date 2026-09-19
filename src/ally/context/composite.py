"""Composition of independent grounding context providers."""

from __future__ import annotations

from collections.abc import Sequence

from ally.context.base import ContextBlock, ContextProvider


class CompositeContextProvider:
    """Combine independent context providers behind one bounded contract."""

    def __init__(
        self,
        providers: Sequence[ContextProvider],
        *,
        limit: int = 12,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self._providers = tuple(providers)
        self._limit = limit

    def retrieve(self, query: str) -> tuple[ContextBlock, ...]:
        blocks: list[ContextBlock] = []
        for provider in self._providers:
            remaining = self._limit - len(blocks)
            if remaining <= 0:
                break
            blocks.extend(provider.retrieve(query)[:remaining])
        return tuple(blocks)
