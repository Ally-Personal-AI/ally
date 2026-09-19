from pathlib import Path

from pydantic import JsonValue

from ally.security.tool_policy import DefaultToolPolicy
from ally.storage.sqlite import SQLiteDatabase, SQLiteTaskStore
from ally.tasks import NewTaskStep, TaskPlan, TaskRunner
from ally.tools import ToolRegistry, ToolRisk, ToolSpec
from ally.tools.audit import ToolAuditRecord
from ally.tools.executor import ToolExecutor


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[ToolAuditRecord] = []

    def append(self, record: ToolAuditRecord) -> None:
        self.records.append(record)

    def list(self, *, limit: int = 100) -> tuple[ToolAuditRecord, ...]:
        return tuple(reversed(self.records[-limit:]))


class SyntheticTool:
    def __init__(
        self,
        *,
        name: str,
        risk: ToolRisk,
        fail_first: bool = False,
    ) -> None:
        self._spec = ToolSpec(
            name=name,
            description="Synthetic task test tool.",
            risk=risk,
        )
        self.calls = 0
        self.fail_first = fail_first

    @property
    def spec(self) -> ToolSpec:
        return self._spec

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("synthetic failure")
        return {"calls": self.calls, "arguments": arguments}


def build_runner(
    tmp_path: Path,
    tool: SyntheticTool,
) -> tuple[SQLiteTaskStore, TaskRunner, InMemoryAuditStore]:
    store = SQLiteTaskStore(SQLiteDatabase(tmp_path / "ally.sqlite3"))
    registry = ToolRegistry()
    registry.register(tool)
    audit = InMemoryAuditStore()
    runner = TaskRunner(
        store,
        ToolExecutor(registry, DefaultToolPolicy(), audit),
    )
    return store, runner, audit


def test_read_only_task_runs_to_verified_success(tmp_path: Path) -> None:
    tool = SyntheticTool(name="test.read", risk="read_only")
    store, runner, audit = build_runner(tmp_path, tool)
    task, steps = store.create(
        TaskPlan(
            goal="Run safe synthetic tool",
            steps=(NewTaskStep(tool_name="test.read", arguments={"x": 1}),),
        )
    )

    result = runner.run(task.id)

    persisted_steps = store.list_steps(task.id)
    assert result.status == "succeeded"
    assert persisted_steps[0].status == "succeeded"
    assert persisted_steps[0].attempts == 1
    assert tool.calls == 1
    assert audit.records[0].status == "succeeded"
    assert steps[0].id == persisted_steps[0].id


def test_reversible_step_pauses_then_resumes_with_explicit_approval(
    tmp_path: Path,
) -> None:
    tool = SyntheticTool(name="test.write", risk="reversible")
    store, runner, _ = build_runner(tmp_path, tool)
    task, steps = store.create(
        TaskPlan(
            goal="Synthetic write",
            steps=(NewTaskStep(tool_name="test.write"),),
        )
    )

    paused = runner.run(task.id)
    paused_step = store.list_steps(task.id)[0]

    assert paused.status == "waiting_approval"
    assert paused_step.status == "approval_required"
    assert tool.calls == 0

    resumed_runner = TaskRunner(
        store,
        runner._tool_executor,  # type: ignore[attr-defined]
    )
    completed = resumed_runner.run(
        task.id,
        approved_steps=(steps[0].id,),
    )

    final_step = store.list_steps(task.id)[0]
    assert completed.status == "succeeded"
    assert final_step.status == "succeeded"
    assert final_step.attempts == 2
    assert tool.calls == 1


def test_high_consequence_step_fails_without_calling_tool(tmp_path: Path) -> None:
    tool = SyntheticTool(name="test.danger", risk="high_consequence")
    store, runner, _ = build_runner(tmp_path, tool)
    task, _ = store.create(
        TaskPlan(
            goal="Synthetic denied action",
            steps=(NewTaskStep(tool_name="test.danger"),),
        )
    )

    result = runner.run(task.id)
    step = store.list_steps(task.id)[0]

    assert result.status == "failed"
    assert step.status == "failed"
    assert tool.calls == 0


def test_failed_step_requires_deliberate_retry(tmp_path: Path) -> None:
    tool = SyntheticTool(name="test.flaky", risk="read_only", fail_first=True)
    store, runner, _ = build_runner(tmp_path, tool)
    task, steps = store.create(
        TaskPlan(
            goal="Synthetic retry",
            steps=(NewTaskStep(tool_name="test.flaky"),),
        )
    )

    failed = runner.run(task.id)
    assert failed.status == "failed"
    assert tool.calls == 1

    still_failed = runner.run(task.id)
    assert still_failed.status == "failed"
    assert tool.calls == 1

    store.retry_failed_step(task.id, steps[0].id)
    completed = runner.run(task.id)

    assert completed.status == "succeeded"
    assert tool.calls == 2
    assert store.list_steps(task.id)[0].attempts == 2
