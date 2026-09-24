"""Resumable validation sessions derived from immutable evidence."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ally import __version__
from ally.diagnostics.readiness import (
    FirstMachineReadinessReport,
    collect_first_machine_readiness,
)
from ally.diagnostics.runtime_privacy import (
    RuntimePrivacyEvidenceError,
    load_runtime_privacy_report,
    verify_runtime_privacy_source,
)
from ally.diagnostics.validation import ValidationReportError, load_validation_report
from ally.diagnostics.workflows import (
    FunctionalWorkflowEvidenceError,
    load_functional_workflow_report,
    verify_functional_workflow_source,
)
from ally.runtime_profiles import (
    ValidatedRuntimeProfileError,
    load_validated_runtime_profile,
    verify_validated_runtime_profile,
)

_MAX_SESSION_BYTES = 1024 * 1024

ValidationStageState = Literal[
    "pending",
    "passed",
    "failed",
    "inconsistent",
    "blocked",
]
ValidationNextStep = Literal[
    "resolve_readiness",
    "create_capability_evidence",
    "replace_candidate_capability",
    "create_workflow_evidence",
    "fix_workflow_evidence",
    "create_privacy_evidence",
    "fix_privacy_evidence",
    "create_validated_profile",
    "recreate_validated_profile",
    "complete",
]


class ValidationSessionError(ValueError):
    """Raised when a validation-session manifest cannot be trusted."""


class ValidationArtifactPlan(BaseModel):
    """Relative artifact filenames expected inside one session directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str = "capability.json"
    privacy: str = "privacy.json"
    workflows: str = "workflows.json"
    profile: str = "profile.json"

    @model_validator(mode="after")
    def validate_leaf_names(self) -> ValidationArtifactPlan:
        for value in self.model_dump(mode="python").values():
            if (
                not isinstance(value, str)
                or value != value.strip()
                or value in {".", ".."}
                or "/" in value
                or "\\" in value
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in value
                )
            ):
                raise ValueError("session artifact names must be printable leaf filenames")
        values = tuple(self.model_dump(mode="python").values())
        if len(values) != len(set(values)):
            raise ValueError("session artifact filenames must be unique")
        return self


class ValidationSessionManifest(BaseModel):
    """Immutable plan for one candidate validation attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    session_id: UUID
    created_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    candidate_label: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
    )
    artifacts: ValidationArtifactPlan = Field(default_factory=ValidationArtifactPlan)

    @model_validator(mode="after")
    def validate_manifest(self) -> ValidationSessionManifest:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("validation session timestamp must include timezone offset")
        return self


class ValidationStageStatus(BaseModel):
    """Derived state for one validation stage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    state: ValidationStageState
    artifact_name: str | None = Field(default=None, max_length=255)
    artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    detail: str = Field(min_length=1, max_length=300)


