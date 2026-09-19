"""Evaluation domain models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class EvalCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    input: dict[str, JsonValue]
    expected: dict[str, JsonValue]
    tags: tuple[str, ...] = ()


class EvaluationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    message: str = ""


EvalStatus = Literal["passed", "failed", "error"]


class EvalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    category: str
    evaluator: str
    status: EvalStatus
    message: str
    duration_ms: float = Field(ge=0.0)


class EvalSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    results: tuple[EvalResult, ...]

    @property
    def successful(self) -> bool:
        return self.failed == 0 and self.errors == 0
