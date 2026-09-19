"""First-machine and local-model validation commands."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ally.diagnostics import (
    LocalModelValidationReport,
    PerformanceObservations,
    RuntimeParameter,
    RuntimeProfile,
    ValidationReportError,
    collect_hardware_profile,
    compare_validation_reports,
    load_validation_report,
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


def _runtime_parameters(values: Sequence[str]) -> tuple[RuntimeParameter, ...]:
    parameters: list[RuntimeParameter] = []
    for value in values:
        name, separator, setting = value.partition("=")
        if not separator or not name or not setting:
            raise ValueError("runtime parameters must use NAME=VALUE")
        parameters.append(RuntimeParameter(name=name, value=setting))
    return tuple(parameters)


def run_local_model_validation_command(
    *,
    endpoint: str,
    model: str,
    runtime_name: str,
    runtime_version: str,
    model_source: str | None,
    quantization: str | None,
    precision: str | None,
    model_size_bytes: int | None,
    context_length: int | None,
    runtime_parameters: Sequence[str],
    model_load_ms: float | None,
    time_to_first_token_ms: float | None,
    prompt_tokens_per_second: float | None,
    generation_tokens_per_second: float | None,
    peak_memory_bytes: int | None,
    maximum_tested_context_tokens: int | None,
    memory_pressure: str,
    thermal_state: str,
    core_case_file: str,
    provider_case_file: str,
    output: str,
) -> int:
    try:
        runtime = RuntimeProfile(
            name=runtime_name,
            version=runtime_version,
            model_source=model_source,
            quantization=quantization,
            precision=precision,
            model_size_bytes=model_size_bytes,
            context_length=context_length,
            parameters=_runtime_parameters(runtime_parameters),
        )
        observations = PerformanceObservations.model_validate(
            {
                "model_load_ms": model_load_ms,
                "time_to_first_token_ms": time_to_first_token_ms,
                "prompt_tokens_per_second": prompt_tokens_per_second,
                "generation_tokens_per_second": generation_tokens_per_second,
                "peak_memory_bytes": peak_memory_bytes,
                "maximum_tested_context_tokens": maximum_tested_context_tokens,
                "memory_pressure": memory_pressure,
                "thermal_state": thermal_state,
            }
        )
        with OpenAICompatibleProvider(
            base_url=endpoint,
            model=model,
            allow_remote=False,
        ) as provider:
            report = run_local_model_validation(
                provider=provider,
                endpoint=endpoint,
                model=model,
                runtime=runtime,
                observations=observations,
                core_case_file=Path(core_case_file),
                provider_case_file=Path(provider_case_file),
            )
        destination = write_validation_report(report, Path(output))
    except ValidationError:
        print("Validation error: runtime or observation metadata is invalid.")
        return 2
    except (FileExistsError, ModelProviderError, OSError, ValueError) as exc:
        print(f"Validation error: {exc}")
        return 2

    print(f"Validation report: {destination}")
    print(
        f"Core: {report.core.passed}/{report.core.total} passed; "
        f"provider: {report.provider.passed}/{report.provider.total} passed"
    )
    return 0 if report.successful else 1


def _optional(value: object, *, suffix: str = "") -> str:
    return "(not recorded)" if value is None else f"{value}{suffix}"


def run_compare_validation_reports(
    *,
    report_paths: Sequence[str],
    json_output: bool,
) -> int:
    try:
        labels = tuple(Path(value).name for value in report_paths)
        if len(labels) != len(set(labels)):
            raise ValueError("validation report filenames must be unique")
        loaded: list[tuple[str, LocalModelValidationReport]] = []
        for label, path in zip(labels, report_paths, strict=True):
            try:
                loaded.append((label, load_validation_report(Path(path))))
            except ValidationReportError as exc:
                raise ValidationReportError(f"{label}: {exc}") from exc
        reports = tuple(loaded)
        comparison = compare_validation_reports(reports)
    except (ValidationReportError, ValueError) as exc:
        print(f"Validation comparison error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                comparison.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(f"Same hardware: {'yes' if comparison.same_hardware else 'no'}")
    print(
        "Same evaluation suite: "
        f"{'yes' if comparison.same_evaluation_suite else 'no'}"
    )
    print(f"Same Ally version: {'yes' if comparison.same_ally_version else 'no'}")
    for warning in comparison.warnings:
        print(f"Warning: {warning}")
    for candidate in comparison.candidates:
        print(f"\nCandidate: {candidate.report}")
        print(f"  Result: {'pass' if candidate.successful else 'fail'}")
        print(f"  Runtime: {candidate.runtime} {candidate.runtime_version}")
        print(f"  Model: {candidate.model}")
        print(f"  Quantization: {_optional(candidate.quantization)}")
        print(f"  Precision: {_optional(candidate.precision)}")
        print(f"  Model size: {_optional(candidate.model_size_bytes, suffix=' bytes')}")
        print(f"  Context: {_optional(candidate.context_length, suffix=' tokens')}")
        print(f"  Core: {candidate.core_passed}/{candidate.core_total}")
        print(f"  Provider: {candidate.provider_passed}/{candidate.provider_total}")
        print(
            "  Time to first token: "
            f"{_optional(candidate.time_to_first_token_ms, suffix=' ms')}"
        )
        print(
            "  Generation rate: "
            f"{_optional(candidate.generation_tokens_per_second, suffix=' tok/s')}"
        )
        print(
            "  Peak memory: "
            f"{_optional(candidate.peak_memory_bytes, suffix=' bytes')}"
        )
        print(f"  Memory pressure: {candidate.memory_pressure}")
        print(f"  Thermal state: {candidate.thermal_state}")
    print("\nNo default is selected automatically; review reliability and resource evidence.")
    return 0
