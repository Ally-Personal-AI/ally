"""CLI dependency construction for local persistence."""

from ally.storage import default_database_path
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
)


def build_database() -> SQLiteDatabase:
    """Create the default local database handle."""

    return SQLiteDatabase(default_database_path())


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


def build_event_store() -> SQLiteEventStore:
    """Create the default local event store."""

    return SQLiteEventStore(build_database())
