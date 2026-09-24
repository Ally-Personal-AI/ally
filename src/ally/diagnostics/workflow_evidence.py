"""Immutable functional-workflow evidence tied to exact capability validation."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ally import __version__
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.validation import (
    LocalModelValidationReport,
    RuntimeProfile,
    ValidationReportError,
    load_validation_report,
)
from ally.diagnostics.workflows import SyntheticWorkflowCheck, SyntheticWorkflowReport

_MAX_REPORT_BYTES = 4 * 1024 * 1024


class FunctionalWorkflowEvidenceError(ValueError):
    """Raised when functional-workflow evidence cannot be trusted."""


class FunctionalWorkflowQualificationReport(BaseModel):
    """Immutable integrated-workflow evidence for one validated candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    source_validation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_validation_successful: bool
    model: str = Field(min_length=1, max_length=300)
    runtime: RuntimeProfile
    hardware: HardwareProfile
    checks: tuple[SyntheticWorkflowCheck, ...]
    duration_ms: float = Field(ge=0.0)

    @property
    def qualified_functionally(self) -> bool:
        return (
            self.source_validation_successful
            and bool(self.checks)
            and all(check.status == "passed" for check in self.checks)
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_functional_workflow_report(
    *,
    validation_path: Path,
    workflow: SyntheticWorkflowReport,
) -> FunctionalWorkflowQualificationReport:
    """Bind one disposable workflow run to exact capability evidence."""

    resolved = validation_path.expanduser().resolve()
    validation: LocalModelValidationReport = load_validation_report(resolved)

    if validation.ally_version != __version__:
        raise ValueError(
            "source validation Ally version must match the current Ally version"
        )
    if workflow.ally_version != __version__:
        raise ValueError(
            "workflow Ally version must match the current Ally version"
        )
    if workflow.model != validation.model:
        raise ValueError("workflow model does not match source validation")

    return FunctionalWorkflowQualificationReport(
        generated_at=datetime.now(UTC),
        ally_version=__version__,
        source_validation_sha256=_sha256(resolved),
        source_validation_successful=validation.successful,
        model=validation.model,
        runtime=validation.runtime,
        hardware=validation.hardware,
        checks=workflow.checks,
        duration_ms=workflow.duration_ms,
    )


def write_functional_workflow_report(
    report: FunctionalWorkflowQualificationReport,
    path: Path,
) -> Path:
    """Atomically publish functional evidence without replacing prior evidence."""

    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(
            f"refusing to overwrite functional workflow report: {resolved}"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, resolved)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite functional workflow report: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_functional_workflow_report(
    path: Path,
) -> FunctionalWorkflowQualificationReport:
    """Load bounded, strictly versioned functional-workflow evidence."""

    resolved = path.expanduser().resolve()
    try:
        if resolved.stat().st_size > _MAX_REPORT_BYTES:
            raise FunctionalWorkflowEvidenceError(
                "functional workflow report exceeds the size limit"
            )
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return FunctionalWorkflowQualificationReport.model_validate(raw)
    except FunctionalWorkflowEvidenceError:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValidationReportError,
    ) as exc:
        raise FunctionalWorkflowEvidenceError(
            "invalid Ally functional workflow report"
        ) from exc


def verify_functional_workflow_source(
    report: FunctionalWorkflowQualificationReport,
    validation_path: Path,
) -> LocalModelValidationReport:
    """Verify functional evidence against the exact capability report."""

    resolved = validation_path.expanduser().resolve()
    validation = load_validation_report(resolved)
    if _sha256(resolved) != report.source_validation_sha256:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow report does not match the source validation digest"
        )
    if validation.ally_version != report.ally_version:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow Ally version does not match source validation"
        )
    if validation.model != report.model:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow model does not match source validation"
        )
    if validation.runtime != report.runtime:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow runtime does not match source validation"
        )
    if validation.hardware != report.hardware:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow hardware does not match source validation"
        )
    if validation.successful != report.source_validation_successful:
        raise FunctionalWorkflowEvidenceError(
            "functional workflow source status does not match validation"
        )
    return validation
