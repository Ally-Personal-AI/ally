"""Provider-backed task-planning evaluations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ally.evals.models import EvalCase, EvaluationOutcome
from ally.models import ModelProvider
from ally.planning import ModelTaskPlanner, PlanProposalError
from ally.tools import ToolRisk, ToolSpec


class _PlanningTool(BaseModel):
    name: str
    description: str
    risk: ToolRisk = "read_only"


class _PlanningInput(BaseModel):
    goal: str
    tools: tuple[_PlanningTool, ...]


class _PlanningExpected(BaseModel):
    tool_sequence: tuple[str, ...] = Field(min_length=1)


class TaskPlanProposalEvaluator:
    """Check that a provider can produce a valid, bounded Ally TaskPlan."""

    def __init__(self, provider: ModelProvider) -> None:
        self._planner = ModelTaskPlanner(provider)
        self._provider = provider

    @property
    def name(self) -> str:
        return f"task-plan-proposal:{self._provider.name}"

    @property
    def category(self) -> str:
        return "task_plan_proposal"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _PlanningInput.model_validate(case.input)
        expected = _PlanningExpected.model_validate(case.expected)
        tools = tuple(
            ToolSpec(
                name=tool.name,
                description=tool.description,
                risk=tool.risk,
            )
            for tool in payload.tools
        )

        try:
            plan = self._planner.propose(goal=payload.goal, tools=tools)
        except PlanProposalError as exc:
            return EvaluationOutcome(passed=False, message=str(exc))

        actual = tuple(step.tool_name for step in plan.steps)
        return EvaluationOutcome(
            passed=actual == expected.tool_sequence,
            message=f"expected tools={expected.tool_sequence!r}, got {actual!r}",
        )
