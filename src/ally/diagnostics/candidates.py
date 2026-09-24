"""Verified capability/privacy candidate evidence and neutral comparison."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ally.diagnostics.hardware import HardwareProfile
from ally.diagnostics.runtime_privacy import (
    NetworkObservationMethod,
    RuntimeIsolationMode,
    RuntimePrivacyChecks,
    RuntimePrivacyQualificationReport,
    load_runtime_privacy_report,
    verify_runtime_privacy_source,
)
from ally.diagnostics.validation import (
    EvaluationSuiteProfile,
    LocalModelValidationReport,
    MemoryPressureState,
    PerformanceObservations,
    RuntimeProfile,
    ThermalState,
    load_validation_report,
)
from ally.diagnostics.workflows import (
    FunctionalWorkflowEvidenceReport,
    SyntheticWorkflowCheck,
    load_functional_workflow_report,
    verify_functional_workflow_source,
)


class CandidateEvidence(BaseModel):
    """One exact, verified capability/privacy evidence pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    validation_report: str
    privacy_report: str
    workflow_report: str
    ally_version: str
    hardware: HardwareProfile
    evaluation_suite: EvaluationSuiteProfile
    runtime: RuntimeProfile
    model: str
    capability_successful: bool
    privacy_qualified: bool
    workflow_qualified: bool
    production_eligible: bool
    isolation_mode: RuntimeIsolationMode
    network_observation: NetworkObservationMethod
    privacy_checks: RuntimePrivacyChecks
    workflow_checks: tuple[SyntheticWorkflowCheck, ...]
    observations: PerformanceObservations
    core_passed: int
    core_total: int
    provider_passed: int
    provider_total: int
    behavior_passed: int | None
    behavior_total: int | None
    memory_pressure: MemoryPressureState
    thermal_state: ThermalState


class CandidateEvidenceComparison(BaseModel):
    """Neutral comparison of verified candidate evidence sets without ranking."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    same_hardware: bool
    same_evaluation_suite: bool
    same_ally_version: bool
    warnings: tuple[str, ...]
    candidates: tuple[CandidateEvidence, ...]


def build_candidate_evidence(
    *,
    validation_path: Path,
    privacy_path: Path,
    workflow_path: Path,
) -> CandidateEvidence:
    """Load and verify one exact capability/privacy/workflow evidence set."""

    validation: LocalModelValidationReport = load_validation_report(validation_path)
    privacy: RuntimePrivacyQualificationReport = load_runtime_privacy_report(privacy_path)
    workflow: FunctionalWorkflowEvidenceReport = load_functional_workflow_report(
        workflow_path
    )
    verify_runtime_privacy_source(privacy, validation_path)
    verify_functional_workflow_source(workflow, validation_path)

    behavior = validation.behavior
    capability_successful = validation.successful
    privacy_qualified = privacy.qualified_for_private_inference
    workflow_qualified = workflow.qualified_for_candidate_use

    return CandidateEvidence(
        validation_report=validation_path.name,
        privacy_report=privacy_path.name,
        workflow_report=workflow_path.name,
        ally_version=validation.ally_version,
        hardware=validation.hardware,
        evaluation_suite=validation.evaluation_suite,
        runtime=validation.runtime,
        model=validation.model,
        capability_successful=capability_successful,
        privacy_qualified=privacy_qualified,
        workflow_qualified=workflow_qualified,
        production_eligible=(
            capability_successful and privacy_qualified and workflow_qualified
        ),
        isolation_mode=privacy.isolation_mode,
        network_observation=privacy.network_observation,
        privacy_checks=privacy.checks,
        workflow_checks=workflow.checks,
        observations=validation.observations,
        core_passed=validation.core.passed,
        core_total=validation.core.total,
        provider_passed=validation.provider.passed,
        provider_total=validation.provider.total,
        behavior_passed=None if behavior is None else behavior.passed,
        behavior_total=None if behavior is None else behavior.total,
        memory_pressure=validation.observations.memory_pressure,
        thermal_state=validation.observations.thermal_state,
    )


def compare_candidate_evidence(
    candidates: Sequence[CandidateEvidence],
) -> CandidateEvidenceComparison:
    """Compare verified candidate evidence without selecting or scoring a winner."""

    if len(candidates) < 2:
        raise ValueError(
            "candidate comparison requires at least two verified evidence sets"
        )

    first = candidates[0]
    same_hardware = all(
        candidate.hardware == first.hardware for candidate in candidates[1:]
    )
    same_suite = all(
        candidate.evaluation_suite == first.evaluation_suite
        for candidate in candidates[1:]
    )
    same_ally_version = all(
        candidate.ally_version == first.ally_version
        for candidate in candidates[1:]
    )

    warnings: list[str] = []
    if not same_hardware:
        warnings.append(
            "Hardware profiles differ; performance results are not directly comparable."
        )
    if not same_suite:
        warnings.append(
            "Evaluation fingerprints differ; capability pass counts are not directly comparable."
        )
    if not same_ally_version:
        warnings.append(
            "Ally versions differ; candidate behavior is not directly comparable."
        )
    if any(not candidate.capability_successful for candidate in candidates):
        warnings.append(
            "At least one candidate failed capability validation and is not production-eligible."
        )
    if any(not candidate.privacy_qualified for candidate in candidates):
        warnings.append(
            "At least one candidate is not privacy-qualified and is not production-eligible."
        )
    if any(not candidate.workflow_qualified for candidate in candidates):
        warnings.append(
            "At least one candidate failed functional workflow qualification "
            "and is not production-eligible."
        )

    return CandidateEvidenceComparison(
        same_hardware=same_hardware,
        same_evaluation_suite=same_suite,
        same_ally_version=same_ally_version,
        warnings=tuple(warnings),
        candidates=tuple(candidates),
    )
