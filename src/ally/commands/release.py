"""Read-only release-readiness verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ally import __version__
from ally.diagnostics import collect_hardware_profile
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceEvidenceError,
    load_machine_acceptance_report,
    verify_machine_acceptance_binding,
)
from ally.diagnostics.runtime_privacy import RuntimePrivacyEvidenceError
from ally.diagnostics.validation import ValidationReportError
from ally.diagnostics.workflows import FunctionalWorkflowEvidenceError
from ally.release.readiness import ReleaseReadinessReport
from ally.runtime_profiles import (
    RuntimeProfileCatalogError,
    ValidatedRuntimeProfileError,
    default_runtime_profile_catalog,
    verify_validated_runtime_profile,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_release_readiness(
    *,
    source_revision: str,
    validation_report: str,
    privacy_report: str,
    workflow_report: str,
    machine_acceptance_report: str,
    json_output: bool,
) -> int:
    """Verify the exact active profile and machine evidence required for a tag."""

    catalog = default_runtime_profile_catalog()
    try:
        selection = catalog.selection()
        if selection is None:
            raise RuntimeProfileCatalogError("no active runtime profile is selected")
        profile = catalog.active()
        hardware = collect_hardware_profile()

        if profile.ally_version != __version__:
            raise RuntimeProfileCatalogError(
                "active runtime profile Ally version does not match the current Ally version"
            )
        if profile.hardware != hardware:
            raise RuntimeProfileCatalogError(
                "active runtime profile hardware does not match the current machine"
            )

        candidate = verify_validated_runtime_profile(
            profile,
            validation_path=Path(validation_report),
            privacy_path=Path(privacy_report),
            workflow_path=Path(workflow_report),
        )

        machine_path = Path(machine_acceptance_report)
        machine = load_machine_acceptance_report(machine_path)
        verify_machine_acceptance_binding(
            machine,
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=selection.profile_id,
            active_profile_sha256=selection.profile_sha256,
        )
        machine_digest = _sha256(machine_path.expanduser().resolve())

        report = ReleaseReadinessReport(
            ally_version=__version__,
            source_revision=source_revision,
            active_profile_id=selection.profile_id,
            active_profile_sha256=selection.profile_sha256,
            capability_evidence_sha256=profile.capability_evidence.sha256,
            privacy_evidence_sha256=profile.privacy_evidence.sha256,
            workflow_evidence_sha256=profile.workflow_evidence.sha256,
            machine_acceptance_sha256=machine_digest,
            candidate_production_eligible=candidate.production_eligible,
            machine_acceptance_qualified=machine.qualified_for_release_acceptance,
        )
    except (
        FunctionalWorkflowEvidenceError,
        MachineAcceptanceEvidenceError,
        OSError,
        RuntimePrivacyEvidenceError,
        RuntimeProfileCatalogError,
        ValidatedRuntimeProfileError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Release readiness error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["ready_for_tagged_prerelease"] = report.ready_for_tagged_prerelease
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Ally version: {report.ally_version}")
        print(f"Source revision: {report.source_revision}")
        print(f"Active profile: {report.active_profile_id}")
        print(
            "Candidate production eligible: "
            + ("yes" if report.candidate_production_eligible else "no")
        )
        print(
            "Machine acceptance qualified: "
            + ("yes" if report.machine_acceptance_qualified else "no")
        )
        print(
            "Ready for tagged pre-release: "
            + ("yes" if report.ready_for_tagged_prerelease else "no")
        )
    return 0 if report.ready_for_tagged_prerelease else 1
