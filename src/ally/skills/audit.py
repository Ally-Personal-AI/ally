"""Persistence contract for payload-free skill execution audit."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from ally.skills.models import (
    SkillExecutionAuditRecord,
    SkillExecutionResult,
)


class SkillExecutionAuditStore(Protocol):
    def record(
        self,
        *,
        installation_id: UUID,
        result: SkillExecutionResult,
    ) -> SkillExecutionAuditRecord:
        ...

    def list(
        self,
        *,
        limit: int = 50,
    ) -> tuple[SkillExecutionAuditRecord, ...]:
        ...
