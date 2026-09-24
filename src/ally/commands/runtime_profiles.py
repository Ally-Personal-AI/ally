"""Commands for immutable validated runtime profiles."""

from __future__ import annotations

import json
from pathlib import Path

from ally.diagnostics.candidates import CandidateEvidence
from ally.diagnostics.runtime_privacy import RuntimePrivacyEvidenceError
from ally.diagnostics.validation import ValidationReportError
from ally.diagnostics.workflows import FunctionalWorkflowEvidenceError
from ally.runtime_profiles import (
    ValidatedRuntimeProfile,
    ValidatedRuntimeProfileError,
    build_validated_runtime_profile,
    load_validated_runtime_profile,
    verify_validated_runtime_profile,
    write_validated_runtime_profile,
)


def run_create_runtime_profile(
    *,
    validation_report: str,
    privacy_report: str,
    workflow_report: str,
    output: str,
    json_output: bool,
) -> int:
    """Create one immutable approved runtime profile from exact qualified evidence."""

    try:
        profile = build_validated_runtime_profile(
            validation_path=Path(validation_report),
            privacy_path=Path(privacy_report),
            workflow_path=Path(workflow_report),
        )
        destination = write_validated_runtime_profile(profile, Path(output))
    except (
        FileExistsError,
        FunctionalWorkflowEvidenceError,
        OSError,
        RuntimePrivacyEvidenceError,
        ValidatedRuntimeProfileError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Runtime profile error: {exc}")
        return 2

    if json_output:
        rendered = profile.model_dump(mode="json")
        rendered["profile_path"] = str(destination)
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Runtime profile: {destination}")
        print(f"Profile ID: {profile.profile_id}")
        print(f"Runtime: {profile.runtime.name} {profile.runtime.version}")
        print(f"Model: {profile.model}")
        print(f"Endpoint: {profile.endpoint}")
    return 0


def run_show_runtime_profile(
    *,
    profile_path: str,
    json_output: bool,
) -> int:
    """Inspect one validated runtime profile."""

    try:
        profile: ValidatedRuntimeProfile = load_validated_runtime_profile(
            Path(profile_path)
        )
    except ValidatedRuntimeProfileError as exc:
        print(f"Runtime profile error: {exc}")
        return 2

    if json_output:
        print(json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"Profile ID: {profile.profile_id}")
        print(f"Ally version: {profile.ally_version}")
        print(f"Runtime: {profile.runtime.name} {profile.runtime.version}")
        print(f"Model: {profile.model}")
        print(f"Endpoint: {profile.endpoint}")
        print(f"Hardware: {profile.hardware.system} {profile.hardware.machine}")
        print(f"Capability evidence: {profile.capability_evidence.name}")
        print(f"Privacy evidence: {profile.privacy_evidence.name}")
        print(f"Workflow evidence: {profile.workflow_evidence.name}")
    return 0


def run_verify_runtime_profile(
    *,
    profile_path: str,
    validation_report: str,
    privacy_report: str,
    workflow_report: str,
    json_output: bool,
) -> int:
    """Re-verify a profile against all exact source artifacts."""

    try:
        profile = load_validated_runtime_profile(Path(profile_path))
        candidate: CandidateEvidence = verify_validated_runtime_profile(
            profile,
            validation_path=Path(validation_report),
            privacy_path=Path(privacy_report),
            workflow_path=Path(workflow_report),
        )
    except (
        FunctionalWorkflowEvidenceError,
        RuntimePrivacyEvidenceError,
        ValidatedRuntimeProfileError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Runtime profile verification error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "verified": True,
                    "profile_id": profile.profile_id,
                    "production_eligible": candidate.production_eligible,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Verified: yes")
        print(f"Profile ID: {profile.profile_id}")
        print("Production eligible: yes")
    return 0
