"""Provider-backed memory extraction evaluations."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ally.evals.models import EvalCase, EvaluationOutcome
from ally.memory import MemorySource
from ally.memory.proposals import ModelMemoryProposer, MemoryProposalError
from ally.models import ModelProvider


class _MemoryProposalInput(BaseModel):
    text: str


class _MemoryProposalExpected(BaseModel):
    kind_sequence: tuple[str, ...] = Field(min_length=1)
    required_terms: tuple[str, ...] = ()


class MemoryProposalEvaluator:
    """Evaluate bounded memory formation quality without persisting anything."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider
        self._proposer = ModelMemoryProposer(provider)

    @property
    def name(self) -> str:
        return f"memory-proposal:{self._provider.name}"

    @property
    def category(self) -> str:
        return "memory_proposal"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _MemoryProposalInput.model_validate(case.input)
        expected = _MemoryProposalExpected.model_validate(case.expected)

        try:
            bundle = self._proposer.propose(
                text=payload.text,
                source=MemorySource(type="system", id=case.id),
            )
        except MemoryProposalError as exc:
            return EvaluationOutcome(passed=False, message=str(exc))

        actual_kinds = tuple(candidate.kind for candidate in bundle.memories)
        combined = " ".join(candidate.content.casefold() for candidate in bundle.memories)
        missing = [
            term
            for term in expected.required_terms
            if term.casefold() not in combined
        ]
        passed = actual_kinds == expected.kind_sequence and not missing
        return EvaluationOutcome(
            passed=passed,
            message=(
                f"expected kinds={expected.kind_sequence!r}, got {actual_kinds!r}; "
                f"missing terms={missing!r}"
            ),
        )
