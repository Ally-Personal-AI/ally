"""Model-provider smoke evaluations for hardware/runtime validation."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, model_validator

from ally.evals.models import EvalCase, EvaluationOutcome
from ally.models import ChatMessage, ChatRequest, ModelProvider


class _ProviderInput(BaseModel):
    prompt: str
    system_prompt: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class _ProviderExpected(BaseModel):
    exact: str | None = None
    contains: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_assertion(self) -> Self:
        if self.exact is None and not self.contains and not self.excludes:
            raise ValueError("provider evaluation requires at least one assertion")
        return self


class ProviderResponseEvaluator:
    """Run basic deterministic smoke assertions against a real model provider."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    @property
    def name(self) -> str:
        return f"provider-response:{self._provider.name}"

    @property
    def category(self) -> str:
        return "provider_response"

    def evaluate(self, case: EvalCase) -> EvaluationOutcome:
        payload = _ProviderInput.model_validate(case.input)
        expected = _ProviderExpected.model_validate(case.expected)

        messages: list[ChatMessage] = []
        if payload.system_prompt is not None:
            messages.append(ChatMessage(role="system", content=payload.system_prompt))
        messages.append(ChatMessage(role="user", content=payload.prompt))

        response = self._provider.chat(
            ChatRequest(
                messages=tuple(messages),
                temperature=payload.temperature,
            )
        )
        content = response.content.strip()

        failures: list[str] = []
        if expected.exact is not None and content != expected.exact:
            failures.append(f"expected exact {expected.exact!r}, got {content!r}")
        for value in expected.contains:
            if value not in content:
                failures.append(f"missing required text {value!r}")
        for value in expected.excludes:
            if value in content:
                failures.append(f"contained forbidden text {value!r}")

        return EvaluationOutcome(
            passed=not failures,
            message="; ".join(failures),
        )
