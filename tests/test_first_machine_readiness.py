from __future__ import annotations

import json
from pathlib import Path

import pytest

from ally.attention.macos import MacOSNotificationStatus
from ally.commands import validate as validate_commands
from ally.config import AllyPaths
from ally.configuration import AllyConfig
from ally.diagnostics import (
    EvaluationSuiteCounts,
    FirstMachineReadinessReport,
    HardwareProfile,
    build_first_machine_readiness,
    collect_first_machine_readiness,
)


def hardware(
    *,
    system: str = "Darwin",
    machine: str = "arm64",
    apple_chip: str | None = "Apple M5 Max",
) -> HardwareProfile:
    return HardwareProfile(
        system=system,
        release="25.0",
        machine=machine,
        processor="arm",
        python_version="3.12.11",
        logical_cpu_count=16,
        total_memory_bytes=128 * 1024**3,
        apple_model="Mac17,1" if system == "Darwin" else None,
        apple_chip=apple_chip,
    )


def notification(
    authorization: str = "authorized",
) -> MacOSNotificationStatus:
    return MacOSNotificationStatus(
        supported=True,
        api_available=True,
        authorization=authorization,  # type: ignore[arg-type]
    )


def suite_counts() -> EvaluationSuiteCounts:
    return EvaluationSuiteCounts(
        core=10,
        provider_smoke=4,
        behavioral_qualification=10,
    )


def test_readiness_allows_clean_apple_silicon_target() -> None:
    report = build_first_machine_readiness(
        hardware=hardware(),
        config=AllyConfig(),
        config_exists=True,
        config_error=False,
        paths=AllyPaths(
            config_dir=Path("/synthetic/config"),
            data_dir=Path("/synthetic/data"),
        ),
        core_database_exists=False,
        runtime_database_exists=False,
        evaluation_suites=suite_counts(),
        evaluation_error=False,
        notification=notification(),
    )

    assert report.ready_to_begin_validation
    assert not any(check.severity == "error" for check in report.checks)


def test_readiness_blocks_wrong_platform_or_architecture() -> None:
    report = build_first_machine_readiness(
        hardware=hardware(system="Linux", machine="x86_64", apple_chip=None),
        config=AllyConfig(),
        config_exists=False,
        config_error=False,
        paths=AllyPaths(
            config_dir=Path("/synthetic/config"),
            data_dir=Path("/synthetic/data"),
        ),
        core_database_exists=False,
        runtime_database_exists=False,
        evaluation_suites=suite_counts(),
        evaluation_error=False,
        notification=MacOSNotificationStatus(
            supported=False,
            api_available=False,
            authorization="unobservable",
        ),
    )

    assert not report.ready_to_begin_validation
    errors = {check.id for check in report.checks if check.severity == "error"}
    assert "target.os" in errors
    assert "target.architecture" in errors


def test_nonblocking_warnings_do_not_prevent_validation() -> None:
    report = build_first_machine_readiness(
        hardware=hardware(),
        config=AllyConfig(),
        config_exists=False,
        config_error=False,
        paths=AllyPaths(
            config_dir=Path("/synthetic/config"),
            data_dir=Path("/synthetic/data"),
        ),
        core_database_exists=True,
        runtime_database_exists=True,
        evaluation_suites=suite_counts(),
        evaluation_error=False,
        notification=notification("unobservable"),
    )

    assert report.ready_to_begin_validation
    warnings = {check.id for check in report.checks if check.severity == "warning"}
    assert "config.file" in warnings
    assert "state.existing" in warnings
    assert "attention.native" in warnings


def test_invalid_config_or_missing_evals_block_readiness() -> None:
    report = build_first_machine_readiness(
        hardware=hardware(),
        config=None,
        config_exists=True,
        config_error=True,
        paths=AllyPaths(
            config_dir=Path("/synthetic/config"),
            data_dir=Path("/synthetic/data"),
        ),
        core_database_exists=False,
        runtime_database_exists=False,
        evaluation_suites=EvaluationSuiteCounts(
            core=0,
            provider_smoke=0,
            behavioral_qualification=0,
        ),
        evaluation_error=True,
        notification=notification(),
    )

    assert not report.ready_to_begin_validation
    errors = {check.id for check in report.checks if check.severity == "error"}
    assert "config.file" in errors
    assert "privacy.private_inference" in errors
    assert "evaluations.bundled" in errors


def test_collector_does_not_create_config_or_database_state(tmp_path: Path) -> None:
    config_dir = tmp_path / "not-created-config"
    data_dir = tmp_path / "not-created-data"
    config_path = config_dir / "config.json"
    database_path = data_dir / "ally.sqlite3"
    runtime_database_path = data_dir / "runtime" / "service.sqlite3"

    report = collect_first_machine_readiness(
        hardware=hardware(),
        paths=AllyPaths(config_dir=config_dir, data_dir=data_dir),
        config_path=config_path,
        database_path=database_path,
        runtime_database_path=runtime_database_path,
        notification=notification("unobservable"),
    )

    assert report.ready_to_begin_validation
    assert not config_dir.exists()
    assert not data_dir.exists()
    assert not config_path.exists()
    assert not database_path.exists()
    assert not runtime_database_path.exists()


def test_readiness_command_json_exposes_ready_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = build_first_machine_readiness(
        hardware=hardware(),
        config=AllyConfig(),
        config_exists=True,
        config_error=False,
        paths=AllyPaths(
            config_dir=Path("/synthetic/config"),
            data_dir=Path("/synthetic/data"),
        ),
        core_database_exists=False,
        runtime_database_exists=False,
        evaluation_suites=suite_counts(),
        evaluation_error=False,
        notification=notification(),
    )
    monkeypatch.setattr(
        validate_commands,
        "collect_first_machine_readiness",
        lambda: report,
    )

    result = validate_commands.run_first_machine_readiness(json_output=True)
    rendered = json.loads(capsys.readouterr().out)

    assert result == 0
    assert rendered["ready_to_begin_validation"] is True
    assert rendered["hardware"]["apple_chip"] == "Apple M5 Max"
