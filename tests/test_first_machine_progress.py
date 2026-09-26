from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

import ally.diagnostics.first_machine_progress as progress
from ally import __version__
from ally.commands import validate as validate_commands
from ally.diagnostics import (
    EvaluationSuiteCounts,
    FirstMachineReadinessCheck,
    FirstMachineReadinessReport,
    HardwareProfile,
    MachineAcceptanceChecks,
    MachineAcceptanceReport,
    MachineAcceptanceStatus,
    build_machine_acceptance_report,
)
from ally.validation_sessions import (
    ValidationNextStep,
    ValidationSessionStatus,
    ValidationStageState,
    ValidationStageStatus,
)


def _hardware() -> HardwareProfile:
    return HardwareProfile(
        system="Darwin",
        release="25.0",
        machine="arm64",
        processor="arm",
        python_version="3.12.11",
        logical_cpu_count=16,
        total_memory_bytes=128 * 1024**3,
        apple_model="Mac17,1",
        apple_chip="Apple M5 Max",
    )


def _readiness(*, ready: bool = True) -> FirstMachineReadinessReport:
    return FirstMachineReadinessReport(
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
        ally_version=__version__,
        hardware=_hardware(),
        config_exists=True,
        core_database_exists=False,
        runtime_database_exists=False,
        paths_distinct=True,
        evaluation_suites=EvaluationSuiteCounts(
            core=1,
            provider_smoke=1,
            behavioral_qualification=1,
        ),
        notification_supported=True,
        notification_api_available=True,
        notification_authorization="authorized",
        checks=(
            FirstMachineReadinessCheck(
                id="synthetic.readiness",
                severity="ok" if ready else "error",
                summary="Synthetic readiness.",
            ),
        ),
    )


def _stage(
    stage_id: str,
    state: ValidationStageState,
    *,
    digest: str | None = None,
) -> ValidationStageStatus:
    return ValidationStageStatus(
        id=stage_id,
        state=state,
        artifact_name=None if stage_id == "readiness" else f"{stage_id}.json",
        artifact_sha256=digest,
        detail="Synthetic stage.",
    )


def _session_status(
    *,
    complete: bool,
    next_step: ValidationNextStep,
) -> ValidationSessionStatus:
    passed: ValidationStageState = "passed" if complete else "pending"
    return ValidationSessionStatus(
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
        candidate_label="candidate-a",
        ally_version=__version__,
        readiness=_stage("readiness", "passed"),
        capability=_stage(
            "capability",
            passed,
            digest="a" * 64 if complete else None,
        ),
        workflows=_stage(
            "workflows",
            passed if complete else "blocked",
            digest="b" * 64 if complete else None,
        ),
        privacy=_stage(
            "privacy",
            passed if complete else "blocked",
            digest="c" * 64 if complete else None,
        ),
        profile=_stage(
            "profile",
            passed if complete else "blocked",
            digest="d" * 64 if complete else None,
        ),
        next_step=next_step,
        complete=complete,
    )


def _prepare_complete_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, str, str]:
    session = tmp_path / "candidate" / "session.json"
    session.parent.mkdir()
    session.write_text("{}\n", encoding="utf-8")
    profile_path = session.parent / "profile.json"
    profile_path.write_text("synthetic-profile\n", encoding="utf-8")
    profile_id = "e" * 64
    profile_sha = "f" * 64

    def fake_inspect(
        _session_path: Path,
        *,
        readiness: FirstMachineReadinessReport | None = None,
    ) -> ValidationSessionStatus:
        _ = readiness
        return _session_status(
            complete=True,
            next_step="complete",
        )

    def fake_load_session(_path: Path) -> SimpleNamespace:
        return SimpleNamespace(
            artifacts=SimpleNamespace(profile="profile.json")
        )

    def fake_load_profile(_path: Path) -> SimpleNamespace:
        return SimpleNamespace(
            hardware=_hardware(),
            ally_version=__version__,
            profile_id=profile_id,
        )

    def fake_sha(_path: Path) -> str:
        return profile_sha

    monkeypatch.setattr(progress, "inspect_validation_session", fake_inspect)
    monkeypatch.setattr(progress, "load_validation_session", fake_load_session)
    monkeypatch.setattr(
        progress,
        "load_validated_runtime_profile",
        fake_load_profile,
    )
    monkeypatch.setattr(progress, "_sha256", fake_sha)
    return session, profile_id, profile_sha


def test_progress_stops_at_readiness_before_session() -> None:
    report = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        readiness=_readiness(ready=False),
        active_profile_binding=None,
    )

    assert report.readiness.state == "failed"
    assert report.next_step == "resolve_readiness"
    assert report.candidate.state == "pending"
    assert report.machine_acceptance.state == "blocked"


def test_progress_requests_validation_session_after_clean_readiness() -> None:
    report = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        readiness=_readiness(),
        active_profile_binding=None,
    )

    assert report.readiness.state == "passed"
    assert report.next_step == "initialize_validation_session"


def test_incomplete_candidate_remains_candidate_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session = tmp_path / "session.json"
    session.write_text("{}\n", encoding="utf-8")
    def fake_inspect(
        _session_path: Path,
        *,
        readiness: FirstMachineReadinessReport | None = None,
    ) -> ValidationSessionStatus:
        _ = readiness
        return _session_status(
            complete=False,
            next_step="create_capability_evidence",
        )

    monkeypatch.setattr(progress, "inspect_validation_session", fake_inspect)

    report = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        readiness=_readiness(),
        active_profile_binding=None,
    )

    assert report.candidate.state == "pending"
    assert report.candidate_next_step == "create_capability_evidence"
    assert report.active_profile.state == "blocked"
    assert report.next_step == "continue_candidate_validation"


