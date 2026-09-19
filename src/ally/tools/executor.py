"""Policy-enforced tool execution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import JsonValue

from ally.security.tool_policy import DefaultToolPolicy, PolicyDecision
from ally.tools.audit import ToolAuditRecord, ToolAuditStore
from ally.tools.models import ToolExecution, ToolInvocation
from ally.tools.registry import ToolRegistry


class ToolExecutor:
    """The only supported path for executing registered tools."""

    def __init__(
        self,
        registry: ToolRegistry,
        policy: DefaultToolPolicy,
        audit_store: ToolAuditStore,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._audit_store = audit_store

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, JsonValue],
        *,
        approved: bool = False,
        invocation_id: UUID | None = None,
    ) -> ToolExecution:
        invocation = ToolInvocation(
            id=invocation_id or uuid4(),
            tool_name=tool_name,
            arguments=arguments,
            approved=approved,
        )
        started_at = datetime.now(UTC)
        tool = self._registry.get(tool_name)

        if tool is None:
            execution = ToolExecution(
                invocation_id=invocation.id,
                tool_name=tool_name,
                risk=None,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=f"Unknown tool: {tool_name}",
            )
            self._audit(invocation, execution, decision=None)
            return execution

        decision = self._policy.decide(tool.spec, approved=approved)
        if decision == "require_approval":
            execution = ToolExecution(
                invocation_id=invocation.id,
                tool_name=tool_name,
                risk=tool.spec.risk,
                status="approval_required",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error="Explicit user approval is required.",
            )
            self._audit(invocation, execution, decision=decision)
            return execution

        if decision == "deny":
            execution = ToolExecution(
                invocation_id=invocation.id,
                tool_name=tool_name,
                risk=tool.spec.risk,
                status="denied",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error="Tool execution is denied by policy.",
            )
            self._audit(invocation, execution, decision=decision)
            return execution

        try:
            output = tool.run(arguments)
        except Exception as exc:
            execution = ToolExecution(
                invocation_id=invocation.id,
                tool_name=tool_name,
                risk=tool.spec.risk,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=f"{type(exc).__name__}: {exc}",
            )
        else:
            execution = ToolExecution(
                invocation_id=invocation.id,
                tool_name=tool_name,
                risk=tool.spec.risk,
                status="succeeded",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                output=output,
            )

        self._audit(invocation, execution, decision=decision)
        return execution

    def _audit(
        self,
        invocation: ToolInvocation,
        execution: ToolExecution,
        *,
        decision: PolicyDecision | None,
    ) -> None:
        self._audit_store.append(
            ToolAuditRecord(
                id=uuid4(),
                invocation_id=invocation.id,
                tool_name=execution.tool_name,
                risk=execution.risk,
                decision=decision,
                status=execution.status,
                arguments=invocation.arguments,
                output=execution.output,
                error=execution.error,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            )
        )
