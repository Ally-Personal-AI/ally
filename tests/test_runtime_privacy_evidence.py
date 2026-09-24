from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from ally import __version__
from ally.commands.validate import (
    run_runtime_privacy_qualification,
    run_show_runtime_privacy_report,
    run_verify_runtime_privacy_report,
)
from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    LocalModelValidationReport,
    RuntimePrivacyChecks,
    RuntimePrivacyEvidenceError,
    RuntimePrivacyQualificationReport,
    RuntimeProfile,
    build_runtime_privacy_report,
    load_runtime_privacy_report,
    write_runtime_privacy_report,
    write_validation_report,
)
from ally.evals import EvalResult, EvalSummary


def summary(*, successful: bool = True) -> EvalSummary:
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


def validation_report(*, successful: bool = True) -> LocalModelValidationReport:
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
        core=summary(successful=successful),
        provider=summary(successful=successful),
        behavior=summary(successful=successful),
        duration_ms=1000.0,
    )


def all_passed_checks() -> RuntimePrivacyChecks:
    return RuntimePrivacyChecks(
        inference_with_egress_blocked="pass",
        synthetic_chat="pass",
        synthetic_planning="pass",
        synthetic_memory_proposal="pass",
        synthetic_grounding="pass",
        no_cloud_auth_required="pass",
        no_cloud_fallback_observed="pass",
        no_prompt_telemetry_observed="pass",
        no_unexpected_outbound_connections="pass",
    )


def test_runtime_privacy_checks_fail_closed_by_default() -> None:
    checks = RuntimePrivacyChecks()

    assert checks.all_passed is False
    assert set(checks.model_dump(mode="python").values()) == {"not_run"}


def test_privacy_report_requires_coherent_isolation_evidence() -> None:
    raw = {
        "schema_version": 1,
        "generated_at": datetime(2026, 9, 24, tzinfo=UTC),
        "ally_version": __version__,
        "source_validation_sha256": "a" * 64,
        "source_validation_successful": True,
        "model": "synthetic",
        "runtime": {"name": "runtime", "version": "1"},
        "hardware": {
            "system": "Darwin",
            "release": "25.0",
            "machine": "arm64",
            "processor": "arm",
            "python_version": "3.12.11",
            "logical_cpu_count": 16,
            "total_memory_bytes": 128 * 1024**3,
            "apple_model": "Mac17,1",
            "apple_chip": "Apple M5 Max",
        },
        "isolation_mode": "unverified",
        "network_observation": "system_tools",
        "checks": {},
    }

    with pytest.raises(ValidationError, match="unverified isolation"):
        RuntimePrivacyQualificationReport.model_validate(raw)


def test_report_is_tied_to_exact_validation_artifact(tmp_path: Path) -> None:
    validation_path = write_validation_report(
        validation_report(),
        tmp_path / "validation.json",
    )
    report = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=all_passed_checks(),
    )

    expected_hash = hashlib.sha256(validation_path.read_bytes()).hexdigest()
    assert report.source_validation_sha256 == expected_hash
    assert report.source_validation_successful is True
    assert report.qualified_for_private_inference is True
    assert report.runtime.name == "synthetic-runtime"
    assert report.model == "synthetic-model"


def test_failed_source_validation_cannot_become_qualified(tmp_path: Path) -> None:
    validation_path = write_validation_report(
        validation_report(successful=False),
        tmp_path / "failed-validation.json",
    )

    report = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=all_passed_checks(),
    )

    assert report.source_validation_successful is False
    assert report.qualified_for_private_inference is False


def test_source_validation_must_match_current_ally_version(tmp_path: Path) -> None:
    stale = validation_report().model_copy(update={"ally_version": "0.0.0-old"})
    path = write_validation_report(stale, tmp_path / "stale.json")

    with pytest.raises(ValueError, match="must match"):
        build_runtime_privacy_report(
            validation_path=path,
            isolation_mode="host_offline",
            network_observation="system_tools",
            checks=all_passed_checks(),
        )


