"""Verification is a phase distinct from tool execution."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from ally.tasks.models import TaskStepRecord
from ally.tools.models import ToolExecution


class VerificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    detail: str


class StepVerifier(Protocol):
    def verify(
        self,
        step: TaskStepRecord,
        execution: ToolExecution,
    ) -> VerificationResult:
        ...


class ExecutionSucceededVerifier:
    """Initial verifier: execution must report success before a step completes."""

    def verify(
        self,
        step: TaskStepRecord,
        execution: ToolExecution,
    ) -> VerificationResult:
        if execution.status == "succeeded":
            return VerificationResult(
                passed=True,
                detail=f"{step.tool_name} completed successfully.",
            )
        return VerificationResult(
            passed=False,
            detail=execution.error or f"{step.tool_name} did not succeed.",
        )
