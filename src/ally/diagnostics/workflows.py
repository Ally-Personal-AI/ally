"""Isolated synthetic end-to-end validation against one local model provider."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ally import __version__
from ally.knowledge.ingestion import TextKnowledgeIngestor
from ally.knowledge.retrieval import KnowledgeContextProvider, LexicalKnowledgeRetriever
from ally.memory import MemorySource, ModelMemoryProposer, NewMemory
from ally.models import ModelProvider
from ally.planning.model_planner import ModelTaskPlanner
from ally.portability import create_backup, restore_backup, validate_backup
from ally.runtime import PersistentConversationRuntime
from ally.runtime.grounded_conversation import GroundedConversationRuntime
from ally.security.tool_policy import DefaultToolPolicy
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
)
from ally.tasks import NewTaskStep, TaskPlan, TaskRunner
from ally.tools.builtin import build_default_tool_registry
from ally.tools.executor import ToolExecutor

WorkflowCheckStatus = Literal["passed", "failed"]


class SyntheticWorkflowCheck(BaseModel):
    """One payload-free functional validation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    status: WorkflowCheckStatus
    duration_ms: float = Field(ge=0.0)
    error_class: str | None = Field(default=None, min_length=1, max_length=100)


class SyntheticWorkflowReport(BaseModel):
    """Safe summary from a disposable synthetic Ally workspace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    ally_version: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=300)
    checks: tuple[SyntheticWorkflowCheck, ...]
    duration_ms: float = Field(ge=0.0)

    @property
    def successful(self) -> bool:
        return bool(self.checks) and all(
            check.status == "passed" for check in self.checks
        )


def _run_check(
    check_id: str,
    operation: Callable[[], None],
) -> SyntheticWorkflowCheck:
    started = perf_counter()
    try:
        operation()
    except Exception as exc:
        return SyntheticWorkflowCheck(
            id=check_id,
            status="failed",
            duration_ms=(perf_counter() - started) * 1000,
            error_class=type(exc).__name__,
        )
    return SyntheticWorkflowCheck(
        id=check_id,
        status="passed",
        duration_ms=(perf_counter() - started) * 1000,
    )


def _require(condition: bool) -> None:
    if not condition:
        raise AssertionError("synthetic validation assertion failed")


def _conversation_check(
    provider: ModelProvider,
    database: SQLiteDatabase,
) -> None:
    store = SQLiteConversationStore(database)
    conversation = store.create(title="Synthetic validation conversation")

    first_runtime = PersistentConversationRuntime(
        provider,
        store,
        conversation.id,
    )
    first = first_runtime.respond(
        "Remember the synthetic validation token ORCHID-731. "
        "Reply with exactly STORED_OK."
    )
    _require(first.content.strip() == "STORED_OK")

    resumed_runtime = PersistentConversationRuntime(
        provider,
        store,
        conversation.id,
    )
    second = resumed_runtime.respond(
        "What synthetic validation token did I ask you to remember? "
        "Reply with exactly ORCHID-731 and nothing else."
    )
    _require(second.content.strip() == "ORCHID-731")

    messages = store.list_messages(conversation.id)
    _require(len(messages) == 4)
    _require(messages[0].role == "user")
    _require(messages[1].role == "assistant")
    _require(messages[2].role == "user")
    _require(messages[3].role == "assistant")


def _memory_lifecycle_check(database: SQLiteDatabase) -> None:
    store = SQLiteMemoryStore(database)
    source = MemorySource(type="user", id="synthetic-validation")
    original = store.create(
        NewMemory(
            kind="preference",
            content="Synthetic subject prefers jasmine tea.",
            source=source,
        )
    )
    _require(any(item.id == original.id for item in store.search("jasmine")))

    old, replacement = store.supersede(
        original.id,
        NewMemory(
            kind="preference",
            content="Synthetic subject prefers oolong tea.",
            source=source,
        ),
    )
    _require(old.superseded_at is not None)
    _require(old.superseded_by == replacement.id)
    _require(store.search("jasmine") == ())
    _require(any(item.id == replacement.id for item in store.search("oolong")))

    retracted = store.retract(replacement.id)
    _require(retracted.retracted_at is not None)
    _require(store.search("oolong") == ())


def _knowledge_grounding_check(
    provider: ModelProvider,
    database: SQLiteDatabase,
) -> None:
    store = SQLiteKnowledgeStore(database)
    ingestor = TextKnowledgeIngestor(store)
    source, _ = ingestor.ingest_text(
        uri="synthetic://validation/greenhouse",
        title="Synthetic greenhouse",
        text=(
            "Synthetic greenhouse reference. The validation code is GLASS-482. "
            "The greenhouse uses drip irrigation for basil."
        ),
    )
    hits = LexicalKnowledgeRetriever(store).retrieve(
        "What is the greenhouse validation code GLASS?"
    )
    _require(bool(hits))
    _require(any("GLASS-482" in hit.chunk.content for hit in hits))

    runtime = GroundedConversationRuntime(
        provider,
        KnowledgeContextProvider(LexicalKnowledgeRetriever(store)),
    )
    response = runtime.respond(
        "Using only the retrieved reference, reply with exactly the validation "
        "code and nothing else."
    )
    _require(response.content.strip() == "GLASS-482")
    _require(store.get_source(source.id) is not None)


def _tool_check(database: SQLiteDatabase) -> None:
    registry = build_default_tool_registry()
    audit = SQLiteToolAuditStore(database)
    executor = ToolExecutor(registry, DefaultToolPolicy(), audit)
    execution = executor.invoke("system.info", {})

    _require(execution.status == "succeeded")
    _require(execution.output is not None)
    records = audit.list()
    _require(len(records) == 1)
    _require(records[0].status == "succeeded")
    _require(records[0].tool_name == "system.info")


def _task_check(database: SQLiteDatabase) -> None:
    registry = build_default_tool_registry()
    audit = SQLiteToolAuditStore(database)
    executor = ToolExecutor(registry, DefaultToolPolicy(), audit)
    store = SQLiteTaskStore(database)
    task, _ = store.create(
        TaskPlan(
            goal="Inspect the synthetic validation runtime",
            steps=(NewTaskStep(tool_name="system.info"),),
        )
    )

    result = TaskRunner(store, executor).run(task.id)

    _require(result.status == "succeeded")
    persisted = store.get(task.id)
    _require(persisted is not None and persisted.status == "succeeded")
    steps = store.list_steps(task.id)
    _require(len(steps) == 1)
    _require(steps[0].status == "succeeded")
    _require(steps[0].attempts == 1)


def _planning_check(provider: ModelProvider) -> None:
    registry = build_default_tool_registry()
    tools = tuple(tool.spec for tool in registry.list())
    plan = ModelTaskPlanner(provider).propose(
        goal="Inspect the synthetic validation runtime",
        tools=tools,
    )

    _require(plan.goal == "Inspect the synthetic validation runtime")
    _require(bool(plan.steps))
    _require(all(step.tool_name == "system.info" for step in plan.steps))


def _memory_proposal_check(provider: ModelProvider) -> None:
    bundle = ModelMemoryProposer(provider).propose(
        text=(
            "Synthetic validation subject has a durable preference for jasmine "
            "tea and chooses it consistently."
        ),
        source=MemorySource(type="user", id="synthetic-validation"),
        privacy="private",
    )

    _require(bool(bundle.memories))
    _require(
        any("jasmine" in candidate.content.casefold() for candidate in bundle.memories)
    )
    _require(all(candidate.confidence >= 0.0 for candidate in bundle.memories))


def _backup_restore_check(
    database: SQLiteDatabase,
    root: Path,
) -> None:
    marker = SQLiteMemoryStore(database).create(
        NewMemory(
            kind="semantic",
            content="Synthetic backup recovery marker BRAVO-904.",
            source=MemorySource(type="system", id="synthetic-validation"),
        )
    )
    archive = root / "synthetic-recovery.ally-backup"
    restored_path = root / "restored-synthetic.sqlite3"

    create_backup(database, archive)
    manifest = validate_backup(archive)
    _require(manifest.database.size_bytes > 0)
    restore_backup(archive, restored_path)

    restored = SQLiteMemoryStore(SQLiteDatabase(restored_path)).get(marker.id)
    _require(restored is not None)
    _require(restored.content == "Synthetic backup recovery marker BRAVO-904.")


def _workspace_integrity_check(root: Path, database_path: Path) -> None:
    _require(database_path.is_file())
    resolved_root = root.resolve()
    resolved_database = database_path.resolve()
    _require(resolved_database.is_relative_to(resolved_root))


def _run_workspace(
    *,
    provider: ModelProvider,
    model: str,
    root: Path,
) -> SyntheticWorkflowReport:
    started = perf_counter()
    database_path = root / "ally-validation.sqlite3"
    database = SQLiteDatabase(database_path)

    checks = (
        _run_check(
            "conversation.persistence",
            lambda: _conversation_check(provider, database),
        ),
        _run_check(
            "memory.lifecycle",
            lambda: _memory_lifecycle_check(database),
        ),
        _run_check(
            "knowledge.grounding",
            lambda: _knowledge_grounding_check(provider, database),
        ),
        _run_check(
            "tool.read_only",
            lambda: _tool_check(database),
        ),
        _run_check(
            "task.persistence",
            lambda: _task_check(database),
        ),
        _run_check(
            "model.planning",
            lambda: _planning_check(provider),
        ),
        _run_check(
            "model.memory_proposal",
            lambda: _memory_proposal_check(provider),
        ),
        _run_check(
            "data.backup_restore",
            lambda: _backup_restore_check(database, root),
        ),
        _run_check(
            "workspace.isolation",
            lambda: _workspace_integrity_check(root, database_path),
        ),
    )

    return SyntheticWorkflowReport(
        generated_at=datetime.now(UTC),
        ally_version=__version__,
        provider=provider.name,
        model=model,
        checks=checks,
        duration_ms=(perf_counter() - started) * 1000,
    )


def run_isolated_synthetic_workflows(
    *,
    provider: ModelProvider,
    model: str,
) -> SyntheticWorkflowReport:
    """Run synthetic functional checks and delete all generated state afterward."""

    if not model.strip():
        raise ValueError("model cannot be empty")

    with TemporaryDirectory(prefix="ally-synthetic-validation-") as temporary:
        report = _run_workspace(
            provider=provider,
            model=model,
            root=Path(temporary),
        )
    return report
