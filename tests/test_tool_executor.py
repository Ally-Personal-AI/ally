from pydantic import JsonValue

from ally.security.tool_policy import DefaultToolPolicy
from ally.tools import ToolExecutor, ToolRegistry, ToolRisk, ToolSpec
from ally.tools.audit import ToolAuditRecord


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[ToolAuditRecord] = []

    def append(self, record: ToolAuditRecord) -> None:
        self.records.append(record)

    def list(self, *, limit: int = 100) -> tuple[ToolAuditRecord, ...]:
        return tuple(reversed(self.records[-limit:]))


class RecordingTool:
    def __init__(self, *, name: str, risk: ToolRisk) -> None:
        self.calls = 0
        self._spec = ToolSpec(
            name=name,
            description="Synthetic test tool.",
            risk=risk,
        )

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        self.calls += 1
        return {"arguments": arguments, "calls": self.calls}


def build_executor(tool: RecordingTool) -> tuple[ToolExecutor, InMemoryAuditStore]:
    registry = ToolRegistry()
    registry.register(tool)
    audit = InMemoryAuditStore()
    return ToolExecutor(registry, DefaultToolPolicy(), audit), audit


def test_read_only_tool_executes_without_approval() -> None:
    tool = RecordingTool(name="test.read", risk="read_only")
    executor, audit = build_executor(tool)

    result = executor.invoke("test.read", {"value": 1})

    assert result.status == "succeeded"
    assert tool.calls == 1
    assert audit.records[0].decision == "allow"
    assert audit.records[0].status == "succeeded"


def test_reversible_tool_requires_explicit_approval() -> None:
    tool = RecordingTool(name="test.write", risk="reversible")
    executor, audit = build_executor(tool)

    blocked = executor.invoke("test.write", {})
    allowed = executor.invoke("test.write", {}, approved=True)

    assert blocked.status == "approval_required"
    assert allowed.status == "succeeded"
    assert tool.calls == 1
    assert [record.decision for record in audit.records] == [
        "require_approval",
        "allow",
    ]


def test_high_consequence_tool_is_denied_even_when_marked_approved() -> None:
    tool = RecordingTool(name="test.danger", risk="high_consequence")
    executor, audit = build_executor(tool)

    result = executor.invoke("test.danger", {}, approved=True)

    assert result.status == "denied"
    assert tool.calls == 0
    assert audit.records[0].decision == "deny"


def test_unknown_tool_fails_closed_and_is_audited() -> None:
    registry = ToolRegistry()
    audit = InMemoryAuditStore()
    executor = ToolExecutor(registry, DefaultToolPolicy(), audit)

    result = executor.invoke("missing.tool", {})

    assert result.status == "failed"
    assert result.risk is None
    assert audit.records[0].decision is None
    assert audit.records[0].tool_name == "missing.tool"
