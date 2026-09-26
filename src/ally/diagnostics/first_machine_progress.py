"""Read-only progress inspection for the dedicated-machine Ally handoff."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ally import __version__
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceChecks,
    MachineAcceptanceEvidenceError,
    load_machine_acceptance_report,
    verify_machine_acceptance_binding,
)
from ally.diagnostics.readiness import (
    FirstMachineReadinessReport,
    collect_first_machine_readiness,
)
from ally.runtime_profiles import (
    RuntimeProfileCatalogError,
    ValidatedRuntimeProfileError,
    default_runtime_profile_catalog,
    load_validated_runtime_profile,
)
from ally.validation_sessions import (
    ValidationSessionError,
    ValidationSessionStatus,
    inspect_validation_session,
    load_validation_session,
)

FirstMachineProgressState = Literal[
    "passed",
    "pending",
    "failed",
    "inconsistent",
    "blocked",
]
FirstMachineProgressNextStep = Literal[
    "resolve_readiness",
    "initialize_validation_session",
    "continue_candidate_validation",
    "select_validated_profile",
    "record_machine_acceptance",
    "complete_machine_acceptance",
    "create_release_readiness",
]


class FirstMachineProgressStage(BaseModel):
    """One derived stage in the first-machine acceptance handoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    state: FirstMachineProgressState
    detail: str = Field(min_length=1, max_length=400)


class FirstMachineProgressReport(BaseModel):
    """Read-only handoff state composed from existing evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    readiness: FirstMachineProgressStage
    candidate: FirstMachineProgressStage
    active_profile: FirstMachineProgressStage
    machine_acceptance: FirstMachineProgressStage
    next_step: FirstMachineProgressNextStep
    candidate_label: str | None = Field(default=None, max_length=100)
    candidate_next_step: str | None = Field(default=None, max_length=100)
    active_profile_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    machine_checks: MachineAcceptanceChecks | None = None


class FirstMachineProgressError(ValueError):
    """Raised when progress sources are invalid or cannot be inspected safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stage(
    stage_id: str,
    state: FirstMachineProgressState,
    detail: str,
) -> FirstMachineProgressStage:
    return FirstMachineProgressStage(
        id=stage_id,
        state=state,
        detail=detail,
    )


def _candidate_stage(
    status: ValidationSessionStatus | None,
) -> FirstMachineProgressStage:
    if status is None:
        return _stage(
            "candidate",
            "pending",
            "No validation session was supplied.",
        )
    if status.complete:
        return _stage(
            "candidate",
            "passed",
            "Capability, workflows, privacy, and validated profile evidence all verify.",
        )

    states = (
        status.capability.state,
        status.workflows.state,
        status.privacy.state,
        status.profile.state,
    )
    if "inconsistent" in states:
        state: FirstMachineProgressState = "inconsistent"
    elif "failed" in states:
        state = "failed"
    elif status.readiness.state != "passed":
        state = "blocked"
    else:
        state = "pending"
    return _stage(
        "candidate",
        state,
        f"Candidate validation is incomplete; session next step is {status.next_step}.",
    )


def _next_step(
    *,
    readiness: FirstMachineProgressStage,
    candidate: FirstMachineProgressStage,
    active_profile: FirstMachineProgressStage,
    machine_acceptance: FirstMachineProgressStage,
    session_supplied: bool,
    machine_acceptance_supplied: bool,
) -> FirstMachineProgressNextStep:
    if readiness.state != "passed":
        return "resolve_readiness"
    if not session_supplied:
        return "initialize_validation_session"
    if candidate.state != "passed":
        return "continue_candidate_validation"
    if active_profile.state != "passed":
        return "select_validated_profile"
    if not machine_acceptance_supplied:
        return "record_machine_acceptance"
    if machine_acceptance.state != "passed":
        return "complete_machine_acceptance"
    return "create_release_readiness"


