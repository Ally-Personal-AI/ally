"""Policy-enforced, data-minimized external egress."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from ally.egress.adapter import EgressAdapter
from ally.egress.audit import EgressAuditRecord, EgressAuditStore
from ally.egress.models import (
    EgressDecision,
    EgressExecution,
    EgressFieldManifest,
    EgressInspection,
    EgressOperationSpec,
    EgressRequest,
    EgressStatus,
)
from ally.egress.policy import DefaultEgressPolicy


class EgressExecutor:
    """The supported boundary for transmitting explicitly declared data externally."""

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
        adapter: EgressAdapter,
        *,
        approved: bool = False,
    ) -> EgressInspection:
        spec, error_class = self._validate_request(request, adapter)
        if spec is None:
            return EgressInspection(
                request_id=request.id,
                service=request.service,
                operation=request.operation,
                decision="deny",
                fields=(),
                error_class=error_class,
            )
        manifest = self._manifest(spec, request)
        return EgressInspection(
            request_id=request.id,
            service=request.service,
            operation=request.operation,
            decision=self._policy.decide(manifest, approved=approved),
            fields=manifest,
        )

    def execute(
        self,
        request: EgressRequest,
        adapter: EgressAdapter,
        *,
        approved: bool = False,
    ) -> EgressExecution:
        started_at = datetime.now(UTC)
        spec, validation_error = self._validate_request(request, adapter)
        if spec is None:
            execution = self._result(
                request=request,
                decision="deny",
                status="denied",
                started_at=started_at,
            )
            self._audit(
                request,
                execution,
                fields=(),
                approved=approved,
                validation_error=validation_error,
            )
            return execution

        manifest = self._manifest(spec, request)
        decision = self._policy.decide(manifest, approved=approved)

        if decision == "require_approval":
            execution = self._result(
                request=request,
                decision=decision,
                status="approval_required",
                started_at=started_at,
            )
            self._audit(request, execution, fields=manifest, approved=approved)
            return execution

        if decision == "deny":
            execution = self._result(
                request=request,
                decision=decision,
                status="denied",
                started_at=started_at,
            )
            self._audit(request, execution, fields=manifest, approved=approved)
            return execution

        try:
            output = adapter.send(request.operation, dict(request.fields))
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

        self._audit(request, execution, fields=manifest, approved=approved)
        return execution

    @staticmethod
    def _operation_spec(
        adapter: EgressAdapter,
        operation: str,
    ) -> EgressOperationSpec | None:
        matches = tuple(item for item in adapter.operations if item.operation == operation)
        if len(matches) != 1:
            return None
        return matches[0]

    @classmethod
    def _validate_request(
        cls,
        request: EgressRequest,
        adapter: EgressAdapter,
    ) -> tuple[EgressOperationSpec | None, str | None]:
        if adapter.service != request.service:
            return None, "ServiceMismatch"

        spec = cls._operation_spec(adapter, request.operation)
        if spec is None:
            return None, "UnknownOperation"

        declared = {field.name: field for field in spec.fields}
        provided = set(request.fields)
        if not provided <= set(declared):
            return None, "UndeclaredField"

        missing = {
            name
            for name, field in declared.items()
            if field.required and name not in provided
        }
        if missing:
            return None, "MissingRequiredField"

        return spec, None

    @staticmethod
    def _manifest(
        spec: EgressOperationSpec,
        request: EgressRequest,
    ) -> tuple[EgressFieldManifest, ...]:
        declared = {field.name: field for field in spec.fields}
        return tuple(
            EgressFieldManifest(
                name=name,
                classification=declared[name].classification,
            )
            for name in sorted(request.fields)
        )

    @staticmethod
    def _result(
        *,
        request: EgressRequest,
        decision: EgressDecision,
        status: EgressStatus,
        started_at: datetime,
        output: JsonValue | None = None,
        error_class: str | None = None,
    ) -> EgressExecution:
        return EgressExecution(
            request_id=request.id,
            service=request.service,
            operation=request.operation,
            decision=decision,
            status=status,
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
        fields: tuple[EgressFieldManifest, ...],
        approved: bool,
        validation_error: str | None = None,
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
                fields=fields,
                error_class=execution.error_class or validation_error,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            )
        )
