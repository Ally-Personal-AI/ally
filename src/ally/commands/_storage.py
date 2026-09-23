"""CLI dependency construction for local persistence."""

from ally.service.leases import SQLiteServiceLeaseStore
from ally.storage import default_database_path, default_runtime_database_path
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventSourceCheckpointStore,
    SQLiteEventStore,
    SQLiteKnowledgeStore,
    SQLiteMemoryStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    SQLiteSkillExecutionAuditStore,
    SQLiteTaskStore,
    SQLiteToolAuditStore,
    SQLiteUserInstructionsStore,
)


def build_database() -> SQLiteDatabase:
    """Create the default local database handle."""

    return SQLiteDatabase(default_database_path())


def build_service_lease_store() -> SQLiteServiceLeaseStore:
    """Create the disposable runtime service lease store."""

    return SQLiteServiceLeaseStore(default_runtime_database_path())


def build_attention_delivery_store() -> SQLiteAttentionDeliveryStore:
    """Create the default local attention delivery store."""

    return SQLiteAttentionDeliveryStore(build_database())


def build_conversation_store() -> SQLiteConversationStore:
    """Create the default local conversation store."""

    return SQLiteConversationStore(build_database())


def build_memory_store() -> SQLiteMemoryStore:
    """Create the default local memory store."""

    return SQLiteMemoryStore(build_database())


def build_user_instructions_store() -> SQLiteUserInstructionsStore:
    """Create the private global user instruction store."""

    return SQLiteUserInstructionsStore(build_database())


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


def build_service_cycle_run_store() -> SQLiteServiceCycleRunStore:
    """Create the portable proactive service lifecycle store."""

    return SQLiteServiceCycleRunStore(build_database())


def build_skill_execution_audit_store() -> SQLiteSkillExecutionAuditStore:
    """Create the payload-free skill execution audit store."""

    return SQLiteSkillExecutionAuditStore(build_database())
