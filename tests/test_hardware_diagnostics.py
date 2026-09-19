from pathlib import Path

from ally.diagnostics.hardware import HardwareProfile, collect_hardware_profile
from ally.diagnostics.validation import (
    run_local_model_validation,
    write_validation_report,
)
from ally.models import ChatRequest, ChatResponse


class DeterministicProvider:
    @property
    def name(self) -> str:
        return "deterministic"

    def chat(self, request: ChatRequest) -> ChatResponse:
        prompt = request.messages[-1].content
        content = "ALLY_OK" if "exactly ALLY_OK" in prompt else "SYSTEM_OK"
        return ChatResponse(
            content=content,
            model="synthetic",
            provider=self.name,
        )


def test_hardware_profile_collects_non_sensitive_basics() -> None:
    profile = collect_hardware_profile()

    assert profile.system
    assert profile.release
    assert profile.machine
    assert profile.python_version


def test_local_model_validation_composes_existing_eval_framework(
    tmp_path: Path,
) -> None:
    core_cases = tmp_path / "core.jsonl"
    core_cases.write_text(
        (
            '{"id":"privacy","category":"private_grounding_policy",'
            '"input":{"endpoint":"http://127.0.0.1:8080/v1",'
            '"allow_remote_private_context":false},'
            '"expected":{"allowed":true}}\n'
        ),
        encoding="utf-8",
    )
    provider_cases = tmp_path / "provider.jsonl"
    provider_cases.write_text(
        (
            '{"id":"provider","category":"provider_response",'
            '"input":{"prompt":"Reply with exactly ALLY_OK and nothing else."},'
            '"expected":{"exact":"ALLY_OK"}}\n'
        ),
        encoding="utf-8",
    )
    hardware = HardwareProfile(
        system="SyntheticOS",
        release="1",
        machine="synthetic",
        processor="synthetic",
        python_version="3.12",
        logical_cpu_count=8,
        total_memory_bytes=128 * 1024**3,
    )

    report = run_local_model_validation(
        provider=DeterministicProvider(),
        endpoint="http://127.0.0.1:8080/v1",
        model="synthetic",
        core_case_file=core_cases,
        provider_case_file=provider_cases,
        hardware=hardware,
    )

    assert report.successful
    assert report.core.passed == 1
    assert report.provider.passed == 1
    assert report.hardware == hardware

    destination = write_validation_report(report, tmp_path / "reports" / "run.json")
    assert destination.is_file()
    rendered = destination.read_text(encoding="utf-8")
    assert '"model": "synthetic"' in rendered
    assert '"system": "SyntheticOS"' in rendered
