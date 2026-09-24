"""UI-neutral application services for Ally presentation adapters."""

from ally.application.facade import (
    AllyApplication,
    InferenceTargetResolver,
    ProviderFactory,
)
from ally.application.models import (
    ApplicationError,
    ApplicationNotFoundError,
    ChatTurnRequest,
    ChatTurnResult,
    ConversationView,
    KnowledgeIngestResult,
    KnowledgeTextIngestRequest,
    KnowledgeSearchResult,
    KnowledgeSourceView,
    MemoryProposalRequest,
    RememberMemoryRequest,
    RuntimeInferenceStatus,
    SupersedeMemoryRequest,
)

__all__ = [
    "AllyApplication",
    "ApplicationError",
    "ApplicationNotFoundError",
    "ChatTurnRequest",
    "ChatTurnResult",
    "ConversationView",
    "InferenceTargetResolver",
    "KnowledgeIngestResult",
    "KnowledgeTextIngestRequest",
    "KnowledgeSearchResult",
    "KnowledgeSourceView",
    "MemoryProposalRequest",
    "ProviderFactory",
    "RememberMemoryRequest",
    "RuntimeInferenceStatus",
    "SupersedeMemoryRequest",
]
