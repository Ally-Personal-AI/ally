from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from ally.commands.validate import (
    run_compare_validation_reports,
    run_local_model_validation_command,
)
from ally.diagnostics import (
    EvaluationSuiteProfile,
    HardwareProfile,
    LocalModelValidationReport,
    PerformanceObservations,
    RuntimeParameter,
    RuntimeProfile,
    ValidationReportError,
    compare_validation_reports,
    load_validation_report,
    write_validation_report,
)
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


def _hardware(*, chip: str = "Apple M5 Max") -> HardwareProfile:
    return HardwareProfile(
        system="Darwin",
        release="25.0",
        machine="arm64",
        processor="arm",
        python_version="3.12.11",
        logical_cpu_count=16,
        total_memory_bytes=128 * 1024**3,
        apple_model="Mac17,1",
        apple_chip=chip,
    )


def _report(
    *,
    runtime: str = "llama.cpp",
    model: str = "synthetic-8b",
    hardware: HardwareProfile | None = None,
    suite: EvaluationSuiteProfile | None = None,
    successful: bool = True,
    include_behavior: bool = False,
) -> LocalModelValidationReport:
    return LocalModelValidationReport(
        generated_at=datetime(2026, 9, 19, tzinfo=UTC),
        ally_version="0.1.0.dev0",
        endpoint="http://127.0.0.1:8080/v1",
        model=model,
        runtime=RuntimeProfile(
            name=runtime,
            version="1.2.3",
            model_source="example/synthetic-8b",
            quantization="Q4_K_M",
            model_size_bytes=5 * 1024**3,
            context_length=8192,
            parameters=(RuntimeParameter(name="threads", value="12"),),
        ),
        observations=PerformanceObservations(
            model_load_ms=1250.0,
            time_to_first_token_ms=210.0,
            prompt_tokens_per_second=320.5,
            generation_tokens_per_second=42.5,
            peak_memory_bytes=8 * 1024**3,
            maximum_tested_context_tokens=8192,
            memory_pressure="normal",
            thermal_state="nominal",
        ),
        evaluation_suite=suite
        or EvaluationSuiteProfile(
            core_sha256="a" * 64,
            provider_sha256="b" * 64,
            behavioral_sha256="e" * 64 if include_behavior else None,
        ),
        hardware=hardware or _hardware(),
        core=_summary(successful=successful),
        provider=_summary(successful=successful),
        behavior=(
            _summary(successful=successful)
            if include_behavior
            else None
        ),
        duration_ms=3500.0,
    )


def test_behavior_evidence_requires_matching_suite_fingerprint() -> None:
    raw = _report().model_dump(mode="python")
    raw["behavior"] = _summary()
    with pytest.raises(ValidationError, match="must appear together"):
        LocalModelValidationReport.model_validate(raw)

    raw = _report().model_dump(mode="python")
    raw["evaluation_suite"]["behavioral_sha256"] = "e" * 64
    with pytest.raises(ValidationError, match="must appear together"):
        LocalModelValidationReport.model_validate(raw)


def test_behavior_evidence_is_preserved_in_neutral_comparison() -> None:
    first = _report(model="candidate-a", include_behavior=True)
    second = _report(model="candidate-b", include_behavior=True)

    comparison = compare_validation_reports(
        (("a.json", first), ("b.json", second))
    )

    assert comparison.candidates[0].behavior_passed == 1
    assert comparison.candidates[0].behavior_total == 1
    assert comparison.same_evaluation_suite


def test_runtime_metadata_rejects_secret_like_and_duplicate_parameters() -> None:
    with pytest.raises(ValidationError, match="secret material"):
        RuntimeParameter(name="api-key", value="do-not-store")

    with pytest.raises(ValidationError, match="printable text"):
        RuntimeParameter(name="threads", value="12\nunsafe")

    duplicate = RuntimeParameter(name="threads", value="12")
    with pytest.raises(ValidationError, match="must be unique"):
        RuntimeProfile(
            name="runtime",
            version="1",
            parameters=(duplicate, duplicate),
        )

    with pytest.raises(ValidationError, match="access material"):
        RuntimeProfile(
            name="runtime",
            version="1",
            model_source="https://models.example/model?token=unsafe",
        )


def test_local_model_command_redacts_invalid_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_marker = "VERY-SENSITIVE-VALUE"

    result = run_local_model_validation_command(
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic",
        runtime_name="runtime",
        runtime_version="1",
        model_source=None,
        quantization=None,
        precision=None,
        model_size_bytes=None,
        context_length=None,
        runtime_parameters=(f"api_key={secret_marker}",),
        model_load_ms=None,
        time_to_first_token_ms=None,
        prompt_tokens_per_second=None,
        generation_tokens_per_second=None,
        peak_memory_bytes=None,
        maximum_tested_context_tokens=None,
        memory_pressure="unknown",
        thermal_state="unknown",
        core_case_file="unused.jsonl",
        provider_case_file="unused.jsonl",
        behavior_case_file=None,
        output=str(tmp_path / "unused.json"),
    )

    output = capsys.readouterr().out
    assert result == 2
    assert "metadata is invalid" in output
    assert secret_marker not in output


