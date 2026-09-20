"""CLI commands for deterministic and provider-backed evaluations."""

from __future__ import annotations

from ally.evals import EvalSummary, EvaluationRunner, EvaluatorRegistry
from ally.evals.builtin import register_builtin_evaluators
from ally.evals.loader import load_eval_cases
from ally.evals.memory_proposal import MemoryProposalEvaluator
from ally.evals.planning import TaskPlanProposalEvaluator
from ally.evals.provider import ProviderResponseEvaluator
from ally.evals.reporting import render_json_summary, render_text_summary
from ally.evals.resources import evaluation_case_file
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider


def _print_summary(*, summary: EvalSummary, json_output: bool) -> None:
    if json_output:
        print(render_json_summary(summary))
    else:
        print(render_text_summary(summary))


def run_core_evals(*, case_file: str | None, json_output: bool) -> int:
    try:
        with evaluation_case_file("core", case_file) as path:
            cases = load_eval_cases(path)
        registry = EvaluatorRegistry()
        register_builtin_evaluators(registry)
        summary = EvaluationRunner(registry).run(cases)
    except ValueError as exc:
        print(f"Evaluation error: {exc}")
        return 2

    _print_summary(summary=summary, json_output=json_output)
    return 0 if summary.successful else 1


def run_provider_evals(
    *,
    case_file: str | None,
    endpoint: str,
    model: str,
    allow_remote: bool,
    json_output: bool,
) -> int:
    try:
        with evaluation_case_file("provider-smoke", case_file) as path:
            cases = load_eval_cases(path)
        registry = EvaluatorRegistry()
        register_builtin_evaluators(registry)

        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=allow_remote,
        ) as provider:
            registry.register(ProviderResponseEvaluator(provider))
            registry.register(TaskPlanProposalEvaluator(provider))
            registry.register(MemoryProposalEvaluator(provider))
            summary = EvaluationRunner(registry).run(cases)
    except (ModelProviderError, ValueError) as exc:
        print(f"Evaluation error: {exc}")
        return 2

    _print_summary(summary=summary, json_output=json_output)
    return 0 if summary.successful else 1
