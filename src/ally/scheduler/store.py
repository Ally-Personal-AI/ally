"""Persistence contract for deterministic schedules."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from ally.scheduler.models import NewSchedule, ScheduleRecord


class ScheduleStore(Protocol):
    def create(self, schedule: NewSchedule) -> ScheduleRecord:
        ...

    def get(self, schedule_id: UUID) -> ScheduleRecord | None:
        ...

    def list(self, *, limit: int = 50) -> tuple[ScheduleRecord, ...]:
        ...

    def due(
        self,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> tuple[ScheduleRecord, ...]:
        ...

    def set_enabled(
        self,
        schedule_id: UUID,
        *,
        enabled: bool,
    ) -> ScheduleRecord:
        ...

    def advance(
        self,
        schedule_id: UUID,
        *,
        expected_next_run_at: datetime,
        next_run_at: datetime | None,
        last_run_at: datetime,
        enabled: bool,
    ) -> ScheduleRecord:
        ...
