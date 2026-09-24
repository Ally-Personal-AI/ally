"""Read-only readiness diagnostics for first-machine validation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ally import __version__
from ally.attention.macos import MacOSNotificationStatus
from ally.attention.factory import macos_notification_status
from ally.config import AllyPaths, default_paths
from ally.configuration import (
    AllyConfig,
    ConfigFileError,
    FileConfigStore,
    default_config_path,
)
from ally.diagnostics.hardware import HardwareProfile, collect_hardware_profile
from ally.evals.loader import load_eval_cases
from ally.evals.resources import evaluation_case_file
from ally.security.network import is_loopback_http_url
from ally.storage import default_database_path, default_runtime_database_path

ReadinessSeverity = Literal["ok", "warning", "error"]


class FirstMachineReadinessCheck(BaseModel):
    """One bounded non-sensitive preflight check."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    severity: ReadinessSeverity
    summary: str = Field(min_length=1, max_length=500)


class EvaluationSuiteCounts(BaseModel):
    """Case counts for the packaged frozen validation suites."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    core: int = Field(ge=0)
    provider_smoke: int = Field(ge=0)
    behavioral_qualification: int = Field(ge=0)


class FirstMachineReadinessReport(BaseModel):
    """Read-only evidence that the environment can begin synthetic validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    hardware: HardwareProfile
    config_exists: bool
    core_database_exists: bool
    runtime_database_exists: bool
    paths_distinct: bool
    evaluation_suites: EvaluationSuiteCounts
    notification_supported: bool
    notification_api_available: bool
    notification_authorization: str
    checks: tuple[FirstMachineReadinessCheck, ...]

    @property
    def ready_to_begin_validation(self) -> bool:
        return not any(check.severity == "error" for check in self.checks)


def _check(
    check_id: str,
    severity: ReadinessSeverity,
    summary: str,
) -> FirstMachineReadinessCheck:
    return FirstMachineReadinessCheck(
        id=check_id,
        severity=severity,
        summary=summary,
    )


def _evaluation_suite_counts() -> EvaluationSuiteCounts:
    with (
        evaluation_case_file("core") as core_path,
        evaluation_case_file("provider-smoke") as provider_path,
        evaluation_case_file("behavioral-qualification") as behavior_path,
    ):
        return EvaluationSuiteCounts(
            core=len(load_eval_cases(core_path)),
            provider_smoke=len(load_eval_cases(provider_path)),
            behavioral_qualification=len(load_eval_cases(behavior_path)),
        )


