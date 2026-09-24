"""Human-facing model plan proposal commands."""

from __future__ import annotations

import json

from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider
from ally.planning import ModelTaskPlanner, PlanProposalError
from ally.tools.builtin import build_default_tool_registry


def run_propose_plan(
    *,
    endpoint: str,
    model: str,
    goal: str,
) -> int:
    registry = build_default_tool_registry()
    specs = tuple(tool.spec for tool in registry.list())

    try:
        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
        ) as provider:
            plan = ModelTaskPlanner(provider).propose(
                goal=goal,
                tools=specs,
            )
    except (ModelProviderError, PlanProposalError, ValueError) as exc:
        print(f"Plan proposal error: {exc}")
        return 2

    print(json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0