class ValidationSessionStatus(BaseModel):
    """Live derived session state; never an alternate source of truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    session_id: UUID
    candidate_label: str
    ally_version: str
    readiness: ValidationStageStatus
    capability: ValidationStageStatus
    workflows: ValidationStageStatus
    privacy: ValidationStageStatus
    profile: ValidationStageStatus
    next_step: ValidationNextStep
    complete: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def initialize_validation_session(
    *,
    directory: Path,
    candidate_label: str,
    artifacts: ValidationArtifactPlan | None = None,
    created_at: datetime | None = None,
) -> tuple[ValidationSessionManifest, Path]:
    """Create one immutable session plan and no candidate evidence."""

    root = directory.expanduser().resolve()
    manifest_path = root / "session.json"
    if manifest_path.exists():
        raise FileExistsError(
            f"refusing to overwrite validation session: {manifest_path}"
        )

    observed_at = datetime.now(UTC) if created_at is None else created_at
    manifest = ValidationSessionManifest(
        session_id=uuid4(),
        created_at=observed_at,
        ally_version=__version__,
        candidate_label=candidate_label,
        artifacts=artifacts or ValidationArtifactPlan(),
    )
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".session.json.{uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, manifest_path)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite validation session: {manifest_path}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return manifest, manifest_path


def load_validation_session(path: Path) -> ValidationSessionManifest:
    """Load one bounded strict session manifest."""

    resolved = path.expanduser().resolve()
    try:
        if resolved.stat().st_size > _MAX_SESSION_BYTES:
            raise ValidationSessionError("validation session exceeds the size limit")
        return ValidationSessionManifest.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except ValidationSessionError:
        raise
    except (OSError, UnicodeError, ValidationError) as exc:
        raise ValidationSessionError("invalid Ally validation session") from exc


def _artifact_path(session_path: Path, name: str) -> Path:
    return session_path.expanduser().resolve().parent / name


def _missing(stage_id: str, name: str, *, blocked: bool = False) -> ValidationStageStatus:
    return ValidationStageStatus(
        id=stage_id,
        state="blocked" if blocked else "pending",
        artifact_name=name,
        detail=(
            "Required upstream evidence is not qualified."
            if blocked
            else "Evidence artifact is not present yet."
        ),
    )


def _readiness_stage(report: FirstMachineReadinessReport) -> ValidationStageStatus:
    return ValidationStageStatus(
        id="readiness",
        state="passed" if report.ready_to_begin_validation else "failed",
        detail=(
            "Read-only machine readiness has no blocking errors."
            if report.ready_to_begin_validation
            else "Read-only machine readiness has blocking errors."
        ),
    )


def _capability_stage(path: Path) -> ValidationStageStatus:
    if not path.is_file():
        return _missing("capability", path.name)
    try:
        report = load_validation_report(path)
        digest = _sha256(path)
    except (OSError, ValidationReportError):
        return ValidationStageStatus(
            id="capability",
            state="inconsistent",
            artifact_name=path.name,
            detail="Capability evidence is invalid or unreadable.",
        )
    return ValidationStageStatus(
        id="capability",
        state="passed" if report.successful else "failed",
        artifact_name=path.name,
        artifact_sha256=digest,
        detail=(
            "Capability and behavioral validation passed."
            if report.successful
            else "Capability or behavioral validation failed."
        ),
    )


def _workflow_stage(
    *,
    workflow_path: Path,
    validation_path: Path,
    capability_passed: bool,
) -> ValidationStageStatus:
    if not workflow_path.is_file():
        return _missing(
            "workflows",
            workflow_path.name,
            blocked=not capability_passed,
        )
    if not validation_path.is_file():
        return _missing("workflows", workflow_path.name, blocked=True)
    try:
        report = load_functional_workflow_report(workflow_path)
        verify_functional_workflow_source(report, validation_path)
        digest = _sha256(workflow_path)
    except (
        FunctionalWorkflowEvidenceError,
        OSError,
        ValidationReportError,
    ):
        return ValidationStageStatus(
            id="workflows",
            state="inconsistent",
            artifact_name=workflow_path.name,
            detail="Functional workflow evidence is invalid or source-mismatched.",
        )
    return ValidationStageStatus(
        id="workflows",
        state="passed" if report.qualified_for_candidate_use else "failed",
        artifact_name=workflow_path.name,
        artifact_sha256=digest,
        detail=(
            "Functional workflow qualification passed."
            if report.qualified_for_candidate_use
            else "Functional workflow qualification failed."
        ),
    )


def _privacy_stage(
    *,
    privacy_path: Path,
    validation_path: Path,
    capability_passed: bool,
) -> ValidationStageStatus:
    if not privacy_path.is_file():
        return _missing(
            "privacy",
            privacy_path.name,
            blocked=not capability_passed,
        )
    if not validation_path.is_file():
        return _missing("privacy", privacy_path.name, blocked=True)
    try:
        report = load_runtime_privacy_report(privacy_path)
        verify_runtime_privacy_source(report, validation_path)
        digest = _sha256(privacy_path)
    except (
        OSError,
        RuntimePrivacyEvidenceError,
        ValidationReportError,
    ):
        return ValidationStageStatus(
            id="privacy",
            state="inconsistent",
            artifact_name=privacy_path.name,
            detail="Runtime privacy evidence is invalid or source-mismatched.",
        )
    return ValidationStageStatus(
        id="privacy",
        state="passed" if report.qualified_for_private_inference else "failed",
        artifact_name=privacy_path.name,
        artifact_sha256=digest,
        detail=(
            "Runtime privacy qualification passed."
            if report.qualified_for_private_inference
            else "Runtime privacy qualification failed."
        ),
    )


def _profile_stage(
    *,
    profile_path: Path,
    validation_path: Path,
    privacy_path: Path,
    workflow_path: Path,
    upstream_passed: bool,
) -> ValidationStageStatus:
    if not profile_path.is_file():
        return _missing("profile", profile_path.name, blocked=not upstream_passed)
    if not all(
        path.is_file()
        for path in (validation_path, privacy_path, workflow_path)
    ):
        return _missing("profile", profile_path.name, blocked=True)
    try:
        profile = load_validated_runtime_profile(profile_path)
        verify_validated_runtime_profile(
            profile,
            validation_path=validation_path,
            privacy_path=privacy_path,
            workflow_path=workflow_path,
        )
        digest = _sha256(profile_path)
    except (
        FunctionalWorkflowEvidenceError,
        OSError,
        RuntimePrivacyEvidenceError,
        ValidatedRuntimeProfileError,
        ValidationReportError,
        ValueError,
    ):
        return ValidationStageStatus(
            id="profile",
            state="inconsistent",
            artifact_name=profile_path.name,
            detail="Validated runtime profile is invalid or source-mismatched.",
        )
    return ValidationStageStatus(
        id="profile",
        state="passed",
        artifact_name=profile_path.name,
        artifact_sha256=digest,
        detail="Validated runtime profile verifies against all exact evidence.",
    )


def _next_step(
    *,
    readiness: ValidationStageStatus,
    capability: ValidationStageStatus,
    workflows: ValidationStageStatus,
    privacy: ValidationStageStatus,
    profile: ValidationStageStatus,
) -> ValidationNextStep:
    if readiness.state != "passed":
        return "resolve_readiness"
    if capability.state == "pending":
        return "create_capability_evidence"
    if capability.state != "passed":
        return "replace_candidate_capability"
    if workflows.state == "pending":
        return "create_workflow_evidence"
    if workflows.state != "passed":
        return "fix_workflow_evidence"
    if privacy.state == "pending":
        return "create_privacy_evidence"
    if privacy.state != "passed":
        return "fix_privacy_evidence"
    if profile.state in {"pending", "blocked"}:
        return "create_validated_profile"
    if profile.state != "passed":
        return "recreate_validated_profile"
    return "complete"


def inspect_validation_session(
    session_path: Path,
    *,
    readiness: FirstMachineReadinessReport | None = None,
) -> ValidationSessionStatus:
    """Recompute session state from live readiness and exact immutable artifacts."""

    manifest = load_validation_session(session_path)
    validation_path = _artifact_path(session_path, manifest.artifacts.capability)
    workflow_path = _artifact_path(session_path, manifest.artifacts.workflows)
    privacy_path = _artifact_path(session_path, manifest.artifacts.privacy)
    profile_path = _artifact_path(session_path, manifest.artifacts.profile)

    readiness_stage = _readiness_stage(
        readiness if readiness is not None else collect_first_machine_readiness()
    )
    capability = _capability_stage(validation_path)
    capability_passed = capability.state == "passed"
    workflows = _workflow_stage(
        workflow_path=workflow_path,
        validation_path=validation_path,
        capability_passed=capability_passed,
    )
    privacy = _privacy_stage(
        privacy_path=privacy_path,
        validation_path=validation_path,
        capability_passed=capability_passed,
    )
    profile = _profile_stage(
        profile_path=profile_path,
        validation_path=validation_path,
        privacy_path=privacy_path,
        workflow_path=workflow_path,
        upstream_passed=(
            capability_passed
            and workflows.state == "passed"
            and privacy.state == "passed"
        ),
    )

    next_step = _next_step(
        readiness=readiness_stage,
        capability=capability,
        workflows=workflows,
        privacy=privacy,
        profile=profile,
    )
    return ValidationSessionStatus(
        session_id=manifest.session_id,
        candidate_label=manifest.candidate_label,
        ally_version=manifest.ally_version,
        readiness=readiness_stage,
        capability=capability,
        workflows=workflows,
        privacy=privacy,
        profile=profile,
        next_step=next_step,
        complete=next_step == "complete",
    )
