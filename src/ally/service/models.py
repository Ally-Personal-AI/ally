"""Safe portable service lifecycle and health models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ServiceCycleRunStatus = Literal[
    "running",
    "succeeded",
    "degraded",
    "failed",
    "interrupted",
]
ServiceHealthStatus = Literal["healthy", "degraded", "uninitialized"]


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("service timestamps must include a timezone offset")
    return value


class ServiceCycleRunRecord(BaseModel):
    """Payload-free portable history for one proactive cycle attempt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    status: ServiceCycleRunStatus
    observed_at: datetime
    started_at: datetime
    finished_at: datetime | None = None
    scheduled_events: int = Field(default=0, ge=0)
    delivery_attempts: int = Field(default=0, ge=0)
    delivery_failures: int = Field(default=0, ge=0)
    error_class: str | None = Field(default=None, min_length=1, max_length=256)

    @field_validator("observed_at", "started_at", "finished_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ServiceCycleRunRecord:
        if self.status == "running" and self.finished_at is not None:
            raise ValueError("running service cycle cannot have finished_at")
        if self.status == "running" and self.error_class is not None:
            raise ValueError("running service cycle cannot have error_class")
        if self.status != "running" and self.finished_at is None:
            raise ValueError("terminal service cycle requires finished_at")

        if (
            self.status in ("failed", "interrupted")
            and self.error_class is None
        ):
            raise ValueError(
                f"{self.status} service cycle requires error_class"
            )
        if (
            self.status not in ("failed", "interrupted")
            and self.error_class is not None
        ):
            raise ValueError(
                f"{self.status} service cycle cannot retain error_class"
            )

        if (
            self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("service cycle cannot finish before it started")

        if self.delivery_failures > self.delivery_attempts:
            raise ValueError(
                "delivery_failures cannot exceed delivery_attempts"
            )
        if self.status == "succeeded" and self.delivery_failures != 0:
            raise ValueError(
                "successful service cycle cannot have delivery failures"
            )
        if self.status == "degraded" and self.delivery_failures < 1:
            raise ValueError(
                "degraded service cycle requires delivery failures"
            )
        return self


class ServiceHealthReport(BaseModel):
    """Read-only local health snapshot without private runtime payloads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ServiceHealthStatus
    database_exists: bool
    database_integrity_ok: bool
    schema_current: bool
    applied_schema_versions: tuple[int, ...] = ()
    expected_schema_versions: tuple[int, ...] = ()
    latest_cycle: ServiceCycleRunRecord | None = None
    runtime_database_exists: bool = False
    runtime_coordination_ok: bool = True
    proactive_lease_active: bool = False
    proactive_lease_expires_at: datetime | None = None

    @field_validator("proactive_lease_expires_at")
    @classmethod
    def validate_lease_timestamp(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return _require_aware(value)
