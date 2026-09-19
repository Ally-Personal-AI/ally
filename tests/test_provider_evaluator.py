from ally.evals import EvalCase
from ally.evals.provider import ProviderResponseEvaluator
from ally.models import ChatRequest, ChatResponse


class FakeProvider:
    @property
    def name(self) -> str:
        return "fake"

    def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            content="ALLY_OK",
            model="synthetic",
            provider=self.name,
        )


def test_provider_evaluator_supports_exact_smoke_assertion() -> None:
    evaluator = ProviderResponseEvaluator(FakeProvider())
    case = EvalCase(
        id="provider",
        category="provider_response",
        input={"prompt": "reply", "temperature": 0.0},
        expected={"exact": "ALLY_OK"},
    )

    outcome = evaluator.evaluate(case)

    assert outcome.passed
    assert outcome.message == ""