def test_runtime_privacy_artifact_is_strict_and_non_overwriting(
    tmp_path: Path,
) -> None:
    validation_path = write_validation_report(
        validation_report(),
        tmp_path / "validation.json",
    )
    report = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=all_passed_checks(),
    )
    path = tmp_path / "privacy.json"

    assert write_runtime_privacy_report(report, path) == path.resolve()
    assert load_runtime_privacy_report(path) == report

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_runtime_privacy_report(report, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RuntimePrivacyEvidenceError, match="invalid Ally"):
        load_runtime_privacy_report(path)


def test_runtime_privacy_command_stays_unqualified_until_every_check_passes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validation_path = write_validation_report(
        validation_report(),
        tmp_path / "validation.json",
    )
    output = tmp_path / "privacy.json"

    result = run_runtime_privacy_qualification(
        validation_report=str(validation_path),
        isolation_mode="host_offline",
        network_observation="system_tools",
        inference_with_egress_blocked="pass",
        synthetic_chat="pass",
        synthetic_planning="pass",
        synthetic_memory_proposal="pass",
        synthetic_grounding="pass",
        no_cloud_auth_required="pass",
        no_cloud_fallback_observed="pass",
        no_prompt_telemetry_observed="not_run",
        no_unexpected_outbound_connections="pass",
        output=str(output),
    )

    assert result == 1
    assert "Qualified for private inference: no" in capsys.readouterr().out
    assert load_runtime_privacy_report(output).qualified_for_private_inference is False


def test_runtime_privacy_command_and_show_report_qualified_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validation_path = write_validation_report(
        validation_report(),
        tmp_path / "validation.json",
    )
    output = tmp_path / "privacy.json"

    result = run_runtime_privacy_qualification(
        validation_report=str(validation_path),
        isolation_mode="host_offline",
        network_observation="external_monitor",
        inference_with_egress_blocked="pass",
        synthetic_chat="pass",
        synthetic_planning="pass",
        synthetic_memory_proposal="pass",
        synthetic_grounding="pass",
        no_cloud_auth_required="pass",
        no_cloud_fallback_observed="pass",
        no_prompt_telemetry_observed="pass",
        no_unexpected_outbound_connections="pass",
        output=str(output),
    )
    assert result == 0
    assert "Qualified for private inference: yes" in capsys.readouterr().out

    assert run_show_runtime_privacy_report(
        report_path=str(output),
        json_output=True,
    ) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["qualified_for_private_inference"] is True
    assert rendered["isolation_mode"] == "host_offline"
    assert rendered["network_observation"] == "external_monitor"


def test_runtime_privacy_verify_rejects_wrong_source_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first_validation = write_validation_report(
        validation_report(),
        tmp_path / "validation-a.json",
    )
    second = validation_report().model_copy(update={"model": "different-model"})
    second_validation = write_validation_report(
        second,
        tmp_path / "validation-b.json",
    )
    privacy = build_runtime_privacy_report(
        validation_path=first_validation,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=all_passed_checks(),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        tmp_path / "privacy.json",
    )

    result = run_verify_runtime_privacy_report(
        report_path=str(privacy_path),
        validation_report=str(second_validation),
        json_output=False,
    )

    assert result == 2
    assert "does not match the source validation digest" in capsys.readouterr().out


def test_runtime_privacy_verify_accepts_exact_source_pair(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validation_path = write_validation_report(
        validation_report(),
        tmp_path / "validation.json",
    )
    privacy = build_runtime_privacy_report(
        validation_path=validation_path,
        isolation_mode="host_offline",
        network_observation="system_tools",
        checks=all_passed_checks(),
    )
    privacy_path = write_runtime_privacy_report(
        privacy,
        tmp_path / "privacy.json",
    )

    result = run_verify_runtime_privacy_report(
        report_path=str(privacy_path),
        validation_report=str(validation_path),
        json_output=True,
    )
    rendered = json.loads(capsys.readouterr().out)

    assert result == 0
    assert rendered["source_matches"] is True
    assert rendered["qualified_for_private_inference"] is True
