"""CLI commands for deterministic and provider-backed evaluations."""

from __future__ import annotations

from ally.evals import EvalSummary, EvaluationRunner, EvaluatorRegistry
from ally.evals.behavior import register_behavioral_evaluators
from ally.evals.builtin import register_builtin_evaluators
from ally.evals.loader import load_eval_cases
from ally.evals.memory_proposal import MemoryProposalEvaluator
from ally.evals.planning import TaskPlanProposalEvaluator
from ally.evals.provider import ProviderResponseEvaluator
from ally.evals.reporting import render_json_summary, render_text_summary
from ally.evals.resources import evaluation_case_file
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatiblePublicProvider


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
    allow_remote_public: bool,
    json_output: bool,
) -> int:
    try:
        if allow_remote_public and case_file is not None:
            raise ValueError(
                "Remote evaluation accepts only Ally's bundled synthetic/public suite; "
                "custom case files must use a local provider."
            )
        with evaluation_case_file("provider-smoke", case_file) as path:
            cases = load_eval_cases(path)
        registry = EvaluatorRegistry()
        register_builtin_evaluators(registry)

        with OpenAICompatiblePublicProvider(
            base_url=endpoint,
            model=model,
            allow_remote_public=allow_remote_public,
        ) as provider:
            registry.register(ProviderResponseEvaluator(provider))
            registry.register(TaskPlanProposalEvaluator(provider))
            registry.register(MemoryProposalEvaluator(provider))
            register_behavioral_evaluators(registry, provider)
            summary = EvaluationRunner(registry).run(cases)
    except (ModelProviderError, ValueError) as exc:
        print(f"Evaluation error: {exc}")
        return 2

    _print_summary(summary=summary, json_output=json_output)
    return 0 if summary.successful else 1


def run_behavior_evals(
    *,
    case_file: str | None,
    endpoint: str,
    model: str,
    allow_remote_public: bool,
    json_output: bool,
) -> int:
    """Run the bundled behavioral qualification suite against one provider."""

    try:
        if allow_remote_public and case_file is not None:
            raise ValueError(
                "Remote evaluation accepts only Ally's bundled synthetic/public suite; "
                "custom case files must use a local provider."
            )
        with evaluation_case_file("behavioral-qualification", case_file) as path:
            cases = load_eval_cases(path)
        registry = EvaluatorRegistry()
        with OpenAICompatiblePublicProvider(
            base_url=endpoint,
            model=model,
            allow_remote_public=allow_remote_public,
        ) as provider:
            register_behavioral_evaluators(registry, provider)
            summary = EvaluationRunner(registry).run(cases)
    except (ModelProviderError, ValueError) as exc:
        print(f"Evaluation error: {exc}")
        return 2

    _print_summary(summary=summary, json_output=json_output)
    return 0 if summary.successful else 1
