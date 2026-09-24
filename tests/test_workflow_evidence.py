from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ally import __version__
from ally.commands import validate as validate_commands
from ally.diagnostics import (
    EvaluationSuiteProfile,
    FunctionalWorkflowEvidenceError,
    HardwareProfile,
    LocalModelValidationReport,
    RuntimeProfile,
    SyntheticWorkflowCheck,
    SyntheticWorkflowReport,
    build_functional_workflow_report,
    load_functional_workflow_report,
    verify_functional_workflow_source,
    write_functional_workflow_report,
    write_validation_report,
)
from ally.evals import EvalResult, EvalSummary
from ally.models import ChatRequest, ChatResponse


class DeterministicWorkflowProvider:
    @property
    def name(self) -> str:
        return "synthetic-workflow-provider"

    def __enter__(self) -> DeterministicWorkflowProvider:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def chat(self, request: ChatRequest) -> ChatResponse:
        system_text = "\n".join(
            message.content
            for message in request.messages
            if message.role == "system"
        )
        user_text = request.messages[-1].content

        if "planning component" in system_text:
            content = json.dumps(
                {
                    "goal": "Inspect the synthetic validation runtime",
                    "steps": [{"tool_name": "system.info", "arguments": {}}],
                }
            )
        elif "extract durable personal memory candidates" in system_text:
            content = json.dumps(
                {
                    "memories": [
                        {
                            "kind": "preference",
                            "content": "Synthetic subject prefers jasmine tea.",
                            "confidence": 0.99,
                            "importance": 0.8,
                        }
                    ]
                }
            )
        elif "retrieved reference" in user_text:
            content = "GLASS-482"
        elif "What synthetic validation token" in user_text:
            content = "ORCHID-731"
        elif "Remember the synthetic validation token" in user_text:
            content = "STORED_OK"
        else:
            raise AssertionError("unexpected synthetic validation prompt")

        return ChatResponse(
            content=content,
            model="synthetic-model",
            provider=self.name,
        )


def _summary() -> EvalSummary:
    result = EvalResult(
        case_id="synthetic",
        category="provider_response",
        evaluator="synthetic",
        status="passed",
        message="",
        duration_ms=1.0,
    )
    return EvalSummary(
        total=1,
        passed=1,
        failed=0,
        errors=0,
        results=(result,),
    )


def _validation(*, model: str = "synthetic-model") -> LocalModelValidationReport:
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
        core=_summary(),
        provider=_summary(),
        behavior=_summary(),
        duration_ms=1000.0,
    )


def _workflow(
    *,
    model: str = "synthetic-model",
    successful: bool = True,
) -> SyntheticWorkflowReport:
    return SyntheticWorkflowReport(
        generated_at=datetime(2026, 9, 24, tzinfo=UTC),
        ally_version=__version__,
        provider="synthetic",
        model=model,
        checks=(
            SyntheticWorkflowCheck(
                id="conversation.persistence",
                status="passed" if successful else "failed",
                duration_ms=10.0,
                error_class=None if successful else "AssertionError",
            ),
        ),
        duration_ms=10.0,
    )


def test_functional_workflow_evidence_round_trip_and_source_verification(
    tmp_path: Path,
) -> None:
    validation_path = write_validation_report(
        _validation(),
        tmp_path / "validation.json",
    )
    report = build_functional_workflow_report(
        validation_path=validation_path,
        workflow=_workflow(),
    )
    report_path = write_functional_workflow_report(
        report,
        tmp_path / "workflows.json",
    )

    loaded = load_functional_workflow_report(report_path)

    assert loaded == report
    assert loaded.qualified_for_candidate_use
    assert verify_functional_workflow_source(loaded, validation_path).model == (
        "synthetic-model"
    )

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_functional_workflow_report(report, report_path)


def test_functional_workflow_evidence_rejects_mismatched_source(
    tmp_path: Path,
) -> None:
    first_validation = write_validation_report(
        _validation(model="model-a"),
        tmp_path / "a.json",
    )
    second_validation = write_validation_report(
        _validation(model="model-b"),
        tmp_path / "b.json",
    )
    report = build_functional_workflow_report(
        validation_path=first_validation,
        workflow=_workflow(model="model-a"),
    )

    with pytest.raises(FunctionalWorkflowEvidenceError, match="does not match"):
        verify_functional_workflow_source(report, second_validation)


def test_failed_workflow_is_preserved_but_not_qualified(
    tmp_path: Path,
) -> None:
    validation_path = write_validation_report(
        _validation(),
        tmp_path / "validation.json",
    )
    report = build_functional_workflow_report(
        validation_path=validation_path,
        workflow=_workflow(successful=False),
    )

    assert report.workflow_successful is False
    assert report.qualified_for_candidate_use is False
    assert report.checks[0].error_class == "AssertionError"


def test_functional_workflow_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    validation_path = write_validation_report(
        _validation(),
        tmp_path / "validation.json",
    )
    report = build_functional_workflow_report(
        validation_path=validation_path,
        workflow=_workflow(),
    )
    report_path = write_functional_workflow_report(
        report,
        tmp_path / "workflows.json",
    )
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    report_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(FunctionalWorkflowEvidenceError, match="invalid Ally"):
        load_functional_workflow_report(report_path)


def test_workflow_command_writes_source_bound_payload_free_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    validation_path = write_validation_report(
        _validation(),
        tmp_path / "validation.json",
    )
    workflow_path = tmp_path / "workflows.json"

    def provider_factory(
        *,
        base_url: str,
        model: str,
    ) -> DeterministicWorkflowProvider:
        assert base_url == "http://127.0.0.1:8080/v1"
        assert model == "synthetic-model"
        return DeterministicWorkflowProvider()

    monkeypatch.setattr(
        validate_commands,
        "OpenAICompatibleProvider",
        provider_factory,
    )

    result = validate_commands.run_synthetic_workflow_validation(
        validation_report=str(validation_path),
        output=str(workflow_path),
        json_output=True,
    )
    output = capsys.readouterr().out
    rendered = json.loads(output)

    assert result == 0
    assert rendered["qualified_for_candidate_use"] is True
    assert "ORCHID-731" not in output
    assert "GLASS-482" not in output
    assert "jasmine" not in output.lower()

    report = load_functional_workflow_report(workflow_path)
    assert report.qualified_for_candidate_use
    verify_functional_workflow_source(report, validation_path)
