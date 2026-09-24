from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally import __version__
from ally.diagnostics import (
    EvaluationSuiteCounts,
    EvaluationSuiteProfile,
    FirstMachineReadinessCheck,
    FirstMachineReadinessReport,
    HardwareProfile,
    LocalModelValidationReport,
    RuntimePrivacyChecks,
    RuntimeProfile,
    SyntheticWorkflowCheck,
    SyntheticWorkflowReport,
    build_functional_workflow_report,
    build_runtime_privacy_report,
    write_functional_workflow_report,
    write_runtime_privacy_report,
    write_validation_report,
)
from ally.evals import EvalResult, EvalSummary
from ally.runtime_profiles import (
    build_validated_runtime_profile,
    write_validated_runtime_profile,
)
from ally.validation_sessions import (
    ValidationArtifactPlan,
    initialize_validation_session,
    inspect_validation_session,
    load_validation_session,
)


def _summary(*, successful: bool = True) -> EvalSummary:
    result = EvalResult(
        case_id="synthetic",
        category="provider_response",
        evaluator="synthetic",
        status="passed" if successful else "failed",
        message="",
        duration_ms=1.0,
    )
    return EvalSummary(
        total=1,
        passed=1 if successful else 0,
        failed=0 if successful else 1,
        errors=0,
        results=(result,),
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


def _ready() -> FirstMachineReadinessReport:
    return FirstMachineReadinessReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        hardware=_hardware(),
        config_exists=False,
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
                id="target.os",
                severity="ok",
                summary="Synthetic readiness passed.",
            ),
        ),
    )


def _validation(*, successful: bool = True) -> LocalModelValidationReport:
    return LocalModelValidationReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic-model",
        runtime=RuntimeProfile(name="synthetic-runtime", version="1.0"),
        evaluation_suite=EvaluationSuiteProfile(
            core_sha256="a" * 64,
            provider_sha256="b" * 64,
            behavioral_sha256="c" * 64,
        ),
        hardware=_hardware(),
        core=_summary(successful=successful),
        provider=_summary(successful=successful),
        behavior=_summary(successful=successful),
        duration_ms=1000.0,
    )


def _write_capability(root: Path, *, successful: bool = True) -> Path:
    return write_validation_report(
        _validation(successful=successful),
        root / "capability.json",
    )


def _write_secondary_evidence(
    root: Path,
    validation_path: Path,
    *,
    workflow_qualified: bool = True,
    privacy_qualified: bool = True,
) -> tuple[Path, Path]:
    privacy_value = "pass" if privacy_qualified else "not_run"
    privacy = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=RuntimePrivacyChecks(
            inference_with_egress_blocked=privacy_value,
            synthetic_chat=privacy_value,
            synthetic_planning=privacy_value,
            synthetic_memory_proposal=privacy_value,
            synthetic_grounding=privacy_value,
            no_cloud_auth_required=privacy_value,
            no_cloud_fallback_observed=privacy_value,
            no_prompt_telemetry_observed=privacy_value,
            no_unexpected_outbound_connections=privacy_value,
        ),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        root / "privacy.json",
    )
    workflow = build_functional_workflow_report(
        validation_path=validation_path,
        workflow=SyntheticWorkflowReport(
            generated_at=datetime(2026, 9, 24, tzinfo=UTC),
            ally_version=__version__,
            provider="synthetic",
            model="synthetic-model",
            checks=(
                SyntheticWorkflowCheck(
                    id="conversation.persistence",
                    status="passed" if workflow_qualified else "failed",
                    duration_ms=1.0,
                    error_class=None if workflow_qualified else "AssertionError",
                ),
            ),
            duration_ms=1.0,
        ),
    )
    workflow_path = write_functional_workflow_report(
        workflow,
        root / "workflows.json",
    )
    return privacy_path, workflow_path


def _write_complete_evidence(root: Path) -> None:
    validation = _write_capability(root)
    privacy, workflows = _write_secondary_evidence(root, validation)
    profile = build_validated_runtime_profile(
        validation_path=validation,
        privacy_path=privacy,
        workflow_path=workflows,
    )
    write_validated_runtime_profile(profile, root / "profile.json")


