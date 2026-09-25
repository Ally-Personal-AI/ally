"""Fail-closed final release-readiness evidence for Ally 0.1."""

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
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceEvidenceError,
    load_machine_acceptance_report,
    verify_machine_acceptance_binding,
)
from ally.runtime_profiles import (
    ValidatedRuntimeProfileError,
    load_validated_runtime_profile,
)
from ally.validation_sessions import (
    ValidationSessionError,
    inspect_validation_session,
    load_validation_session,
)

_MAX_REPORT_BYTES = 1024 * 1024


class ReleaseReadinessEvidenceError(ValueError):
    """Raised when final release-readiness evidence cannot be trusted."""


class ReleaseReadinessReport(BaseModel):
    """Path-free binding of candidate and machine acceptance evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    validation_session_id: UUID
    candidate_label: str = Field(min_length=1, max_length=100)
    validation_session_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    privacy_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    workflow_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validated_profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    validated_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    machine_acceptance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_evidence_complete: bool
    machine_acceptance_qualified: bool

    @model_validator(mode="after")
    def validate_report(self) -> ReleaseReadinessReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("release readiness timestamp must include timezone")
        return self

    @property
    def qualified_for_release(self) -> bool:
        return self.candidate_evidence_complete and self.machine_acceptance_qualified


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_stage_digest(
    *,
    stage_id: str,
    state: str,
    artifact_sha256: str | None,
) -> str:
    if state != "passed" or artifact_sha256 is None:
        raise ReleaseReadinessEvidenceError(
            f"{stage_id} evidence is not currently verified and passed"
        )
    return artifact_sha256


def build_release_readiness_report(
    *,
    validation_session_path: Path,
    machine_acceptance_path: Path,
    source_revision: str,
    hardware: HardwareProfile,
    active_profile_id: str,
    active_profile_sha256: str,
    generated_at: datetime | None = None,
    readiness: object | None = None,
) -> ReleaseReadinessReport:
    """Bind exact candidate evidence to exact dedicated-machine acceptance.

    This function has no release, signing, update, publication, or selection
    authority. It only re-verifies existing evidence and produces a path-free
    summary of the exact source artifacts.
    """

    session_path = validation_session_path.expanduser().resolve()
    machine_path = machine_acceptance_path.expanduser().resolve()

    try:
        manifest = load_validation_session(session_path)
        if manifest.ally_version != __version__:
            raise ReleaseReadinessEvidenceError(
                "validation session Ally version does not match the current Ally version"
            )
        status = inspect_validation_session(
            session_path,
            readiness=readiness,  # type: ignore[arg-type]
        )
    except ReleaseReadinessEvidenceError:
        raise
    except (OSError, ValidationSessionError, ValueError) as exc:
        raise ReleaseReadinessEvidenceError(
            "validation session cannot be used for release readiness"
        ) from exc

    if (
        status.session_id != manifest.session_id
        or status.candidate_label != manifest.candidate_label
    ):
        raise ReleaseReadinessEvidenceError(
            "validation session live status does not match its immutable manifest"
        )

    capability_digest = _require_stage_digest(
        stage_id="capability",
        state=status.capability.state,
        artifact_sha256=status.capability.artifact_sha256,
    )
    workflow_digest = _require_stage_digest(
        stage_id="workflow",
        state=status.workflows.state,
        artifact_sha256=status.workflows.artifact_sha256,
    )
    privacy_digest = _require_stage_digest(
        stage_id="privacy",
        state=status.privacy.state,
        artifact_sha256=status.privacy.artifact_sha256,
    )
    profile_digest = _require_stage_digest(
        stage_id="validated profile",
        state=status.profile.state,
        artifact_sha256=status.profile.artifact_sha256,
    )

    profile_path = session_path.parent / manifest.artifacts.profile
    try:
        profile = load_validated_runtime_profile(profile_path)
        actual_profile_digest = _sha256(profile_path)
    except (OSError, ValidatedRuntimeProfileError) as exc:
        raise ReleaseReadinessEvidenceError(
            "validated profile artifact cannot be used for release readiness"
        ) from exc

    if actual_profile_digest != profile_digest:
        raise ReleaseReadinessEvidenceError(
            "validated profile digest does not match validation-session evidence"
        )
    if profile.profile_id != active_profile_id:
        raise ReleaseReadinessEvidenceError(
            "validation-session profile is not the active runtime profile"
        )
    if actual_profile_digest != active_profile_sha256:
        raise ReleaseReadinessEvidenceError(
            "validation-session profile bytes do not match the active selection"
        )
    if profile.ally_version != __version__:
        raise ReleaseReadinessEvidenceError(
            "active validated profile Ally version does not match current Ally"
        )
    if profile.hardware != hardware:
        raise ReleaseReadinessEvidenceError(
            "active validated profile hardware does not match the current machine"
        )

    try:
        machine = load_machine_acceptance_report(machine_path)
        verify_machine_acceptance_binding(
            machine,
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=active_profile_id,
            active_profile_sha256=active_profile_sha256,
        )
        machine_digest = _sha256(machine_path)
        session_digest = _sha256(session_path)
    except (MachineAcceptanceEvidenceError, OSError) as exc:
        raise ReleaseReadinessEvidenceError(
            "machine acceptance cannot be used for release readiness"
        ) from exc

    return ReleaseReadinessReport(
        generated_at=datetime.now(UTC) if generated_at is None else generated_at,
        ally_version=__version__,
        source_revision=source_revision,
        validation_session_id=manifest.session_id,
        candidate_label=manifest.candidate_label,
        validation_session_sha256=session_digest,
        capability_evidence_sha256=capability_digest,
        privacy_evidence_sha256=privacy_digest,
        workflow_evidence_sha256=workflow_digest,
        validated_profile_id=profile.profile_id,
        validated_profile_sha256=actual_profile_digest,
        machine_acceptance_sha256=machine_digest,
        candidate_evidence_complete=status.complete,
        machine_acceptance_qualified=machine.qualified_for_release_acceptance,
    )


def write_release_readiness_report(
    report: ReleaseReadinessReport,
    path: Path,
) -> Path:
    """Atomically publish release-readiness evidence without replacing history."""

    expanded = path.expanduser()
    resolved = expanded.parent.resolve() / expanded.name
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(
            f"refusing to overwrite release readiness report: {resolved}"
        )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, resolved)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite release readiness report: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_release_readiness_report(path: Path) -> ReleaseReadinessReport:
    """Load bounded, strictly versioned release-readiness evidence."""

    expanded = path.expanduser()
    if expanded.is_symlink():
        raise ReleaseReadinessEvidenceError(
            "release readiness report must not be a symlink"
        )
    resolved = expanded.resolve()
    try:
        if resolved.stat().st_size > _MAX_REPORT_BYTES:
            raise ReleaseReadinessEvidenceError(
                "release readiness report exceeds the size limit"
            )
        return ReleaseReadinessReport.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except ReleaseReadinessEvidenceError:
        raise
    except (OSError, UnicodeError, ValidationError) as exc:
        raise ReleaseReadinessEvidenceError(
            "invalid Ally release readiness report"
        ) from exc


def verify_release_readiness_sources(
    report: ReleaseReadinessReport,
    *,
    validation_session_path: Path,
    machine_acceptance_path: Path,
    source_revision: str,
    hardware: HardwareProfile,
    active_profile_id: str,
    active_profile_sha256: str,
    readiness: object | None = None,
) -> ReleaseReadinessReport:
    """Rebuild release readiness from live sources and require an exact match."""

    if report.ally_version != __version__:
        raise ReleaseReadinessEvidenceError(
            "release readiness Ally version does not match current Ally"
        )
    rebuilt = build_release_readiness_report(
        validation_session_path=validation_session_path,
        machine_acceptance_path=machine_acceptance_path,
        source_revision=source_revision,
        hardware=hardware,
        active_profile_id=active_profile_id,
        active_profile_sha256=active_profile_sha256,
        generated_at=report.generated_at,
        readiness=readiness,
    )
    if rebuilt != report:
        raise ReleaseReadinessEvidenceError(
            "release readiness report does not match its current source evidence"
        )
    return rebuilt
