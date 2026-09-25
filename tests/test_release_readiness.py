from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

import ally.diagnostics.release_readiness as release_readiness
from ally import __version__
from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.machine_acceptance import (
    MachineAcceptanceChecks,
    build_machine_acceptance_report,
    write_machine_acceptance_report,
)
from ally.diagnostics.release_readiness import (
    ReleaseReadinessEvidenceError,
    build_release_readiness_report,
    load_release_readiness_report,
    verify_release_readiness_sources,
    write_release_readiness_report,
)
from ally.validation_sessions import (
    ValidationArtifactPlan,
    ValidationSessionManifest,
    ValidationSessionStatus,
    ValidationStageStatus,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hardware() -> HardwareProfile:
    return HardwareProfile(
        system="Darwin",
        release="26.0",
        machine="arm64",
        processor="arm",
        python_version="3.12.14",
        logical_cpu_count=16,
        total_memory_bytes=64 * 1024**3,
        apple_model="Mac16,5",
        apple_chip="Apple M5 Max",
    )


def _passed_stage(stage_id: str, artifact: Path) -> ValidationStageStatus:
    return ValidationStageStatus(
        id=stage_id,
        state="passed",
        artifact_name=artifact.name,
        artifact_sha256=_sha256(artifact),
        detail=f"{stage_id} passed.",
    )


def _machine_checks(*, notifications: str = "pass") -> MachineAcceptanceChecks:
    return MachineAcceptanceChecks.model_validate(
        {
            "keychain": "pass",
            "recovery": "pass",
            "background_service": "pass",
            "notifications": notifications,
            "signed_release": "pass",
            "update_preparation": "pass",
            "app_replacement": "pass",
            "integrated_daily_use": "pass",
        }
    )


def _sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    readiness_passed: bool = True,
    machine_notifications: str = "pass",
) -> tuple[
    Path,
    Path,
    HardwareProfile,
    str,
    str,
    dict[str, ValidationSessionStatus],
]:
    session_id = UUID("00000000-0000-0000-0000-000000000125")
    session_path = tmp_path / "session.json"
    artifacts = ValidationArtifactPlan()
    manifest = ValidationSessionManifest(
        session_id=session_id,
        created_at=datetime(2026, 9, 25, 3, 30, tzinfo=UTC),
        ally_version=__version__,
        candidate_label="synthetic-candidate",
        artifacts=artifacts,
    )
    session_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    capability = tmp_path / artifacts.capability
    privacy = tmp_path / artifacts.privacy
    workflows = tmp_path / artifacts.workflows
    profile = tmp_path / artifacts.profile
    capability.write_bytes(b"qualified-capability")
    privacy.write_bytes(b"qualified-privacy")
    workflows.write_bytes(b"qualified-workflows")
    profile.write_bytes(b"qualified-profile")

    readiness_stage = ValidationStageStatus(
        id="readiness",
        state="passed" if readiness_passed else "failed",
        detail=(
            "Readiness passed."
            if readiness_passed
            else "Readiness has blocking errors."
        ),
    )
    status = ValidationSessionStatus(
        session_id=session_id,
        candidate_label="synthetic-candidate",
        ally_version=__version__,
        readiness=readiness_stage,
        capability=_passed_stage("capability", capability),
        workflows=_passed_stage("workflows", workflows),
        privacy=_passed_stage("privacy", privacy),
        profile=_passed_stage("profile", profile),
        next_step="complete" if readiness_passed else "resolve_readiness",
        complete=readiness_passed,
    )
    status_holder = {"status": status}

    def fake_inspect(
        _path: Path,
        *,
        readiness: object | None = None,
    ) -> ValidationSessionStatus:
        del readiness
        return status_holder["status"]

    hardware = _hardware()
    active_profile_id = "b" * 64
    active_profile_sha256 = _sha256(profile)

    def fake_load_profile(_path: Path) -> Any:
        return SimpleNamespace(
            profile_id=active_profile_id,
            ally_version=__version__,
            hardware=hardware,
        )

    monkeypatch.setattr(
        release_readiness,
        "inspect_validation_session",
        fake_inspect,
    )
    monkeypatch.setattr(
        release_readiness,
        "load_validated_runtime_profile",
        fake_load_profile,
    )

    source_revision = "a" * 40
    machine_path = tmp_path / "machine-acceptance.json"
    machine = build_machine_acceptance_report(
        source_revision=source_revision,
        hardware=hardware,
        active_profile_id=active_profile_id,
        active_profile_sha256=active_profile_sha256,
        checks=_machine_checks(notifications=machine_notifications),
        generated_at=datetime(2026, 9, 25, 3, 40, tzinfo=UTC),
    )
    write_machine_acceptance_report(machine, machine_path)

    return (
        session_path,
        machine_path,
        hardware,
        active_profile_id,
        active_profile_sha256,
        status_holder,
    )