def collect_first_machine_progress(
    *,
    source_revision: str,
    validation_session_path: Path | None = None,
    machine_acceptance_path: Path | None = None,
    readiness: FirstMachineReadinessReport | None = None,
    active_profile_binding: tuple[str, str] | None = None,
) -> FirstMachineProgressReport:
    """Derive the next handoff gate without mutating Ally or empirical evidence."""

    if len(source_revision) != 40 or any(
        character not in "0123456789abcdef" for character in source_revision
    ):
        raise FirstMachineProgressError(
            "source revision must be a 40-character lowercase Git SHA"
        )

    readiness_report = readiness or collect_first_machine_readiness()
    readiness_stage = _stage(
        "readiness",
        "passed" if readiness_report.ready_to_begin_validation else "failed",
        (
            "Read-only first-machine readiness has no blocking errors."
            if readiness_report.ready_to_begin_validation
            else "Read-only first-machine readiness has blocking errors."
        ),
    )

    session_status: ValidationSessionStatus | None = None
    session_profile_id: str | None = None
    session_profile_sha256: str | None = None

    if validation_session_path is not None:
        try:
            session_path = validation_session_path.expanduser().resolve()
            session_status = inspect_validation_session(
                session_path,
                readiness=readiness_report,
            )
            if session_status.complete:
                manifest = load_validation_session(session_path)
                profile_path = session_path.parent / manifest.artifacts.profile
                profile = load_validated_runtime_profile(profile_path)
                if profile.hardware != readiness_report.hardware:
                    raise FirstMachineProgressError(
                        "candidate validated profile hardware does not match the current machine"
                    )
                if profile.ally_version != __version__:
                    raise FirstMachineProgressError(
                        "candidate validated profile Ally version does not match current Ally"
                    )
                session_profile_id = profile.profile_id
                session_profile_sha256 = _sha256(profile_path)
        except FirstMachineProgressError:
            raise
        except (
            OSError,
            ValidationSessionError,
            ValidatedRuntimeProfileError,
            ValueError,
        ) as exc:
            raise FirstMachineProgressError(
                "validation session cannot be inspected safely"
            ) from exc

    candidate_stage = _candidate_stage(session_status)

    binding = active_profile_binding
    binding_error: str | None = None
    if binding is None:
        try:
            catalog = default_runtime_profile_catalog()
            selection = catalog.selection()
            if selection is not None:
                profile = catalog.active()
                if profile.profile_id != selection.profile_id:
                    raise RuntimeProfileCatalogError(
                        "active profile selection is inconsistent"
                    )
                if profile.ally_version != __version__:
                    raise RuntimeProfileCatalogError(
                        "active profile Ally version does not match current Ally"
                    )
                if profile.hardware != readiness_report.hardware:
                    raise RuntimeProfileCatalogError(
                        "active profile hardware does not match current machine"
                    )
                binding = (selection.profile_id, selection.profile_sha256)
        except (OSError, RuntimeProfileCatalogError, ValueError):
            binding_error = "Active runtime profile state is invalid or inconsistent."

    if candidate_stage.state != "passed":
        active_profile_stage = _stage(
            "active_profile",
            "blocked",
            "A qualified candidate profile is required before production selection.",
        )
    elif binding_error is not None:
        active_profile_stage = _stage(
            "active_profile",
            "inconsistent",
            binding_error,
        )
    elif binding is None:
        active_profile_stage = _stage(
            "active_profile",
            "pending",
            "The candidate profile is qualified but no validated runtime profile is active.",
        )
    elif (
        binding[0] != session_profile_id
        or binding[1] != session_profile_sha256
    ):
        active_profile_stage = _stage(
            "active_profile",
            "inconsistent",
            "The active runtime profile does not match the exact candidate session profile.",
        )
    else:
        active_profile_stage = _stage(
            "active_profile",
            "passed",
            "The exact candidate validated profile is active and bound to this machine.",
        )

    machine_checks: MachineAcceptanceChecks | None = None
    if active_profile_stage.state != "passed":
        machine_stage = _stage(
            "machine_acceptance",
            "blocked",
            "Machine acceptance requires the exact qualified candidate profile to be active.",
        )
    elif machine_acceptance_path is None:
        machine_stage = _stage(
            "machine_acceptance",
            "pending",
            "No immutable machine-acceptance artifact was supplied.",
        )
    else:
        assert binding is not None
        try:
            machine = load_machine_acceptance_report(
                machine_acceptance_path.expanduser().resolve()
            )
            verify_machine_acceptance_binding(
                machine,
                source_revision=source_revision,
                hardware=readiness_report.hardware,
                active_profile_id=binding[0],
                active_profile_sha256=binding[1],
            )
        except (MachineAcceptanceEvidenceError, OSError, ValueError) as exc:
            machine_stage = _stage(
                "machine_acceptance",
                "inconsistent",
                "Machine-acceptance evidence does not match the current source, machine, or active profile.",
            )
        else:
            machine_checks = machine.checks
            values = tuple(machine.checks.model_dump(mode="python").values())
            if machine.qualified_for_release_acceptance:
                machine_stage = _stage(
                    "machine_acceptance",
                    "passed",
                    "Every explicit empirical machine-acceptance gate is recorded as passed.",
                )
            elif "fail" in values:
                machine_stage = _stage(
                    "machine_acceptance",
                    "failed",
                    "At least one explicit empirical machine-acceptance gate is recorded as failed.",
                )
            else:
                machine_stage = _stage(
                    "machine_acceptance",
                    "pending",
                    "Machine-acceptance evidence is bound correctly but still contains not-run gates.",
                )

    next_step = _next_step(
        readiness=readiness_stage,
        candidate=candidate_stage,
        active_profile=active_profile_stage,
        machine_acceptance=machine_stage,
        session_supplied=validation_session_path is not None,
        machine_acceptance_supplied=machine_acceptance_path is not None,
    )

    return FirstMachineProgressReport(
        readiness=readiness_stage,
        candidate=candidate_stage,
        active_profile=active_profile_stage,
        machine_acceptance=machine_stage,
        next_step=next_step,
        candidate_label=(
            None if session_status is None else session_status.candidate_label
        ),
        candidate_next_step=(
            None if session_status is None else session_status.next_step
        ),
        active_profile_id=(None if binding is None else binding[0]),
        machine_checks=machine_checks,
    )
