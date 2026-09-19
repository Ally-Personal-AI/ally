"""Evaluation execution and failure isolation."""

from __future__ import annotations

from time import perf_counter

from ally.evals.models import EvalCase, EvalResult, EvalSummary
from ally.evals.registry import EvaluatorRegistry


class EvaluationRunner:
    """Run frozen cases and return a machine-readable summary."""

    def __init__(self, registry: EvaluatorRegistry) -> None:
        self._registry = registry

    def run(self, cases: tuple[EvalCase, ...]) -> EvalSummary:
        results: list[EvalResult] = []

        for case in cases:
            started = perf_counter()
            try:
                evaluator = self._registry.get(case.category)
                outcome = evaluator.evaluate(case)
                status = "passed" if outcome.passed else "failed"
                message = outcome.message
                evaluator_name = evaluator.name
            except Exception as exc:
                status = "error"
                message = f"{type(exc).__name__}: {exc}"
                evaluator_name = case.category

            duration_ms = (perf_counter() - started) * 1000
            results.append(
                EvalResult(
                    case_id=case.id,
                    category=case.category,
                    evaluator=evaluator_name,
                    status=status,
                    message=message,
                    duration_ms=duration_ms,
                )
            )

        passed = sum(result.status == "passed" for result in results)
        failed = sum(result.status == "failed" for result in results)
        errors = sum(result.status == "error" for result in results)

        return EvalSummary(
            total=len(results),
            passed=passed,
            failed=failed,
            errors=errors,
            results=tuple(results),
        )
