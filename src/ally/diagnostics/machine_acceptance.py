"""Versioned evidence for dedicated-machine Ally acceptance."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ally import __version__
from ally.diagnostics.hardware import HardwareProfile

_MAX_REPORT_BYTES = 1024 * 1024

MachineAcceptanceStatus = Literal["pass", "fail", "not_run"]


class MachineAcceptanceEvidenceError(ValueError):
    """Raised when dedicated-machine acceptance evidence cannot be trusted."""


class MachineAcceptanceChecks(BaseModel):
    """Fixed empirical gates required before Ally 0.1 desktop release acceptance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    keychain: MachineAcceptanceStatus = "not_run"
    recovery: MachineAcceptanceStatus = "not_run"
    background_service: MachineAcceptanceStatus = "not_run"
    notifications: MachineAcceptanceStatus = "not_run"
    signed_release: MachineAcceptanceStatus = "not_run"
    update_preparation: MachineAcceptanceStatus = "not_run"
    app_replacement: MachineAcceptanceStatus = "not_run"
    integrated_daily_use: MachineAcceptanceStatus = "not_run"

    @property
    def complete(self) -> bool:
        return all(value == "pass" for value in self.model_dump(mode="python").values())


class MachineAcceptanceReport(BaseModel):
    """Payload-free acceptance evidence bound to one machine and active profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    hardware: HardwareProfile
    active_profile_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: MachineAcceptanceChecks

    @model_validator(mode="after")
    def validate_report(self) -> MachineAcceptanceReport:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("machine acceptance timestamp must include timezone")
        return self

    @property
    def qualified_for_release_acceptance(self) -> bool:
        return self.checks.complete


def build_machine_acceptance_report(
    *,
    source_revision: str,
    hardware: HardwareProfile,
    active_profile_id: str,
    active_profile_sha256: str,
    checks: MachineAcceptanceChecks,
    generated_at: datetime | None = None,
) -> MachineAcceptanceReport:
    """Build one acceptance report from explicit empirical observations."""

    return MachineAcceptanceReport(
        generated_at=datetime.now(UTC) if generated_at is None else generated_at,
        ally_version=__version__,
        source_revision=source_revision,
        hardware=hardware,
        active_profile_id=active_profile_id,
        active_profile_sha256=active_profile_sha256,
        checks=checks,
    )


def write_machine_acceptance_report(
    report: MachineAcceptanceReport,
    path: Path,
) -> Path:
    """Atomically publish acceptance evidence without replacing prior evidence."""

    expanded = path.expanduser()
    resolved = expanded.parent.resolve() / expanded.name
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(
            f"refusing to overwrite machine acceptance report: {resolved}"
        )
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
                f"refusing to overwrite machine acceptance report: {resolved}"
            ) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return resolved


def load_machine_acceptance_report(path: Path) -> MachineAcceptanceReport:
    """Load bounded, strictly versioned dedicated-machine acceptance evidence."""

    expanded = path.expanduser()
    if expanded.is_symlink():
        raise MachineAcceptanceEvidenceError(
            "machine acceptance report must not be a symlink"
        )
    resolved = expanded.resolve()
    try:
        if resolved.stat().st_size > _MAX_REPORT_BYTES:
            raise MachineAcceptanceEvidenceError(
                "machine acceptance report exceeds the size limit"
            )
        return MachineAcceptanceReport.model_validate_json(
            resolved.read_text(encoding="utf-8")
        )
    except MachineAcceptanceEvidenceError:
        raise
    except (OSError, UnicodeError, ValidationError) as exc:
        raise MachineAcceptanceEvidenceError(
            "invalid Ally machine acceptance report"
        ) from exc


def verify_machine_acceptance_binding(
    report: MachineAcceptanceReport,
    *,
    source_revision: str,
    hardware: HardwareProfile,
    active_profile_id: str,
    active_profile_sha256: str,
) -> None:
    """Require evidence to match the exact current release/machine/profile binding."""

    if report.ally_version != __version__:
        raise MachineAcceptanceEvidenceError(
            "machine acceptance Ally version does not match the current Ally version"
        )
    if report.source_revision != source_revision:
        raise MachineAcceptanceEvidenceError(
            "machine acceptance source revision does not match"
        )
    if report.hardware != hardware:
        raise MachineAcceptanceEvidenceError(
            "machine acceptance hardware profile does not match"
        )
    if report.active_profile_id != active_profile_id:
        raise MachineAcceptanceEvidenceError(
            "machine acceptance active runtime profile does not match"
        )
    if report.active_profile_sha256 != active_profile_sha256:
        raise MachineAcceptanceEvidenceError(
            "machine acceptance active runtime profile digest does not match"
        )
