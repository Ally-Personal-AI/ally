"""Default local composition for UI-neutral Ally application services."""

from __future__ import annotations

from contextlib import AbstractContextManager

from ally.application import AllyApplication
from ally.models import ModelProvider
from ally.models.providers import OpenAICompatibleProvider
from ally.runtime_profiles import ResolvedInferenceTarget, resolve_inference_target
from ally.storage import default_database_path
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteUserInstructionsStore,
)


def _resolve_target(
    development_endpoint: str | None,
    development_model: str | None,
) -> ResolvedInferenceTarget:
    return resolve_inference_target(
        development_endpoint=development_endpoint,
        development_model=development_model,
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

    database = SQLiteDatabase(default_database_path())
    return AllyApplication(
        conversations=SQLiteConversationStore(database),
        memories=SQLiteMemoryStore(database),
        knowledge=SQLiteKnowledgeStore(database),
        instructions=SQLiteUserInstructionsStore(database),
        target_resolver=_resolve_target,
        provider_factory=_provider,
    )
