"""Persistence contract for proactive service-cycle lifecycle metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ally.service.models import ServiceCycleRunRecord, ServiceCycleRunStatus


class ServiceRunConflictError(RuntimeError):
    """Raised when another non-stale proactive cycle is already running."""


class ServiceCycleRunStore(Protocol):
    def recover_stale(
        self,
        *,
        before: datetime,
        finished_at: datetime,
    ) -> int:
        ...

    def start(
        self,
        *,
        observed_at: datetime,
        started_at: datetime,
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
