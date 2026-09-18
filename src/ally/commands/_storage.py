"""CLI dependency construction for local persistence."""

from ally.storage import default_database_path
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase


def build_conversation_store() -> SQLiteConversationStore:
    """Create the default local conversation store."""

    return SQLiteConversationStore(SQLiteDatabase(default_database_path()))
