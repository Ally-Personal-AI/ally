from ally.evals.models import EvalCase
from ally.evals.planning import TaskPlanProposalEvaluator
from ally.models import ChatRequest, ChatResponse


class PlanningProvider:
    @property
    def name(self) -> str:
        return "planning-test"

    def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=(
                '{"goal":"Inspect the local runtime",'
                '"steps":[{"tool_name":"system.info","arguments":{}}]}'
            ),
            model="synthetic",
            provider=self.name,
        )


def test_task_plan_proposal_evaluator_checks_tool_sequence() -> None:
    evaluator = TaskPlanProposalEvaluator(PlanningProvider())
    case = EvalCase(
        id="plan",
        category="task_plan_proposal",
        input={
            "goal": "Inspect the local runtime",
            "tools": [
                {
                    "name": "system.info",
                    "description": "Return local runtime information.",
                    "risk": "read_only",
                }
            ],
        },
        expected={"tool_sequence": ["system.info"]},
    )

    outcome = evaluator.evaluate(case)

    assert outcome.passed is True
