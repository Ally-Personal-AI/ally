import pytest

from ally.models import ChatRequest, ChatResponse
from ally.planning import ModelTaskPlanner, PlanProposalError
from ally.tools import ToolSpec


class StaticProvider:
    def __init__(self, content: str) -> None:
        self._content = content
        self.requests: list[ChatRequest] = []

    @property
    def name(self) -> str:
        return "static"

    def chat(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        return ChatResponse(
            content=self._content,
            model="synthetic",
            provider=self.name,
        )


def tool(name: str = "system.info") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Synthetic read-only tool.",
        risk="read_only",
    )


def test_planner_returns_valid_task_plan_without_execution() -> None:
    provider = StaticProvider(
        '{"goal":"Inspect runtime","steps":[{"tool_name":"system.info","arguments":{}}]}'
    )

    plan = ModelTaskPlanner(provider).propose(
        goal="Inspect runtime",
        tools=(tool(),),
    )

    assert plan.goal == "Inspect runtime"
    assert plan.steps[0].tool_name == "system.info"
    assert len(provider.requests) == 1


def test_planner_rejects_non_json_output() -> None:
    provider = StaticProvider("Here is your plan.")

    with pytest.raises(PlanProposalError, match="not valid JSON"):
        ModelTaskPlanner(provider).propose(
            goal="Inspect runtime",
            tools=(tool(),),
        )


def test_planner_rejects_goal_drift() -> None:
    provider = StaticProvider(
        '{"goal":"Different goal","steps":[{"tool_name":"system.info","arguments":{}}]}'
    )

    with pytest.raises(PlanProposalError, match="changed the requested goal"):
        ModelTaskPlanner(provider).propose(
            goal="Inspect runtime",
            tools=(tool(),),
        )


def test_planner_rejects_undeclared_tool() -> None:
    provider = StaticProvider(
        '{"goal":"Inspect runtime","steps":[{"tool_name":"shell.exec","arguments":{}}]}'
    )

    with pytest.raises(PlanProposalError, match=r"undeclared tools: shell\.exec"):
        ModelTaskPlanner(provider).propose(
            goal="Inspect runtime",
            tools=(tool(),),
        )


def test_planner_requires_non_empty_goal_and_tool_set() -> None:
    provider = StaticProvider("{}")

    with pytest.raises(ValueError, match="goal cannot be empty"):
        ModelTaskPlanner(provider).propose(goal="  ", tools=(tool(),))

    with pytest.raises(ValueError, match="at least one available tool"):
        ModelTaskPlanner(provider).propose(goal="Inspect runtime", tools=())
