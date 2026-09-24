"""Immutable validated runtime profiles derived from qualified evidence."""

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
from ally.diagnostics.candidates import CandidateEvidence, build_candidate_evidence
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.validation import (
    EvaluationSuiteProfile,
    PerformanceObservations,
    RuntimeProfile,
    load_validation_report,
)
from ally.security.network import is_loopback_http_url

_MAX_PROFILE_BYTES = 4 * 1024 * 1024


class ValidatedRuntimeProfileError(ValueError):
    """Raised when a validated runtime profile cannot be trusted or loaded."""


class EvidenceReference(BaseModel):
    """Path-free identity for one immutable evidence artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_name(self) -> EvidenceReference:
        if (
            self.name != self.name.strip()
            or self.name in {".", ".."}
            or "/" in self.name
            or "\\" in self.name
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in self.name
            )
        ):
            raise ValueError(
                "evidence reference names must be printable leaf filenames"
            )
        return self


class ValidatedRuntimeProfile(BaseModel):
    """One production-eligible local runtime/model profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = 2
    profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=300)
    runtime: RuntimeProfile
    hardware: HardwareProfile
    evaluation_suite: EvaluationSuiteProfile
    observations: PerformanceObservations
    capability_evidence: EvidenceReference
    privacy_evidence: EvidenceReference
    workflow_evidence: EvidenceReference

    @model_validator(mode="after")
    def validate_profile(self) -> ValidatedRuntimeProfile:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("runtime profile timestamp must include a timezone offset")
        if not is_loopback_http_url(self.endpoint):
            raise ValueError("validated private runtime profiles require loopback inference")
        expected = runtime_profile_id(
            ally_version=self.ally_version,
            endpoint=self.endpoint,
            model=self.model,
            runtime=self.runtime,
            hardware=self.hardware,
            evaluation_suite=self.evaluation_suite,
            observations=self.observations,
            capability_evidence=self.capability_evidence,
            privacy_evidence=self.privacy_evidence,
            workflow_evidence=self.workflow_evidence,
        )
        if self.profile_id != expected:
            raise ValueError(
                "runtime profile ID does not match its evidence-backed metadata"
            )
        return self


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_profile_id(
    *,
    ally_version: str,
    endpoint: str,
    model: str,
    runtime: RuntimeProfile,
    hardware: HardwareProfile,
    evaluation_suite: EvaluationSuiteProfile,
    observations: PerformanceObservations,
    capability_evidence: EvidenceReference,
    privacy_evidence: EvidenceReference,
    workflow_evidence: EvidenceReference,
) -> str:
    """Derive identity from exact evidence plus all copied operational metadata."""

    payload = {
        "ally_version": ally_version,
        "endpoint": endpoint,
        "model": model,
        "runtime": runtime.model_dump(mode="json"),
        "hardware": hardware.model_dump(mode="json"),
        "evaluation_suite": evaluation_suite.model_dump(mode="json"),
        "observations": observations.model_dump(mode="json"),
        "capability_evidence": capability_evidence.model_dump(mode="json"),
        "privacy_evidence": privacy_evidence.model_dump(mode="json"),
        "workflow_evidence": workflow_evidence.model_dump(mode="json"),
    }
    rendered = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(b"ally-validated-runtime-profile-v2\0")
    digest.update(rendered)
    return digest.hexdigest()


def _reference(path: Path) -> EvidenceReference:
    resolved = path.expanduser().resolve()
    return EvidenceReference(name=resolved.name, sha256=_sha256(resolved))


def build_validated_runtime_profile(
    *,
    validation_path: Path,
    privacy_path: Path,
    workflow_path: Path,
) -> ValidatedRuntimeProfile:
    """Create a profile only from one fully qualified exact candidate."""

    candidate: CandidateEvidence = build_candidate_evidence(
        validation_path=validation_path,
        privacy_path=privacy_path,
        workflow_path=workflow_path,
    )
    if not candidate.production_eligible:
        raise ValueError(
            "candidate is not production-eligible; capability, privacy, and "
            "functional workflow qualification must all pass"
        )

    validation = load_validation_report(validation_path)
    if validation.ally_version != __version__:
        raise ValueError(
            "validated runtime profiles must be created by the same Ally version "
            "as the source capability report"
        )

    capability = _reference(validation_path)
    privacy = _reference(privacy_path)
    workflow = _reference(workflow_path)

    return ValidatedRuntimeProfile(
        profile_id=runtime_profile_id(
            ally_version=validation.ally_version,
            endpoint=validation.endpoint,
            model=validation.model,
            runtime=validation.runtime,
            hardware=validation.hardware,
            evaluation_suite=validation.evaluation_suite,
            observations=validation.observations,
            capability_evidence=capability,
            privacy_evidence=privacy,
            workflow_evidence=workflow,
        ),
        generated_at=datetime.now(UTC),
        ally_version=validation.ally_version,
        endpoint=validation.endpoint,
        model=validation.model,
        runtime=validation.runtime,
        hardware=validation.hardware,
        evaluation_suite=validation.evaluation_suite,
        observations=validation.observations,
        capability_evidence=capability,
        privacy_evidence=privacy,
        workflow_evidence=workflow,
    )


def write_validated_runtime_profile(
    profile: ValidatedRuntimeProfile,
    path: Path,
) -> Path:
    """Atomically publish a profile without replacing prior qualification."""

    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite runtime profile: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, resolved)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite runtime profile: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_validated_runtime_profile(path: Path) -> ValidatedRuntimeProfile:
    """Load one bounded strict runtime profile."""

    resolved = path.expanduser().resolve()
    try:
        if resolved.stat().st_size > _MAX_PROFILE_BYTES:
            raise ValidatedRuntimeProfileError("runtime profile exceeds the size limit")
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return ValidatedRuntimeProfile.model_validate(raw)
    except ValidatedRuntimeProfileError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValidatedRuntimeProfileError(
            "invalid Ally validated runtime profile"
        ) from exc


def verify_validated_runtime_profile(
    profile: ValidatedRuntimeProfile,
    *,
    validation_path: Path,
    privacy_path: Path,
    workflow_path: Path,
) -> CandidateEvidence:
    """Verify a profile against all exact source evidence and re-qualification."""

    candidate = build_candidate_evidence(
        validation_path=validation_path,
        privacy_path=privacy_path,
        workflow_path=workflow_path,
    )
    if not candidate.production_eligible:
        raise ValidatedRuntimeProfileError(
            "runtime profile source candidate is no longer production-eligible"
        )

    validation = load_validation_report(validation_path)
    expected_references = (
        (profile.capability_evidence, _reference(validation_path)),
        (profile.privacy_evidence, _reference(privacy_path)),
        (profile.workflow_evidence, _reference(workflow_path)),
    )
    if any(expected != actual for expected, actual in expected_references):
        raise ValidatedRuntimeProfileError(
            "runtime profile evidence digest or filename does not match source artifacts"
        )

    if (
        profile.ally_version != validation.ally_version
        or profile.endpoint != validation.endpoint
        or profile.model != validation.model
        or profile.runtime != validation.runtime
        or profile.hardware != validation.hardware
        or profile.evaluation_suite != validation.evaluation_suite
        or profile.observations != validation.observations
    ):
        raise ValidatedRuntimeProfileError(
            "runtime profile metadata does not match source capability evidence"
        )
    return candidate
