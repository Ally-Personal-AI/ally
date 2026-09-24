"""Human-facing model plan proposal commands."""

from __future__ import annotations

import json

from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.planning import ModelTaskPlanner, PlanProposalError
from ally.runtime_profiles import InferenceTargetError, resolve_inference_target
from ally.tools.builtin import build_default_tool_registry


def run_propose_plan(
    *,
    development_endpoint: str | None,
    development_model: str | None,
    goal: str,
) -> int:
    registry = build_default_tool_registry()
    specs = tuple(tool.spec for tool in registry.list())

    try:
        target = resolve_inference_target(
            development_endpoint=development_endpoint,
            development_model=development_model,
        )
    except InferenceTargetError as exc:
        print(f"Inference target error: {exc}")
        return 2

    try:
        with OpenAICompatibleProvider(
            base_url=target.endpoint,
            model=target.model,
        ) as provider:
            plan = ModelTaskPlanner(provider).propose(
                goal=goal,
                tools=specs,
            )
    except ModelProviderError as exc:
        print(f"Plan provider error: {exc}")
        return 2
    except (PlanProposalError, ValueError) as exc:
        print(f"Plan proposal error: {exc}")
        return 2

    print(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0
