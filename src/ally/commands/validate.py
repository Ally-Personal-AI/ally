"""First-machine and local-model validation commands."""

from __future__ import annotations

import json
from pathlib import Path

from ally.diagnostics import (
    collect_hardware_profile,
    run_local_model_validation,
    write_validation_report,
)
from ally.models.errors import ModelProviderError
from ally.models.providers import OpenAICompatibleProvider


def run_hardware_report(*, json_output: bool) -> int:
    profile = collect_hardware_profile()
    if json_output:
        print(json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(f"System: {profile.system} {profile.release}")
        print(f"Machine: {profile.machine}")
        print(f"Processor: {profile.processor or '(unknown)'}")
        print(f"Python: {profile.python_version}")
        print(f"Logical CPUs: {profile.logical_cpu_count or '(unknown)'}")
        print(f"Memory bytes: {profile.total_memory_bytes or '(unknown)'}")
        if profile.apple_model is not None:
            print(f"Apple model: {profile.apple_model}")
        if profile.apple_chip is not None:
            print(f"Apple chip: {profile.apple_chip}")
    return 0


def run_local_model_validation_command(
    *,
    endpoint: str,
    model: str,
    core_case_file: str,
    provider_case_file: str,
    output: str,
) -> int:
    try:
        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=False,
        ) as provider:
            report = run_local_model_validation(
                provider=provider,
                endpoint=endpoint,
                model=model,
                core_case_file=Path(core_case_file),
                provider_case_file=Path(provider_case_file),
            )
    except (ModelProviderError, ValueError) as exc:
        print(f"Validation error: {exc}")
        return 2

    destination = write_validation_report(report, Path(output))
    print(f"Validation report: {destination}")
    print(
        f"Core: {report.core.passed}/{report.core.total} passed; "
        f"provider: {report.provider.passed}/{report.provider.total} passed"
    )
    return 0 if report.successful else 1
