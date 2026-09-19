"""CLI dependency construction for local persistence."""

from ally.storage import default_database_path
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
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
