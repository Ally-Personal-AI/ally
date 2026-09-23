from ally.evals import EvalCase, EvaluatorRegistry
from ally.evals.behavior import (
    BehaviorResponseEvaluator,
    BehaviorViewpointPairEvaluator,
    register_behavioral_evaluators,
)
from ally.models import ChatRequest, ChatResponse


class PromptProvider:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses

    @property
    def name(self) -> str:
        return "prompt-provider"

    def chat(self, request: ChatRequest) -> ChatResponse:
        prompt = request.messages[-1].content
        return ChatResponse(
            content=self._responses[prompt],
            model="synthetic",
            provider=self.name,
        )


def test_behavior_response_evaluator_detects_excluded_refusal_text() -> None:
    provider = PromptProvider({"question": "I cannot help with that."})
    evaluator = BehaviorResponseEvaluator(provider, "behavior_refusal")
    case = EvalCase(
        id="refusal",
        category="behavior_refusal",
        input={"prompt": "question"},
        expected={
            "excludes": ["I cannot help with that"],
            "min_chars": 5,
        },
    )

    outcome = evaluator.evaluate(case)

    assert not outcome.passed
    assert "excluded text" in outcome.message


def test_behavior_response_evaluator_checks_instruction_constraints() -> None:
    provider = PromptProvider({"question": "CUSTOM_OK"})
    evaluator = BehaviorResponseEvaluator(
        provider,
        "behavior_instruction_following",
    )
    case = EvalCase(
        id="instruction",
        category="behavior_instruction_following",
        input={"prompt": "question"},
        expected={
            "contains": ["CUSTOM_OK"],
            "min_chars": 9,
            "max_chars": 9,
        },
    )

    outcome = evaluator.evaluate(case)

    assert outcome.passed


def test_viewpoint_pair_evaluator_uses_same_structural_standard() -> None:
    provider = PromptProvider(
        {
            "side-a": "Counterarguments " + ("A" * 120),
            "side-b": "Counterarguments " + ("B" * 100),
        }
    )
    evaluator = BehaviorViewpointPairEvaluator(provider)
    case = EvalCase(
        id="pair",
        category="behavior_viewpoint_pair",
        input={
            "prompt_a": "side-a",
            "prompt_b": "side-b",
        },
        expected={
            "contains_a": ["Counterarguments"],
            "contains_b": ["Counterarguments"],
            "min_chars_each": 80,
            "max_length_ratio": 2.0,
        },
    )

    outcome = evaluator.evaluate(case)

    assert outcome.passed


def test_viewpoint_pair_evaluator_flags_large_response_asymmetry() -> None:
    provider = PromptProvider(
        {
            "side-a": "A" * 300,
            "side-b": "B" * 80,
        }
    )
    evaluator = BehaviorViewpointPairEvaluator(provider)
    case = EvalCase(
        id="pair",
        category="behavior_viewpoint_pair",
        input={
            "prompt_a": "side-a",
            "prompt_b": "side-b",
        },
        expected={
            "min_chars_each": 50,
            "max_length_ratio": 2.0,
        },
    )

    outcome = evaluator.evaluate(case)

    assert not outcome.passed
    assert "length ratio" in outcome.message


def test_behavioral_registry_exposes_dimensions_separately() -> None:
    registry = EvaluatorRegistry()
    register_behavioral_evaluators(registry, PromptProvider({}))

    assert registry.categories() == (
        "behavior_calibration",
        "behavior_instruction_following",
        "behavior_moralizing",
        "behavior_refusal",
        "behavior_viewpoint_pair",
    )
