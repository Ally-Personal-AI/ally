"""Evaluator registration and lookup."""

from __future__ import annotations

from ally.evals.base import Evaluator


class EvaluatorRegistry:
    """Map evaluation case categories to evaluator implementations."""

    def __init__(self) -> None:
        self._evaluators: dict[str, Evaluator] = {}

    def register(self, evaluator: Evaluator) -> None:
        category = evaluator.category.strip()
        if not category:
            raise ValueError("Evaluator category cannot be empty.")
        if category in self._evaluators:
            raise ValueError(f"Evaluator already registered for category: {category}")
        self._evaluators[category] = evaluator

    def get(self, category: str) -> Evaluator:
        try:
            return self._evaluators[category]
        except KeyError as exc:
            raise KeyError(f"No evaluator registered for category: {category}") from exc

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted(self._evaluators))
