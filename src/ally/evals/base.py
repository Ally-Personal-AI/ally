"""Evaluator protocol."""

from __future__ import annotations

from typing import Protocol

from ally.evals.models import EvalCase, EvaluationOutcome


class Evaluator(Protocol):
    """Evaluate one category of frozen Ally behavior cases."""

    @property
    def name(self) -> str:
        ...

    @property
    def category(self) -> str:
        ...

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        ...
