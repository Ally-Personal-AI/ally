"""Reproducible local-model validation reports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field

from ally import __version__
from ally.diagnostics.hardware import HardwareProfile, collect_hardware_profile
from ally.evals import EvalSummary, EvaluationRunner, EvaluatorRegistry
from ally.evals.builtin import register_builtin_evaluators
from ally.evals.loader import load_eval_cases
from ally.evals.provider import ProviderResponseEvaluator
from ally.models import ModelProvider


class LocalModelValidationReport(BaseModel):
    """Machine-readable result from one local model/runtime validation run."""

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    ally_version: str
    endpoint: str
    model: str
    hardware: HardwareProfile
    core: EvalSummary
    provider: EvalSummary
    duration_ms: float = Field(ge=0.0)

    @property
    def successful(self) -> bool:
        return self.core.successful and self.provider.successful


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
    return EvaluationRunner(registry).run(load_eval_cases(case_file))


def run_local_model_validation(
    *,
    provider: ModelProvider,
    endpoint: str,
    model: str,
    core_case_file: Path,
    provider_case_file: Path,
    hardware: HardwareProfile | None = None,
) -> LocalModelValidationReport:
    """Run frozen Ally checks and return one reproducible validation artifact."""

    started = perf_counter()
    core = _core_summary(core_case_file)
    provider_summary = _provider_summary(provider_case_file, provider)

    return LocalModelValidationReport(
        generated_at=datetime.now(UTC),
        ally_version=__version__,
        endpoint=endpoint,
        model=model,
        hardware=hardware or collect_hardware_profile(),
        core=core,
        provider=provider_summary,
        duration_ms=(perf_counter() - started) * 1000,
    )


def write_validation_report(
    report: LocalModelValidationReport,
    path: Path,
) -> Path:
    """Write a JSON validation artifact to an explicit destination."""

    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return resolved
