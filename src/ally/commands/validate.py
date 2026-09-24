"""First-machine and local-model validation commands."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from ally.diagnostics import (
    ArtifactFingerprint,
    CandidateEvidence,
    FirstMachineReadinessReport,
    FunctionalWorkflowEvidenceError,
    FunctionalWorkflowEvidenceReport,
    LocalModelValidationReport,
    NetworkObservationMethod,
    PerformanceObservations,
    RuntimeIsolationMode,
    RuntimeParameter,
    RuntimePrivacyChecks,
    RuntimePrivacyEvidenceError,
    RuntimePrivacyQualificationReport,
    RuntimeProfile,
    SyntheticWorkflowReport,
    ValidationReportError,
    build_candidate_evidence,
    build_functional_workflow_report,
    build_runtime_privacy_report,
    collect_first_machine_readiness,
    collect_hardware_profile,
    compare_candidate_evidence,
    compare_validation_reports,
    fingerprint_artifact,
    load_functional_workflow_report,
    load_runtime_privacy_report,
    load_validation_report,
    run_isolated_synthetic_workflows,
    run_local_model_validation,
    verify_functional_workflow_source,
    verify_runtime_privacy_source,
    write_functional_workflow_report,
    write_runtime_privacy_report,
    write_validation_report,
)
from ally.evals.resources import evaluation_case_file
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


def _artifact_fingerprints(values: Sequence[str]) -> tuple[ArtifactFingerprint, ...]:
    return tuple(fingerprint_artifact(Path(value)) for value in values)


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
    model_artifacts: Sequence[str],
    runtime_artifacts: Sequence[str],
    model_load_ms: float | None,
    time_to_first_token_ms: float | None,
    prompt_tokens_per_second: float | None,
    generation_tokens_per_second: float | None,
    peak_memory_bytes: int | None,
    maximum_tested_context_tokens: int | None,
    memory_pressure: str,
    thermal_state: str,
    core_case_file: str | None,
    provider_case_file: str | None,
    behavior_case_file: str | None,
    output: str,
) -> int:
    try:
        model_fingerprints = _artifact_fingerprints(model_artifacts)
        runtime_fingerprints = _artifact_fingerprints(runtime_artifacts)
        effective_model_size = model_size_bytes
        if model_fingerprints and effective_model_size is None:
            effective_model_size = sum(
                artifact.size_bytes for artifact in model_fingerprints
            )
        runtime = RuntimeProfile(
            name=runtime_name,
            version=runtime_version,
            model_source=model_source,
            quantization=quantization,
            precision=precision,
            model_size_bytes=effective_model_size,
            context_length=context_length,
            parameters=_runtime_parameters(runtime_parameters),
            model_artifacts=model_fingerprints,
            runtime_artifacts=runtime_fingerprints,
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
        with (
            evaluation_case_file("core", core_case_file) as core_path,
            evaluation_case_file("provider-smoke", provider_case_file) as provider_path,
            evaluation_case_file(
                "behavioral-qualification",
                behavior_case_file,
            ) as behavior_path,
            OpenAICompatibleProvider(
                base_url=endpoint,
                model=model,
            ) as provider,
        ):
            report = run_local_model_validation(
                provider=provider,
                endpoint=endpoint,
                model=model,
                runtime=runtime,
                observations=observations,
                core_case_file=core_path,
                provider_case_file=provider_path,
                behavior_case_file=behavior_path,
            )
        destination = write_validation_report(report, Path(output))
    except ValidationError:
        print("Validation error: runtime or observation metadata is invalid.")
        return 2
    except (FileExistsError, ModelProviderError, OSError, ValueError) as exc:
        print(f"Validation error: {exc}")
        return 2

    print(f"Validation report: {destination}")
    if report.runtime.model_artifacts:
        print(f"Model artifacts fingerprinted: {len(report.runtime.model_artifacts)}")
    if report.runtime.runtime_artifacts:
        print(
            f"Runtime artifacts fingerprinted: "
            f"{len(report.runtime.runtime_artifacts)}"
        )
    print(
        f"Core: {report.core.passed}/{report.core.total} passed; "
        f"provider: {report.provider.passed}/{report.provider.total} passed; "
        f"behavior: "
        f"{report.behavior.passed if report.behavior is not None else 0}/"
        f"{report.behavior.total if report.behavior is not None else 0} passed"
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
        if candidate.behavior_total is not None:
            print(
                f"  Behavior: {candidate.behavior_passed}/"
                f"{candidate.behavior_total}"
            )
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



def run_runtime_privacy_qualification(
    *,
    validation_report: str,
    isolation_mode: RuntimeIsolationMode,
    network_observation: NetworkObservationMethod,
    inference_with_egress_blocked: str,
    synthetic_chat: str,
    synthetic_planning: str,
    synthetic_memory_proposal: str,
    synthetic_grounding: str,
    no_cloud_auth_required: str,
    no_cloud_fallback_observed: str,
    no_prompt_telemetry_observed: str,
    no_unexpected_outbound_connections: str,
    output: str,
) -> int:
    """Record fail-closed runtime privacy evidence tied to one validation report."""

    try:
        checks = RuntimePrivacyChecks.model_validate(
            {
                "inference_with_egress_blocked": inference_with_egress_blocked,
                "synthetic_chat": synthetic_chat,
                "synthetic_planning": synthetic_planning,
                "synthetic_memory_proposal": synthetic_memory_proposal,
                "synthetic_grounding": synthetic_grounding,
                "no_cloud_auth_required": no_cloud_auth_required,
                "no_cloud_fallback_observed": no_cloud_fallback_observed,
                "no_prompt_telemetry_observed": no_prompt_telemetry_observed,
                "no_unexpected_outbound_connections": (
                    no_unexpected_outbound_connections
                ),
            }
        )
        report = build_runtime_privacy_report(
            validation_path=Path(validation_report),
            isolation_mode=isolation_mode,
            network_observation=network_observation,
            checks=checks,
        )
        destination = write_runtime_privacy_report(report, Path(output))
    except ValidationError:
        print("Runtime privacy error: evidence metadata is invalid.")
        return 2
    except (
        FileExistsError,
        OSError,
        RuntimePrivacyEvidenceError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Runtime privacy error: {exc}")
        return 2

    print(f"Runtime privacy report: {destination}")
    print(
        "Qualified for private inference: "
        f"{'yes' if report.qualified_for_private_inference else 'no'}"
    )
    for name, value in report.checks.model_dump(mode="python").items():
        print(f"{name}: {value}")
    return 0 if report.qualified_for_private_inference else 1


def run_show_runtime_privacy_report(
    *,
    report_path: str,
    json_output: bool,
) -> int:
    """Inspect one runtime privacy artifact without modifying it."""

    try:
        report: RuntimePrivacyQualificationReport = load_runtime_privacy_report(
            Path(report_path)
        )
    except RuntimePrivacyEvidenceError as exc:
        print(f"Runtime privacy error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["qualified_for_private_inference"] = (
            report.qualified_for_private_inference
        )
        print(json.dumps(rendered, indent=2, sort_keys=True))
        return 0

    print(
        "Qualified for private inference: "
        f"{'yes' if report.qualified_for_private_inference else 'no'}"
    )
    print(f"Runtime: {report.runtime.name} {report.runtime.version}")
    print(f"Model: {report.model}")
    print(f"Isolation mode: {report.isolation_mode}")
    print(f"Network observation: {report.network_observation}")
    print(f"Source validation SHA-256: {report.source_validation_sha256}")
    for name, value in report.checks.model_dump(mode="python").items():
        print(f"{name}: {value}")
    return 0 if report.qualified_for_private_inference else 1



def run_verify_runtime_privacy_report(
    *,
    report_path: str,
    validation_report: str,
    json_output: bool,
) -> int:
    """Verify one privacy artifact against the exact capability report."""

    try:
        report = load_runtime_privacy_report(Path(report_path))
        verify_runtime_privacy_source(report, Path(validation_report))
    except (RuntimePrivacyEvidenceError, ValidationReportError) as exc:
        print(f"Runtime privacy verification error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "source_matches": True,
                    "qualified_for_private_inference": (
                        report.qualified_for_private_inference
                    ),
                    "source_validation_sha256": report.source_validation_sha256,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Source matches: yes")
        print(
            "Qualified for private inference: "
            f"{'yes' if report.qualified_for_private_inference else 'no'}"
        )
    return 0 if report.qualified_for_private_inference else 1



def _candidate_summary(candidate: CandidateEvidence) -> dict[str, object]:
    return candidate.model_dump(mode="json")


def run_show_candidate_evidence(
    *,
    validation_report: str,
    privacy_report: str,
    workflow_report: str,
    json_output: bool,
) -> int:
    """Inspect one exact capability/privacy/workflow evidence set."""

    try:
        candidate = build_candidate_evidence(
            validation_path=Path(validation_report),
            privacy_path=Path(privacy_report),
            workflow_path=Path(workflow_report),
        )
    except (
        FunctionalWorkflowEvidenceError,
        RuntimePrivacyEvidenceError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Candidate evidence error: {exc}")
        return 2

    if json_output:
        print(json.dumps(_candidate_summary(candidate), indent=2, sort_keys=True))
    else:
        print(
            "Production eligible: "
            f"{'yes' if candidate.production_eligible else 'no'}"
        )
        print(
            "Capability validation: "
            f"{'pass' if candidate.capability_successful else 'fail'}"
        )
        print(
            "Runtime privacy: "
            f"{'qualified' if candidate.privacy_qualified else 'unqualified'}"
        )
        print(
            "Functional workflows: "
            f"{'qualified' if candidate.workflow_qualified else 'unqualified'}"
        )
        print(f"Runtime: {candidate.runtime.name} {candidate.runtime.version}")
        print(f"Model: {candidate.model}")
        print(f"Isolation mode: {candidate.isolation_mode}")
        print(f"Network observation: {candidate.network_observation}")
        print(f"Core: {candidate.core_passed}/{candidate.core_total}")
        print(f"Provider: {candidate.provider_passed}/{candidate.provider_total}")
        if candidate.behavior_total is not None:
            print(
                f"Behavior: {candidate.behavior_passed}/"
                f"{candidate.behavior_total}"
            )
        workflow_passed = sum(
            check.status == "passed" for check in candidate.workflow_checks
        )
        print(
            f"Workflows: {workflow_passed}/{len(candidate.workflow_checks)} passed"
        )
        print(
            "Time to first token: "
            f"{_optional(candidate.observations.time_to_first_token_ms, suffix=' ms')}"
        )
        print(
            "Generation rate: "
            f"{_optional(candidate.observations.generation_tokens_per_second, suffix=' tok/s')}"
        )
        print(
            "Peak memory: "
            f"{_optional(candidate.observations.peak_memory_bytes, suffix=' bytes')}"
        )
    return 0 if candidate.production_eligible else 1


def run_compare_candidate_evidence(
    *,
    evidence_sets: Sequence[Sequence[str]],
    json_output: bool,
) -> int:
    """Compare exact verified evidence sets without choosing a winner."""

    try:
        if len(evidence_sets) < 2:
            raise ValueError(
                "candidate comparison requires at least two --candidate values"
            )
        candidates: list[CandidateEvidence] = []
        labels: set[tuple[str, str, str]] = set()
        for evidence_set in evidence_sets:
            if len(evidence_set) != 3:
                raise ValueError(
                    "each --candidate requires VALIDATION PRIVACY WORKFLOWS"
                )
            validation_report, privacy_report, workflow_report = evidence_set
            label = (
                Path(validation_report).name,
                Path(privacy_report).name,
                Path(workflow_report).name,
            )
            if label in labels:
                raise ValueError("candidate evidence sets must be unique")
            labels.add(label)
            candidates.append(
                build_candidate_evidence(
                    validation_path=Path(validation_report),
                    privacy_path=Path(privacy_report),
                    workflow_path=Path(workflow_report),
                )
            )
        comparison = compare_candidate_evidence(candidates)
    except (
        FunctionalWorkflowEvidenceError,
        RuntimePrivacyEvidenceError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Candidate comparison error: {exc}")
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
        print(
            f"\nCandidate: {candidate.validation_report} + "
            f"{candidate.privacy_report} + {candidate.workflow_report}"
        )
        print(
            "  Production eligible: "
            f"{'yes' if candidate.production_eligible else 'no'}"
        )
        print(
            "  Capability: "
            f"{'pass' if candidate.capability_successful else 'fail'}"
        )
        print(
            "  Privacy: "
            f"{'qualified' if candidate.privacy_qualified else 'unqualified'}"
        )
        print(
            "  Workflows: "
            f"{'qualified' if candidate.workflow_qualified else 'unqualified'}"
        )
        print(f"  Runtime: {candidate.runtime.name} {candidate.runtime.version}")
        print(f"  Model: {candidate.model}")
        print(f"  Isolation: {candidate.isolation_mode}")
        print(f"  Network observation: {candidate.network_observation}")
        print(f"  Core: {candidate.core_passed}/{candidate.core_total}")
        print(f"  Provider: {candidate.provider_passed}/{candidate.provider_total}")
        if candidate.behavior_total is not None:
            print(
                f"  Behavior: {candidate.behavior_passed}/"
                f"{candidate.behavior_total}"
            )
        workflow_passed = sum(
            check.status == "passed" for check in candidate.workflow_checks
        )
        print(
            f"  Workflow checks: {workflow_passed}/"
            f"{len(candidate.workflow_checks)}"
        )
        print(
            "  Time to first token: "
            f"{_optional(candidate.observations.time_to_first_token_ms, suffix=' ms')}"
        )
        print(
            "  Generation rate: "
            f"{_optional(candidate.observations.generation_tokens_per_second, suffix=' tok/s')}"
        )
        print(
            "  Peak memory: "
            f"{_optional(candidate.observations.peak_memory_bytes, suffix=' bytes')}"
        )
        print(f"  Memory pressure: {candidate.memory_pressure}")
        print(f"  Thermal state: {candidate.thermal_state}")

    print(
        "\nNo default is selected automatically; review only verified, "
        "production-eligible candidates."
    )
    return 0


def run_first_machine_readiness(*, json_output: bool) -> int:
    """Inspect readiness without mutating Ally state or external services."""

    report: FirstMachineReadinessReport = collect_first_machine_readiness()

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["ready_to_begin_validation"] = report.ready_to_begin_validation
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(
            "Ready to begin validation: "
            f"{'yes' if report.ready_to_begin_validation else 'no'}"
        )
        print(f"Ally version: {report.ally_version}")
        print(f"Target: {report.hardware.system} {report.hardware.machine}")
        if report.hardware.apple_chip is not None:
            print(f"Apple chip: {report.hardware.apple_chip}")
        for check in report.checks:
            print(f"[{check.severity.upper()}] {check.id}: {check.summary}")

    return 0 if report.ready_to_begin_validation else 2



def run_synthetic_workflow_validation(
    *,
    validation_report: str,
    output: str,
    json_output: bool,
) -> int:
    """Run disposable workflows and bind evidence to one capability report."""

    try:
        validation = load_validation_report(Path(validation_report))
        with OpenAICompatibleProvider(
            base_url=validation.endpoint,
            model=validation.model,
        ) as provider:
            workflow: SyntheticWorkflowReport = run_isolated_synthetic_workflows(
                provider=provider,
                model=validation.model,
            )
        report = build_functional_workflow_report(
            validation_path=Path(validation_report),
            workflow=workflow,
        )
        destination = write_functional_workflow_report(report, Path(output))
    except (
        FileExistsError,
        FunctionalWorkflowEvidenceError,
        ModelProviderError,
        OSError,
        ValidationReportError,
        ValueError,
    ) as exc:
        print(f"Synthetic workflow validation error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["qualified_for_candidate_use"] = (
            report.qualified_for_candidate_use
        )
        rendered["report_path"] = str(destination)
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(f"Functional workflow report: {destination}")
        print(
            "Qualified for candidate use: "
            f"{'yes' if report.qualified_for_candidate_use else 'no'}"
        )
        for check in report.checks:
            suffix = (
                ""
                if check.error_class is None
                else f" error={check.error_class}"
            )
            print(
                f"[{check.status.upper()}] {check.id} "
                f"({check.duration_ms:.1f} ms){suffix}"
            )
        print(f"Total duration: {report.duration_ms:.1f} ms")

    return 0 if report.qualified_for_candidate_use else 1


def run_show_functional_workflow_report(
    *,
    report_path: str,
    json_output: bool,
) -> int:
    """Inspect one functional workflow artifact without modifying it."""

    try:
        report: FunctionalWorkflowEvidenceReport = (
            load_functional_workflow_report(Path(report_path))
        )
    except FunctionalWorkflowEvidenceError as exc:
        print(f"Functional workflow error: {exc}")
        return 2

    if json_output:
        rendered = report.model_dump(mode="json")
        rendered["qualified_for_candidate_use"] = (
            report.qualified_for_candidate_use
        )
        print(json.dumps(rendered, indent=2, sort_keys=True))
    else:
        print(
            "Qualified for candidate use: "
            f"{'yes' if report.qualified_for_candidate_use else 'no'}"
        )
        print(f"Runtime: {report.runtime.name} {report.runtime.version}")
        print(f"Model: {report.model}")
        print(f"Source validation SHA-256: {report.source_validation_sha256}")
        for check in report.checks:
            print(f"{check.id}: {check.status}")
    return 0 if report.qualified_for_candidate_use else 1


def run_verify_functional_workflow_report(
    *,
    report_path: str,
    validation_report: str,
    json_output: bool,
) -> int:
    """Verify one functional artifact against the exact capability report."""

    try:
        report = load_functional_workflow_report(Path(report_path))
        verify_functional_workflow_source(report, Path(validation_report))
    except (
        FunctionalWorkflowEvidenceError,
        ValidationReportError,
    ) as exc:
        print(f"Functional workflow verification error: {exc}")
        return 2

    if json_output:
        print(
            json.dumps(
                {
                    "source_matches": True,
                    "qualified_for_candidate_use": (
                        report.qualified_for_candidate_use
                    ),
                    "source_validation_sha256": report.source_validation_sha256,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print("Source matches: yes")
        print(
            "Qualified for candidate use: "
            f"{'yes' if report.qualified_for_candidate_use else 'no'}"
        )
    return 0 if report.qualified_for_candidate_use else 1