def test_release_readiness_qualifies_only_complete_exact_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        session_path,
        machine_path,
        hardware,
        profile_id,
        profile_sha256,
        _,
    ) = _sources(tmp_path, monkeypatch)

    report = build_release_readiness_report(
        validation_session_path=session_path,
        machine_acceptance_path=machine_path,
        source_revision="a" * 40,
        hardware=hardware,
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha256,
        generated_at=datetime(2026, 9, 25, 3, 50, tzinfo=UTC),
    )

    assert report.candidate_evidence_complete is True
    assert report.machine_acceptance_qualified is True
    assert report.qualified_for_release is True
    assert report.validated_profile_id == profile_id
    assert report.validated_profile_sha256 == profile_sha256
    rendered = json.dumps(report.model_dump(mode="json"), sort_keys=True)
    assert str(tmp_path) not in rendered


def test_readiness_or_machine_failure_blocks_release_qualification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        session_path,
        machine_path,
        hardware,
        profile_id,
        profile_sha256,
        _,
    ) = _sources(
        tmp_path,
        monkeypatch,
        readiness_passed=False,
        machine_notifications="fail",
    )

    report = build_release_readiness_report(
        validation_session_path=session_path,
        machine_acceptance_path=machine_path,
        source_revision="a" * 40,
        hardware=hardware,
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha256,
    )

    assert report.candidate_evidence_complete is False
    assert report.machine_acceptance_qualified is False
    assert report.qualified_for_release is False


def test_release_readiness_rejects_profile_not_bound_to_active_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        session_path,
        machine_path,
        hardware,
        _,
        profile_sha256,
        _,
    ) = _sources(tmp_path, monkeypatch)

    with pytest.raises(ReleaseReadinessEvidenceError, match="active runtime profile"):
        build_release_readiness_report(
            validation_session_path=session_path,
            machine_acceptance_path=machine_path,
            source_revision="a" * 40,
            hardware=hardware,
            active_profile_id="d" * 64,
            active_profile_sha256=profile_sha256,
        )


def test_release_readiness_verification_detects_changed_candidate_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        session_path,
        machine_path,
        hardware,
        profile_id,
        profile_sha256,
        status_holder,
    ) = _sources(tmp_path, monkeypatch)

    report = build_release_readiness_report(
        validation_session_path=session_path,
        machine_acceptance_path=machine_path,
        source_revision="a" * 40,
        hardware=hardware,
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha256,
        generated_at=datetime(2026, 9, 25, 3, 50, tzinfo=UTC),
    )
    original = status_holder["status"]
    status_holder["status"] = original.model_copy(
        update={
            "capability": original.capability.model_copy(
                update={"artifact_sha256": "f" * 64}
            )
        }
    )

    with pytest.raises(ReleaseReadinessEvidenceError, match="current source evidence"):
        verify_release_readiness_sources(
            report,
            validation_session_path=session_path,
            machine_acceptance_path=machine_path,
            source_revision="a" * 40,
            hardware=hardware,
            active_profile_id=profile_id,
            active_profile_sha256=profile_sha256,
        )


def test_release_readiness_round_trip_is_immutable_and_rejects_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        session_path,
        machine_path,
        hardware,
        profile_id,
        profile_sha256,
        _,
    ) = _sources(tmp_path, monkeypatch)
    report = build_release_readiness_report(
        validation_session_path=session_path,
        machine_acceptance_path=machine_path,
        source_revision="a" * 40,
        hardware=hardware,
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha256,
    )
    path = tmp_path / "release-readiness.json"

    write_release_readiness_report(report, path)
    assert load_release_readiness_report(path) == report

    with pytest.raises(FileExistsError, match="overwrite"):
        write_release_readiness_report(report, path)

    link = tmp_path / "linked-readiness.json"
    link.symlink_to(path)
    with pytest.raises(ReleaseReadinessEvidenceError, match="symlink"):
        load_release_readiness_report(link)
