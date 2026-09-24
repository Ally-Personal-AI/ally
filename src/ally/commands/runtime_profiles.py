"""Commands for immutable validated runtime profiles."""

from __future__ import annotations

import json
from pathlib import Path

from ally.diagnostics.candidates import CandidateEvidence
from ally.diagnostics.runtime_privacy import RuntimePrivacyEvidenceError
from ally.diagnostics.validation import ValidationReportError
from ally.diagnostics.workflows import FunctionalWorkflowEvidenceError
from ally.runtime_profiles import (
    RuntimeProfileCatalogError,
    ValidatedRuntimeProfile,
    ValidatedRuntimeProfileError,
    build_validated_runtime_profile,
    default_runtime_profile_catalog,
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


def run_install_runtime_profile(
    *,
    profile_path: str,
    validation_report: str,
    privacy_report: str,
    workflow_report: str,
    json_output: bool,
) -> int:
    """Install one fully re-verified profile into Ally-owned config state."""

    catalog = default_runtime_profile_catalog()
    try:
        destination = catalog.install(
            profile_path=Path(profile_path),
            validation_path=Path(validation_report),
            privacy_path=Path(privacy_report),
            workflow_path=Path(workflow_report),
        )
        profile = catalog.get(destination.stem)
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "installed": True,
                    "profile_id": profile.profile_id,
                    "model": profile.model,
                    "runtime": profile.runtime.name,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Installed profile: {profile.profile_id}")
        print(f"Runtime: {profile.runtime.name} {profile.runtime.version}")
        print(f"Model: {profile.model}")
    return 0


def run_list_runtime_profiles(*, json_output: bool) -> int:
    """List installed validated runtime profiles without contacting a model."""

    catalog = default_runtime_profile_catalog()
    try:
        profiles = catalog.list()
        selection = catalog.selection()
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2

    active_id = None if selection is None else selection.profile_id
    if json_output:
        print(
            json.dumps(
                {
                    "active_profile_id": active_id,
                    "profiles": [
                        {
                            "profile_id": profile.profile_id,
                            "model": profile.model,
                            "runtime": profile.runtime.name,
                            "runtime_version": profile.runtime.version,
                            "active": profile.profile_id == active_id,
                        }
                        for profile in profiles
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if not profiles:
        print("No installed runtime profiles.")
        return 0
    for profile in profiles:
        marker = "*" if profile.profile_id == active_id else " "
        print(
            f"{marker} {profile.profile_id}  "
            f"{profile.runtime.name} {profile.runtime.version}  {profile.model}"
        )
    return 0


def run_select_runtime_profile(*, profile_id: str, json_output: bool) -> int:
    """Select one installed validated runtime profile."""

    catalog = default_runtime_profile_catalog()
    try:
        selection = catalog.select(profile_id)
        profile = catalog.active()
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "selected": True,
                    "profile_id": selection.profile_id,
                    "profile_sha256": selection.profile_sha256,
                    "model": profile.model,
                    "runtime": profile.runtime.name,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"Selected profile: {selection.profile_id}")
        print(f"Runtime: {profile.runtime.name} {profile.runtime.version}")
        print(f"Model: {profile.model}")
    return 0


def run_active_runtime_profile(*, json_output: bool) -> int:
    """Resolve and inspect the exact active installed profile."""

    catalog = default_runtime_profile_catalog()
    try:
        profile = catalog.active()
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2

    if json_output:
        print(json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"Profile ID: {profile.profile_id}")
        print(f"Runtime: {profile.runtime.name} {profile.runtime.version}")
        print(f"Model: {profile.model}")
        print(f"Endpoint: {profile.endpoint}")
    return 0


def run_deselect_runtime_profile() -> int:
    """Clear active profile selection without deleting installed profiles."""

    catalog = default_runtime_profile_catalog()
    try:
        changed = catalog.deselect()
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2
    print("Runtime profile selection cleared." if changed else "No active runtime profile.")
    return 0


def run_remove_runtime_profile(*, profile_id: str) -> int:
    """Remove one inactive installed runtime profile."""

    catalog = default_runtime_profile_catalog()
    try:
        removed = catalog.remove(profile_id)
    except RuntimeProfileCatalogError as exc:
        print(f"Runtime profile catalog error: {exc}")
        return 2
    print("Runtime profile removed." if removed else "Runtime profile not installed.")
    return 0