def test_session_manifest_is_immutable_path_free_plan(tmp_path: Path) -> None:
    private_root = tmp_path / "PRIVATE-SESSION-DIRECTORY"
    manifest, path = initialize_validation_session(
        directory=private_root,
        candidate_label="candidate-a",
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
    )

    assert path == private_root.resolve() / "session.json"
    assert load_validation_session(path) == manifest
    rendered = path.read_text(encoding="utf-8")
    assert "PRIVATE-SESSION-DIRECTORY" not in rendered
    assert str(tmp_path) not in rendered
    assert manifest.artifacts == ValidationArtifactPlan()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        initialize_validation_session(
            directory=private_root,
            candidate_label="candidate-a",
        )


def test_new_session_derives_capability_as_next_step(tmp_path: Path) -> None:
    _, session = initialize_validation_session(
        directory=tmp_path / "candidate",
        candidate_label="candidate",
    )

    status = inspect_validation_session(session, readiness=_ready())

    assert status.readiness.state == "passed"
    assert status.capability.state == "pending"
    assert status.workflows.state == "blocked"
    assert status.privacy.state == "blocked"
    assert status.profile.state == "blocked"
    assert status.next_step == "create_capability_evidence"
    assert not status.complete


def test_session_resumes_from_partial_capability_evidence(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    _, session = initialize_validation_session(
        directory=root,
        candidate_label="candidate",
    )
    _write_capability(root)

    status = inspect_validation_session(session, readiness=_ready())

    assert status.capability.state == "passed"
    assert status.workflows.state == "pending"
    assert status.privacy.state == "pending"
    assert status.next_step == "create_workflow_evidence"


def test_complete_session_rederives_all_passed_state_after_reload(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    manifest, session = initialize_validation_session(
        directory=root,
        candidate_label="candidate",
    )
    _write_complete_evidence(root)

    reloaded = load_validation_session(session)
    status = inspect_validation_session(session, readiness=_ready())

    assert reloaded.session_id == manifest.session_id
    assert status.capability.state == "passed"
    assert status.workflows.state == "passed"
    assert status.privacy.state == "passed"
    assert status.profile.state == "passed"
    assert status.next_step == "complete"
    assert status.complete


def test_failed_workflow_blocks_profile_creation_step(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    _, session = initialize_validation_session(
        directory=root,
        candidate_label="candidate",
    )
    validation = _write_capability(root)
    _write_secondary_evidence(
        root,
        validation,
        workflow_qualified=False,
    )

    status = inspect_validation_session(session, readiness=_ready())

    assert status.workflows.state == "failed"
    assert status.privacy.state == "passed"
    assert status.profile.state == "blocked"
    assert status.next_step == "fix_workflow_evidence"
    assert not status.complete


def test_tampered_privacy_artifact_invalidates_completed_session(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    _, session = initialize_validation_session(
        directory=root,
        candidate_label="candidate",
    )
    _write_complete_evidence(root)

    privacy_path = root / "privacy.json"
    raw = json.loads(privacy_path.read_text(encoding="utf-8"))
    raw["source_validation_sha256"] = "f" * 64
    privacy_path.write_text(json.dumps(raw), encoding="utf-8")

    status = inspect_validation_session(session, readiness=_ready())

    assert status.privacy.state == "inconsistent"
    assert status.profile.state == "inconsistent"
    assert status.next_step == "fix_privacy_evidence"
    assert not status.complete


def test_readiness_failure_precedes_other_next_actions(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    _, session = initialize_validation_session(
        directory=root,
        candidate_label="candidate",
    )
    _write_complete_evidence(root)
    not_ready = _ready().model_copy(
        update={
            "checks": (
                FirstMachineReadinessCheck(
                    id="target.os",
                    severity="error",
                    summary="Synthetic blocking error.",
                ),
            )
        }
    )

    status = inspect_validation_session(session, readiness=not_ready)

    assert status.readiness.state == "failed"
    assert status.profile.state == "passed"
    assert status.next_step == "resolve_readiness"
    assert not status.complete