def build_first_machine_readiness(
    *,
    hardware: HardwareProfile,
    config: AllyConfig | None,
    config_exists: bool,
    config_error: bool,
    paths: AllyPaths,
    core_database_exists: bool,
    runtime_database_exists: bool,
    evaluation_suites: EvaluationSuiteCounts,
    evaluation_error: bool,
    notification: MacOSNotificationStatus,
    generated_at: datetime | None = None,
) -> FirstMachineReadinessReport:
    """Build readiness from already observed state without performing I/O."""

    observed_at = datetime.now(UTC) if generated_at is None else generated_at
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("readiness timestamp must include a timezone offset")

    checks: list[FirstMachineReadinessCheck] = []

    if hardware.system == "Darwin":
        checks.append(_check("target.os", "ok", "macOS target detected."))
    else:
        checks.append(
            _check(
                "target.os",
                "error",
                "First-machine validation requires the dedicated macOS target.",
            )
        )

    if hardware.machine.lower() in {"arm64", "aarch64"}:
        checks.append(
            _check("target.architecture", "ok", "ARM64 architecture detected.")
        )
    else:
        checks.append(
            _check(
                "target.architecture",
                "error",
                "First-machine validation requires Apple Silicon ARM64.",
            )
        )

    if hardware.apple_chip:
        checks.append(
            _check(
                "target.apple_chip",
                "ok",
                f"Apple chip detected: {hardware.apple_chip}.",
            )
        )
    else:
        checks.append(
            _check(
                "target.apple_chip",
                "warning",
                "Apple chip metadata is unavailable; record it manually before comparison.",
            )
        )

    if hardware.logical_cpu_count is None:
        checks.append(
            _check(
                "hardware.cpu",
                "warning",
                "Logical CPU count is unavailable.",
            )
        )
    else:
        checks.append(
            _check(
                "hardware.cpu",
                "ok",
                f"Logical CPU count: {hardware.logical_cpu_count}.",
            )
        )

    if hardware.total_memory_bytes is None:
        checks.append(
            _check(
                "hardware.memory",
                "warning",
                "Total memory could not be determined.",
            )
        )
    else:
        checks.append(
            _check(
                "hardware.memory",
                "ok",
                f"Total memory bytes: {hardware.total_memory_bytes}.",
            )
        )

    if config_error:
        checks.append(
            _check(
                "config.file",
                "error",
                "Existing Ally configuration is invalid or unreadable.",
            )
        )
    elif config_exists:
        checks.append(_check("config.file", "ok", "Existing Ally config is valid."))
    else:
        checks.append(
            _check(
                "config.file",
                "warning",
                "Ally config is not initialized; safe defaults will apply.",
            )
        )

    private_config_ok = (
        config is not None
        and config.privacy.private_inference_local_only
        and is_loopback_http_url(config.inference.endpoint)
    )
    checks.append(
        _check(
            "privacy.private_inference",
            "ok" if private_config_ok else "error",
            (
                "Private inference is constrained to a loopback endpoint."
                if private_config_ok
                else "Private inference configuration is not safely loopback-only."
            ),
        )
    )

    paths_distinct = paths.config_dir != paths.data_dir
    checks.append(
        _check(
            "paths.separate",
            "ok" if paths_distinct else "error",
            (
                "Configuration and personal data directories are distinct."
                if paths_distinct
                else "Configuration and personal data directories must be distinct."
            ),
        )
    )

    if core_database_exists or runtime_database_exists:
        checks.append(
            _check(
                "state.existing",
                "warning",
                "Existing Ally state is present; keep synthetic validation separate from future personal use.",
            )
        )
    else:
        checks.append(
            _check(
                "state.existing",
                "ok",
                "No existing Ally core/runtime database state was detected.",
            )
        )

    suites_ok = (
        not evaluation_error
        and evaluation_suites.core > 0
        and evaluation_suites.provider_smoke > 0
        and evaluation_suites.behavioral_qualification > 0
    )
    checks.append(
        _check(
            "evaluations.bundled",
            "ok" if suites_ok else "error",
            (
                "Bundled core, provider, and behavioral evaluation suites are available."
                if suites_ok
                else "Bundled validation suites are missing or unreadable."
            ),
        )
    )

    if not notification.supported:
        notification_severity: ReadinessSeverity = (
            "error" if hardware.system == "Darwin" else "warning"
        )
        notification_summary = "Native macOS notification support is unavailable."
    elif not notification.api_available:
        notification_severity = "warning"
        notification_summary = (
            "Native Notification Center API is unavailable; model validation may proceed, "
            "but notification acceptance remains pending."
        )
    elif notification.authorization == "denied":
        notification_severity = "warning"
        notification_summary = (
            "Notification delivery appears denied; model validation may proceed, "
            "but native-attention acceptance remains pending."
        )
    elif notification.authorization in {"not_determined", "unobservable"}:
        notification_severity = "warning"
        notification_summary = (
            "Notification authorization is not yet confirmed; this does not block "
            "synthetic model validation."
        )
    else:
        notification_severity = "ok"
        notification_summary = "Native notification readiness is available."

    checks.append(
        _check(
            "attention.native",
            notification_severity,
            notification_summary,
        )
    )

    return FirstMachineReadinessReport(
        generated_at=observed_at,
        ally_version=__version__,
        hardware=hardware,
        config_exists=config_exists,
        core_database_exists=core_database_exists,
        runtime_database_exists=runtime_database_exists,
        paths_distinct=paths_distinct,
        evaluation_suites=evaluation_suites,
        notification_supported=notification.supported,
        notification_api_available=notification.api_available,
        notification_authorization=notification.authorization,
        checks=tuple(checks),
    )


def collect_first_machine_readiness(
    *,
    hardware: HardwareProfile | None = None,
    paths: AllyPaths | None = None,
    config_path: Path | None = None,
    database_path: Path | None = None,
    runtime_database_path: Path | None = None,
    notification: MacOSNotificationStatus | None = None,
) -> FirstMachineReadinessReport:
    """Collect readiness using read-only operations only."""

    active_paths = paths or default_paths()
    active_config_path = config_path or default_config_path()
    active_database_path = database_path or default_database_path()
    active_runtime_database_path = (
        runtime_database_path or default_runtime_database_path()
    )

    config_exists = active_config_path.is_file()
    config_error = False
    config: AllyConfig | None
    if config_exists:
        try:
            config = FileConfigStore(active_config_path).load()
        except ConfigFileError:
            config = None
            config_error = True
    else:
        config = AllyConfig()

    try:
        suites = _evaluation_suite_counts()
        evaluation_error = False
    except (OSError, UnicodeError, ValueError):
        suites = EvaluationSuiteCounts(
            core=0,
            provider_smoke=0,
            behavioral_qualification=0,
        )
        evaluation_error = True

    return build_first_machine_readiness(
        hardware=hardware or collect_hardware_profile(),
        config=config,
        config_exists=config_exists,
        config_error=config_error,
        paths=active_paths,
        core_database_exists=active_database_path.is_file(),
        runtime_database_exists=active_runtime_database_path.is_file(),
        evaluation_suites=suites,
        evaluation_error=evaluation_error,
        notification=notification or macos_notification_status(),
    )
