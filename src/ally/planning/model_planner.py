"""Provider-backed task-plan proposal generation.

Planning is intentionally separate from task persistence and execution.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from ally.models import ChatMessage, ChatRequest, ModelProvider
from ally.tasks import TaskPlan
from ally.tools import ToolSpec


class PlanProposalError(ValueError):
    """Raised when a model returns an invalid or unauthorized plan proposal."""


class ModelTaskPlanner:
    """Ask a model for TaskPlan data without persisting or executing it."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    def propose(
        self,
        *,
        goal: str,
        tools: tuple[ToolSpec, ...],
    ) -> TaskPlan:
        normalized_goal = goal.strip()
        if not normalized_goal:
            raise ValueError("goal cannot be empty")
        if not tools:
            raise ValueError("at least one available tool is required")

        available_names = {tool.name for tool in tools}
        tool_payload = [
            {
                "name": tool.name,
                "description": tool.description,
                "risk": tool.risk,
            }
            for tool in tools
        ]
        request = ChatRequest(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "You are Ally's planning component. Produce only a single JSON "
                        "object. Do not use Markdown or code fences. The JSON must match "
                        'this shape exactly: {"goal": "<goal copied exactly>", '
                        '"steps": [{"tool_name": "<available tool name>", '
                        '"arguments": {}}]}. Use only the tools explicitly supplied. '
                        "This is a proposal only; it will not be executed automatically."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"Goal:\n{normalized_goal}\n\n"
                        "Available tools:\n"
                        f"{json.dumps(tool_payload, sort_keys=True)}"
                    ),
                ),
            ),
            temperature=0.0,
        )
        response = self._provider.chat(request)
        raw = response.content.strip()

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlanProposalError("planner response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise PlanProposalError("planner response must be one JSON object")

        try:
            plan = TaskPlan.model_validate(payload)
        except ValidationError as exc:
            raise PlanProposalError(f"planner response is not a valid TaskPlan: {exc}") from exc

        if plan.goal != normalized_goal:
            raise PlanProposalError("planner changed the requested goal")

        undeclared = sorted(
            {
                step.tool_name
                for step in plan.steps
                if step.tool_name not in available_names
            }
        )
        if undeclared:
            joined = ", ".join(undeclared)
            raise PlanProposalError(f"planner used undeclared tools: {joined}")

        return plan
