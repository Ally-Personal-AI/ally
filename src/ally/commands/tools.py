"""Human-facing tool runtime commands."""

from __future__ import annotations

import json
from typing import cast

from pydantic import JsonValue

from ally.commands._storage import build_tool_audit_store
from ally.security.tool_policy import DefaultToolPolicy
from ally.tools.builtin import build_default_tool_registry
from ally.tools.executor import ToolExecutor


def run_list_tools() -> int:
    registry = build_default_tool_registry()
    for tool in registry.list():
        print(f"{tool.spec.name}  {tool.spec.risk}  {tool.spec.description}")
    return 0


def run_tool(
    *,
    name: str,
    arguments_json: str,
    approved: bool,
) -> int:
    try:
        parsed = json.loads(arguments_json)
    except json.JSONDecodeError as exc:
        print(f"Tool arguments must be valid JSON: {exc}")
        return 2

    if not isinstance(parsed, dict):
        print("Tool arguments must be a JSON object.")
        return 2

    arguments = cast(dict[str, JsonValue], parsed)
    executor = ToolExecutor(
        build_default_tool_registry(),
        DefaultToolPolicy(),
        build_tool_audit_store(),
    )
    execution = executor.invoke(name, arguments, approved=approved)

    print(f"Status: {execution.status}")
    if execution.output is not None:
        print(json.dumps(execution.output, sort_keys=True, indent=2))
    if execution.error is not None:
        print(f"Error: {execution.error}")
    return 0 if execution.status == "succeeded" else 2


def run_tool_audit(*, limit: int) -> int:
    try:
        records = build_tool_audit_store().list(limit=limit)
    except ValueError as exc:
        print(f"Tool audit error: {exc}")
        return 2

    if not records:
        print("No tool audit records.")
        return 0

    for record in records:
        risk = record.risk or "unknown"
        decision = record.decision or "none"
        print(
            f"{record.started_at.isoformat()}  {record.tool_name}  "
            f"{risk}  {decision}  {record.status}"
        )
    return 0
