from ally.evals.memory_proposal import MemoryProposalEvaluator
from ally.evals.models import EvalCase
from ally.models import ChatRequest, ChatResponse


class MemoryProvider:
    @property
    def name(self) -> str:
        return "memory-test"

    def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content=(
                '{"memories":[{"kind":"preference",'
                '"content":"Prefers tea over coffee.",'
                '"confidence":0.95,"importance":0.7}]}'
            ),
            model="synthetic",
            provider=self.name,
        )


def test_memory_proposal_evaluator_checks_kind_and_terms() -> None:
    evaluator = MemoryProposalEvaluator(MemoryProvider())
    case = EvalCase(
        id="memory",
        category="memory_proposal",
        input={"text": "I prefer tea over coffee."},
        expected={
            "kind_sequence": ["preference"],
            "required_terms": ["tea", "coffee"],
        },
    )

    outcome = evaluator.evaluate(case)

    assert outcome.passed is True
