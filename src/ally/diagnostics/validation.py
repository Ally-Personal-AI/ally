"""Reproducible, comparable local-model validation evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ally import __version__
from ally.diagnostics.hardware import HardwareProfile, collect_hardware_profile
from ally.evals import EvalSummary, EvaluationRunner, EvaluatorRegistry
from ally.evals.builtin import register_builtin_evaluators
from ally.evals.loader import load_eval_cases
from ally.evals.memory_proposal import MemoryProposalEvaluator
from ally.evals.planning import TaskPlanProposalEvaluator
from ally.evals.provider import ProviderResponseEvaluator
from ally.models import ModelProvider

_MAX_REPORT_BYTES = 16 * 1024 * 1024
_SENSITIVE_PARAMETER_FRAGMENTS = (
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authentication",
    "authorization",
    "bearer",
    "credential",
    "password",
    "private_key",
    "secret",
)

MemoryPressureState = Literal["normal", "warning", "critical", "unknown"]
ThermalState = Literal["nominal", "fair", "serious", "critical", "unknown"]


class ValidationReportError(ValueError):
    """Raised when a validation artifact cannot be safely loaded."""


class RuntimeParameter(BaseModel):
    """One explicit, non-secret runtime setting used for a validation run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def reject_sensitive_or_multiline_values(self) -> RuntimeParameter:
        normalized = self.name.lower().replace("-", "_").replace(".", "_")
        if any(fragment in normalized for fragment in _SENSITIVE_PARAMETER_FRAGMENTS):
            raise ValueError("runtime parameter names must not identify secret material")
        if any(character in self.value for character in ("\n", "\r", "\x00")):
            raise ValueError("runtime parameter values must be single-line text")
        return self


class RuntimeProfile(BaseModel):
    """Reproducibility metadata for the inference runtime and model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    model_source: str | None = Field(default=None, min_length=1, max_length=300)
    quantization: str | None = Field(default=None, min_length=1, max_length=100)
    precision: str | None = Field(default=None, min_length=1, max_length=100)
    model_size_bytes: int | None = Field(default=None, ge=1)
    context_length: int | None = Field(default=None, ge=1)
    parameters: tuple[RuntimeParameter, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def require_unique_parameter_names(self) -> RuntimeProfile:
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("runtime parameter names must be unique")
        return self


class PerformanceObservations(BaseModel):
    """Optional runtime-native measurements recorded alongside an evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_load_ms: float | None = Field(default=None, ge=0.0)
    time_to_first_token_ms: float | None = Field(default=None, ge=0.0)
    prompt_tokens_per_second: float | None = Field(default=None, gt=0.0)
    generation_tokens_per_second: float | None = Field(default=None, gt=0.0)
    peak_memory_bytes: int | None = Field(default=None, ge=1)
    maximum_tested_context_tokens: int | None = Field(default=None, ge=1)
    memory_pressure: MemoryPressureState = "unknown"
    thermal_state: ThermalState = "unknown"


class EvaluationSuiteProfile(BaseModel):
    """Content fingerprints for the frozen cases used by one run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    core_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LocalModelValidationReport(BaseModel):
    """Machine-readable result from one local model/runtime validation run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=300)
    runtime: RuntimeProfile
    observations: PerformanceObservations = Field(default_factory=PerformanceObservations)
    evaluation_suite: EvaluationSuiteProfile
    hardware: HardwareProfile
    core: EvalSummary
    provider: EvalSummary
    duration_ms: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_evidence_invariants(self) -> LocalModelValidationReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("validation report timestamp must include a timezone offset")
        for name, summary in (("core", self.core), ("provider", self.provider)):
            if summary.total != summary.passed + summary.failed + summary.errors:
                raise ValueError(f"{name} evaluation counts must add up to total")
            if summary.total != len(summary.results):
                raise ValueError(f"{name} evaluation total must match result count")
        return self

    @property
    def successful(self) -> bool:
        return self.core.successful and self.provider.successful


