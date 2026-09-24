from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally import __version__
from ally.commands.runtime_profiles import (
    run_create_runtime_profile,
    run_verify_runtime_profile,
)
from ally.diagnostics import (
    EvaluationSuiteProfile,
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
    ValidatedRuntimeProfileError,
    build_validated_runtime_profile,
    load_validated_runtime_profile,
    verify_validated_runtime_profile,
    write_validated_runtime_profile,
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


def _validation(
    *,
    model: str = "synthetic-model",
    successful: bool = True,
) -> LocalModelValidationReport:
    return LocalModelValidationReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model=model,
        runtime=RuntimeProfile(
            name="synthetic-runtime",
            version="1.0",
            context_length=32768,
        ),
        evaluation_suite=EvaluationSuiteProfile(
            core_sha256="a" * 64,
            provider_sha256="b" * 64,
            behavioral_sha256="c" * 64,
        ),
        hardware=HardwareProfile(
            system="Darwin",
            release="25.0",
            machine="arm64",
            processor="arm",
            python_version="3.12.11",
            logical_cpu_count=16,
            total_memory_bytes=128 * 1024**3,
            apple_model="Mac17,1",
            apple_chip="Apple M5 Max",
        ),
        core=_summary(successful=successful),
        provider=_summary(successful=successful),
        behavior=_summary(successful=successful),
        duration_ms=1000.0,
    )


def _evidence(
    tmp_path: Path,
    *,
    model: str = "synthetic-model",
    successful: bool = True,
    privacy_qualified: bool = True,
    workflow_qualified: bool = True,
) -> tuple[Path, Path, Path]:
    hidden = tmp_path / "PRIVATE-LOCAL-EVIDENCE-DIRECTORY"
    hidden.mkdir(parents=True, exist_ok=True)
    validation_path = write_validation_report(
        _validation(model=model, successful=successful),
        hidden / "capability.json",
    )
    value = "pass" if privacy_qualified else "not_run"
    privacy = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=RuntimePrivacyChecks(
            inference_with_egress_blocked=value,
            synthetic_chat=value,
            synthetic_planning=value,
            synthetic_memory_proposal=value,
            synthetic_grounding=value,
            no_cloud_auth_required=value,
            no_cloud_fallback_observed=value,
            no_prompt_telemetry_observed=value,
            no_unexpected_outbound_connections=value,
        ),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        hidden / "privacy.json",
    )
    workflow = build_functional_workflow_report(
        validation_path=validation_path,
        workflow=SyntheticWorkflowReport(
            generated_at=datetime(2026, 9, 24, tzinfo=UTC),
            ally_version=__version__,
            provider="synthetic",
            model=model,
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
        hidden / "workflows.json",
    )
    return validation_path, privacy_path, workflow_path


def test_profile_identity_is_deterministic_for_exact_evidence(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)

    first = build_validated_runtime_profile(
        validation_path=evidence[0],
        privacy_path=evidence[1],
        workflow_path=evidence[2],
    )
    second = build_validated_runtime_profile(
        validation_path=evidence[0],
        privacy_path=evidence[1],
        workflow_path=evidence[2],
    )

    assert first.profile_id == second.profile_id
    assert first.capability_evidence == second.capability_evidence
    assert first.privacy_evidence == second.privacy_evidence
    assert first.workflow_evidence == second.workflow_evidence


def test_profile_creation_rejects_ineligible_candidate(tmp_path: Path) -> None:
    validation, privacy, workflow = _evidence(
        tmp_path,
        privacy_qualified=False,
    )

    with pytest.raises(ValueError, match="not production-eligible"):
        build_validated_runtime_profile(
            validation_path=validation,
            privacy_path=privacy,
            workflow_path=workflow,
        )


def test_profile_is_path_free_and_immutable(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    profile = build_validated_runtime_profile(
        validation_path=evidence[0],
        privacy_path=evidence[1],
        workflow_path=evidence[2],
    )
    output = tmp_path / "profile.json"

    write_validated_runtime_profile(profile, output)
    rendered = output.read_text(encoding="utf-8")

    assert "PRIVATE-LOCAL-EVIDENCE-DIRECTORY" not in rendered
    assert str(tmp_path) not in rendered
    assert '"name": "capability.json"' in rendered

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_validated_runtime_profile(profile, output)


def test_profile_loader_is_strict(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    profile = build_validated_runtime_profile(
        validation_path=evidence[0],
        privacy_path=evidence[1],
        workflow_path=evidence[2],
    )
    output = write_validated_runtime_profile(profile, tmp_path / "profile.json")
    raw = json.loads(output.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    output.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidatedRuntimeProfileError, match="invalid Ally"):
        load_validated_runtime_profile(output)


def test_profile_verification_rejects_different_source_evidence(
    tmp_path: Path,
) -> None:
    first = _evidence(tmp_path / "a", model="model-a")
    second = _evidence(tmp_path / "b", model="model-b")
    profile = build_validated_runtime_profile(
        validation_path=first[0],
        privacy_path=first[1],
        workflow_path=first[2],
    )

    with pytest.raises(ValidatedRuntimeProfileError, match="evidence digest"):
        verify_validated_runtime_profile(
            profile,
            validation_path=second[0],
            privacy_path=second[1],
            workflow_path=second[2],
        )


def test_profile_commands_create_and_verify(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = _evidence(tmp_path)
    output = tmp_path / "profile.json"

    result = run_create_runtime_profile(
        validation_report=str(evidence[0]),
        privacy_report=str(evidence[1]),
        workflow_report=str(evidence[2]),
        output=str(output),
        json_output=True,
    )
    rendered = json.loads(capsys.readouterr().out)

    assert result == 0
    assert rendered["profile_id"] == load_validated_runtime_profile(output).profile_id
    assert "PRIVATE-LOCAL-EVIDENCE-DIRECTORY" not in json.dumps(rendered)

    verify_result = run_verify_runtime_profile(
        profile_path=str(output),
        validation_report=str(evidence[0]),
        privacy_report=str(evidence[1]),
        workflow_report=str(evidence[2]),
        json_output=True,
    )
    verified = json.loads(capsys.readouterr().out)

    assert verify_result == 0
    assert verified["verified"] is True
    assert verified["production_eligible"] is True



def test_profile_id_detects_operational_metadata_tampering(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    profile = build_validated_runtime_profile(
        validation_path=evidence[0],
        privacy_path=evidence[1],
        workflow_path=evidence[2],
    )
    output = write_validated_runtime_profile(profile, tmp_path / "profile.json")
    raw = json.loads(output.read_text(encoding="utf-8"))
    raw["model"] = "tampered-model"
    output.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValidatedRuntimeProfileError, match="invalid Ally"):
        load_validated_runtime_profile(output)
