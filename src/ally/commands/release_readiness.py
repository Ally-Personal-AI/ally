"""Commands for final Ally release-readiness evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ally import __version__
from ally.diagnostics import HardwareProfile, collect_hardware_profile
from ally.diagnostics.release_readiness import (
    ReleaseReadinessEvidenceError,
    ReleaseReadinessReport,
    build_release_readiness_report,
    load_release_readiness_report,
    verify_release_readiness_sources,
    write_release_readiness_report,
)
from ally.runtime_profiles import RuntimeProfileCatalogError, default_runtime_profile_catalog


def _active_profile_binding(hardware: HardwareProfile) -> tuple[str, str]:
    catalog = default_runtime_profile_catalog()
    selection = catalog.selection()
    if selection is None:
        raise RuntimeProfileCatalogError("no active runtime profile is selected")
    profile = catalog.active()
    if profile.profile_id != selection.profile_id:
        raise RuntimeProfileCatalogError(
            "active runtime profile selection is inconsistent"
        )
    if profile.ally_version != __version__:
        raise RuntimeProfileCatalogError(
            "active runtime profile Ally version does not match current Ally"
        )
    if profile.hardware != hardware:
        raise RuntimeProfileCatalogError(
            "active runtime profile hardware does not match current machine"
        )
    return selection.profile_id, selection.profile_sha256


def _render(report: ReleaseReadinessReport) -> None:
    print(f"Ally version: {report.ally_version}")
    print(f"Source revision: {report.source_revision}")
    print(f"Candidate: {report.candidate_label}")
    print(f"Active profile: {report.validated_profile_id}")
    print(
        "Candidate evidence complete: "
        + ("yes" if report.candidate_evidence_complete else "no")
    )
    print(
        "Machine acceptance qualified: "
        + ("yes" if report.machine_acceptance_qualified else "no")
    )
    print(
        "Qualified for release: "
        + ("yes" if report.qualified_for_release else "no")
    )


def run_create_release_readiness(
    *,
    validation_session: str,
    machine_acceptance: str,
    source_revision: str,
    output: str,
    json_output: bool,
) -> int:
    """Create an immutable binding of candidate and machine evidence."""

    try:
        hardware = collect_hardware_profile()
        profile_id, profile_sha256 = _active_profile_binding(hardware)
        report = build_release_readiness_report(
            validation_session_path=Path(validation_session),
            machine_acceptance_path=Path(machine_acceptance),
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=profile_id,
            active_profile_sha256=profile_sha256,
        )
        destination = write_release_readiness_report(report, Path(output))
    except (
        FileExistsError,
        OSError,
        ReleaseReadinessEvidenceError,
        RuntimeProfileCatalogError,
        ValueError,
    ) as exc:
        print(f"Release readiness error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["report_path"] = str(destination)
        rendered["qualified_for_release"] = report.qualified_for_release
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Release readiness report: {destination}")
        _render(report)
    return 0


def run_show_release_readiness(*, report_path: str, json_output: bool) -> int:
    """Inspect one release-readiness artifact without asserting live sources."""

    try:
        report = load_release_readiness_report(Path(report_path))
    except ReleaseReadinessEvidenceError as exc:
        print(f"Release readiness error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["qualified_for_release"] = report.qualified_for_release
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        _render(report)
    return 0


def run_verify_release_readiness(
    *,
    report_path: str,
    validation_session: str,
    machine_acceptance: str,
    source_revision: str,
    json_output: bool,
) -> int:
    """Re-verify final readiness against every current source boundary."""

    try:
        report = load_release_readiness_report(Path(report_path))
        hardware = collect_hardware_profile()
        profile_id, profile_sha256 = _active_profile_binding(hardware)
        verified = verify_release_readiness_sources(
            report,
            validation_session_path=Path(validation_session),
            machine_acceptance_path=Path(machine_acceptance),
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=profile_id,
            active_profile_sha256=profile_sha256,
        )
    except (
        ReleaseReadinessEvidenceError,
        RuntimeProfileCatalogError,
    ) as exc:
        print(f"Release readiness verification error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "verified": True,
                    "qualified_for_release": verified.qualified_for_release,
                    "candidate_label": verified.candidate_label,
                    "validated_profile_id": verified.validated_profile_id,
                    "source_revision": verified.source_revision,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Verified sources: yes")
        _render(verified)
    return 0 if verified.qualified_for_release else 1
