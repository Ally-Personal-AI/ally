"""Commands for dedicated-machine acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path

from ally import __version__
from ally.diagnostics import HardwareProfile, collect_hardware_profile
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceChecks,
    MachineAcceptanceEvidenceError,
    MachineAcceptanceReport,
    MachineAcceptanceStatus,
    build_machine_acceptance_report,
    load_machine_acceptance_report,
    verify_machine_acceptance_binding,
    write_machine_acceptance_report,
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
            "active runtime profile Ally version does not match the current Ally version"
        )
    if profile.hardware != hardware:
        raise RuntimeProfileCatalogError(
            "active runtime profile hardware does not match the current machine"
        )
    return selection.profile_id, selection.profile_sha256


def _render(report: MachineAcceptanceReport) -> None:
    print(f"Ally version: {report.ally_version}")
    print(f"Source revision: {report.source_revision}")
    print(f"Active profile: {report.active_profile_id}")
    for name, status in report.checks.model_dump(mode="python").items():
        print(f"{name}: {status}")
    print(
        "Qualified for release acceptance: "
        + ("yes" if report.qualified_for_release_acceptance else "no")
    )


def run_create_machine_acceptance(
    *,
    source_revision: str,
    output: str,
    keychain: MachineAcceptanceStatus,
    recovery: MachineAcceptanceStatus,
    background_service: MachineAcceptanceStatus,
    notifications: MachineAcceptanceStatus,
    signed_release: MachineAcceptanceStatus,
    update_preparation: MachineAcceptanceStatus,
    app_replacement: MachineAcceptanceStatus,
    integrated_daily_use: MachineAcceptanceStatus,
    json_output: bool,
) -> int:
    """Create immutable payload-free evidence from explicit machine observations."""

    try:
        hardware = collect_hardware_profile()
        profile_id, profile_sha256 = _active_profile_binding(hardware)
        report = build_machine_acceptance_report(
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=profile_id,
            active_profile_sha256=profile_sha256,
            checks=MachineAcceptanceChecks(
                keychain=keychain,
                recovery=recovery,
                background_service=background_service,
                notifications=notifications,
                signed_release=signed_release,
                update_preparation=update_preparation,
                app_replacement=app_replacement,
                integrated_daily_use=integrated_daily_use,
            ),
        )
        destination = write_machine_acceptance_report(report, Path(output))
    except (
        FileExistsError,
        MachineAcceptanceEvidenceError,
        OSError,
        RuntimeProfileCatalogError,
        ValueError,
    ) as exc:
        print(f"Machine acceptance error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["report_path"] = str(destination)
        rendered["qualified_for_release_acceptance"] = (
            report.qualified_for_release_acceptance
        )
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Machine acceptance report: {destination}")
        _render(report)
    return 0


def run_show_machine_acceptance(*, report_path: str, json_output: bool) -> int:
    """Inspect one machine acceptance artifact without asserting current binding."""

    try:
        report = load_machine_acceptance_report(Path(report_path))
    except MachineAcceptanceEvidenceError as exc:
        print(f"Machine acceptance error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["qualified_for_release_acceptance"] = (
            report.qualified_for_release_acceptance
        )
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        _render(report)
    return 0


def run_verify_machine_acceptance(
    *,
    report_path: str,
    source_revision: str,
    json_output: bool,
) -> int:
    """Re-verify acceptance against the current Ally/machine/active-profile state."""

    try:
        report = load_machine_acceptance_report(Path(report_path))
        hardware = collect_hardware_profile()
        profile_id, profile_sha256 = _active_profile_binding(hardware)
        verify_machine_acceptance_binding(
            report,
            source_revision=source_revision,
            hardware=hardware,
            active_profile_id=profile_id,
            active_profile_sha256=profile_sha256,
        )
    except (
        MachineAcceptanceEvidenceError,
        RuntimeProfileCatalogError,
    ) as exc:
        print(f"Machine acceptance verification error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "verified": True,
                    "qualified_for_release_acceptance": (
                        report.qualified_for_release_acceptance
                    ),
                    "active_profile_id": report.active_profile_id,
                    "source_revision": report.source_revision,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Verified binding: yes")
        _render(report)
    return 0 if report.qualified_for_release_acceptance else 1
