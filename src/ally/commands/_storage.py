"""CLI dependency construction for local persistence."""

from ally.storage import default_database_path
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventSourceCheckpointStore,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteScheduleStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
)


def build_database() -> SQLiteDatabase:
    """Create the default local database handle."""

    return SQLiteDatabase(default_database_path())


def build_attention_delivery_store() -> SQLiteAttentionDeliveryStore:
    """Create the default local attention delivery store."""

    return SQLiteAttentionDeliveryStore(build_database())


def build_conversation_store() -> SQLiteConversationStore:
    """Create the default local conversation store."""

    return SQLiteConversationStore(build_database())


def build_memory_store() -> SQLiteMemoryStore:
    """Create the default local memory store."""

    return SQLiteMemoryStore(build_database())


def build_knowledge_store() -> SQLiteKnowledgeStore:
    """Create the default local knowledge store."""

    return SQLiteKnowledgeStore(build_database())


def build_tool_audit_store() -> SQLiteToolAuditStore:
    """Create the default local tool audit store."""

    return SQLiteToolAuditStore(build_database())


def build_task_store() -> SQLiteTaskStore:
    """Create the default local task store."""

    return SQLiteTaskStore(build_database())


def build_event_source_checkpoint_store() -> SQLiteEventSourceCheckpointStore:
    """Create the default external event-source checkpoint store."""

    return SQLiteEventSourceCheckpointStore(build_database())


def build_event_store() -> SQLiteEventStore:
    """Create the default local event store."""

    return SQLiteEventStore(build_database())


def build_schedule_store() -> SQLiteScheduleStore:
    """Create the default local schedule store."""

    return SQLiteScheduleStore(build_database())
