"""Policy-enforced, data-minimized external egress."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from ally.egress.adapter import EgressAdapter
from ally.egress.audit import EgressAuditRecord, EgressAuditStore
from ally.egress.models import (
    EgressExecution,
    EgressFieldManifest,
    EgressInspection,
    EgressRequest,
)
from ally.egress.policy import DefaultEgressPolicy


class EgressExecutor:
    """The supported boundary for transmitting declared data externally."""

    def __init__(
        self,
        policy: DefaultEgressPolicy,
        audit_store: EgressAuditStore,
    ) -> None:
        self._policy = policy
        self._audit_store = audit_store

    def inspect(
        self,
        request: EgressRequest,
        *,
        approved: bool = False,
    ) -> EgressInspection:
        decision = self._policy.decide(request, approved=approved)
        return EgressInspection(
            request_id=request.id,
            service=request.service,
            operation=request.operation,
            decision=decision,
            fields=self._manifest(request),
        )

    def execute(
        self,
        request: EgressRequest,
        adapter: EgressAdapter,
        *,
        approved: bool = False,
    ) -> EgressExecution:
        started_at = datetime.now(UTC)
        decision = self._policy.decide(request, approved=approved)

        if adapter.service != request.service:
            execution = self._result(
                request=request,
                decision="deny",
                status="denied",
                started_at=started_at,
                error_class="ServiceMismatch",
            )
            self._audit(request, execution, approved=approved)
            return execution

        if decision == "require_approval":
            execution = self._result(
                request=request,
                decision=decision,
                status="approval_required",
                started_at=started_at,
            )
            self._audit(request, execution, approved=approved)
            return execution

        if decision == "deny":
            execution = self._result(
                request=request,
                decision=decision,
                status="denied",
                started_at=started_at,
            )
            self._audit(request, execution, approved=approved)
            return execution

        payload: dict[str, JsonValue] = {
            field.name: field.value for field in request.fields
        }
        try:
            output = adapter.send(request.operation, payload)
        except Exception as exc:
            execution = self._result(
                request=request,
                decision=decision,
                status="failed",
                started_at=started_at,
                error_class=type(exc).__name__,
            )
        else:
            execution = self._result(
                request=request,
                decision=decision,
                status="succeeded",
                started_at=started_at,
                output=output,
            )

        self._audit(request, execution, approved=approved)
        return execution

    @staticmethod
    def _manifest(request: EgressRequest) -> tuple[EgressFieldManifest, ...]:
        return tuple(
            EgressFieldManifest(
                name=field.name,
                classification=field.classification,
            )
            for field in request.fields
        )

    @staticmethod
    def _result(
        *,
        request: EgressRequest,
        decision: str,
        status: str,
        started_at: datetime,
        output: JsonValue | None = None,
        error_class: str | None = None,
    ) -> EgressExecution:
        from typing import cast

        from ally.egress.models import EgressDecision, EgressStatus

        return EgressExecution(
            request_id=request.id,
            service=request.service,
            operation=request.operation,
            decision=cast(EgressDecision, decision),
            status=cast(EgressStatus, status),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            output=output,
            error_class=error_class,
        )

    def _audit(
        self,
        request: EgressRequest,
        execution: EgressExecution,
        *,
        approved: bool,
    ) -> None:
        self._audit_store.append(
            EgressAuditRecord(
                id=uuid4(),
                request_id=request.id,
                service=request.service,
                operation=request.operation,
                decision=execution.decision,
                status=execution.status,
                approved=approved,
                fields=self._manifest(request),
                error_class=execution.error_class,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            )
        )