def test_validation_report_round_trip_is_strict_and_non_overwriting(
    tmp_path: Path,
) -> None:
    report = _report()
    path = tmp_path / "candidate.json"

    assert write_validation_report(report, path) == path.resolve()
    assert load_validation_report(path) == report

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_validation_report(report, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValidationReportError, match="invalid Ally"):
        load_validation_report(path)


def test_comparison_preserves_evidence_without_selecting_a_winner() -> None:
    first = _report(runtime="llama.cpp", model="candidate-a")
    second = _report(runtime="MLX LM", model="candidate-b")

    comparison = compare_validation_reports(
        (("a.json", first), ("b.json", second))
    )

    assert comparison.same_hardware
    assert comparison.same_evaluation_suite
    assert comparison.same_ally_version
    assert comparison.warnings == ()
    assert [candidate.model for candidate in comparison.candidates] == [
        "candidate-a",
        "candidate-b",
    ]
    assert comparison.candidates[0].generation_tokens_per_second == 42.5
    assert "winner" not in comparison.model_dump_json().lower()
    assert "recommend" not in comparison.model_dump_json().lower()


def test_comparison_warns_when_hardware_or_evaluations_differ() -> None:
    different_suite = EvaluationSuiteProfile(
        core_sha256="c" * 64,
        provider_sha256="d" * 64,
    )
    comparison = compare_validation_reports(
        (
            ("a.json", _report()),
            (
                "b.json",
                _report(
                    hardware=_hardware(chip="Different chip"),
                    suite=different_suite,
                ),
            ),
        )
    )

    assert not comparison.same_hardware
    assert not comparison.same_evaluation_suite
    assert len(comparison.warnings) == 2
    assert "Hardware profiles differ" in comparison.warnings[0]
    assert "Evaluation fingerprints differ" in comparison.warnings[1]


def test_comparison_warns_when_ally_versions_differ() -> None:
    first = _report()
    second = _report().model_copy(update={"ally_version": "0.2.0"})

    comparison = compare_validation_reports(
        (("a.json", first), ("b.json", second))
    )

    assert not comparison.same_ally_version
    assert comparison.warnings == (
        "Ally versions differ; behavior and results are not directly comparable.",
    )


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://models.example/v1",
        "http://user:password@127.0.0.1:8080/v1",
        "http://127.0.0.1:8080/v1?api_key=unsafe",
    ),
)
def test_validation_report_requires_credential_free_loopback_endpoint(
    endpoint: str,
) -> None:
    raw = _report().model_dump(mode="python")
    raw["endpoint"] = endpoint

    with pytest.raises(ValidationError, match="credential-free loopback"):
        LocalModelValidationReport.model_validate(raw)


def test_comparison_requires_two_reports() -> None:
    with pytest.raises(ValueError, match="at least two"):
        compare_validation_reports((("only.json", _report()),))


def test_compare_command_supports_human_and_json_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = write_validation_report(_report(model="candidate-a"), tmp_path / "a.json")
    second = write_validation_report(_report(model="candidate-b"), tmp_path / "b.json")

    assert run_compare_validation_reports(
        report_paths=(str(first), str(second)),
        json_output=False,
    ) == 0
    human = capsys.readouterr().out
    assert "Candidate: a.json" in human
    assert "Generation rate: 42.5 tok/s" in human
    assert "No default is selected automatically" in human

    assert run_compare_validation_reports(
        report_paths=(str(first), str(second)),
        json_output=True,
    ) == 0
    structured = json.loads(capsys.readouterr().out)
    assert structured["same_hardware"] is True
    assert structured["same_ally_version"] is True
    assert [item["model"] for item in structured["candidates"]] == [
        "candidate-a",
        "candidate-b",
    ]


def test_compare_command_rejects_invalid_or_ambiguous_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    assert run_compare_validation_reports(
        report_paths=(str(invalid), str(tmp_path / "missing.json")),
        json_output=False,
    ) == 2
    assert "invalid Ally validation report" in capsys.readouterr().out

    first = tmp_path / "first" / "same.json"
    second = tmp_path / "second" / "same.json"
    first.parent.mkdir()
    second.parent.mkdir()
    write_validation_report(_report(), first)
    write_validation_report(_report(), second)
    assert run_compare_validation_reports(
        report_paths=(str(first), str(second)),
        json_output=False,
    ) == 2
    assert "filenames must be unique" in capsys.readouterr().out