class ValidationComparisonCandidate(BaseModel):
    """One concise candidate entry in a comparison artifact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report: str
    runtime: str
    runtime_version: str
    model: str
    quantization: str | None
    precision: str | None
    model_size_bytes: int | None
    context_length: int | None
    successful: bool
    core_passed: int
    core_total: int
    provider_passed: int
    provider_total: int
    duration_ms: float
    time_to_first_token_ms: float | None
    generation_tokens_per_second: float | None
    peak_memory_bytes: int | None
    maximum_tested_context_tokens: int | None
    memory_pressure: MemoryPressureState
    thermal_state: ThermalState


class ValidationComparison(BaseModel):
    """Neutral comparison of candidate evidence without choosing a default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    same_hardware: bool
    same_evaluation_suite: bool
    warnings: tuple[str, ...]
    candidates: tuple[ValidationComparisonCandidate, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _core_summary(case_file: Path) -> EvalSummary:
    registry = EvaluatorRegistry()
    register_builtin_evaluators(registry)
    return EvaluationRunner(registry).run(load_eval_cases(case_file))


def _provider_summary(
    case_file: Path,
    provider: ModelProvider,
) -> EvalSummary:
    registry = EvaluatorRegistry()
    register_builtin_evaluators(registry)
    registry.register(ProviderResponseEvaluator(provider))
    registry.register(TaskPlanProposalEvaluator(provider))
    registry.register(MemoryProposalEvaluator(provider))
    return EvaluationRunner(registry).run(load_eval_cases(case_file))


def run_local_model_validation(
    *,
    provider: ModelProvider,
    endpoint: str,
    model: str,
    runtime: RuntimeProfile,
    core_case_file: Path,
    provider_case_file: Path,
    observations: PerformanceObservations | None = None,
    hardware: HardwareProfile | None = None,
) -> LocalModelValidationReport:
    """Run frozen Ally checks and return one reproducible validation artifact."""

    started = perf_counter()
    suite = EvaluationSuiteProfile(
        core_sha256=_sha256(core_case_file),
        provider_sha256=_sha256(provider_case_file),
    )
    core = _core_summary(core_case_file)
    provider_summary = _provider_summary(provider_case_file, provider)

    return LocalModelValidationReport(
        generated_at=datetime.now(UTC),
        ally_version=__version__,
        endpoint=endpoint,
        model=model,
        runtime=runtime,
        observations=observations or PerformanceObservations(),
        evaluation_suite=suite,
        hardware=hardware or collect_hardware_profile(),
        core=core,
        provider=provider_summary,
        duration_ms=(perf_counter() - started) * 1000,
    )


def write_validation_report(
    report: LocalModelValidationReport,
    path: Path,
) -> Path:
    """Atomically write a new JSON artifact without replacing prior evidence."""

    resolved = path.expanduser().resolve()
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite validation report: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    temporary = resolved.with_name(f".{resolved.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            os.link(temporary, resolved)
        except FileExistsError as exc:
            raise FileExistsError(
                f"refusing to overwrite validation report: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_validation_report(path: Path) -> LocalModelValidationReport:
    """Load a bounded, strictly versioned Ally validation artifact."""

    resolved = path.expanduser().resolve()
    try:
        size = resolved.stat().st_size
        if size > _MAX_REPORT_BYTES:
            raise ValidationReportError("validation report exceeds the size limit")
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        return LocalModelValidationReport.model_validate(raw)
    except ValidationReportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValidationReportError("invalid Ally validation report") from exc


def compare_validation_reports(
    reports: Sequence[tuple[str, LocalModelValidationReport]],
) -> ValidationComparison:
    """Compare evidence neutrally; never infer or select a default candidate."""

    if len(reports) < 2:
        raise ValueError("comparison requires at least two validation reports")

    first = reports[0][1]
    same_hardware = all(report.hardware == first.hardware for _, report in reports[1:])
    same_suite = all(
        report.evaluation_suite == first.evaluation_suite for _, report in reports[1:]
    )
    warnings: list[str] = []
    if not same_hardware:
        warnings.append(
            "Hardware profiles differ; latency, throughput, and memory are not directly comparable."
        )
    if not same_suite:
        warnings.append(
            "Evaluation fingerprints differ; pass counts are not directly comparable."
        )

    candidates = tuple(
        ValidationComparisonCandidate(
            report=label,
            runtime=report.runtime.name,
            runtime_version=report.runtime.version,
            model=report.model,
            quantization=report.runtime.quantization,
            precision=report.runtime.precision,
            model_size_bytes=report.runtime.model_size_bytes,
            context_length=report.runtime.context_length,
            successful=report.successful,
            core_passed=report.core.passed,
            core_total=report.core.total,
            provider_passed=report.provider.passed,
            provider_total=report.provider.total,
            duration_ms=report.duration_ms,
            time_to_first_token_ms=report.observations.time_to_first_token_ms,
            generation_tokens_per_second=(
                report.observations.generation_tokens_per_second
            ),
            peak_memory_bytes=report.observations.peak_memory_bytes,
            maximum_tested_context_tokens=(
                report.observations.maximum_tested_context_tokens
            ),
            memory_pressure=report.observations.memory_pressure,
            thermal_state=report.observations.thermal_state,
        )
        for label, report in reports
    )
    return ValidationComparison(
        same_hardware=same_hardware,
        same_evaluation_suite=same_suite,
        warnings=tuple(warnings),
        candidates=candidates,
    )
