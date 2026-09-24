from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally import __version__
from ally.commands.validate import (
    run_compare_candidate_evidence,
    run_show_candidate_evidence,
)
from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    LocalModelValidationReport,
    RuntimePrivacyChecks,
    RuntimeProfile,
    build_candidate_evidence,
    build_runtime_privacy_report,
    compare_candidate_evidence,
    write_runtime_privacy_report,
    write_validation_report,
)
from ally.diagnostics.runtime_privacy import RuntimePrivacyEvidenceError
from ally.evals import EvalResult, EvalSummary


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


def _validation(
    *,
    model: str,
    successful: bool = True,
    hardware: HardwareProfile | None = None,
) -> LocalModelValidationReport:
    return LocalModelValidationReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        endpoint="http://127.0.0.1:8080/v1",
        model=model,
        runtime=RuntimeProfile(name="synthetic-runtime", version="1.0"),
        evaluation_suite=EvaluationSuiteProfile(
            core_sha256="a" * 64,
            provider_sha256="b" * 64,
            behavioral_sha256="c" * 64,
        ),
        hardware=hardware or _hardware(),
        core=_summary(successful=successful),
        provider=_summary(successful=successful),
        behavior=_summary(successful=successful),
        duration_ms=1000.0,
    )


def _checks(*, qualified: bool = True) -> RuntimePrivacyChecks:
    value = "pass" if qualified else "not_run"
    return RuntimePrivacyChecks(
        inference_with_egress_blocked=value,
        synthetic_chat=value,
        synthetic_planning=value,
        synthetic_memory_proposal=value,
        synthetic_grounding=value,
        no_cloud_auth_required=value,
        no_cloud_fallback_observed=value,
        no_prompt_telemetry_observed=value,
        no_unexpected_outbound_connections=value,
    )


def _pair(
    tmp_path: Path,
    *,
    stem: str,
    model: str,
    successful: bool = True,
    privacy_qualified: bool = True,
    hardware: HardwareProfile | None = None,
) -> tuple[Path, Path]:
    validation_path = write_validation_report(
        _validation(model=model, successful=successful, hardware=hardware),
        tmp_path / f"{stem}-validation.json",
    )
    privacy = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=_checks(qualified=privacy_qualified),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        tmp_path / f"{stem}-privacy.json",
    )
    return validation_path, privacy_path


def test_candidate_pair_requires_exact_matching_evidence(tmp_path: Path) -> None:
    validation_a, privacy_a = _pair(
        tmp_path,
        stem="a",
        model="model-a",
    )
    validation_b, _ = _pair(
        tmp_path,
        stem="b",
        model="model-b",
    )

    candidate = build_candidate_evidence(
        validation_path=validation_a,
        privacy_path=privacy_a,
    )
    assert candidate.production_eligible is True

    with pytest.raises(RuntimePrivacyEvidenceError, match="does not match"):
        build_candidate_evidence(
            validation_path=validation_b,
            privacy_path=privacy_a,
        )


def test_privacy_unqualified_candidate_is_not_production_eligible(
    tmp_path: Path,
) -> None:
    validation, privacy = _pair(
        tmp_path,
        stem="candidate",
        model="model",
        privacy_qualified=False,
    )

    candidate = build_candidate_evidence(
        validation_path=validation,
        privacy_path=privacy,
    )

    assert candidate.capability_successful is True
    assert candidate.privacy_qualified is False
    assert candidate.production_eligible is False


def test_failed_capability_candidate_is_not_production_eligible(
    tmp_path: Path,
) -> None:
    validation, privacy = _pair(
        tmp_path,
        stem="candidate",
        model="model",
        successful=False,
    )

    candidate = build_candidate_evidence(
        validation_path=validation,
        privacy_path=privacy,
    )

    assert candidate.capability_successful is False
    assert candidate.privacy_qualified is False
    assert candidate.production_eligible is False


def test_candidate_comparison_is_neutral_and_surfaces_ineligible_state(
    tmp_path: Path,
) -> None:
    a_validation, a_privacy = _pair(
        tmp_path,
        stem="a",
        model="model-a",
    )
    b_validation, b_privacy = _pair(
        tmp_path,
        stem="b",
        model="model-b",
        privacy_qualified=False,
    )
    candidates = (
        build_candidate_evidence(
            validation_path=a_validation,
            privacy_path=a_privacy,
        ),
        build_candidate_evidence(
            validation_path=b_validation,
            privacy_path=b_privacy,
        ),
    )

    comparison = compare_candidate_evidence(candidates)

    assert comparison.same_hardware
    assert comparison.same_evaluation_suite
    assert comparison.same_ally_version
    assert comparison.candidates[0].production_eligible is True
    assert comparison.candidates[1].production_eligible is False
    assert any("privacy-qualified" in warning for warning in comparison.warnings)


def test_candidate_comparison_warns_when_hardware_differs(tmp_path: Path) -> None:
    first_validation, first_privacy = _pair(
        tmp_path,
        stem="a",
        model="model-a",
    )
    different_hardware = _hardware().model_copy(
        update={"total_memory_bytes": 64 * 1024**3}
    )
    second_validation, second_privacy = _pair(
        tmp_path,
        stem="b",
        model="model-b",
        hardware=different_hardware,
    )

    comparison = compare_candidate_evidence(
        (
            build_candidate_evidence(
                validation_path=first_validation,
                privacy_path=first_privacy,
            ),
            build_candidate_evidence(
                validation_path=second_validation,
                privacy_path=second_privacy,
            ),
        )
    )

    assert comparison.same_hardware is False
    assert any("Hardware profiles differ" in warning for warning in comparison.warnings)



def test_candidate_command_reports_verified_eligibility(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validation, privacy = _pair(
        tmp_path,
        stem="candidate",
        model="model",
    )

    result = run_show_candidate_evidence(
        validation_report=str(validation),
        privacy_report=str(privacy),
        json_output=False,
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "Production eligible: yes" in output
    assert "Capability validation: pass" in output
    assert "Runtime privacy: qualified" in output


def test_candidate_command_rejects_mismatched_pair(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, privacy_a = _pair(
        tmp_path,
        stem="a",
        model="model-a",
    )
    validation_b, _ = _pair(
        tmp_path,
        stem="b",
        model="model-b",
    )

    result = run_show_candidate_evidence(
        validation_report=str(validation_b),
        privacy_report=str(privacy_a),
        json_output=False,
    )

    assert result == 2
    assert "Candidate evidence error:" in capsys.readouterr().out


def test_candidate_comparison_command_shows_privacy_eligibility(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    a_validation, a_privacy = _pair(
        tmp_path,
        stem="a",
        model="model-a",
    )
    b_validation, b_privacy = _pair(
        tmp_path,
        stem="b",
        model="model-b",
        privacy_qualified=False,
    )

    result = run_compare_candidate_evidence(
        pairs=(
            (str(a_validation), str(a_privacy)),
            (str(b_validation), str(b_privacy)),
        ),
        json_output=False,
    )
    output = capsys.readouterr().out

    assert result == 0
    assert output.count("Production eligible:") == 2
    assert "Privacy: unqualified" in output
    assert "No default is selected automatically" in output
