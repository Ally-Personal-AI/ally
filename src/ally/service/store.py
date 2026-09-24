"""Persistence contract for portable service-cycle lifecycle history."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ally.service.models import ServiceCycleRunRecord, ServiceCycleRunStatus


class ServiceRunConflictError(RuntimeError):
    """Raised when portable lifecycle history is internally inconsistent."""


class ServiceCycleRunStore(Protocol):
    def interrupt_running(
        self,
        *,
        finished_at: datetime,
        error_class: str = "PreviousProcessInterrupted",
    ) -> int:
        ...

    def start(
        self,
        *,
        observed_at: datetime,
        started_at: datetime,
    ) -> ServiceCycleRunRecord:
        ...

    def update_running_progress(
        self,
        run_id: UUID,
        *,
        scheduled_events: int | None = None,
        delivery_attempts_delta: int = 0,
        delivery_failures_delta: int = 0,
    ) -> ServiceCycleRunRecord:
        ...

    def finish(
        self,
        run_id: UUID,
        *,
        status: ServiceCycleRunStatus,
        finished_at: datetime,
        scheduled_events: int = 0,
        delivery_attempts: int = 0,
        delivery_failures: int = 0,
        error_class: str | None = None,
    ) -> ServiceCycleRunRecord:
        ...

    def get(self, run_id: UUID) -> ServiceCycleRunRecord | None:
        ...

    def latest(self) -> ServiceCycleRunRecord | None:
        ...

    def list(self, *, limit: int = 50) -> tuple[ServiceCycleRunRecord, ...]:
        ...
