"""Default local composition for UI-neutral Ally application services."""

from __future__ import annotations

from contextlib import AbstractContextManager

from ally.application import AllyApplication, ApplicationOperations
from ally.events import EventRuntime
from ally.configuration import default_config_path
from ally.diagnostics import build_service_health
from ally.models import ModelProvider
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime_profiles import (
    ResolvedInferenceTarget,
    RuntimeProfileCatalog,
    default_runtime_profile_catalog,
    resolve_inference_target,
)
from ally.scheduler import SchedulerRuntime
from ally.security.tool_policy import DefaultToolPolicy
from ally.service import DesktopProactiveCoordinator, SQLiteServiceLeaseStore
from ally.storage import default_database_path, default_runtime_database_path
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
    SQLiteUserInstructionsStore,
)
from ally.tasks import TaskRunner
from ally.tools.builtin import build_default_tool_registry
from ally.tools.executor import ToolExecutor


def _resolve_target(
    catalog: RuntimeProfileCatalog,
    development_endpoint: str | None,
    development_model: str | None,
) -> ResolvedInferenceTarget:
    return resolve_inference_target(
        development_endpoint=development_endpoint,
        development_model=development_model,
        active_profile_resolver=catalog.active,
    )


def _provider(
    target: ResolvedInferenceTarget,
) -> AbstractContextManager[ModelProvider]:
    return OpenAICompatibleProvider(
        base_url=target.endpoint,
        model=target.model,
    )


def build_default_application() -> AllyApplication:
    """Compose the local application facade from Ally-owned concrete adapters."""

    database_path = default_database_path()
    database = SQLiteDatabase(database_path)
    runtime_profiles = default_runtime_profile_catalog()
    task_store = SQLiteTaskStore(database)
    event_store = SQLiteEventStore(database)
    delivery_store = SQLiteAttentionDeliveryStore(database)
    service_run_store = SQLiteServiceCycleRunStore(database)
    operations = ApplicationOperations(
        tasks=task_store,
        task_runner=TaskRunner(
            task_store,
            ToolExecutor(
                build_default_tool_registry(),
                DefaultToolPolicy(),
                SQLiteToolAuditStore(database),
            ),
        ),
        events=event_store,
        attention_deliveries=delivery_store,
        service_runs=service_run_store,
        service_health=lambda: build_service_health(
            config_path=default_config_path(),
            database_path=database_path,
            runtime_database_path=default_runtime_database_path(),
        ),
        desktop_proactive=DesktopProactiveCoordinator(
            scheduler=SchedulerRuntime(
                SQLiteScheduleStore(database),
                EventRuntime(event_store),
            ),
            events=event_store,
            deliveries=delivery_store,
            runs=service_run_store,
            leases=SQLiteServiceLeaseStore(default_runtime_database_path()),
        ),
    )
    return AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=lambda endpoint, model: _resolve_target(
            runtime_profiles,
            endpoint,
            model,
        ),
        provider_factory=_provider,
        operations=operations,
        runtime_profiles=runtime_profiles,
    )
