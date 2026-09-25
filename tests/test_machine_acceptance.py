from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import ally.diagnostics.machine_acceptance as acceptance
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceChecks,
    MachineAcceptanceEvidenceError,
    MachineAcceptanceStatus,
    build_machine_acceptance_report,
    load_machine_acceptance_report,
    verify_machine_acceptance_binding,
    write_machine_acceptance_report,
)


def _hardware(*, release: str = "26.0") -> HardwareProfile:
    return HardwareProfile(
        system="Darwin",
        release=release,
        machine="arm64",
        processor="arm",
        python_version="3.12.14",
        logical_cpu_count=16,
        total_memory_bytes=64 * 1024**3,
        apple_model="Mac16,5",
        apple_chip="Apple M5 Max",
    )


def _checks(*, notification_status: MachineAcceptanceStatus = "pass") -> MachineAcceptanceChecks:
    return MachineAcceptanceChecks(
        keychain="pass",
        recovery="pass",
        background_service="pass",
        notifications=notification_status,
        signed_release="pass",
        update_preparation="pass",
        app_replacement="pass",
        integrated_daily_use="pass",
    )


def _report(
    *,
    checks: MachineAcceptanceChecks | None = None,
    hardware: HardwareProfile | None = None,
) -> acceptance.MachineAcceptanceReport:
    return build_machine_acceptance_report(
        source_revision="a" * 40,
        hardware=hardware or _hardware(),
        active_profile_id="b" * 64,
        active_profile_sha256="c" * 64,
        checks=checks or _checks(),
        generated_at=datetime(2026, 9, 25, 3, 0, tzinfo=UTC),
    )


def test_complete_machine_acceptance_is_release_qualified() -> None:
    report = _report()

    assert report.qualified_for_release_acceptance is True
    assert report.checks.complete is True


def test_failed_or_not_run_gate_blocks_release_acceptance() -> None:
    failed = _report(
        checks=MachineAcceptanceChecks(
            keychain="pass",
            recovery="pass",
            background_service="pass",
            notifications="fail",
            signed_release="pass",
            update_preparation="pass",
            app_replacement="pass",
            integrated_daily_use="pass",
        )
    )
    pending = _report(
        checks=MachineAcceptanceChecks(
            keychain="pass",
            recovery="pass",
            background_service="pass",
            notifications="not_run",
            signed_release="pass",
            update_preparation="pass",
            app_replacement="pass",
            integrated_daily_use="pass",
        )
    )

    assert failed.qualified_for_release_acceptance is False
    assert pending.qualified_for_release_acceptance is False


def test_machine_acceptance_round_trip_is_strict_and_immutable(tmp_path: Path) -> None:
    path = tmp_path / "machine-acceptance.json"
    report = _report()

    write_machine_acceptance_report(report, path)
    assert load_machine_acceptance_report(path) == report

    with pytest.raises(FileExistsError, match="overwrite"):
        write_machine_acceptance_report(report, path)


def test_machine_acceptance_binding_requires_exact_current_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _report()
    monkeypatch.setattr(acceptance, "__version__", report.ally_version)

    verify_machine_acceptance_binding(
        report,
        source_revision="a" * 40,
        hardware=_hardware(),
        active_profile_id="b" * 64,
        active_profile_sha256="c" * 64,
    )

    with pytest.raises(MachineAcceptanceEvidenceError, match="source revision"):
        verify_machine_acceptance_binding(
            report,
            source_revision="d" * 40,
            hardware=_hardware(),
            active_profile_id="b" * 64,
            active_profile_sha256="c" * 64,
        )

    with pytest.raises(MachineAcceptanceEvidenceError, match="hardware"):
        verify_machine_acceptance_binding(
            report,
            source_revision="a" * 40,
            hardware=_hardware(release="27.0"),
            active_profile_id="b" * 64,
            active_profile_sha256="c" * 64,
        )

    with pytest.raises(MachineAcceptanceEvidenceError, match="runtime profile"):
        verify_machine_acceptance_binding(
            report,
            source_revision="a" * 40,
            hardware=_hardware(),
            active_profile_id="d" * 64,
            active_profile_sha256="c" * 64,
        )


def test_machine_acceptance_rejects_malformed_evidence(tmp_path: Path) -> None:
    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version": 99}\n', encoding="utf-8")

    with pytest.raises(MachineAcceptanceEvidenceError, match="invalid"):
        load_machine_acceptance_report(path)


def test_machine_acceptance_rejects_symlink_artifact(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    write_machine_acceptance_report(_report(), target)
    link = tmp_path / "linked.json"
    link.symlink_to(target)

    with pytest.raises(MachineAcceptanceEvidenceError, match="symlink"):
        load_machine_acceptance_report(link)

    occupied = tmp_path / "occupied.json"
    occupied.symlink_to(tmp_path / "missing.json")
    with pytest.raises(FileExistsError, match="overwrite"):
        write_machine_acceptance_report(_report(), occupied)