def test_qualified_candidate_requires_exact_active_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session, profile_id, profile_sha = _prepare_complete_session(
        monkeypatch,
        tmp_path,
    )

    missing = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        readiness=_readiness(),
        active_profile_binding=None,
    )
    assert missing.candidate.state == "passed"
    assert missing.active_profile.state == "pending"
    assert missing.next_step == "select_validated_profile"

    mismatched = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        readiness=_readiness(),
        active_profile_binding=("1" * 64, profile_sha),
    )
    assert mismatched.active_profile.state == "inconsistent"
    assert mismatched.next_step == "select_validated_profile"

    exact = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        readiness=_readiness(),
        active_profile_binding=(profile_id, profile_sha),
    )
    assert exact.active_profile.state == "passed"
    assert exact.next_step == "record_machine_acceptance"


@pytest.mark.parametrize(
    ("notification_status", "expected_state"),
    [
        ("not_run", "pending"),
        ("fail", "failed"),
        ("pass", "passed"),
    ],
)
def test_machine_acceptance_uses_only_explicit_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    notification_status: MachineAcceptanceStatus,
    expected_state: progress.FirstMachineProgressState,
) -> None:
    session, profile_id, profile_sha = _prepare_complete_session(
        monkeypatch,
        tmp_path,
    )
    machine_path = tmp_path / "machine.json"
    machine_path.write_text("{}\n", encoding="utf-8")
    checks = MachineAcceptanceChecks(
        keychain="pass",
        recovery="pass",
        background_service="pass",
        notifications=notification_status,
        signed_release="pass",
        update_preparation="pass",
        app_replacement="pass",
        integrated_daily_use="pass",
    )
    machine = build_machine_acceptance_report(
        source_revision="a" * 40,
        hardware=_hardware(),
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha,
        checks=checks,
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    def fake_load_machine(_path: Path) -> MachineAcceptanceReport:
        return machine

    monkeypatch.setattr(
        progress,
        "load_machine_acceptance_report",
        fake_load_machine,
    )

    report = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        machine_acceptance_path=machine_path,
        readiness=_readiness(),
        active_profile_binding=(profile_id, profile_sha),
    )

    assert report.machine_acceptance.state == expected_state
    assert report.machine_checks == checks
    assert report.next_step == (
        "create_release_readiness"
        if notification_status == "pass"
        else "complete_machine_acceptance"
    )


def test_machine_acceptance_binding_mismatch_is_inconsistent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    session, profile_id, profile_sha = _prepare_complete_session(
        monkeypatch,
        tmp_path,
    )
    machine_path = tmp_path / "machine.json"
    machine_path.write_text("{}\n", encoding="utf-8")
    machine = build_machine_acceptance_report(
        source_revision="b" * 40,
        hardware=_hardware(),
        active_profile_id=profile_id,
        active_profile_sha256=profile_sha,
        checks=MachineAcceptanceChecks(),
        generated_at=datetime(2026, 9, 26, tzinfo=UTC),
    )
    def fake_load_machine(_path: Path) -> MachineAcceptanceReport:
        return machine

    monkeypatch.setattr(
        progress,
        "load_machine_acceptance_report",
        fake_load_machine,
    )

    report = progress.collect_first_machine_progress(
        source_revision="a" * 40,
        validation_session_path=session,
        machine_acceptance_path=machine_path,
        readiness=_readiness(),
        active_profile_binding=(profile_id, profile_sha),
    )

    assert report.machine_acceptance.state == "inconsistent"
    assert report.machine_checks is None
    assert report.next_step == "complete_machine_acceptance"


def test_progress_rejects_noncanonical_source_revision() -> None:
    with pytest.raises(
        progress.FirstMachineProgressError,
        match="source revision",
    ):
        progress.collect_first_machine_progress(
            source_revision="ABC",
            readiness=_readiness(),
        )


def test_progress_command_json_is_read_only_status_surface(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = progress.FirstMachineProgressReport(
        readiness=progress.FirstMachineProgressStage(
            id="readiness",
            state="passed",
            detail="Synthetic.",
        ),
        candidate=progress.FirstMachineProgressStage(
            id="candidate",
            state="pending",
            detail="Synthetic.",
        ),
        active_profile=progress.FirstMachineProgressStage(
            id="active_profile",
            state="blocked",
            detail="Synthetic.",
        ),
        machine_acceptance=progress.FirstMachineProgressStage(
            id="machine_acceptance",
            state="blocked",
            detail="Synthetic.",
        ),
        next_step="continue_candidate_validation",
        candidate_label="candidate-a",
        candidate_next_step="create_capability_evidence",
    )
    def fake_collect_progress(
        **_kwargs: object,
    ) -> progress.FirstMachineProgressReport:
        return report

    monkeypatch.setattr(
        validate_commands,
        "collect_first_machine_progress",
        fake_collect_progress,
    )

    result = validate_commands.run_first_machine_progress(
        source_revision="a" * 40,
        validation_session="/synthetic/session.json",
        machine_acceptance=None,
        json_output=True,
    )
    rendered = json.loads(capsys.readouterr().out)

    assert result == 0
    assert rendered["next_step"] == "continue_candidate_validation"
    assert rendered["candidate_label"] == "candidate-a"
    assert rendered["machine_checks"] is None
