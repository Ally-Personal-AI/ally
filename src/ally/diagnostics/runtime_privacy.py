"""Runtime privacy qualification evidence for local model runtimes."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ally import __version__
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.validation import (
    LocalModelValidationReport,
    RuntimeProfile,
    ValidationReportError,
    load_validation_report,
)

_MAX_REPORT_BYTES = 4 * 1024 * 1024

RuntimeIsolationMode = Literal[
    "unverified",
    "host_offline",
    "process_egress_denied",
    "system_content_filter",
]
RuntimePrivacyCheck = Literal["pass", "fail", "not_run"]
NetworkObservationMethod = Literal[
    "none",
    "system_tools",
    "content_filter",
    "external_monitor",
]


class RuntimePrivacyEvidenceError(ValueError):
    """Raised when runtime-privacy evidence cannot be safely loaded."""


class RuntimePrivacyChecks(BaseModel):
    """Operator-observed checks required for private runtime qualification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inference_with_egress_blocked: RuntimePrivacyCheck = "not_run"
    synthetic_chat: RuntimePrivacyCheck = "not_run"
    synthetic_planning: RuntimePrivacyCheck = "not_run"
    synthetic_memory_proposal: RuntimePrivacyCheck = "not_run"
    synthetic_grounding: RuntimePrivacyCheck = "not_run"
    no_cloud_auth_required: RuntimePrivacyCheck = "not_run"
    no_cloud_fallback_observed: RuntimePrivacyCheck = "not_run"
    no_prompt_telemetry_observed: RuntimePrivacyCheck = "not_run"
    no_unexpected_outbound_connections: RuntimePrivacyCheck = "not_run"

    @property
    def all_passed(self) -> bool:
        return all(
            value == "pass"
            for value in self.model_dump(mode="python").values()
        )


class RuntimePrivacyQualificationReport(BaseModel):
    """Immutable evidence that one validated runtime/model passed privacy checks."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    source_validation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_validation_successful: bool
    model: str = Field(min_length=1, max_length=300)
    runtime: RuntimeProfile
    hardware: HardwareProfile
    isolation_mode: RuntimeIsolationMode
    network_observation: NetworkObservationMethod
    checks: RuntimePrivacyChecks

    @model_validator(mode="after")
    def validate_evidence(self) -> RuntimePrivacyQualificationReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError(
                "runtime privacy report timestamp must include a timezone offset"
            )
        if (
            self.isolation_mode == "unverified"
            and self.network_observation != "none"
        ):
            raise ValueError(
                "unverified isolation cannot claim a network observation method"
            )
        if (
            self.isolation_mode != "unverified"
            and self.network_observation == "none"
        ):
            raise ValueError(
                "verified isolation requires a network observation method"
            )
        return self

    @property
    def qualified_for_private_inference(self) -> bool:
        return (
            self.source_validation_successful
            and self.isolation_mode != "unverified"
            and self.network_observation != "none"
            and self.checks.all_passed
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_runtime_privacy_report(
    *,
    validation_path: Path,
    isolation_mode: RuntimeIsolationMode,
    network_observation: NetworkObservationMethod,
    checks: RuntimePrivacyChecks,
) -> RuntimePrivacyQualificationReport:
    """Build privacy evidence tied cryptographically to one validation report."""

    resolved = validation_path.expanduser().resolve()
    validation: LocalModelValidationReport = load_validation_report(resolved)
    if validation.ally_version != __version__:
        raise ValueError(
            "source validation Ally version must match the current Ally version"
        )
    return RuntimePrivacyQualificationReport(
        generated_at=datetime.now(UTC),
        ally_version=__version__,
        source_validation_sha256=_sha256(resolved),
        source_validation_successful=validation.successful,
        model=validation.model,
        runtime=validation.runtime,
        hardware=validation.hardware,
        isolation_mode=isolation_mode,
        network_observation=network_observation,
        checks=checks,
    )


def write_runtime_privacy_report(
    report: RuntimePrivacyQualificationReport,
    path: Path,
) -> Path:
    """Atomically publish a new privacy artifact without replacing evidence."""

    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(
            f"refusing to overwrite runtime privacy report: {resolved}"
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
                f"refusing to overwrite runtime privacy report: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_runtime_privacy_report(
    path: Path,
) -> RuntimePrivacyQualificationReport:
    """Load bounded, strictly versioned runtime privacy evidence."""

    resolved = path.expanduser().resolve()
    try:
        size = resolved.stat().st_size
        if size > _MAX_REPORT_BYTES:
            raise RuntimePrivacyEvidenceError(
                "runtime privacy report exceeds the size limit"
            )
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return RuntimePrivacyQualificationReport.model_validate(raw)
    except RuntimePrivacyEvidenceError:
        raise
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        ValidationReportError,
    ) as exc:
        raise RuntimePrivacyEvidenceError(
            "invalid Ally runtime privacy report"
        ) from exc



def verify_runtime_privacy_source(
    report: RuntimePrivacyQualificationReport,
    validation_path: Path,
) -> LocalModelValidationReport:
    """Verify that a privacy artifact still matches its exact source evidence."""

    resolved = validation_path.expanduser().resolve()
    validation = load_validation_report(resolved)
    if _sha256(resolved) != report.source_validation_sha256:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report does not match the source validation digest"
        )
    if validation.ally_version != report.ally_version:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report Ally version does not match source validation"
        )
    if validation.model != report.model:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report model does not match source validation"
        )
    if validation.runtime != report.runtime:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report runtime does not match source validation"
        )
    if validation.hardware != report.hardware:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report hardware does not match source validation"
        )
    if validation.successful != report.source_validation_successful:
        raise RuntimePrivacyEvidenceError(
            "runtime privacy report source status does not match validation"
        )
    return validation
